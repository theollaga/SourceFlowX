"""
Phase 1 Collector - 수집 오케스트레이터
검색 → ASIN 목록 추출 → 상세 페이지 수집 → JSONL 저장.
병렬 처리, 체크포인트 저장/복원, 장기 운영을 지원합니다.
파일당 1,000개 제품 단위로 자동 분할 저장합니다.
"""

import os
import json
import time
import random
import logging
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import config as collector_config
from proxy_manager import ProxyManager
from fetcher import fetch_search_page, fetch_product_html
from raw_parser import parse_search_results, parse_product_page


logger = logging.getLogger("collector")

CHUNK_SIZE = 1000  # 파일당 최대 제품 수


class AmazonCollector:
    """
    아마존 제품 원본 데이터 수집기.
    병렬 처리, 체크포인트, 프록시 자동 복구를 지원합니다.
    JSONL 형식으로 1,000개 단위 자동 분할 저장합니다.
    """

    def __init__(self, proxy_file=None):
        self.proxy_mgr = ProxyManager(proxy_file)
        self.results = []
        self.failed = []
        self.processed_asins = set()
        self.delay_range = (collector_config.DELAY_MIN, collector_config.DELAY_MAX)
        self.lock = threading.Lock()

    # ================================================================
    # 체크포인트 관리
    # ================================================================

    def _checkpoint_path(self, keyword):
        """키워드별 체크포인트 파일 경로를 반환합니다."""
        safe = keyword.replace(" ", "_").replace("/", "_")[:50]
        return os.path.join(
            collector_config.CHECKPOINT_DIR,
            "checkpoint_{}.json".format(safe),
        )

    def _save_checkpoint(self, keyword):
        """현재 진행 상태를 체크포인트로 저장합니다."""
        filepath = self._checkpoint_path(keyword)
        data = {
            "keyword": keyword,
            "saved_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "processed_asins": list(self.processed_asins),
            "failed_asins": self.failed,
            "total_collected": len(self.results),
            "products": self.results,
        }
        try:
            tmp_path = filepath + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            if os.path.exists(filepath):
                os.remove(filepath)
            os.rename(tmp_path, filepath)
            logger.info(
                "[체크포인트] 저장 완료: %d개 제품 (%s)",
                len(self.results), filepath,
            )
        except Exception as e:
            logger.error("[체크포인트] 저장 실패: %s", e)

    def _load_checkpoint(self, keyword):
        """키워드별 체크포인트를 복원합니다."""
        filepath = self._checkpoint_path(keyword)
        if not os.path.exists(filepath):
            return False

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.results = data.get("products", [])
            self.processed_asins = set(data.get("processed_asins", []))
            self.failed = data.get("failed_asins", [])

            logger.info(
                "[체크포인트] 복원 완료: %d개 제품, %d개 처리됨 (%s)",
                len(self.results), len(self.processed_asins), filepath,
            )
            return True

        except Exception as e:
            logger.warning("[체크포인트] 복원 실패: %s", e)
            return False

    def _delete_checkpoint(self, keyword):
        """키워드 완료 후 체크포인트 파일을 삭제합니다."""
        filepath = self._checkpoint_path(keyword)
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                logger.info("[체크포인트] 삭제: %s", filepath)
        except Exception:
            pass

    # ================================================================
    # 검색
    # ================================================================

    def search_keyword(self, keyword, search_url=None, max_pages=None):
        """키워드를 검색하여 ASIN 목록을 수집합니다."""
        if max_pages is None:
            max_pages = collector_config.MAX_PAGES

        all_products = []
        seen_asins = set()

        logger.info("=" * 60)
        logger.info("[검색 시작] 키워드: '%s', 최대 %d페이지", keyword, max_pages)
        logger.info("=" * 60)

        for page in range(1, max_pages + 1):
            html = fetch_search_page(
                query=keyword,
                search_url=search_url,
                page=page,
                proxy_mgr=self.proxy_mgr,
            )

            if not html:
                logger.warning("[검색] 페이지 %d 수집 실패, 건너뜀", page)
                continue

            products = parse_search_results(html)

            if not products:
                logger.info("[검색] 페이지 %d: 결과 없음. 검색 종료.", page)
                break

            new_count = 0
            for p in products:
                if p["asin"] not in seen_asins:
                    seen_asins.add(p["asin"])
                    all_products.append(p)
                    new_count += 1

            logger.info(
                "[검색] 페이지 %d: %d개 발견, 신규 %d개 (누적 %d개)",
                page, len(products), new_count, len(all_products),
            )

            delay = random.uniform(*self.delay_range)
            time.sleep(delay)

        logger.info("[검색 완료] '%s': 총 %d개 ASIN 수집", keyword, len(all_products))
        return all_products

    # ================================================================
    # 단일 제품 수집
    # ================================================================

    def collect_product(self, asin):
        """단일 제품의 상세 데이터를 수집합니다."""
        html = fetch_product_html(asin, proxy_mgr=self.proxy_mgr)

        if not html:
            return None

        domain = collector_config.MARKETPLACE["domain"]
        product = parse_product_page(html, marketplace_domain=domain)

        if product is None:
            return None

        product["marketplace"] = "https://{}".format(domain)
        product["locale"] = collector_config.MARKETPLACE["language"]
        product["scraped_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        return product

    # ================================================================
    # 전체 수집 (병렬 처리)
    # ================================================================

    def collect_all(self, search_results, keyword, limit=None):
        """
        검색 결과의 모든 ASIN에 대해 상세 데이터를 병렬로 수집합니다.
        체크포인트 저장/복원을 지원합니다.
        """
        self._load_checkpoint(keyword)

        all_asins = [p["asin"] for p in search_results]
        if limit:
            all_asins = all_asins[:limit]

        remaining_asins = [a for a in all_asins if a not in self.processed_asins]
        search_map = {p["asin"]: p for p in search_results}

        total_all = len(all_asins)
        total_remaining = len(remaining_asins)
        already_done = total_all - total_remaining

        logger.info("=" * 60)
        logger.info(
            "[상세 수집 시작] 전체 %d개, 이미 처리 %d개, 남은 %d개",
            total_all, already_done, total_remaining,
        )
        logger.info("=" * 60)

        if total_remaining == 0:
            logger.info("모든 제품이 이미 처리되었습니다.")
            return self.results

        available_proxies = self.proxy_mgr.get_available_count()
        workers = min(
            collector_config.MAX_WORKERS,
            max(available_proxies, 1),
        )
        logger.info("[병렬 처리] 워커 %d개 (프록시 %d개)", workers, available_proxies)

        collected_count = 0

        if workers > 1:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {}
                for asin in remaining_asins:
                    future = executor.submit(self._collect_single, asin, search_map)
                    futures[future] = asin

                for future in as_completed(futures):
                    asin = futures[future]
                    collected_count += 1

                    try:
                        product = future.result()

                        if product:
                            with self.lock:
                                self.results.append(product)
                                self.processed_asins.add(asin)
                            logger.info(
                                "[%d/%d] ASIN %s: 성공 (제목: %s)",
                                already_done + collected_count,
                                total_all, asin,
                                product.get("title", "")[:50],
                            )
                        else:
                            with self.lock:
                                self.failed.append(asin)
                            logger.warning(
                                "[%d/%d] ASIN %s: 수집 실패",
                                already_done + collected_count,
                                total_all, asin,
                            )

                    except Exception as e:
                        with self.lock:
                            self.failed.append(asin)
                        logger.error(
                            "[%d/%d] ASIN %s: 에러 (%s)",
                            already_done + collected_count,
                            total_all, asin, e,
                        )

                    if collected_count % collector_config.CHECKPOINT_INTERVAL == 0:
                        with self.lock:
                            self._save_checkpoint(keyword)

                    if collected_count % 50 == 0:
                        pct = ((already_done + collected_count) / total_all) * 100
                        logger.info(
                            "--- 진행률: %.1f%% (%d/%d) | 성공: %d, 실패: %d ---",
                            pct, already_done + collected_count, total_all,
                            len(self.results), len(self.failed),
                        )
        else:
            for asin in remaining_asins:
                collected_count += 1
                logger.info(
                    "[%d/%d] ASIN %s: 수집 중...",
                    already_done + collected_count, total_all, asin,
                )

                product = self._collect_single(asin, search_map)

                if product:
                    self.results.append(product)
                    self.processed_asins.add(asin)
                    logger.info(
                        "[%d/%d] ASIN %s: 성공 (제목: %s)",
                        already_done + collected_count,
                        total_all, asin,
                        product.get("title", "")[:50],
                    )
                else:
                    self.failed.append(asin)
                    logger.warning(
                        "[%d/%d] ASIN %s: 수집 실패",
                        already_done + collected_count,
                        total_all, asin,
                    )

                if collected_count % collector_config.CHECKPOINT_INTERVAL == 0:
                    self._save_checkpoint(keyword)

                delay = random.uniform(*self.delay_range)
                time.sleep(delay)

        self._save_checkpoint(keyword)

        logger.info("=" * 60)
        logger.info(
            "[상세 수집 완료] 성공: %d, 실패: %d",
            len(self.results), len(self.failed),
        )
        logger.info("=" * 60)

        return self.results

    def _collect_single(self, asin, search_map):
        """단일 ASIN 수집 + 검색 데이터 병합."""
        product = self.collect_product(asin)

        if product and asin in search_map:
            search_data = search_map[asin]
            product["search_thumbnail"] = search_data.get("thumbnail", "")
            product["search_badge"] = search_data.get("badge", "")

        delay = random.uniform(*self.delay_range)
        time.sleep(delay)

        return product

    # ================================================================
    # JSONL 분할 저장
    # ================================================================

    def save_results(self, keyword):
        """
        수집 결과를 JSONL 형식으로 1,000개 단위 분할 저장합니다.
        manifest.json에 전체 현황을 기록합니다.

        Returns:
            list: 생성된 파일 경로 리스트
        """
        if not self.results:
            logger.warning("[저장] 저장할 제품이 없습니다.")
            return []

        safe_keyword = keyword.replace(" ", "_").replace("/", "_")[:50]
        output_dir = collector_config.OUTPUT_DIR

        # 1,000개씩 청크 분할
        chunks = []
        for i in range(0, len(self.results), CHUNK_SIZE):
            chunks.append(self.results[i:i + CHUNK_SIZE])

        # JSONL 파일 저장
        saved_files = []
        for chunk_idx, chunk in enumerate(chunks, 1):
            filename = "raw_{}_{:03d}.jsonl".format(safe_keyword, chunk_idx)
            filepath = os.path.join(output_dir, filename)

            with open(filepath, "w", encoding="utf-8") as f:
                for product in chunk:
                    f.write(json.dumps(product, ensure_ascii=False))
                    f.write("\n")

            saved_files.append({
                "file": filename,
                "count": len(chunk),
            })

            logger.info(
                "[저장] %s (%d개 제품)", filepath, len(chunk),
            )

        # manifest.json 업데이트
        self._update_manifest(keyword, saved_files)

        # 체크포인트 삭제
        self._delete_checkpoint(keyword)

        logger.info(
            "[저장 완료] '%s': %d개 제품 → %d개 파일",
            keyword, len(self.results), len(saved_files),
        )

        return [f["file"] for f in saved_files]

    def _update_manifest(self, keyword, saved_files):
        """
        manifest.json을 업데이트합니다.
        전체 수집 현황을 추적합니다.
        """
        manifest_path = os.path.join(collector_config.OUTPUT_DIR, "manifest.json")

        # 기존 manifest 로드
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
            except Exception:
                manifest = {
                    "created_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "marketplace": collector_config.MARKETPLACE["domain"],
                    "chunk_size": CHUNK_SIZE,
                    "total_products": 0,
                    "keywords": [],
                }
        else:
            manifest = {
                "created_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "marketplace": collector_config.MARKETPLACE["domain"],
                "chunk_size": CHUNK_SIZE,
                "total_products": 0,
                "keywords": [],
            }

        # 이미 같은 키워드가 있으면 교체, 없으면 추가
        keyword_entry = {
            "keyword": keyword,
            "collected_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "total_collected": len(self.results),
            "total_failed": len(self.failed),
            "failed_asins": self.failed[:50],  # 최대 50개만 기록
            "files": saved_files,
            "status": "completed",
        }

        # 기존 키워드 업데이트 or 신규 추가
        existing_idx = None
        for idx, kw in enumerate(manifest["keywords"]):
            if kw["keyword"] == keyword:
                existing_idx = idx
                break

        if existing_idx is not None:
            manifest["keywords"][existing_idx] = keyword_entry
        else:
            manifest["keywords"].append(keyword_entry)

        # 전체 제품 수 재계산
        manifest["total_products"] = sum(
            kw["total_collected"] for kw in manifest["keywords"]
        )
        manifest["updated_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        # 저장
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        logger.info(
            "[매니페스트] 업데이트: 전체 %d개 제품, %d개 키워드",
            manifest["total_products"], len(manifest["keywords"]),
        )

    # ================================================================
    # 상태 초기화
    # ================================================================

    def reset(self):
        """다음 키워드 수집을 위해 상태를 초기화합니다."""
        self.results = []
        self.failed = []
        self.processed_asins = set()

"""
Phase 1 Collector - 수집 오케스트레이터
검색 → ASIN 목록 추출 → 상세 페이지 수집 → JSON 저장.
제품당 1회 HTTP 요청, 가공 없이 원본 데이터를 저장합니다.
"""

import os
import json
import time
import random
import logging
from datetime import datetime

import config as collector_config
from proxy_manager import ProxyManager
from fetcher import fetch_search_page, fetch_product_html
from raw_parser import parse_search_results, parse_product_page


logger = logging.getLogger("collector")


class AmazonCollector:
    """
    아마존 제품 원본 데이터 수집기.

    워크플로:
      1. 키워드 검색 → ASIN 목록 수집
      2. 각 ASIN에 대해 상세 페이지 HTML 1회 수집
      3. raw_parser로 모든 필드 추출
      4. JSON 파일로 저장 (가공 없음)
    """

    def __init__(self, proxy_file=None):
        self.proxy_mgr = ProxyManager(proxy_file)
        self.results = []
        self.failed = []
        self.processed_asins = set()
        self.delay_range = (collector_config.DELAY_MIN, collector_config.DELAY_MAX)

    def search_keyword(self, keyword, search_url=None, max_pages=None):
        """
        키워드를 검색하여 ASIN 목록을 수집합니다.

        Returns:
            list[dict]: 검색 결과 (asin, title, price, rating 등).
        """
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

            # 페이지 간 딜레이
            delay = random.uniform(*self.delay_range)
            time.sleep(delay)

        logger.info("[검색 완료] '%s': 총 %d개 ASIN 수집", keyword, len(all_products))
        return all_products

    def collect_product(self, asin):
        """
        단일 제품의 상세 데이터를 수집합니다.

        Returns:
            dict: 전체 원본 데이터. 실패 시 None.
        """
        html = fetch_product_html(asin, proxy_mgr=self.proxy_mgr)

        if not html:
            return None

        domain = collector_config.MARKETPLACE["domain"]
        product = parse_product_page(html, marketplace_domain=domain)

        if product is None:
            return None

        # 메타데이터 추가
        product["marketplace"] = "https://{}".format(domain)
        product["locale"] = collector_config.MARKETPLACE["language"]
        product["scraped_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        return product

    def collect_all(self, search_results, limit=None):
        """
        검색 결과의 모든 ASIN에 대해 상세 데이터를 수집합니다.

        Args:
            search_results: search_keyword()의 반환값.
            limit: 수집 상한. None이면 전체.

        Returns:
            list[dict]: 수집된 제품 데이터 리스트.
        """
        asins = [p["asin"] for p in search_results]
        if limit:
            asins = asins[:limit]

        total = len(asins)
        logger.info("=" * 60)
        logger.info("[상세 수집 시작] %d개 제품", total)
        logger.info("=" * 60)

        for idx, asin in enumerate(asins):
            if asin in self.processed_asins:
                logger.info("[%d/%d] ASIN %s: 이미 처리됨, 건너뜀", idx + 1, total, asin)
                continue

            logger.info("[%d/%d] ASIN %s: 수집 중...", idx + 1, total, asin)

            product = self.collect_product(asin)

            if product:
                # 검색 결과의 기본 정보도 raw로 병합 (search_ 접두사)
                search_data = next((p for p in search_results if p["asin"] == asin), {})
                product["search_thumbnail"] = search_data.get("thumbnail", "")
                product["search_badge"] = search_data.get("badge", "")

                self.results.append(product)
                self.processed_asins.add(asin)
                logger.info(
                    "[%d/%d] ASIN %s: 성공 (제목: %s)",
                    idx + 1, total, asin,
                    product.get("title", "")[:50],
                )
            else:
                self.failed.append(asin)
                logger.warning("[%d/%d] ASIN %s: 수집 실패", idx + 1, total, asin)

            # 체크포인트 저장
            if len(self.results) % collector_config.CHECKPOINT_INTERVAL == 0 and self.results:
                self._save_checkpoint()

            # 제품 간 딜레이
            delay = random.uniform(*self.delay_range)
            time.sleep(delay)

        logger.info("=" * 60)
        logger.info(
            "[상세 수집 완료] 성공: %d, 실패: %d", len(self.results), len(self.failed)
        )
        logger.info("=" * 60)

        return self.results

    def _save_checkpoint(self):
        """현재까지 수집된 데이터를 체크포인트로 저장합니다."""
        filepath = os.path.join(
            collector_config.CHECKPOINT_DIR,
            "checkpoint_{}.json".format(len(self.results)),
        )
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(self.results, f, ensure_ascii=False, indent=2)
            logger.info("[체크포인트] %d개 제품 저장: %s", len(self.results), filepath)
        except Exception as e:
            logger.error("[체크포인트] 저장 실패: %s", e)

    def save_results(self, keyword):
        """
        수집 결과를 JSON 파일로 저장합니다.

        파일명: raw_{keyword}_{timestamp}.json
        """
        safe_keyword = keyword.replace(" ", "_").replace("/", "_")[:50]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = "raw_{}_{}.json".format(safe_keyword, timestamp)
        filepath = os.path.join(collector_config.OUTPUT_DIR, filename)

        data = {
            "metadata": {
                "keyword": keyword,
                "marketplace": collector_config.MARKETPLACE["domain"],
                "currency": collector_config.MARKETPLACE["currency"],
                "collected_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "total_collected": len(self.results),
                "total_failed": len(self.failed),
                "failed_asins": self.failed,
            },
            "products": self.results,
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info("[저장 완료] %s (%d개 제품)", filepath, len(self.results))
        return filepath

    def reset(self):
        """다음 키워드 수집을 위해 상태를 초기화합니다."""
        self.results = []
        self.failed = []
        self.processed_asins = set()
"""
Phase 1 Collector - 메인 실행 파일
키워드별로 검색 → 수집 → 저장을 순차적으로 실행합니다.
장기 운영(5일+)을 위한 에러 복구, 키워드 재개를 지원합니다.
"""

import os
import sys
import json
import time
import logging
from datetime import datetime

import config as collector_config
from collector import AmazonCollector


def setup_logging():
    """로깅을 설정합니다. 콘솔 + 파일 동시 출력."""
    log_file = os.path.join(
        collector_config.OUTPUT_DIR, "collector.log"
    )

    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s [%(name)s] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 루트 로거
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # 기존 핸들러 제거 (중복 방지)
    root_logger.handlers.clear()

    # 콘솔 핸들러
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 파일 핸들러
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    return logging.getLogger("main")


def load_progress():
    """
    완료된 키워드 목록을 로드합니다.
    키워드별 완료 상태를 추적하여 중단 후 재개를 지원합니다.
    """
    progress_file = os.path.join(
        collector_config.OUTPUT_DIR, "progress.json"
    )

    if os.path.exists(progress_file):
        try:
            with open(progress_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"completed_keywords": []}

    return {"completed_keywords": []}


def save_progress(progress):
    """완료된 키워드 목록을 저장합니다."""
    progress_file = os.path.join(
        collector_config.OUTPUT_DIR, "progress.json"
    )

    with open(progress_file, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def main():
    logger = setup_logging()

    logger.info("=" * 60)
    logger.info("SourceFlowX Phase 1 Collector 시작")
    logger.info("마켓: %s (%s)", 
                collector_config.MARKETPLACE["domain"],
                collector_config.MARKETPLACE["currency"])
    logger.info("키워드: %d개", len(collector_config.CATEGORY_KEYWORDS))
    logger.info("최대 페이지: %d (키워드당)", collector_config.MAX_PAGES)
    logger.info("병렬 워커: %d", collector_config.MAX_WORKERS)
    logger.info("=" * 60)

    # 진행 상태 로드 (중단 후 재개용)
    progress = load_progress()
    completed = set(progress.get("completed_keywords", []))

    collector = AmazonCollector()

    keywords = collector_config.CATEGORY_KEYWORDS
    total_keywords = len(keywords)

    for idx, keyword in enumerate(keywords, 1):
        # 이미 완료된 키워드 건너뛰기
        if keyword in completed:
            logger.info(
                "[%d/%d] '%s': 이미 완료됨, 건너뜀",
                idx, total_keywords, keyword,
            )
            continue

        logger.info("")
        logger.info("▶ 키워드 [%d/%d]: '%s'", idx, total_keywords, keyword)

        try:
            # 검색 URL이 지정되어 있으면 사용
            search_url = collector_config.CATEGORY_URLS.get(keyword)

            # 1. 검색
            search_results = collector.search_keyword(
                keyword,
                search_url=search_url,
                max_pages=collector_config.MAX_PAGES,
            )

            if not search_results:
                logger.warning("  '%s': 검색 결과 없음, 건너뜀", keyword)
                collector.reset()
                continue

            # 2. 상세 수집 (병렬, 체크포인트 포함)
            collector.collect_all(
                search_results,
                keyword=keyword,
                limit=collector_config.ENRICH_LIMIT,
            )

            # 3. 결과 저장
            if collector.results:
                filepath = collector.save_results(keyword)
                logger.info("  '%s': 완료 → %s", keyword, filepath)
            else:
                logger.warning("  '%s': 수집된 제품 없음", keyword)

            # 4. 진행 상태 저장
            completed.add(keyword)
            progress["completed_keywords"] = list(completed)
            save_progress(progress)

        except KeyboardInterrupt:
            logger.info("")
            logger.info("사용자 중단 감지! 현재 진행 상태를 저장합니다...")
            # 현재 키워드의 체크포인트 저장
            collector._save_checkpoint(keyword)
            save_progress(progress)
            logger.info("저장 완료. 다시 실행하면 이어서 수집합니다.")
            sys.exit(0)

        except Exception as e:
            logger.error(
                "  '%s': 에러 발생 (%s). 체크포인트 저장 후 다음 키워드로 진행.",
                keyword, e,
            )
            collector._save_checkpoint(keyword)

        finally:
            # 다음 키워드를 위해 상태 초기화
            collector.reset()

            # 키워드 간 대기 (마지막 키워드 제외)
            if idx < total_keywords:
                wait = collector_config.KEYWORD_DELAY
                logger.info("다음 키워드까지 %d초 대기...", wait)
                time.sleep(wait)

    logger.info("")
    logger.info("=" * 60)
    logger.info("Phase 1 수집 완료!")
    logger.info("완료 키워드: %d/%d", len(completed), total_keywords)
    logger.info("결과 폴더: %s/", collector_config.OUTPUT_DIR)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

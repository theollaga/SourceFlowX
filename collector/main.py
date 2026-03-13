"""
SourceFlowX Phase 1 Collector - 실행 진입점

아마존 제품 페이지의 모든 원본 데이터를 가공 없이 수집하여 JSON으로 저장합니다.
키워드를 순차적으로 처리하며, 키워드 간에 IP 교체(비행기 모드)를 위한
대기 프롬프트를 표시합니다.

사용법:
  cd collector
  python main.py

출력:
  collector_output/raw_{keyword}_{timestamp}.json
"""

import sys
import time
import logging

import config as collector_config
from collector import AmazonCollector


def setup_logging():
    """루트 로거를 설정합니다."""
    log_format = "[%(asctime)s] %(levelname)s [%(name)s] - %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(
                "{}/collector.log".format(collector_config.OUTPUT_DIR),
                encoding="utf-8",
            ),
        ],
    )


def main():
    setup_logging()
    logger = logging.getLogger("main")

    keywords = collector_config.CATEGORY_KEYWORDS
    if not keywords:
        logger.error("검색 키워드가 설정되지 않았습니다. config.py를 확인하세요.")
        return

    marketplace = collector_config.MARKETPLACE
    logger.info("=" * 60)
    logger.info("SourceFlowX Phase 1 Collector 시작")
    logger.info("마켓: %s (%s)", marketplace["domain"], marketplace["currency"])
    logger.info("키워드: %d개", len(keywords))
    logger.info("최대 페이지: %d (키워드당)", collector_config.MAX_PAGES)
    logger.info("=" * 60)

    collector = AmazonCollector()

    for idx, keyword in enumerate(keywords):
        logger.info("")
        logger.info("▶ 키워드 [%d/%d]: '%s'", idx + 1, len(keywords), keyword)

        # 검색 URL 확인
        search_url = collector_config.CATEGORY_URLS.get(keyword)

        # Step 1: 검색
        search_results = collector.search_keyword(keyword, search_url=search_url)

        if not search_results:
            logger.warning("  '%s': 검색 결과 없음. 다음 키워드로 넘어갑니다.", keyword)
            collector.reset()
            continue

        # Step 2: 상세 수집
        collector.collect_all(
            search_results, limit=collector_config.ENRICH_LIMIT
        )

        # Step 3: 저장
        filepath = collector.save_results(keyword)
        logger.info("  '%s': 완료 → %s", keyword, filepath)

        # 다음 키워드를 위한 초기화
        collector.reset()

        # 다음 키워드 전 IP 교체 안내
        if idx < len(keywords) - 1:
            logger.info("")
            logger.info("=" * 60)
            print("\n  ✋ 다음 키워드 전 IP를 교체하세요.")
            print("     → 핸드폰 비행기 모드 ON → 5초 대기 → OFF")
            input("     → 준비되면 Enter를 누르세요... ")
            logger.info("  IP 교체 완료. 다음 키워드로 진행합니다.")
            logger.info("=" * 60)

    # 완료 보고
    logger.info("")
    logger.info("=" * 60)
    logger.info("Phase 1 수집 완료!")
    logger.info("결과 폴더: %s/", collector_config.OUTPUT_DIR)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
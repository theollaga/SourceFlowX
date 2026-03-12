"""
SourceFlowX - 체크포인트 관리 모듈
스크래핑 중간 결과를 주기적으로 저장하고,
프로그램 재시작 시 이어서 처리할 수 있게 한다.
"""

import os
import json
import glob
from datetime import datetime

import config
from utils import setup_logger


class CheckpointManager:
    """
    스크래핑 중간 결과를 체크포인트 파일로 관리하는 클래스.

    주기적으로 진행 상황을 JSON 파일로 저장하고,
    프로그램 재시작 시 가장 최근 체크포인트에서 이어서 처리할 수 있다.
    """

    def __init__(self, checkpoint_dir=None):
        # type: (str) -> None
        """
        CheckpointManager를 초기화한다.

        Args:
            checkpoint_dir: 체크포인트 저장 폴더 경로.
                            None이면 config.CHECKPOINT_DIR 사용.
        """
        if checkpoint_dir is None:
            checkpoint_dir = config.CHECKPOINT_DIR

        self.checkpoint_dir = checkpoint_dir
        self.logger = setup_logger("checkpoint")

        # 폴더가 없으면 자동 생성
        os.makedirs(self.checkpoint_dir, exist_ok=True)

    def save(self, results, processed_asins, keyword):
        # type: (list, set, str) -> None
        """
        체크포인트 파일을 저장한다.

        수집 완료된 상품 리스트와 처리된 ASIN 집합을 JSON 파일로 저장한다.
        저장 실패 시 에러 로그만 남기고 메인 프로세스를 중단하지 않는다.

        Args:
            results: 수집 완료된 상품 딕셔너리 리스트.
            processed_asins: 처리 완료된 ASIN 집합 (set).
            keyword: 검색 키워드.
        """
        try:
            safe_keyword = keyword.replace(" ", "_").strip() or "default"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = "checkpoint_{}_{}.json".format(safe_keyword, timestamp)
            filepath = os.path.join(self.checkpoint_dir, filename)

            data = {
                "keyword": keyword,
                "saved_at": datetime.now().isoformat(),
                "total_processed": len(results),
                "processed_asins": list(processed_asins),
                "results": results,
            }

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            self.logger.info("[체크포인트] %d개 저장 완료: %s", len(results), filename)

        except Exception as e:
            self.logger.error("[체크포인트] 저장 실패: %s", e)

    def load_latest(self, keyword):
        # type: (str) -> tuple or None
        """
        해당 keyword의 가장 최근 체크포인트를 로드한다.

        Args:
            keyword: 검색 키워드.

        Returns:
            tuple: (results 리스트, processed_asins set) 또는
            None: 체크포인트가 없거나 로드 실패 시.
        """
        try:
            safe_keyword = keyword.replace(" ", "_").strip() or "default"
            pattern = os.path.join(
                self.checkpoint_dir, "checkpoint_{}_*.json".format(safe_keyword)
            )
            files = glob.glob(pattern)

            if not files:
                return None

            # 파일명 기준 정렬 → 마지막이 최신
            files = sorted(files)
            latest_file = files[-1]

            with open(latest_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            results = data["results"]
            processed_asins = set(data["processed_asins"])

            self.logger.info(
                "[체크포인트 복원] %d개 이미 처리됨, 이어서 진행", len(results)
            )

            return (results, processed_asins)

        except Exception as e:
            self.logger.error("[체크포인트] 로드 실패: %s", e)
            return None

    def should_save(self, current_count):
        # type: (int) -> bool
        """
        현재 처리 개수가 체크포인트 저장 시점인지 판단한다.

        Args:
            current_count: 현재까지 처리된 상품 수.

        Returns:
            bool: 저장 시점이면 True, 아니면 False.
        """
        return current_count > 0 and current_count % config.CHECKPOINT_INTERVAL == 0

    def cleanup_old(self, keyword, keep_latest=3):
        # type: (str, int) -> None
        """
        해당 keyword의 체크포인트 중 최근 keep_latest개만 남기고 삭제한다.

        디스크 공간 관리를 위해 오래된 체크포인트를 정리한다.
        정리 실패 시 에러 로그만 남기고 메인 프로세스를 중단하지 않는다.

        Args:
            keyword: 검색 키워드.
            keep_latest: 유지할 최근 파일 수. 기본값 3.
        """
        try:
            safe_keyword = keyword.replace(" ", "_").strip() or "default"
            pattern = os.path.join(
                self.checkpoint_dir, "checkpoint_{}_*.json".format(safe_keyword)
            )
            files = sorted(glob.glob(pattern))

            if len(files) <= keep_latest:
                return

            # 오래된 것부터 삭제
            files_to_delete = files[:-keep_latest]
            for f in files_to_delete:
                os.remove(f)

            self.logger.info(
                "[체크포인트] 정리 완료: %d개 삭제, %d개 유지",
                len(files_to_delete),
                keep_latest,
            )

        except Exception as e:
            self.logger.error("[체크포인트] 정리 실패: %s", e)

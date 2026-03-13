"""
Phase 1 Collector - 프록시 관리 모듈
기존 SourceFlowX proxy_manager.py를 독립화한 버전.
proxies.txt 파일 기반 프록시 로드, 랜덤 선택, 실패 관리.
프록시 없이도 정상 동작합니다 (핫스팟 환경 지원).
"""

import random
import threading
import logging

import config as collector_config


logger = logging.getLogger("collector.proxy")


class ProxyManager:
    """
    프록시 로드, 랜덤 로테이션, 실패 프록시 제외를 관리하는 클래스.
    프록시 파일이 없거나 비어 있으면 프록시 없이 진행합니다.
    """

    def __init__(self, proxy_file=None):
        if proxy_file is None:
            proxy_file = collector_config.PROXY_FILE

        self.proxies = []
        self.failed_proxies = set()
        self.lock = threading.Lock()

        self._load_proxies(proxy_file)

    def _load_proxies(self, proxy_file):
        try:
            with open(proxy_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue

                    parts = line.split(":")

                    if len(parts) == 4:
                        ip, port, username, password = parts
                        proxy_url = "http://{}:{}@{}:{}".format(
                            username, password, ip, port
                        )
                        self.proxies.append({"http": proxy_url, "https": proxy_url})

                    elif len(parts) == 2:
                        ip, port = parts
                        proxy_url = "http://{}:{}".format(ip, port)
                        self.proxies.append({"http": proxy_url, "https": proxy_url})

                    else:
                        logger.warning("[프록시] 알 수 없는 형식 무시: %s", line)

        except FileNotFoundError:
            self.proxies = []
            logger.info("[프록시] %s 없음 → 프록시 없이 진행", proxy_file)

        logger.info("[프록시] %d개 로드 완료", len(self.proxies))

    def get_random(self):
        """사용 가능한 프록시 중 랜덤 1개 반환. 없으면 None."""
        with self.lock:
            available = [
                p for p in self.proxies if p["http"] not in self.failed_proxies
            ]
            if available:
                return random.choice(available)
            return None

    def mark_failed(self, proxy_dict):
        """특정 프록시를 실패 목록에 추가."""
        if proxy_dict is None:
            return
        with self.lock:
            self.failed_proxies.add(proxy_dict["http"])
            remaining = len(self.proxies) - len(self.failed_proxies)
            logger.warning(
                "[프록시] 제외됨: %s (남은 프록시: %d개)", proxy_dict["http"], remaining
            )

    def get_available_count(self):
        with self.lock:
            return len(self.proxies) - len(self.failed_proxies)

    def reset_failed(self):
        with self.lock:
            self.failed_proxies = set()
            logger.info("[프록시] 실패 목록 초기화, %d개 프록시 사용 가능", len(self.proxies))
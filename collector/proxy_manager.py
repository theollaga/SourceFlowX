"""
Phase 1 Collector - 프록시 관리 모듈
프록시 로드, 랜덤 로테이션, 실패 프록시 제외, 자동 리셋을 관리합니다.
"""

import random
import threading
import logging


logger = logging.getLogger("collector.proxy")


class ProxyManager:
    """
    프록시 로드, 랜덤 로테이션, 실패 프록시 제외를 관리하는 클래스.
    프록시를 {"http": url, "https": url} 딕셔너리 형식으로 관리합니다.
    프록시 소진 시 자동으로 실패 목록을 리셋합니다.
    """

    def __init__(self, proxy_file=None):
        if proxy_file is None:
            import config as collector_config
            proxy_file = collector_config.PROXY_FILE

        self.proxies = []
        self.failed_proxies = set()
        self.lock = threading.Lock()

        self._load_proxies(proxy_file)

    def _load_proxies(self, proxy_file):
        """
        프록시 파일을 읽어서 로드합니다.
        지원 형식:
          - ip:port:username:password (인증 프록시)
          - ip:port (비인증 프록시)
        """
        try:
            with open(proxy_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue

                    parts = line.split(":")

                    if len(parts) == 4:
                        ip, port, username, password = parts
                        proxy_url = "http://{}:{}@{}:{}".format(username, password, ip, port)
                    elif len(parts) == 2:
                        ip, port = parts
                        proxy_url = "http://{}:{}".format(ip, port)
                    else:
                        logger.warning("[프록시] 알 수 없는 형식 무시: %s", line)
                        continue

                    self.proxies.append({"http": proxy_url, "https": proxy_url})

        except FileNotFoundError:
            self.proxies = []
            logger.info("[프록시] %s 없음 → 프록시 없이 진행", proxy_file)

        logger.info("[프록시] %d개 로드 완료", len(self.proxies))

    def get_random(self):
        """
        사용 가능한 프록시 중 랜덤으로 하나를 반환합니다.
        모든 프록시가 실패 상태면 자동으로 리셋 후 재시도합니다.

        Returns:
            dict: {"http": proxy_url, "https": proxy_url} 또는 None
        """
        with self.lock:
            available = [
                p for p in self.proxies if p["http"] not in self.failed_proxies
            ]

            if available:
                return random.choice(available)

            # 프록시 소진 → 자동 리셋
            if self.proxies:
                logger.warning(
                    "[프록시] 모든 프록시 소진 (%d개 실패). 실패 목록 자동 리셋.",
                    len(self.failed_proxies),
                )
                self.failed_proxies.clear()
                return random.choice(self.proxies)

            return None

    def mark_failed(self, proxy_dict):
        """
        특정 프록시를 실패 목록에 추가합니다.

        Args:
            proxy_dict: {"http": url, "https": url} 딕셔너리. None이면 무시.
        """
        if proxy_dict is None:
            return

        with self.lock:
            proxy_url = proxy_dict.get("http", "")
            if proxy_url:
                self.failed_proxies.add(proxy_url)
                remaining = len(self.proxies) - len(self.failed_proxies)
                logger.warning(
                    "[프록시] 제외됨: %s (남은 프록시: %d개)", proxy_url, remaining
                )

    def get_available_count(self):
        """현재 사용 가능한 프록시 수를 반환합니다."""
        with self.lock:
            return len(self.proxies) - len(self.failed_proxies)

    def reset_failed(self):
        """실패 프록시 목록을 초기화하여 모든 프록시를 다시 사용 가능하게 합니다."""
        with self.lock:
            self.failed_proxies.clear()
            logger.info("[프록시] 실패 목록 초기화, %d개 프록시 사용 가능", len(self.proxies))

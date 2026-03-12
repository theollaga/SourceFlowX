"""
SourceFlowX - 프록시 관리 모듈
프록시 리스트를 로드하고, 랜덤 로테이션하며,
실패한 프록시를 자동으로 제외하는 관리자.
"""

import random
import threading

import config
from utils import setup_logger


class ProxyManager:
    """
    프록시 로드, 랜덤 로테이션, 실패 프록시 제외를 관리하는 클래스.

    프록시 파일에서 프록시 목록을 읽어들이고,
    스레드-안전하게 랜덤 프록시를 제공하며,
    실패한 프록시를 자동으로 제외한다.
    """

    def __init__(self, proxy_file=None):
        # type: (str) -> None
        """
        ProxyManager를 초기화하고 프록시 파일을 로드한다.

        Args:
            proxy_file: 프록시 리스트 파일 경로.
                        None이면 config.PROXY_FILE 사용.
        """
        if proxy_file is None:
            proxy_file = config.PROXY_FILE

        self.proxies = []  # 로드된 프록시 딕셔너리 리스트
        self.failed_proxies = set()  # 실패한 프록시 URL 집합
        self.lock = threading.Lock()  # 스레드 안전용 락
        self.logger = setup_logger("proxy")

        self._load_proxies(proxy_file)

    def _load_proxies(self, proxy_file):
        # type: (str) -> None
        """
        프록시 파일을 읽어서 self.proxies에 로드한다.

        지원 형식:
        - ip:port:username:password (인증 프록시)
        - ip:port (비인증 프록시)

        Args:
            proxy_file: 프록시 리스트 파일 경로.
        """
        try:
            with open(proxy_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()

                    # 빈 줄 무시
                    if not line:
                        continue

                    # 주석 줄 무시
                    if line.startswith("#"):
                        continue

                    parts = line.split(":")

                    if len(parts) == 4:
                        # ip:port:username:password
                        ip, port, username, password = parts
                        proxy_url = "http://{}:{}@{}:{}".format(
                            username, password, ip, port
                        )
                        self.proxies.append({"http": proxy_url, "https": proxy_url})

                    elif len(parts) == 2:
                        # ip:port
                        ip, port = parts
                        proxy_url = "http://{}:{}".format(ip, port)
                        self.proxies.append({"http": proxy_url, "https": proxy_url})

                    else:
                        # 알 수 없는 형식
                        self.logger.warning("[프록시] 알 수 없는 형식 무시: %s", line)

        except FileNotFoundError:
            self.proxies = []
            self.logger.info("[프록시] %s 없음 → 프록시 없이 진행", proxy_file)

        self.logger.info("[프록시] %d개 로드 완료", len(self.proxies))

    def get_random(self):
        # type: () -> dict or None
        """
        사용 가능한 프록시 중에서 랜덤으로 하나를 반환한다.

        실패 목록에 포함된 프록시는 제외하고 선택한다.
        사용 가능한 프록시가 없으면 None을 반환한다.

        Returns:
            dict: {"http": proxy_url, "https": proxy_url} 또는 None
        """
        with self.lock:
            available = [
                p for p in self.proxies if p["http"] not in self.failed_proxies
            ]

            if available:
                return random.choice(available)

            return None

    def mark_failed(self, proxy_dict):
        # type: (dict) -> None
        """
        특정 프록시를 실패 목록에 추가하여 더 이상 사용하지 않게 한다.

        Args:
            proxy_dict: 실패한 프록시 딕셔너리. None이면 무시.
        """
        if proxy_dict is None:
            return

        with self.lock:
            proxy_url = proxy_dict["http"]
            self.failed_proxies.add(proxy_url)

            remaining = len(self.proxies) - len(self.failed_proxies)
            self.logger.warning(
                "[프록시] 제외됨: %s (남은 프록시: %d개)", proxy_url, remaining
            )

    def get_available_count(self):
        # type: () -> int
        """
        현재 사용 가능한 프록시 수를 반환한다.

        Returns:
            int: 전체 프록시 수 - 실패한 프록시 수
        """
        with self.lock:
            return len(self.proxies) - len(self.failed_proxies)

    def reset_failed(self):
        # type: () -> None
        """
        실패 프록시 목록을 초기화하여 모든 프록시를 다시 사용 가능하게 한다.
        """
        with self.lock:
            self.failed_proxies = set()
            self.logger.info(
                "[프록시] 실패 목록 초기화, %d개 프록시 사용 가능", len(self.proxies)
            )

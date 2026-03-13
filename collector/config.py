"""
Phase 1 Collector 설정 파일
아마존 마켓 선택, 검색 키워드, HTTP 요청, 프록시, 출력 경로 등 모든 설정을 관리합니다.
"""

import os

# ================================================================
# 섹션 1: 마켓(국가) 설정
# ================================================================

MARKETPLACE = {
    "country_code": "com",           # com, co.uk, de, co.jp, ca, etc.
    "domain": "www.amazon.com",
    "language": "en_US",
    "currency": "USD",
    "currency_cookie_key": "i18n-prefs",
    "locale_cookie_key": "lc-main",
}
# 지원 마켓 예시:
#   US:  {"country_code": "com",   "domain": "www.amazon.com",    "language": "en_US", "currency": "USD"}
#   UK:  {"country_code": "co.uk", "domain": "www.amazon.co.uk",  "language": "en_GB", "currency": "GBP"}
#   DE:  {"country_code": "de",    "domain": "www.amazon.de",     "language": "de_DE", "currency": "EUR"}
#   JP:  {"country_code": "co.jp", "domain": "www.amazon.co.jp",  "language": "ja_JP", "currency": "JPY"}

# ================================================================
# 섹션 2: 검색 키워드
# ================================================================

CATEGORY_KEYWORDS = ["wireless earbuds"]

CATEGORY_URLS = {}
# 특정 키워드에 카테고리 URL 직접 지정 시 사용
# 예: {"automatic pet feeder": "https://www.amazon.com/s?i=pets&rh=n%3A2975312011"}

MAX_PAGES = 1
# 검색 페이지 수. 페이지당 약 48개 상품. 20페이지 ≒ 960개

ENRICH_LIMIT = 3
# 상세 수집 상한. None이면 전체, 숫자면 상위 N개만 수집

# ================================================================
# 섹션 3: HTTP 요청 설정
# ================================================================

IMPERSONATE = "chrome119"
# curl_cffi TLS 핑거프린트. "chrome120", "safari15_5" 등으로 변경 가능

REQUEST_TIMEOUT = 25
# HTTP 요청 타임아웃 (초)

MAX_RETRIES = 3
# 요청 실패 시 최대 재시도 횟수

RETRY_BACKOFF = 5
# 재시도 대기 기본 초. 실제 대기 = RETRY_BACKOFF × (시도 횟수)

DELAY_MIN = 3.0
# 요청 간 최소 딜레이 (초)

DELAY_MAX = 7.0
# 요청 간 최대 딜레이 (초)

KEYWORD_DELAY = 10
# 키워드 간 대기 시간 (초)

IMPERSONATE_ROTATION = ["chrome119", "chrome120", "safari15_5"]
# 상세 페이지 요청 시 TLS 핑거프린트 로테이션 목록

# ================================================================
# 섹션 4: 프록시 설정
# ================================================================

PROXY_FILE = "proxies.txt"
# 프록시 리스트 파일 경로. 비어 있으면 프록시 없이 진행.

# ================================================================
# 섹션 5: 출력 설정
# ================================================================

OUTPUT_DIR = "collector_output"
# 수집 결과 JSON 파일 저장 폴더

CHECKPOINT_DIR = "collector_checkpoints"
# 체크포인트 파일 저장 폴더

CHECKPOINT_INTERVAL = 50
# N개 상품마다 체크포인트 저장

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(CHECKPOINT_DIR, exist_ok=True)
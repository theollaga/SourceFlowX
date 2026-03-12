"""
SourceFlowX - 공통 유틸리티 모듈
프로젝트 전체에서 공통으로 사용하는 함수들을 모아놓은 모듈.
"""

import re
import logging
import os
import time

import config


def parse_price(price_str):
    # type: (object) -> float
    """
    아마존 가격 문자열을 float으로 변환한다.

    다양한 형식의 가격 문자열을 처리할 수 있다.
    범위 가격인 경우 첫 번째(최저) 가격만 사용한다.

    Examples:
        >>> parse_price("$29.99")
        29.99
        >>> parse_price("$1,299.00")
        1299.0
        >>> parse_price("$29.99 - $49.99")
        29.99
        >>> parse_price("29.99")
        29.99
        >>> parse_price("")
        0.0
        >>> parse_price(None)
        0.0
        >>> parse_price("Currently unavailable")
        0.0

    Args:
        price_str: 가격 문자열. None, 빈 문자열, 숫자가 아닌 문자열도 허용.

    Returns:
        float: 파싱된 가격. 변환 실패 시 0.0
    """
    try:
        # None이거나 빈 문자열이면 0.0 반환
        if price_str is None or str(price_str).strip() == "":
            return 0.0

        price_str = str(price_str)

        # 숫자 패턴을 모두 찾기 (쉼표 포함 숫자, 소수점 포함)
        matches = re.findall(r"[\d,]+\.?\d*", price_str)

        if matches:
            # 첫 번째 매치에서 쉼표 제거 후 float 변환
            return float(matches[0].replace(",", ""))

        return 0.0

    except (ValueError, TypeError):
        return 0.0


def retry_request(func, max_retries=None, backoff=None, logger=None):
    """
    재시도 래퍼 함수. 실패하는 HTTP 요청 등을 자동으로 재시도한다.

    지정된 횟수만큼 func()를 호출하며, 실패 시 점진적으로
    대기 시간을 늘려가며 재시도한다 (선형 백오프).

    Args:
        func: 호출할 callable (인자 없는 함수, lambda, functools.partial 등)
        max_retries: 최대 재시도 횟수. None이면 config.MAX_RETRIES 사용.
        backoff: 재시도 대기 기본 초. None이면 config.RETRY_BACKOFF 사용.
                 실제 대기 시간 = backoff × (시도 횟수)
        logger: 로거 객체. None이면 print로 출력.

    Returns:
        func()의 반환값 또는 모든 시도 실패 시 None
    """
    if max_retries is None:
        max_retries = config.MAX_RETRIES
    if backoff is None:
        backoff = config.RETRY_BACKOFF

    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt < max_retries - 1:
                # 마지막 시도가 아니면 대기 후 재시도
                wait = backoff * (attempt + 1)
                msg = "[재시도 {}/{}] {} ({}초 대기)".format(
                    attempt + 1, max_retries, e, wait
                )
                if logger:
                    logger.warning(msg)
                else:
                    print(msg)
                time.sleep(wait)
            else:
                # 마지막 시도도 실패
                msg = "[재시도 실패] {}회 모두 실패: {}".format(max_retries, e)
                if logger:
                    logger.error(msg)
                else:
                    print(msg)

    return None


def setup_logger(name="sourceflowx"):
    # type: (str) -> logging.Logger
    """
    Python logging 모듈 기반 로거를 생성하여 반환한다.

    콘솔(INFO 레벨)과 파일(DEBUG 레벨) 두 가지 핸들러를 설정한다.
    이미 핸들러가 설정된 로거라면 중복 추가 없이 그대로 반환한다.

    Args:
        name: 로거 이름. 기본값 "sourceflowx".

    Returns:
        logging.Logger: 설정이 완료된 로거 객체
    """
    logger = logging.getLogger(name)

    # 이미 핸들러가 있으면 그대로 반환 (중복 핸들러 방지)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # 콘솔 핸들러 (INFO 레벨)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_fmt = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_fmt)

    # 파일 핸들러 (DEBUG 레벨)
    log_path = os.path.join(config.OUTPUT_DIR, "sourceflowx.log")
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_fmt = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)s [%(name)s] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_fmt)

    # 핸들러 추가
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


def clean_html_body(html_str):
    # type: (object) -> str
    """
    HTML 문자열에서 CSV를 깨뜨릴 수 있는 문자를 정리한다.

    쇼피파이 CSV의 Body (HTML) 필드에 넣을 때
    개행 문자로 인해 행이 깨지는 것을 방지한다.

    Args:
        html_str: 정리할 HTML 문자열. None이면 빈 문자열 반환.

    Returns:
        str: 개행 및 연속 공백이 제거된 HTML 문자열
    """
    if html_str is None:
        return ""

    result = str(html_str)
    result = result.replace("\r\n", " ")
    result = result.replace("\n", " ")
    result = result.replace("\r", " ")
    result = re.sub(r" {2,}", " ", result)
    result = result.strip()

    return result


def sanitize_text(text):
    # type: (object) -> str
    """
    상품 제목 등의 텍스트에서 CSV를 깨뜨릴 수 있는 문자를 정리한다.

    탭, 개행 등 CSV 파싱을 방해하는 문자를 공백으로 치환하고,
    연속 공백을 단일 공백으로 정리한다.

    Args:
        text: 정리할 텍스트. None이면 빈 문자열 반환.

    Returns:
        str: 정리된 텍스트 문자열
    """
    if text is None:
        return ""

    result = str(text)
    result = result.replace("\t", " ")
    result = result.replace("\r\n", " ")
    result = result.replace("\n", " ")
    result = result.replace("\r", " ")
    result = re.sub(r" {2,}", " ", result)
    result = result.strip()

    return result


def check_state():
    # type: () -> None
    """
    현재 실행 상태(일시정지, 중지)를 확인한다.
    중지 상태면 RuntimeError를 발생시키고, 일시정지 상태면 풀릴 때까지 대기한다.
    긴 스크래핑 파이프라인(scraper.py 등)의 주요 루프에서 호출된다.
    """
    import config
    import time

    # 중지 검사
    if getattr(config, "RUNTIME_STOPPED", False):
        raise RuntimeError("사용자에 의해 명시적으로 중지되었습니다.")

    # 일시정지 검사 및 대기
    while getattr(config, "RUNTIME_PAUSED", False):
        if getattr(config, "RUNTIME_STOPPED", False):
            raise RuntimeError("사용자에 의해 명시적으로 중지되었습니다.")
        time.sleep(1.0)

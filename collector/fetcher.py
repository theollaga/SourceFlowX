"""
Phase 1 Collector - HTTP 수집 모듈
curl_cffi 세션을 사용하여 아마존 페이지 HTML을 가져옵니다.
세션 기반 요청으로 쿠키/핑거프린트 일관성을 유지합니다.
CAPTCHA 감지, 프록시 교체, TLS 핑거프린트 로테이션을 지원합니다.
"""

import re
import time
import random
import logging

from curl_cffi import requests as cffi_requests

import config as collector_config


logger = logging.getLogger("collector.fetcher")


def _build_cookies():
    """
    미국 ZIP 코드를 배송 주소 쿠키에 강제 설정하여
    어떤 IP에서 접속해도 미국 가격/재고를 표시하도록 합니다.
    """
    mp = collector_config.MARKETPLACE

    address_cookie = (
        '{"is498702":false,'
        '"subpromptCount":0,'
        '"ward498498":"",'
        '"wardIdent":"",'
        '"postalCode":"10001",'
        '"countryCode":"US",'
        '"deviceType":"web",'
        '"storeContext":"generic",'
        '"storeName":"generic",'
        '"serviceRegion":"default"}'
    )

    return {
        mp["locale_cookie_key"]: mp["language"],
        mp["currency_cookie_key"]: mp["currency"],
        "sp-cdn": '"L5Z9:US"',
        "session-token": "",
        "ubid-main": "",
        "lc-main": "en_US",
        "i18n-prefs": "USD",
        "address": address_cookie,
        "session-id-time": "2082787201l",
    }


def _build_headers():
    """미국 브라우저로 인식되도록 헤더를 설정합니다."""
    return {
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }


def _create_session(impersonate, proxy_dict=None):
    """
    curl_cffi 세션을 생성합니다.
    세션을 유지하면 쿠키/핑거프린트 일관성이 유지되어 봇 탐지가 줄어듭니다.

    Args:
        impersonate: TLS 핑거프린트 문자열.
        proxy_dict: {"http": url, "https": url} 딕셔너리. None이면 프록시 없이.

    Returns:
        cffi_requests.Session
    """
    session = cffi_requests.Session(impersonate=impersonate)
    session.headers.update(_build_headers())
    session.cookies.update(_build_cookies())

    if proxy_dict is not None:
        session.proxies = proxy_dict

    return session


def _is_captcha(html):
    """CAPTCHA 페이지인지 확인합니다."""
    lower = html.lower()
    return "captcha" in lower or "api-services-support@amazon.com" in lower


def _is_geo_blocked(html):
    """
    진짜 지역 제한 페이지인지 확인합니다.
    "cannot be shipped" 메시지가 있으면서 가격이 없으면 geo-block입니다.
    """
    lower = html.lower()

    # 가격이 있으면 절대 geo-block 아님
    if re.search(r'"priceAmount"\s*:\s*([1-9][\d.]*)', html):
        return False

    # 가격 셀렉터로 한 번 더 확인 (.a-offscreen에 $숫자가 있으면 정상)
    if re.search(r'class="a-offscreen"[^>]*>\s*\$[\d,]+\.?\d*', html):
        return False

    # 명확한 geo-block 메시지 확인 (가격이 없는 상태에서)
    geo_signals = [
        "cannot be shipped to your selected delivery location",
        "currently unavailable in your region",
    ]

    for signal in geo_signals:
        if signal in lower:
            return True

    return False


def fetch_product_html(asin, proxy_mgr=None, impersonate=None):
    """
    아마존 상세 페이지 HTML을 세션 기반으로 가져옵니다.
    CAPTCHA/geo-block 감지 시 세션+프록시를 교체하여 재시도합니다.
    """
    domain = collector_config.MARKETPLACE["domain"]
    url = "https://{}/dp/{}".format(domain, asin)
    rotation = collector_config.IMPERSONATE_ROTATION
    max_retries = collector_config.MAX_RETRIES

    for attempt in range(max_retries):
        imp = impersonate or rotation[attempt % len(rotation)]
        proxy = proxy_mgr.get_random() if proxy_mgr else None

        # 매 시도마다 새 세션 (프록시/핑거프린트 교체 반영)
        session = _create_session(imp, proxy)

        try:
            resp = session.get(url, timeout=collector_config.REQUEST_TIMEOUT)
            html = resp.text

            if _is_captcha(html):
                logger.warning(
                    "[FETCH] ASIN %s: CAPTCHA 감지 (시도 %d/%d). 세션+프록시 교체.",
                    asin, attempt + 1, max_retries,
                )
                if proxy and proxy_mgr:
                    proxy_mgr.mark_failed(proxy)
                wait = collector_config.RETRY_BACKOFF * (attempt + 1)
                time.sleep(wait)
                continue

            if len(html) < 5000:
                logger.warning(
                    "[FETCH] ASIN %s: 응답이 너무 짧음 (%d bytes). 재시도 %d/%d",
                    asin, len(html), attempt + 1, max_retries,
                )
                if proxy and proxy_mgr:
                    proxy_mgr.mark_failed(proxy)
                wait = collector_config.RETRY_BACKOFF * (attempt + 1)
                time.sleep(wait)
                continue

            if _is_geo_blocked(html):
                logger.warning(
                    "[FETCH] ASIN %s: 지역 제한 감지 (시도 %d/%d). 세션+프록시 교체.",
                    asin, attempt + 1, max_retries,
                )
                if proxy and proxy_mgr:
                    proxy_mgr.mark_failed(proxy)
                wait = collector_config.RETRY_BACKOFF * (attempt + 1)
                time.sleep(wait)
                continue

            return html

        except Exception as e:
            logger.warning(
                "[FETCH] ASIN %s: 요청 실패 (%s). 재시도 %d/%d",
                asin, e, attempt + 1, max_retries,
            )
            if proxy and proxy_mgr:
                proxy_mgr.mark_failed(proxy)
            wait = collector_config.RETRY_BACKOFF * (attempt + 1)
            time.sleep(wait)

        finally:
            try:
                session.close()
            except Exception:
                pass

    logger.error("[FETCH] ASIN %s: %d회 시도 모두 실패", asin, max_retries)
    return None


def fetch_search_page(query=None, search_url=None, page=1, proxy_mgr=None):
    """
    아마존 검색 결과 페이지 HTML을 세션 기반으로 가져옵니다.
    """
    domain = collector_config.MARKETPLACE["domain"]

    if search_url:
        sep = "&" if "?" in search_url else "?"
        url = "{}{}page={}".format(search_url, sep, page)
    else:
        from urllib.parse import quote_plus
        safe_query = quote_plus(query) if query else ""
        url = "https://{}/s?k={}&page={}".format(domain, safe_query, page)

    rotation = collector_config.IMPERSONATE_ROTATION

    for attempt in range(collector_config.MAX_RETRIES):
        imp = rotation[attempt % len(rotation)]
        proxy = proxy_mgr.get_random() if proxy_mgr else None

        session = _create_session(imp, proxy)

        try:
            resp = session.get(url, timeout=collector_config.REQUEST_TIMEOUT)
            html = resp.text

            if _is_captcha(html):
                logger.warning(
                    "[SEARCH] 페이지 %d: CAPTCHA 감지. 세션+프록시 교체. 재시도 %d/%d",
                    page, attempt + 1, collector_config.MAX_RETRIES,
                )
                if proxy and proxy_mgr:
                    proxy_mgr.mark_failed(proxy)
                time.sleep(collector_config.RETRY_BACKOFF * (attempt + 1))
                continue

            return html

        except Exception as e:
            logger.warning(
                "[SEARCH] 페이지 %d: 요청 실패 (%s). 재시도 %d/%d",
                page, e, attempt + 1, collector_config.MAX_RETRIES,
            )
            if proxy and proxy_mgr:
                proxy_mgr.mark_failed(proxy)
            time.sleep(collector_config.RETRY_BACKOFF * (attempt + 1))

        finally:
            try:
                session.close()
            except Exception:
                pass

    logger.error("[SEARCH] 페이지 %d: 모든 시도 실패", page)
    return None

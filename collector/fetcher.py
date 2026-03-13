"""
Phase 1 Collector - HTTP 수집 모듈
curl_cffi를 사용하여 아마존 페이지 HTML을 가져옵니다.
제품당 1회 요청으로 트래픽을 최소화합니다 (~0.7MB/제품).
CAPTCHA 감지, 프록시 교체, TLS 핑거프린트 로테이션을 지원합니다.
"""

import time
import random
import logging

from curl_cffi import requests as cffi_requests

import config as collector_config


logger = logging.getLogger("collector.fetcher")


def _build_cookies():
    """마켓 설정에 따른 통화/언어 쿠키를 생성합니다."""
    mp = collector_config.MARKETPLACE
    return {
        mp["locale_cookie_key"]: mp["language"],
        mp["currency_cookie_key"]: mp["currency"],
        "sp-cdn": '"L5Z9:KR"',
    }


def _build_headers():
    return {
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }


def _is_captcha(html):
    """CAPTCHA 페이지인지 확인합니다."""
    lower = html.lower()
    return "captcha" in lower or "api-services-support@amazon.com" in lower


def fetch_product_html(asin, proxy_mgr=None, impersonate=None):
    """
    아마존 상세 페이지 HTML을 1회 요청으로 가져옵니다.

    Args:
        asin: 아마존 ASIN.
        proxy_mgr: ProxyManager 인스턴스. None이면 프록시 없이 요청.
        impersonate: TLS 핑거프린트. None이면 로테이션 목록에서 순환 선택.

    Returns:
        str: HTML 문자열. 모든 시도 실패 시 None.
    """
    domain = collector_config.MARKETPLACE["domain"]
    url = "https://{}/dp/{}".format(domain, asin)
    cookies = _build_cookies()
    headers = _build_headers()
    rotation = collector_config.IMPERSONATE_ROTATION

    for attempt in range(collector_config.MAX_RETRIES):
        imp = impersonate or rotation[attempt % len(rotation)]
        proxy = proxy_mgr.get_random() if proxy_mgr else None

        kwargs = {
            "impersonate": imp,
            "headers": headers,
            "cookies": cookies,
            "timeout": collector_config.REQUEST_TIMEOUT,
        }
        if proxy is not None:
            kwargs["proxies"] = proxy

        try:
            resp = cffi_requests.get(url, **kwargs)
            html = resp.text

            if _is_captcha(html):
                logger.warning(
                    "[FETCH] ASIN %s: CAPTCHA 감지 (시도 %d/%d). 프록시 교체 후 재시도.",
                    asin, attempt + 1, collector_config.MAX_RETRIES,
                )
                if proxy and proxy_mgr:
                    proxy_mgr.mark_failed(proxy)
                wait = collector_config.RETRY_BACKOFF * (attempt + 1)
                time.sleep(wait)
                continue

            if len(html) < 5000:
                logger.warning(
                    "[FETCH] ASIN %s: 응답이 너무 짧음 (%d bytes). 재시도 %d/%d",
                    asin, len(html), attempt + 1, collector_config.MAX_RETRIES,
                )
                wait = collector_config.RETRY_BACKOFF * (attempt + 1)
                time.sleep(wait)
                continue

            return html

        except Exception as e:
            logger.warning(
                "[FETCH] ASIN %s: 요청 실패 (%s). 재시도 %d/%d",
                asin, e, attempt + 1, collector_config.MAX_RETRIES,
            )
            if proxy and proxy_mgr:
                proxy_mgr.mark_failed(proxy)
            wait = collector_config.RETRY_BACKOFF * (attempt + 1)
            time.sleep(wait)

    logger.error("[FETCH] ASIN %s: %d회 시도 모두 실패", asin, collector_config.MAX_RETRIES)
    return None


def fetch_search_page(query=None, search_url=None, page=1, proxy_mgr=None):
    """
    아마존 검색 결과 페이지 HTML을 가져옵니다.

    Args:
        query: 검색 키워드. search_url과 택일.
        search_url: 카테고리 URL 직접 지정.
        page: 페이지 번호.
        proxy_mgr: ProxyManager 인스턴스.

    Returns:
        str: HTML 문자열. 실패 시 None.
    """
    domain = collector_config.MARKETPLACE["domain"]

    if search_url:
        sep = "&" if "?" in search_url else "?"
        url = "{}{}page={}".format(search_url, sep, page)
    else:
        from urllib.parse import quote_plus
        safe_query = quote_plus(query) if query else ""
        url = "https://{}/s?k={}&page={}".format(domain, safe_query, page)

    cookies = _build_cookies()
    headers = _build_headers()
    proxy = proxy_mgr.get_random() if proxy_mgr else None

    kwargs = {
        "impersonate": collector_config.IMPERSONATE,
        "headers": headers,
        "cookies": cookies,
        "timeout": collector_config.REQUEST_TIMEOUT,
    }
    if proxy is not None:
        kwargs["proxies"] = proxy

    for attempt in range(collector_config.MAX_RETRIES):
        try:
            resp = cffi_requests.get(url, **kwargs)
            html = resp.text

            if _is_captcha(html):
                logger.warning("[SEARCH] 페이지 %d: CAPTCHA 감지. 재시도 %d/%d", page, attempt + 1, collector_config.MAX_RETRIES)
                if proxy and proxy_mgr:
                    proxy_mgr.mark_failed(proxy)
                    proxy = proxy_mgr.get_random()
                    if proxy:
                        kwargs["proxies"] = proxy
                time.sleep(collector_config.RETRY_BACKOFF * (attempt + 1))
                continue

            return html

        except Exception as e:
            logger.warning("[SEARCH] 페이지 %d: 요청 실패 (%s). 재시도 %d/%d", page, e, attempt + 1, collector_config.MAX_RETRIES)
            if proxy and proxy_mgr:
                proxy_mgr.mark_failed(proxy)
                proxy = proxy_mgr.get_random()
                if proxy:
                    kwargs["proxies"] = proxy
            time.sleep(collector_config.RETRY_BACKOFF * (attempt + 1))

    logger.error("[SEARCH] 페이지 %d: 모든 시도 실패", page)
    return None
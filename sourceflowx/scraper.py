"""
SourceFlowX - 메인 스크래퍼 모듈
curl_cffi 직접 검색 + 상세 정보 수집 + 이미지/설명 추출을
통합 관리하는 핵심 모듈. 병렬 처리와 체크포인트를 지원한다.
AmzPy는 검색 폴백용으로만 유지한다.
"""

import time
import random
import json
import os
import re
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote_plus

from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup
from amzpy import AmazonScraper

import config
from proxy_manager import ProxyManager
from checkpoint_manager import CheckpointManager
from image_extractor import (
    extract_product_data,
    fetch_product_page,
    extract_all_images,
    extract_description,
    extract_aplus_content,
    extract_product_specs,
)
from utils import retry_request, setup_logger, sanitize_text, check_state


class AmazonFullScraper:
    """
    아마존 US 상품 검색, 상세 정보 수집, 이미지/설명 추출을
    통합 관리하는 메인 스크래퍼 클래스.

    STEP 1(검색)은 curl_cffi 직접 요청을 우선 사용하고,
    실패 시 AmzPy로 폴백한다.
    STEP 2(상세)는 fetch_product_page + BeautifulSoup으로
    HTML에서 모든 정보를 추출한다.
    """

    def __init__(self, proxy_file=None, proxy_mgr=None):
        # type: (str, object) -> None
        """
        AmazonFullScraper를 초기화한다.

        Args:
            proxy_file: 프록시 리스트 파일 경로. None이면 config.PROXY_FILE 사용.
            proxy_mgr: 외부에서 주입할 ProxyManager 인스턴스. 주입 시 proxy_file은 무시됨.
        """
        if proxy_mgr is not None:
            self.proxy_mgr = proxy_mgr
        else:
            self.proxy_mgr = ProxyManager(proxy_file)

        self.results = []  # 수집 완료된 상품 리스트
        self.failed = []  # 실패한 ASIN 리스트
        self.processed_asins = set()  # 처리 완료 ASIN (체크포인트/중복 방지)
        self.checkpoint_mgr = CheckpointManager()
        self.logger = setup_logger("scraper")
        self.lock = threading.Lock()  # 스레드 안전용

    def _create_amzpy_scraper(self, proxy=None):
        """
        AmzPy 인스턴스를 생성한다. API 버전 호환성을 위해 단계적으로 시도.
        생성 후 세션에 USD 쿠키를 설정하여 한국 IP에서도 달러 가격을 받는다.
        검색 폴백용으로만 사용된다.

        Args:
            proxy: 프록시 딕셔너리. None이면 프록시 미사용.

        Returns:
            AmazonScraper: 생성된 스크래퍼 인스턴스.
        """
        scraper = None

        # 시도 1: 전체 파라미터
        try:
            scraper = AmazonScraper(
                country_code="com", impersonate=config.IMPERSONATE, proxies=proxy
            )
            self.logger.debug("AmzPy 생성 성공 (전체 파라미터)")
        except TypeError:
            # 시도 2: 최소 파라미터
            try:
                scraper = AmazonScraper()
                self.logger.debug("AmzPy 생성 성공 (기본 파라미터)")
            except Exception as e:
                self.logger.error("AmzPy 생성 실패: %s", e)
                raise

        # config 메서드 시도
        if scraper is not None:
            try:
                scraper.config(
                    MAX_RETRIES=config.MAX_RETRIES,
                    REQUEST_TIMEOUT=config.REQUEST_TIMEOUT,
                    DELAY_BETWEEN_REQUESTS=(config.DELAY_MIN, config.DELAY_MAX),
                )
                self.logger.debug("AmzPy config 적용 성공")
            except (AttributeError, TypeError):
                self.logger.warning("AmzPy config() 미지원, 기본 설정 사용")

        # USD 쿠키 강제 설정 시도 (한국 IP에서도 달러 가격 표시)
        usd_cookies = {
            "lc-main": "en_US",
            "i18n-prefs": "USD",
        }
        try:
            if hasattr(scraper, "session"):
                session = scraper.session
                if hasattr(session, "cookies"):
                    for key, value in usd_cookies.items():
                        session.cookies.set(key, value, domain=".amazon.com")
                    self.logger.debug("AmzPy 세션에 USD 쿠키 설정 완료")
                elif hasattr(session, "session") and hasattr(
                    session.session, "cookies"
                ):
                    for key, value in usd_cookies.items():
                        session.session.cookies.set(key, value, domain=".amazon.com")
                    self.logger.debug("AmzPy 내부 세션에 USD 쿠키 설정 완료")
        except Exception as e:
            self.logger.debug("AmzPy USD 쿠키 설정 실패 (무시): %s", e)

        return scraper

    def _parse_review_count(self, text):
        # type: (str) -> int
        """
        리뷰 수 텍스트를 정수로 변환한다.

        축약형(K, M)과 쉼표, 괄호를 처리한다.
        예: '(7.5K)' → 7500, '1,234' → 1234, '2M' → 2000000

        Args:
            text: 리뷰 수 텍스트.

        Returns:
            int: 리뷰 수. 변환 실패 시 0.
        """
        try:
            text = text.strip().strip("()")
            text = text.replace(",", "")
            upper = text.upper()
            if "K" in upper:
                num = float(upper.replace("K", ""))
                return int(num * 1000)
            elif "M" in upper:
                num = float(upper.replace("M", ""))
                return int(num * 1000000)
            else:
                match = re.search(r"[\d]+", text)
                return int(match.group()) if match else 0
        except (ValueError, AttributeError):
            return 0

    def _search_with_curl(self, query, search_url, max_pages):
        # type: (str, str, int) -> list
        """
        curl_cffi로 직접 아마존 검색 페이지를 스크래핑한다.

        USD 쿠키를 포함하여 요청하고, BeautifulSoup으로 HTML을 파싱하여
        검색 결과 상품 목록을 추출한다.

        Args:
            query: 검색 키워드.
            search_url: 카테고리 URL 직접 지정. None이면 query로 검색.
            max_pages: 최대 페이지 수.

        Returns:
            list: 상품 딕셔너리 리스트.
        """
        products = []

        # 한 키워드의 여러 페이지를 검색할 때, 동일한 세션(쿠키)을 유지해야 아마존 봇 탐지에 덜 걸립니다.
        session = None
        current_proxy = None

        def _init_session():
            s = cffi_requests.Session(impersonate=config.IMPERSONATE)
            s.headers.update(
                {
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                }
            )
            s.cookies.update(
                {
                    "lc-main": "en_US",
                    "i18n-prefs": "USD",
                    "sp-cdn": '"L5Z9:KR"',
                }
            )
            p = self.proxy_mgr.get_random()
            if p is None:
                available = self.proxy_mgr.get_available_count()
                if available == 0:
                    self.logger.warning(
                        "[프록시 소진] 검색 시 사용 가능한 프록시 없음, 30초 대기 후 프록시 리셋"
                    )
                    time.sleep(30)
                    self.proxy_mgr.reset_failed()
                    p = self.proxy_mgr.get_random()

            if p is not None:
                s.proxies = p
            return s, p

        try:
            session, current_proxy = _init_session()

            for page in range(1, max_pages + 1):
                check_state()  # 일시정지/중지 확인

                # URL 구성
                if search_url:
                    sep = "&" if "?" in search_url else "?"
                    page_url = "{}{}page={}".format(search_url, sep, page)
                else:
                    safe_query = quote_plus(query) if query else ""
                    page_url = "https://www.amazon.com/s?k={}&page={}".format(
                        safe_query, page
                    )

                def fetch_page():
                    nonlocal session, current_proxy
                    res = session.get(page_url, timeout=config.REQUEST_TIMEOUT)
                    html_text = res.text

                    # 1. 봇 디텍션 화면인지 확인 (명시적)
                    if (
                        "captcha" in html_text.lower()
                        or "api-services-support@amazon.com" in html_text
                    ):
                        self.logger.warning(
                            "  페이지 %d: CAPTCHA 차단됨. 세션 및 프록시를 교체합니다.",
                            page,
                        )
                        if current_proxy:
                            self.proxy_mgr.mark_failed(current_proxy)
                        session, current_proxy = _init_session()
                        raise Exception("CAPTCHA detected")

                    # 2. 빈 검색 결과 (Soft Block / 개 페이지 리다이렉트 등) 방지
                    if 'data-component-type="s-search-result"' not in html_text:
                        # 진짜 검색 결과가 없는 0건 화면인지 확인
                        if (
                            "Try checking your spelling" in html_text
                            or "No results for" in html_text
                        ):
                            pass  # 진짜결과 없음
                        else:
                            self.logger.warning(
                                "  페이지 %d: HTML 정상 응답이나 상품 목록 누락 (Soft Block 의심). 재시도 유발.",
                                page,
                            )
                            if current_proxy:
                                self.proxy_mgr.mark_failed(current_proxy)
                            session, current_proxy = _init_session()
                            raise Exception("Empty items container detected")

                    return html_text

                # retry_request로 감싸서 요청
                html = retry_request(
                    fetch_page,
                    max_retries=config.MAX_RETRIES,
                    backoff=config.RETRY_BACKOFF,
                    logger=self.logger,
                )

                if html is None:
                    self.logger.warning("  페이지 %d 로드 실패, 검색 중단", page)
                    break

                # BeautifulSoup으로 파싱
                soup = BeautifulSoup(html, "lxml")

                # 상품 컨테이너 찾기
                items = soup.select('[data-component-type="s-search-result"]')
                if not items:
                    self.logger.info(
                        "  페이지 %d: 상품 없음 (마지막 페이지이거나 봇 화면)", page
                    )
                    break

                page_count = 0
                for item in items:
                    try:
                        # ASIN
                        asin = item.get("data-asin", "")
                        if not asin:
                            continue

                        # 제목 (다중 선택자 순서대로 시도)
                        title = ""
                        title_selectors = [
                            "h2 a span",
                            "h2 span",
                            "h2",
                            ".a-text-normal",
                        ]
                        for sel in title_selectors:
                            title_tag = item.select_one(sel)
                            if title_tag:
                                title = title_tag.get_text(strip=True)
                                if title:
                                    break

                        # 제목이 없으면 건너뛰기
                        if not title:
                            continue

                        # 가격 (다중 선택자 순서대로 시도)
                        price = ""
                        price_selectors = [
                            "span.a-price span.a-offscreen",
                            ".a-price .a-offscreen",
                        ]
                        for sel in price_selectors:
                            price_tag = item.select_one(sel)
                            if price_tag:
                                price = (
                                    price_tag.get_text(strip=True)
                                    .replace("$", "")
                                    .replace(",", "")
                                )
                                if price:
                                    break

                        # 폴백: a-price-whole + a-price-fraction
                        if not price:
                            price_whole = item.select_one("span.a-price-whole")
                            if price_whole:
                                price_text = (
                                    price_whole.get_text(strip=True)
                                    .replace(",", "")
                                    .rstrip(".")
                                )
                                price_fraction = item.select_one(
                                    "span.a-price-fraction"
                                )
                                if price_fraction:
                                    price_text += "." + price_fraction.get_text(
                                        strip=True
                                    )
                                price = price_text

                        # 원래 가격 (할인 전)
                        original_price = ""
                        original_price_tag = item.select_one(
                            "span.a-price.a-text-price span.a-offscreen"
                        )
                        if original_price_tag:
                            original_price = original_price_tag.get_text(
                                strip=True
                            ).replace("$", "")

                        # 평점
                        rating = ""
                        rating_tag = item.select_one("span.a-icon-alt")
                        if rating_tag:
                            rating_text = rating_tag.get_text(strip=True)
                            try:
                                rating = float(rating_text.split(" ")[0])
                            except (ValueError, IndexError):
                                rating = ""

                        # 리뷰 수 (다중 선택자 순서대로 시도)
                        reviews_count = ""
                        review_selectors = [
                            "a[href*='#customerReviews'] span",
                            "span.a-size-base.s-underline-text",
                            "a.a-link-normal.s-underline-text",
                        ]
                        for selector in review_selectors:
                            tag = item.select_one(selector)
                            if tag:
                                review_text = tag.get_text(strip=True)
                                if review_text:
                                    parsed = self._parse_review_count(review_text)
                                    if parsed > 0:
                                        reviews_count = str(parsed)
                                        break

                        # 폴백: aria-label에서 추출 ("4,523 ratings" 패턴)
                        if not reviews_count:
                            all_links = item.select("a[aria-label]")
                            for link in all_links:
                                label = link.get("aria-label", "")
                                if "rating" in label.lower():
                                    match = re.search(
                                        r"([\d,]+)\s*rating", label, re.IGNORECASE
                                    )
                                    if match:
                                        parsed = self._parse_review_count(
                                            match.group(1)
                                        )
                                        if parsed > 0:
                                            reviews_count = str(parsed)
                                            break

                        # 이미지
                        img_url = ""
                        img_tag = item.select_one("img.s-image")
                        if img_tag:
                            img_url = img_tag.get("src", "")

                        # Prime
                        prime_tag = item.select_one("i.a-icon-prime")
                        prime = True if prime_tag else False

                        # 배지
                        badge = ""
                        badge_tag = item.select_one("span.a-badge-text")
                        if badge_tag:
                            badge = badge_tag.get_text(strip=True)

                        product = {
                            "asin": asin,
                            "title": title,
                            "price": price,
                            "currency": "$",
                            "original_price": original_price,
                            "discount_percent": "",
                            "rating": rating,
                            "reviews_count": reviews_count,
                            "brand": "",
                            "prime": prime,
                            "delivery_info": "",
                            "badge": badge,
                            "img_url": img_url,
                        }
                        products.append(product)
                        page_count += 1

                    except Exception as e:
                        self.logger.debug("  상품 파싱 오류: %s", e)
                        continue

                self.logger.info(
                    "  페이지 %d/%d: %d개 상품", page, max_pages, page_count
                )

                # 랜덤 딜레이
                time.sleep(random.uniform(config.DELAY_MIN, config.DELAY_MAX))

        except Exception as e:
            self.logger.error("[검색 오류] %s", e)

        return products

    def _extract_detail_from_html(self, html):
        # type: (str) -> tuple
        """
        상품 상세 페이지 HTML에서 제목, 브랜드, 평점, 리뷰 수를 추출한다.

        Args:
            html: 아마존 상품 상세 페이지 HTML 문자열.

        Returns:
            tuple: (detail_title, detail_brand, detail_rating, detail_reviews).
                   추출 실패 시 빈 문자열이 포함된 튜플.
        """
        try:
            soup = BeautifulSoup(html, "lxml")

            # 제목
            title_tag = soup.select_one("#productTitle")
            detail_title = title_tag.get_text(strip=True) if title_tag else ""

            # 브랜드
            detail_brand = ""
            brand_tag = soup.select_one("#bylineInfo")
            if brand_tag:
                brand_text = brand_tag.get_text(strip=True)
                # "Visit the PETLIBRO Store" → "PETLIBRO"
                if "Visit the" in brand_text:
                    detail_brand = (
                        brand_text.replace("Visit the", "").replace("Store", "").strip()
                    )
                # "Brand: PETLIBRO" → "PETLIBRO"
                elif "Brand:" in brand_text:
                    detail_brand = brand_text.replace("Brand:", "").strip()
                else:
                    detail_brand = brand_text

            # 평점
            detail_rating = ""
            rating_tag = soup.select_one("#acrPopover")
            if rating_tag:
                rating_text = rating_tag.get("title", "")
                # "4.6 out of 5 stars" → 4.6
                try:
                    detail_rating = float(rating_text.split(" ")[0])
                except (ValueError, IndexError):
                    detail_rating = ""

            # 리뷰 수 추출
            detail_reviews = ""
            avg_text = ""

            # 방법 1: #averageCustomerReviews 전체 텍스트에서 괄호 안 숫자 추출
            avg_div = soup.select_one("#averageCustomerReviews")
            if avg_div:
                avg_text = avg_div.get_text(strip=True)
                # "(71,774)" 형태에서 숫자 추출
                match = re.search(r"\(([\d,]+)\)", avg_text)
                if match:
                    detail_reviews = match.group(1).replace(",", "")

            # 방법 2: 폴백 - customerReviews 링크에서 추출
            if not detail_reviews:
                review_link = soup.select_one('a[href*="customerReviews"]')
                if review_link:
                    link_text = review_link.get_text(strip=True)
                    match = re.search(r"([\d,]+)", link_text)
                    if match:
                        detail_reviews = match.group(1).replace(",", "")

            # 방법 3: 폴백 - "X ratings" 패턴 추출
            if not detail_reviews and avg_text:
                match = re.search(
                    r"([\d,]+)\s*(?:ratings|reviews|global ratings)", avg_text
                )
                if match:
                    detail_reviews = match.group(1).replace(",", "")

            return (detail_title, detail_brand, detail_rating, detail_reviews)

        except Exception:
            return ("", "", "", "")

    def _is_valid_product_page(self, html):
        # type: (str) -> bool
        """
        상품 페이지 HTML이 유효한지 검증한다.

        CAPTCHA, 봇 차단, 불완전한 HTML을 감지한다.

        Args:
            html: 아마존 상품 페이지 HTML 문자열.

        Returns:
            bool: 유효하면 True, 무효하면 False.
        """
        if not html:
            return False
        if len(html) < 10000:
            return False
        if "captcha" in html.lower():
            return False
        if "robot" in html.lower() and "productTitle" not in html:
            return False
        if "productTitle" not in html and "dp-container" not in html:
            return False
        return True

    def search_category(self, query=None, search_url=None, max_pages=None):
        # type: (str, str, int) -> list
        """
        카테고리 검색으로 상품 목록을 수집한다.

        curl_cffi 직접 검색을 우선 사용하고,
        결과가 없으면 AmzPy로 폴백 시도한다.

        Args:
            query: 검색 키워드. None이면 search_url 사용.
            search_url: 카테고리 URL 직접 지정. None이면 query 사용.
            max_pages: 최대 검색 페이지 수. None이면 config.MAX_PAGES 사용.

        Returns:
            list: 검색된 상품 딕셔너리 리스트.
        """
        if max_pages is None:
            max_pages = config.MAX_PAGES

        self.logger.info("")
        self.logger.info("[STEP 1] 카테고리 검색 시작")
        self.logger.info("  키워드: %s", query)
        self.logger.info("  최대 페이지: %s", max_pages)
        self.logger.info("")

        # 방법 1: curl_cffi 직접 검색 (우선)
        products = self._search_with_curl(query, search_url, max_pages)

        # 방법 2: AmzPy 폴백 (curl_cffi 실패 시)
        if not products:
            self.logger.info("[STEP 1] curl_cffi 검색 실패, AmzPy로 폴백 시도...")
            try:
                proxy = self.proxy_mgr.get_random()
                if proxy is None:
                    available = self.proxy_mgr.get_available_count()
                    if available == 0:
                        self.logger.warning(
                            "[프록시 소진] 폴백 검색 시 사용 가능한 프록시 없음, 30초 대기 후 프록시 리셋"
                        )
                        time.sleep(30)
                        self.proxy_mgr.reset_failed()
                        proxy = self.proxy_mgr.get_random()

                scraper = self._create_amzpy_scraper(proxy)

                if search_url:
                    products = retry_request(
                        lambda: scraper.search_products(
                            search_url=search_url, max_pages=max_pages
                        ),
                        max_retries=config.MAX_RETRIES,
                        backoff=config.RETRY_BACKOFF,
                        logger=self.logger,
                    )
                else:
                    products = retry_request(
                        lambda: scraper.search_products(
                            query=query, max_pages=max_pages
                        ),
                        max_retries=config.MAX_RETRIES,
                        backoff=config.RETRY_BACKOFF,
                        logger=self.logger,
                    )

                if products is None:
                    products = []

            except Exception as e:
                self.logger.error("[STEP 1] AmzPy 폴백도 실패: %s", e)
                products = []

        self.logger.info("[STEP 1 완료] 검색 결과: %d개 상품 발견", len(products))

        return products

    def enrich_product(self, product):
        # type: (dict) -> dict or None
        """
        단일 상품의 상세 정보 + 이미지 + 설명을 수집한다.

        fetch_product_page로 HTML을 가져오고, 유효성 검증 후 실패 시
        최대 3회 재시도한다. 이미지 추출 실패 시 검색 썸네일로 폴백한다.
        병렬 처리 시 여러 스레드에서 동시 호출될 수 있다.

        Args:
            product: 검색 결과에서 가져온 상품 기본 정보 딕셔너리.

        Returns:
            dict: 병합된 상품 데이터. 실패 시 None.
        """
        try:
            asin = product.get("asin")

            # ASIN이 없으면 처리 불가
            if not asin:
                return None

            # 이미 처리된 ASIN이면 건너뛰기
            with self.lock:
                if asin in self.processed_asins:
                    return None

            # HTML 가져오기 (최대 3회 재시도)
            html = None
            used_proxy = None
            for attempt in range(3):
                check_state()  # 일시정지/중지 확인

                used_proxy = self.proxy_mgr.get_random()
                # 사용 가능한 프록시가 없으면 대기 후 재시도
                if used_proxy is None:
                    available = self.proxy_mgr.get_available_count()
                    if available == 0:
                        self.logger.warning(
                            "[프록시 소진] %s: 사용 가능한 프록시 없음, 30초 대기 후 프록시 리셋",
                            asin,
                        )
                        time.sleep(30)
                        self.proxy_mgr.reset_failed()
                        used_proxy = self.proxy_mgr.get_random()
                        if used_proxy is None:
                            self.logger.error(
                                "[프록시 소진] %s: 리셋 후에도 프록시 없음, 건너뜀",
                                asin,
                            )
                            return None

                html = fetch_product_page(asin, proxy=used_proxy)
                if self._is_valid_product_page(html):
                    break
                else:
                    self.logger.warning(
                        "[HTML 재시도] %s: 시도 %d/3 실패", asin, attempt + 1
                    )
                    if used_proxy:
                        self.proxy_mgr.mark_failed(used_proxy)
                    html = None
                    if attempt < 2:
                        time.sleep(random.uniform(2, 4))

            if html:
                images = extract_all_images(html)
                description = extract_description(html)
                aplus_content = extract_aplus_content(html)
                specs_html = extract_product_specs(html)

                # 추출한 데이터를 description HTML 하단에 병합
                combined_desc = description
                if specs_html:
                    combined_desc += "<br><h3>Product Specifications</h3><br>{}".format(
                        specs_html
                    )

                # A+ Content는 본문 결합을 생략함 (사용자 요청)
                description = combined_desc

                detail_title, detail_brand, detail_rating, detail_reviews = (
                    self._extract_detail_from_html(html)
                )
            else:
                images = []
                description = ""
                aplus_content = ""
                specs_html = ""
                detail_title = ""
                detail_brand = ""
                detail_rating = ""
                detail_reviews = ""

            # 이미지 폴백: 검색 썸네일을 고해상도로 변환하여 사용
            if not images and product.get("img_url"):
                search_img = product["img_url"]
                high_res = re.sub(r"\._[A-Z]{2}_.*?\.", ".", search_img)
                images = [high_res]
                self.logger.info("[이미지 폴백] %s: 검색 썸네일 사용 (1장)", asin)

            # 랜덤 딜레이 (봇 감지 방지)
            time.sleep(random.uniform(config.DELAY_MIN, config.DELAY_MAX))

            # 데이터 병합
            merged = {
                "asin": asin,
                "title": sanitize_text(product.get("title", "")),
                "price": product.get("price", ""),
                "currency": product.get("currency", "$"),
                "original_price": product.get("original_price", ""),
                "discount_percent": product.get("discount_percent", ""),
                "rating": product.get("rating", ""),
                "reviews_count": (
                    detail_reviews
                    if detail_reviews
                    else product.get("reviews_count", "")
                ),
                "brand": product.get("brand", ""),
                "prime": product.get("prime", False),
                "delivery_info": product.get("delivery_info", ""),
                "badge": product.get("badge", ""),
                "detail_title": (
                    detail_title
                    if detail_title
                    else sanitize_text(product.get("title", ""))
                ),
                "detail_brand": detail_brand,
                "detail_rating": detail_rating,
                "description": description,
                "aplus_html": aplus_content,
                "specs_html": specs_html,
                "main_image": (images[0] if images else product.get("img_url", "")),
                "all_images": images,
                "image_count": len(images),
                "url": "https://www.amazon.com/dp/{}".format(asin),
                "scraped_at": datetime.now().isoformat(),
            }

            return merged

        except Exception as e:
            self.logger.error("[처리 오류] %s: %s", product.get("asin", "?"), e)
            return None

    def enrich_all(self, products, limit=None):
        # type: (list, int) -> None
        """
        전체 상품 목록에 대해 상세 수집을 실행한다.

        config.MAX_WORKERS에 따라 병렬 또는 직렬로 처리하며,
        체크포인트 저장/복원을 지원한다.

        Args:
            products: 검색 결과 상품 리스트.
            limit: 상세 수집 상한. None이면 전체, 숫자면 상위 N개만.
        """
        # limit 적용
        target = products[:limit] if limit else products

        # 체크포인트 복원 시도
        checkpoint = self.checkpoint_mgr.load_latest(config.CATEGORY_KEYWORD)
        if checkpoint is not None:
            restored_results, restored_asins = checkpoint
            self.results = restored_results
            self.processed_asins = restored_asins

        # 이미 처리된 ASIN 필터링
        target = [p for p in target if p.get("asin") not in self.processed_asins]
        total = len(target)

        self.logger.info("")
        self.logger.info("[STEP 2] 상세 정보 + 이미지 수집 시작 (%d개)", total)
        self.logger.info("")

        if total == 0:
            self.logger.info("이미 모든 상품이 처리됨")
            return

        # 사용 가능한 프록시 수에 맞춰 워커 수 조정
        available = self.proxy_mgr.get_available_count()
        workers = min(config.MAX_WORKERS, max(available, 1))
        if workers != config.MAX_WORKERS:
            self.logger.info(
                "[워커 조정] %d → %d (사용 가능 프록시: %d)",
                config.MAX_WORKERS,
                workers,
                available,
            )

        if workers > 1:
            # ── 병렬 처리 ──
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(self.enrich_product, p): p for p in target}

                completed = 0
                for future in as_completed(futures):
                    # 중지 요청 시 미완료 future 취소
                    try:
                        check_state()
                    except RuntimeError:
                        for f in futures:
                            f.cancel()
                        raise
                    completed += 1

                    try:
                        result = future.result()
                    except Exception as e:
                        product = futures[future]
                        self.logger.error(
                            "[처리 오류] %s: %s", product.get("asin", "?"), e
                        )
                        with self.lock:
                            self.failed.append(product.get("asin", "?"))
                        continue

                    if result is not None:
                        with self.lock:
                            self.results.append(result)
                            self.processed_asins.add(result["asin"])
                            self.logger.info(
                                "  [%d/%d] %s ✓ (이미지 %d장)",
                                completed,
                                total,
                                result["asin"],
                                result["image_count"],
                            )
                    else:
                        product = futures[future]
                        with self.lock:
                            asin = product.get("asin", "?")
                            if asin not in self.processed_asins:
                                self.failed.append(asin)
                                self.logger.info(
                                    "  [%d/%d] %s ✗ 실패", completed, total, asin
                                )

                    # 진행률 표시 (50개마다)
                    if completed % 50 == 0:
                        pct = (completed / total) * 100
                        self.logger.info(
                            "  --- 진행률: %.1f%% (%d/%d) ---", pct, completed, total
                        )

                    # 체크포인트 저장
                    if self.checkpoint_mgr.should_save(completed):
                        with self.lock:
                            self.checkpoint_mgr.save(
                                self.results,
                                self.processed_asins,
                                config.CATEGORY_KEYWORD,
                            )

        else:
            # ── 직렬 처리 (MAX_WORKERS == 1) ──
            for i, product in enumerate(target, 1):
                check_state()  # 일시정지/중지 확인
                asin = product.get("asin", "?")
                self.logger.info("  [%d/%d] %s 처리 중...", i, total, asin)

                result = self.enrich_product(product)

                if result is not None:
                    self.results.append(result)
                    self.processed_asins.add(result["asin"])
                    self.logger.info("    ✓ 완료 (이미지 %d장)", result["image_count"])
                else:
                    if asin not in self.processed_asins:
                        self.failed.append(asin)
                        self.logger.info("    ✗ 실패")

                # 진행률 표시 (50개마다)
                if i % 50 == 0:
                    pct = (i / total) * 100
                    self.logger.info("  --- 진행률: %.1f%% (%d/%d) ---", pct, i, total)

                # 체크포인트 저장
                if self.checkpoint_mgr.should_save(i):
                    self.checkpoint_mgr.save(
                        self.results, self.processed_asins, config.CATEGORY_KEYWORD
                    )

        self.logger.info(
            "[STEP 2 완료] 성공: %d개 / 실패: %d개", len(self.results), len(self.failed)
        )

    def export_json(self, filename=None):
        # type: (str) -> None
        """
        수집 결과를 JSON 파일로 저장한다.

        Args:
            filename: 저장 파일 경로. None이면
                      config.OUTPUT_DIR/config.JSON_FILENAME 사용.
        """
        if filename is None:
            filename = os.path.join(config.OUTPUT_DIR, config.JSON_FILENAME)

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)

        self.logger.info("  ✓ %s 저장 완료 (%d개 상품)", filename, len(self.results))

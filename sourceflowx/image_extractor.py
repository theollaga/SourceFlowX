"""
SourceFlowX - 이미지 + 설명 통합 추출 모듈
아마존 상품 상세 페이지 HTML에서 이미지 URL과 상품 설명을
한 번의 HTTP 요청으로 모두 추출한다.
"""

import re
import json

from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup

import config
from utils import retry_request, clean_html_body, setup_logger

# 파일 레벨 로거
logger = setup_logger("extractor")


def fetch_product_page(asin, proxy=None, impersonate=None):
    # type: (str, dict, str) -> str or None
    """
    curl_cffi를 사용하여 아마존 상품 상세 페이지 HTML을 가져온다.

    retry_request로 감싸서 실패 시 자동으로 재시도한다.
    USD 통화 강제 쿠키를 설정하여 한국 IP에서도 달러 가격을 받는다.

    Args:
        asin: 아마존 상품 ASIN.
        proxy: 프록시 딕셔너리 {"http": url, "https": url}. None이면 프록시 미사용.
        impersonate: curl_cffi TLS 핑거프린트. None이면 config.IMPERSONATE 사용.

    Returns:
        str: 상품 페이지 HTML 문자열. 실패 시 None.
    """
    if impersonate is None:
        impersonate = config.IMPERSONATE

    page_url = "https://www.amazon.com/dp/{}".format(asin)

    headers = {
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    # USD 통화 강제 쿠키 (한국 IP에서도 달러 가격 표시)
    cookies = {
        "lc-main": "en_US",
        "i18n-prefs": "USD",
        "sp-cdn": '"L5Z9:KR"',
    }

    kwargs = {
        "impersonate": impersonate,
        "headers": headers,
        "cookies": cookies,
        "timeout": config.REQUEST_TIMEOUT,
    }

    if proxy is not None:
        kwargs["proxies"] = proxy

    html = retry_request(
        lambda: cffi_requests.get(page_url, **kwargs).text,
        max_retries=config.MAX_RETRIES,
        backoff=config.RETRY_BACKOFF,
        logger=logger,
    )

    if html is None:
        logger.error("[추출] 페이지 로드 실패: %s", asin)
        return None

    return html


def extract_all_images(html):
    # type: (str) -> list
    """
    HTML 문자열에서 전체 이미지 URL을 추출한다.

    세 가지 방법을 단계적으로 시도한다:
    1. colorImages/imageGalleryData JSON에서 고해상도 이미지 추출 (다중 패턴)
    2. JSON 키 직접 추출 + HTML 전체 정규식 추출 (폴백)
    3. 최종 폴백: 전체 HTML에서 .jpg URL 직접 추출

    Args:
        html: 아마존 상품 페이지 HTML 문자열.

    Returns:
        list: 이미지 URL 리스트. 첫 번째가 메인 이미지. 없으면 빈 리스트.
    """
    if not html:
        return []

    # 방법 1: JSON 데이터에서 추출 (다중 패턴, 우선순위 높음)
    json_patterns = [
        r"'colorImages'.*?'initial'\s*:\s*(\[.*?\])",
        r'"colorImages".*?"initial"\s*:\s*(\[.*?\])',
        r'"imageGalleryData"\s*:\s*(\[.*?\])',
        r"'initial'\s*:\s*(\[\s*\{.*?\"hiRes\".*?\}\s*\])",
    ]

    for pattern in json_patterns:
        try:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                images = []
                items = json.loads(match.group(1))
                for item in items:
                    # hiRes 우선, 없으면 large 사용
                    img_url = item.get("hiRes") or item.get("large")
                    if img_url is not None:
                        images.append(img_url)

                if images:
                    return images

        except (json.JSONDecodeError, Exception):
            continue

    # 방법 2 (폴백): HTML 전체에서 아마존 이미지 URL 정규식 추출
    try:
        seen = set()
        images = []

        # 패턴 E: JSON 내 hiRes 키에서 직접 URL 추출
        hires_urls = re.findall(
            r'"hiRes"\s*:\s*"(https://m\.media-amazon\.com/images/I/[^"]+)"', html
        )
        for img_url in hires_urls:
            clean_url = re.sub(r"\._[^.]+_\.", ".", img_url)
            if not clean_url.endswith(".gif") and clean_url not in seen:
                seen.add(clean_url)
                images.append(clean_url)

        # 패턴 F: JSON 내 large 키에서 직접 URL 추출
        large_urls = re.findall(
            r'"large"\s*:\s*"(https://m\.media-amazon\.com/images/I/[^"]+)"', html
        )
        for img_url in large_urls:
            clean_url = re.sub(r"\._[^.]+_\.", ".", img_url)
            if not clean_url.endswith(".gif") and clean_url not in seen:
                seen.add(clean_url)
                images.append(clean_url)

        # 기존 폴백: HTML 전체에서 이미지 URL 추출
        raw_urls = re.findall(r'"(https://m\.media-amazon\.com/images/I/[^"]+)"', html)
        for img_url in raw_urls:
            clean_url = re.sub(r"\._[^.]+_\.", ".", img_url)
            if clean_url.endswith(".gif"):
                continue
            if clean_url not in seen:
                seen.add(clean_url)
                images.append(clean_url)

        if images:
            return images

    except Exception:
        pass

    # 방법 3 (최종 폴백): 전체 HTML에서 .jpg URL 직접 추출
    try:
        raw_jpg_urls = re.findall(
            r"https://m\.media-amazon\.com/images/I/[A-Za-z0-9._%-]+\.jpg", html
        )

        seen = set()
        images = []
        for img_url in raw_jpg_urls:
            clean_url = re.sub(r"\._[^.]+_\.", ".", img_url)
            if clean_url not in seen:
                seen.add(clean_url)
                images.append(clean_url)

        return images

    except Exception:
        return []


def extract_description(html):
    # type: (str) -> str
    """
    HTML에서 상품 설명(불렛 포인트 + 상세 설명)을 추출하여 HTML 문자열로 반환한다.

    About this item 섹션의 불렛 포인트와
    productDescription 섹션의 상세 설명을 조합한다.

    Args:
        html: 아마존 상품 페이지 HTML 문자열.

    Returns:
        str: HTML 형식의 상품 설명. 없으면 빈 문자열.
    """
    if not html:
        return ""

    try:
        soup = BeautifulSoup(html, "lxml")

        # 불렛 포인트 추출 (About this item)
        bullets = []
        feature_div = soup.select_one("#feature-bullets")
        if feature_div:
            for li_span in feature_div.select("li span.a-list-item"):
                text = li_span.get_text(strip=True)
                if text and len(text) > 5:
                    bullets.append(text)

        # 상품 설명 추출
        desc = ""
        desc_div = soup.select_one("#productDescription")
        if desc_div:
            desc = desc_div.get_text(strip=True)

        # HTML 조합
        html_body = ""

        if bullets:
            html_body += "<ul>"
            for bullet in bullets:
                html_body += "<li>{}</li>".format(bullet)
            html_body += "</ul>"

        if desc:
            html_body += "<p>{}</p>".format(desc)

        return clean_html_body(html_body)

    except Exception:
        return ""


def extract_product_data(asin, proxy=None):
    # type: (str, dict) -> dict
    """
    상품 페이지를 1회만 요청하여 이미지와 설명을 모두 추출하는 메인 함수.

    fetch_product_page → extract_all_images + extract_description 순서로
    호출하며, 동일 HTML에서 모든 데이터를 추출한다.

    Args:
        asin: 아마존 상품 ASIN.
        proxy: 프록시 딕셔너리. None이면 프록시 미사용.

    Returns:
        dict: 항상 딕셔너리 반환 (실패 시에도 기본값 포함).
            {
                "images": list,        # 이미지 URL 리스트
                "description": str,    # HTML 형식 상품 설명
                "image_count": int     # 이미지 개수
            }
    """
    html = fetch_product_page(asin, proxy)

    if html is None:
        logger.warning("[추출] 데이터 추출 불가 (HTML 없음): %s", asin)
        return {"images": [], "description": "", "image_count": 0}

    images = extract_all_images(html)
    description = extract_description(html)

    return {"images": images, "description": description, "image_count": len(images)}


def extract_aplus_content(html):
    # type: (str) -> str
    """
    아마존 A+ Content HTML을 추출하고 Shopify용으로 정리한다.

    #aplus 영역에서 브랜드 스토리, 캐러셀, 불필요 스크립트/스타일,
    data-/aria- 속성, 빈 태그를 제거하고 이미지 URL을 정규화하여
    깨끗한 HTML을 반환한다.

    Args:
        html: 아마존 상품 페이지 전체 HTML 문자열.

    Returns:
        str: 정리된 A+ Content HTML. 없거나 실패 시 빈 문자열.
    """
    if not html:
        return ""

    try:
        soup = BeautifulSoup(html, "lxml")
        aplus = soup.select_one(
            "#aplus, #aplus_feature_div, #aplus3p_feature_div, .aplus-v2"
        )
        if not aplus:
            return ""

        # ── 1. 불가시적 태그 및 기본 위젯 제거 ──
        for tag in aplus.select(
            "script, noscript, link, hr, .cr-widget-FocalReviews, style, input, button, form, iframe, video"
        ):
            tag.decompose()

        # 크로스셀/다른 상품 광고 모듈 전체 삭제 (썸네일 누락 후 h3 제목만 남는 현상 방지)
        for tag in aplus.select(
            ".brand-story-card-1-four-asin, .brand-story-card-quad-asin, .apm-brand-story-image-grid, [cel_widget_id*='four-asin']"
        ):
            tag.decompose()

        # ── 2. 아웃바운드 링크, 스토어 버튼, 불필요 텍스트 제거 ──
        junk_texts = [
            "previous page",
            "next page",
            "visit the store",
            "from the brand",
            "all product",
            "all products",
            "featured activities",
        ]
        for text_element in aplus.find_all(string=True):
            if text_element.strip().lower() in junk_texts:
                parent = text_element.parent
                if parent:
                    if parent.name in ["h2", "h3", "a", "button", "span"]:
                        parent.decompose()
                    elif parent.parent and parent.parent.name in ["a", "button"]:
                        parent.parent.decompose()
                    else:
                        parent.decompose()

        # 쇼피파이에 불필요한 아마존 내부 스토어 링크 등 제거 및 단순 링크 언랩
        for a_tag in aplus.find_all("a"):
            href = a_tag.get("href", "")
            if "/stores/" in href or "store_ref" in href or "/dp/" in href:
                parent = a_tag.parent
                if (
                    parent
                    and parent.name in ["p", "div"]
                    and len(parent.get_text(strip=True)) < 30
                ):
                    parent.decompose()
                else:
                    a_tag.decompose()
            else:
                a_tag.unwrap()

        # 리스트 포맷(1,2,3..)을 강제로 만들어 레이아웃을 망치는 캐러셀(슬라이드) 구조 강제 언랩(태그 껍데기만 삭제)
        for tag in aplus.select(
            ".a-carousel-container, .a-carousel-viewport, .a-carousel, .a-carousel-card, .a-carousel-row-inner, .a-carousel-col"
        ):
            tag.unwrap()
        # 기타 불필요한 리스트 태그가 캐러셀 잔재일 경우 언랩
        for tag in aplus.find_all(["ul", "ol", "li"]):
            if not tag.parent:
                continue
            tag.unwrap()

        # ── 3. 이미지 정규화 및 Lazy Load 처리, 작은 썸네일 방어 ──
        import re

        for img in aplus.find_all("img"):
            src = img.get("src", "") or ""
            data_src = img.get("data-src") or img.get("data-lazy-load") or ""

            if data_src:
                img["src"] = data_src
                src = data_src

            if "grey-pixel.gif" in src and not data_src:
                img.decompose()
                continue

            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/images/"):
                src = "https://images-na.ssl-images-amazon.com" + src

            if "amazon.com" not in src and "ssl-images-amazon" not in src:
                img.decompose()
                continue

            # 쓰레기 썸네일(250px 이하 해상도) 필터링
            match = re.search(r"_S[RXYL]([0-9]+)", src)
            if match and int(match.group(1)) < 250:
                img.decompose()
                continue

            img["src"] = src
            # 쇼피파이 형태에 맞춤: 둥근 테두리 및 그림자, 중앙 정렬
            img["style"] = (
                "max-width:100%; height:auto; display:block; margin:20px auto; border-radius:10px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);"
            )
            if not img.get("alt"):
                img["alt"] = "Product Introduction Image"

        # ── 4. 쓸데없는 속성 정리 (id, class, data-* 등) ──
        allowed_attrs = {"src", "alt", "style"}
        for tag in aplus.find_all(True):
            attrs_to_remove = []
            for attr_name in list(tag.attrs.keys()):
                if attr_name not in allowed_attrs:
                    attrs_to_remove.append(attr_name)
            for attr in attrs_to_remove:
                del tag[attr]

        # ── 5. 빈 태그들 연쇄 삭제 ──
        empty_tags = {
            "div",
            "span",
            "p",
            "li",
            "ul",
            "ol",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
        }
        changed = True
        while changed:
            changed = False
            for tag in aplus.find_all(empty_tags):
                if not tag.get_text(strip=True) and not tag.find_all(["img", "table"]):
                    tag.decompose()
                    changed = True

        # ── 6. 텍스트 컨테이너 스타일링 (예쁘게) ──
        # 쇼피파이 SEO 원칙 준수(H1은 페이지당 1개): A+ 콘텐츠 내의 H1은 H2로 강제 하향 변환
        for h1 in aplus.find_all("h1"):
            h1.name = "h2"

        for div in aplus.find_all("div"):
            if div.get_text(strip=True) and not div.find("img", recursive=False):
                div["style"] = (
                    "margin:15px 0; line-height:1.8; font-size:16px; color:#444; text-align:left; max-width:800px;"
                )

        for h in aplus.find_all(["h2", "h3", "h4"]):
            h["style"] = (
                "font-size:22px; font-weight:600; margin:30px 0 15px; color:#222; text-align:left; letter-spacing:0.5px;"
            )

        # ── 8. 최종 검증 ──
        result = str(aplus)
        if len(result) < 100:
            return ""

        # 유효 이미지 카운트 (amazon CDN 도메인만)
        valid_images = [
            img
            for img in aplus.find_all("img")
            if "media-amazon.com" in (img.get("src", "") or "")
            or "ssl-images-amazon" in (img.get("src", "") or "")
        ]
        img_count = len(valid_images)
        text_length = len(aplus.get_text(strip=True))

        # 이미지 0개이고 텍스트도 200자 미만이면 유용한 콘텐츠 없음
        if img_count == 0 and text_length < 200:
            logger.warning(
                "[A+ Content] 유효 콘텐츠 부족: 이미지 0장, 텍스트 %d자", text_length
            )
            return ""

        if img_count == 0:
            logger.warning(
                "[A+ Content] 이미지 없음 (텍스트만 존재: %d자)", text_length
            )

        logger.info(
            "[A+ Content] 추출 완료: HTML %d자, 이미지 %d장, 텍스트 %d자",
            len(result),
            img_count,
            text_length,
        )
        return result

    except Exception as e:
        logger.warning("[A+ Content] 추출 실패: %s", e)
        return ""


def extract_product_specs(html):
    # type: (str) -> str
    """
    HTML에서 제품 상세 스펙(Technical Details / Product Details)을 추출하여
    단일 HTML <table> 또는 <ul> 문자열로 반환한다.
    """
    if not html:
        return ""

    try:
        soup = BeautifulSoup(html, "lxml")
        specs_html = ""

        # 방법 1: Technical Details 테이블 (tech specs)
        tech_table = soup.select_one("#productDetails_techSpec_section_1")
        if tech_table:
            # 기본 스타일과 테두리를 추가
            for tag in tech_table.find_all(True):
                attrs_to_remove = ["class", "id", "data-a-word-break", "style"]
                for attr in attrs_to_remove:
                    if attr in tag.attrs:
                        del tag[attr]

            tech_table["style"] = (
                "width: 100%; border-collapse: collapse; margin-bottom: 20px; border: 1px solid #ddd;"
            )
            for th in tech_table.find_all("th"):
                th["style"] = (
                    "border: 1px solid #ddd; padding: 8px; background-color: #f4f4f4; text-align: left; font-weight: bold; width: 40%;"
                )
            for td in tech_table.find_all("td"):
                td["style"] = "border: 1px solid #ddd; padding: 8px; text-align: left;"

            specs_html += str(tech_table)

        # 방법 2: Product Details 불렛 리스트 (detail bullets)
        detail_bullets = soup.select_one("#detailBullets_feature_div")
        if detail_bullets and not specs_html:
            ul_tag = detail_bullets.select_one("ul")
            if ul_tag:
                # 불필요 스크립트, 스타일 태그 등 제거
                for tag in ul_tag.find_all(["script", "style"]):
                    tag.decompose()
                for tag in ul_tag.find_all(True):
                    attrs_to_remove = ["class", "id", "style", "dir"]
                    for attr in attrs_to_remove:
                        if attr in tag.attrs:
                            del tag[attr]

                ul_tag["style"] = (
                    "list-style-type: none; padding-left: 0; margin-bottom: 20px;"
                )
                for li in ul_tag.find_all("li"):
                    li["style"] = "margin-bottom: 10px; line-height: 1.5;"
                    # <span> 레이아웃 조정
                    spans = li.find_all("span", recursive=False)
                    if spans and len(spans) == 1:
                        inner_spans = spans[0].find_all("span", recursive=False)
                        if len(inner_spans) >= 2:
                            # "항목 :" 텍스트를 진하게
                            inner_spans[0][
                                "style"
                            ] = "font-weight: bold; margin-right: 5px;"

                specs_html += str(ul_tag)

        # 텍스트만 덩그러니 남는 걸 방지하기 위해 clean_html_body 호출
        return clean_html_body(specs_html)
    except Exception as e:
        logger.warning("[Product Specs] 추출 실패: %s", e)
        return ""

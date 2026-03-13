"""
Phase 1 Collector - 원본 데이터 파서
아마존 상세 페이지 HTML에서 모든 필드를 가공 없이 추출합니다.
네트워크 요청 없이 HTML 문자열만으로 동작합니다.

추출 필드:
  식별: asin, parent_asin, url
  기본: title, brand, category_breadcrumb, bsr_ranks, date_first_available
  가격: price, currency, original_price, discount_percent, coupon_text,
        deal_type, subscribe_save_price, is_prime
  이미지: main_image, all_images, image_count, has_video
  콘텐츠: bullet_points, description_text, description_html, aplus_html
  사양: specifications (dict), product_overview (dict)
  베리에이션: variations
  리뷰: rating, reviews_count, rating_distribution, answered_questions
  배송: availability, seller, fulfilled_by, is_addon, delivery_info
  구조화: schema_org, meta_tags
"""

import re
import json
import logging

from bs4 import BeautifulSoup


logger = logging.getLogger("collector.parser")


# ================================================================
# 개별 추출 함수들
# ================================================================

def extract_asin(soup, html):
    """ASIN을 추출합니다."""
    # 방법 1: input 태그
    tag = soup.find("input", {"name": "ASIN"})
    if tag and tag.get("value"):
        return tag["value"].strip()

    # 방법 2: URL에서
    match = re.search(r'/dp/([A-Z0-9]{10})', html)
    if match:
        return match.group(1)

    # 방법 3: data-asin
    tag = soup.find(attrs={"data-asin": True})
    if tag and tag["data-asin"]:
        return tag["data-asin"].strip()

    return ""


def extract_parent_asin(soup):
    """Parent ASIN (베리에이션 그룹)을 추출합니다."""
    tag = soup.find("input", {"name": "parentAsin"})
    if tag and tag.get("value"):
        return tag["value"].strip()
    return ""


def extract_title(soup):
    """제품명을 추출합니다."""
    tag = soup.select_one("#productTitle")
    if tag:
        return tag.get_text(strip=True)
    return ""


def extract_brand(soup):
    """브랜드를 추출합니다."""
    # 방법 1: bylineInfo
    tag = soup.select_one("#bylineInfo")
    if tag:
        text = tag.get_text(strip=True)
        # "Visit the Sony Store" → "Sony"
        # "Brand: Sony" → "Sony"
        for prefix in ["Visit the ", "Brand: ", "Brand:", "Visit the"]:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
        text = text.replace(" Store", "").strip()
        if text:
            return text

    # 방법 2: #brand
    tag = soup.select_one("#brand")
    if tag:
        return tag.get_text(strip=True)

    return ""


def extract_breadcrumb(soup):
    """카테고리 경로(breadcrumb)를 추출합니다."""
    # 방법 1: wayfinding breadcrumbs
    container = soup.select_one("#wayfinding-breadcrumbs_container")
    if container:
        links = container.select("a")
        crumbs = [a.get_text(strip=True) for a in links if a.get_text(strip=True)]
        if crumbs:
            return crumbs

    # 방법 2: a-breadcrumb
    container = soup.select_one(".a-breadcrumb, #nav-subnav")
    if container:
        links = container.select("a")
        crumbs = [a.get_text(strip=True) for a in links if a.get_text(strip=True)]
        if crumbs:
            return crumbs

    # 방법 3: categoryPath JavaScript에서 추출
    match = re.search(r'"categoryPath"\s*:\s*"([^"]+)"', str(soup))
    if match:
        path = match.group(1)
        return [p.strip() for p in path.split("/") if p.strip()]

    # 방법 4: nav-subnav data-category
    subnav = soup.select_one("#nav-subnav")
    if subnav:
        cat = subnav.get("data-category", "")
        if cat:
            return [cat]

    return []

def extract_bsr(soup):
    """Best Sellers Rank를 추출합니다."""
    ranks = []
    seen = set()

    # BSR 전용 패턴: "#숫자 in 카테고리명" — 카테고리명은 알파벳/공백/&/'-만 허용
    bsr_pattern = re.compile(r'#([\d,]+)\s+in\s+([A-Za-z][A-Za-z0-9 &,\'\-]+)')

    # 방법 1: Product Details 테이블들
    for table_id in ["#productDetails_detailBullets_sections1",
                      "#detailBullets_feature_div",
                      "#productDetails_db_sections"]:
        section = soup.select_one(table_id)
        if section:
            # BSR 관련 행만 추출
            for row in section.select("tr"):
                header = row.select_one("th")
                if header and "best sellers rank" in header.get_text(strip=True).lower():
                    text = row.get_text()
                    matches = bsr_pattern.findall(text)
                    for rank_str, cat in matches:
                        rank = int(rank_str.replace(",", ""))
                        cat_clean = cat.strip()
                        key = (rank, cat_clean)
                        if key not in seen:
                            seen.add(key)
                            ranks.append({"rank": rank, "category": cat_clean})

    # 방법 2: SalesRank div
    if not ranks:
        sr = soup.select_one("#SalesRank")
        if sr:
            text = sr.get_text()
            matches = bsr_pattern.findall(text)
            for rank_str, cat in matches:
                rank = int(rank_str.replace(",", ""))
                cat_clean = cat.strip()
                key = (rank, cat_clean)
                if key not in seen:
                    seen.add(key)
                    ranks.append({"rank": rank, "category": cat_clean})

    # 방법 3: Detail Bullets에서 BSR 항목
    if not ranks:
        bullets_div = soup.select_one("#detailBullets_feature_div")
        if bullets_div:
            for li in bullets_div.select("li"):
                text = li.get_text()
                if "best sellers rank" in text.lower() or "#" in text:
                    matches = bsr_pattern.findall(text)
                    for rank_str, cat in matches:
                        rank = int(rank_str.replace(",", ""))
                        cat_clean = cat.strip()
                        key = (rank, cat_clean)
                        if key not in seen:
                            seen.add(key)
                            ranks.append({"rank": rank, "category": cat_clean})

    return ranks


def extract_date_first_available(soup):
    """출시일(Date First Available)을 추출합니다."""
    # Product Details 테이블에서 찾기
    for table in soup.select("table"):
        for row in table.select("tr"):
            header = row.select_one("th")
            value = row.select_one("td")
            if header and value:
                if "date first available" in header.get_text(strip=True).lower():
                    return value.get_text(strip=True)

    # Detail Bullets에서 찾기
    bullets_div = soup.select_one("#detailBullets_feature_div")
    if bullets_div:
        for li in bullets_div.select("li"):
            text = li.get_text()
            if "date first available" in text.lower():
                parts = text.split(":")
                if len(parts) >= 2:
                    return ":".join(parts[1:]).strip()

    return ""


def extract_price(soup):
    """현재 가격과 통화를 추출합니다."""
    price = 0.0
    currency = ""

    selectors = [
        "#corePriceDisplay_desktop_feature_div .a-offscreen",
        "#corePrice_desktop .a-offscreen",
        "#priceblock_ourprice",
        "#priceblock_dealprice",
        "#price_inside_buybox",
        "#newBuyBoxPrice",
        "#tp_price_block_total_price_ww .a-offscreen",
        ".a-price .a-offscreen",
        "#price .a-offscreen",
        "#buyNewSection .a-offscreen",
        ".offer-price",
        "#kindle-price",
    ]

    for sel in selectors:
        tags = soup.select(sel)
        for price_tag in tags:
            text = price_tag.get_text(strip=True)
            if not text:
                continue
            match = re.match(r'([^\d]*)([\d,]+\.?\d*)', text)
            if match:
                cur = match.group(1).strip()
                try:
                    val = float(match.group(2).replace(",", ""))
                except ValueError:
                    continue
                if val > 0:
                    return val, cur

    # 폴백: HTML 전체에서 priceAmount 찾기
    match = re.search(r'"priceAmount"\s*:\s*([\d.]+)', str(soup))
    if match:
        try:
            price = float(match.group(1))
            currency = "$"
            return price, currency
        except ValueError:
            pass

    return price, currency

def extract_original_price(soup):
    """정가(할인 전 가격)를 추출합니다."""
    selectors = [
        ".a-text-price[data-a-strike='true'] .a-offscreen",
        ".basisPrice .a-offscreen",
        "#listPrice .a-offscreen",
        "#priceblock_ourprice_lbl + .a-text-price .a-offscreen",
        ".a-price[data-a-color='secondary'] .a-offscreen",
    ]

    for sel in selectors:
        tag = soup.select_one(sel)
        if tag:
            text = tag.get_text(strip=True)
            match = re.search(r'[\d,]+\.?\d*', text)
            if match:
                try:
                    return float(match.group().replace(",", ""))
                except ValueError:
                    continue

    # 폴백: 가격 영역에서 취소선 가격 찾기
    for strike in soup.select(".a-text-price .a-offscreen"):
        text = strike.get_text(strip=True)
        match = re.search(r'[\d,]+\.?\d*', text)
        if match:
            try:
                return float(match.group().replace(",", ""))
            except ValueError:
                continue

    return 0.0


def extract_discount_percent(soup):
    """할인율을 추출합니다."""
    # 방법 1: savingsPercentage
    tag = soup.select_one(".savingsPercentage")
    if tag:
        text = tag.get_text(strip=True)
        match = re.search(r'(\d+)', text)
        if match:
            return int(match.group(1))

    # 방법 2: savingsAmount 옆의 퍼센트
    for sel in [".priceBlockSavingsString", ".saving-percentage", "#dealprice_savings .priceBlockSavingsString"]:
        tag = soup.select_one(sel)
        if tag:
            text = tag.get_text(strip=True)
            match = re.search(r'(\d+)\s*%', text)
            if match:
                return int(match.group(1))

    # 방법 3: 가격에서 직접 계산
    price_val, _ = extract_price(soup)
    orig_val = extract_original_price(soup)
    if price_val > 0 and orig_val > price_val:
        discount = int(round((1 - price_val / orig_val) * 100))
        return discount

    return 0


def extract_coupon(soup):
    """쿠폰 텍스트를 추출합니다."""
    tag = soup.select_one("#couponBadge, .couponText, #vpcButton")
    if tag:
        return tag.get_text(strip=True)
    return ""


def extract_deal_type(soup):
    """딜 타입(Lightning Deal 등)을 추출합니다."""
    # Lightning Deal
    if soup.select_one("#dealBadge, .lightning-deal-bxgy-container"):
        return "Lightning Deal"

    # Deal of the Day
    dotd = soup.select_one("#dotd-badge, .dotdBadge")
    if dotd:
        return "Deal of the Day"

    return ""


def extract_subscribe_save_price(soup):
    """Subscribe & Save 가격을 추출합니다."""
    tag = soup.select_one("#snsPrice .a-offscreen, #sns-base-price")
    if tag:
        text = tag.get_text(strip=True)
        match = re.search(r'[\d,]+\.?\d*', text)
        if match:
            return float(match.group().replace(",", ""))
    return 0.0


def extract_is_prime(soup):
    """Prime 배송 여부를 확인합니다."""
    if soup.select_one("i.a-icon-prime, .a-icon-prime"):
        return True
    if soup.select_one("#prime-tp, #primeExclusiveBadge_feature_div"):
        return True
    # HTML 텍스트에서 직접 확인
    html_str = str(soup)
    if '"isPrimeExclusive"' in html_str or '"isPrime":true' in html_str:
        return True
    return False


def extract_all_images(html):
    """
    HTML에서 모든 이미지 URL을 추출합니다. 네트워크 요청 없음.

    방법 1: colorImages/imageGalleryData JSON에서 hiRes/large 추출 (최고 품질)
    방법 2: JSON 키에서 직접 URL 추출 + 전체 HTML 정규식 (포괄)
    방법 3: 전체 HTML에서 .jpg URL 직접 추출 (최종 폴백)
    """
    if not html:
        return []

    # 방법 1: JSON 파싱
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
                    img_url = item.get("hiRes") or item.get("large")
                    if img_url is not None:
                        images.append(img_url)
                if images:
                    return images
        except (json.JSONDecodeError, Exception):
            continue

    # 방법 2: 정규식으로 hiRes/large URL 직접 추출
    try:
        seen = set()
        images = []

        hires_urls = re.findall(
            r'"hiRes"\s*:\s*"(https://m\.media-amazon\.com/images/I/[^"]+)"', html
        )
        for img_url in hires_urls:
            clean_url = re.sub(r"\._[^.]+_\.", ".", img_url)
            if not clean_url.endswith(".gif") and clean_url not in seen:
                seen.add(clean_url)
                images.append(clean_url)

        large_urls = re.findall(
            r'"large"\s*:\s*"(https://m\.media-amazon\.com/images/I/[^"]+)"', html
        )
        for img_url in large_urls:
            clean_url = re.sub(r"\._[^.]+_\.", ".", img_url)
            if not clean_url.endswith(".gif") and clean_url not in seen:
                seen.add(clean_url)
                images.append(clean_url)

        if images:
            return images
    except Exception:
        pass

    # 방법 3: 전체 HTML에서 .jpg URL
    try:
        raw_urls = re.findall(
            r"https://m\.media-amazon\.com/images/I/[A-Za-z0-9._%-]+\.jpg", html
        )
        seen = set()
        images = []
        for img_url in raw_urls:
            clean_url = re.sub(r"\._[^.]+_\.", ".", img_url)
            if clean_url not in seen:
                seen.add(clean_url)
                images.append(clean_url)
        return images
    except Exception:
        return []


def extract_has_video(soup):
    """비디오 유무를 확인합니다."""
    return soup.select_one("#videoBlock, .videoCount, #altImages .videoThumbnail") is not None


def extract_bullet_points(soup):
    """주요 특징(bullet points)을 리스트로 추출합니다."""
    bullets = []
    feature_div = soup.select_one("#feature-bullets")
    if feature_div:
        for li_span in feature_div.select("li span.a-list-item"):
            text = li_span.get_text(strip=True)
            if text and len(text) > 5:
                bullets.append(text)
    return bullets


def extract_description(soup):
    """제품 설명을 text와 html로 분리 추출합니다."""
    desc_text = ""
    desc_html = ""

    # 방법 1: productDescription
    desc_div = soup.select_one("#productDescription")
    if desc_div:
        desc_text = desc_div.get_text(strip=True)
        desc_html = str(desc_div)

    # 방법 2: productDescription_feature_div
    if not desc_text:
        desc_div = soup.select_one("#productDescription_feature_div")
        if desc_div:
            desc_text = desc_div.get_text(strip=True)
            desc_html = str(desc_div)

    # 방법 3: bookDescription
    if not desc_text:
        desc_div = soup.select_one("#bookDescription_feature_div, #bookDesc_iframe_content")
        if desc_div:
            desc_text = desc_div.get_text(strip=True)
            desc_html = str(desc_div)

    # 방법 4: feature-bullets를 description으로도 기록 (별도 bullet_points와 별개로)
    if not desc_text:
        bullets_div = soup.select_one("#feature-bullets")
        if bullets_div:
            desc_text = bullets_div.get_text(strip=True)
            desc_html = str(bullets_div)

    return desc_text, desc_html



def extract_aplus_html(soup):
    """A+ Content HTML을 원본 그대로 추출합니다."""
    selectors = [
        "#aplus",
        "#aplus_feature_div",
        "#aplus3p_feature_div",
        ".aplus-v2",
        "#aplusProductDescription",
        "#productDescription_feature_div .aplus-v2",
        "#aplus-content",
    ]
    for sel in selectors:
        aplus = soup.select_one(sel)
        if aplus and len(str(aplus)) > 100:
            return str(aplus)
    return ""


def extract_specifications(soup):
    """기술 사양을 {키: 값} 딕셔너리로 추출합니다."""
    specs = {}

    # 방법 1: techSpec 테이블
    table = soup.select_one("#productDetails_techSpec_section_1")
    if table:
        for row in table.select("tr"):
            header = row.select_one("th")
            value = row.select_one("td")
            if header and value:
                key = header.get_text(strip=True)
                val = value.get_text(strip=True)
                if key:
                    specs[key] = val

    # 방법 2: Additional Information 테이블
    table2 = soup.select_one("#productDetails_detailBullets_sections1")
    if table2:
        for row in table2.select("tr"):
            header = row.select_one("th")
            value = row.select_one("td")
            if header and value:
                key = header.get_text(strip=True)
                val = value.get_text(strip=True)
                if key and key not in specs:
                    specs[key] = val

    # 방법 3: Detail Bullets
    if not specs:
        bullets_div = soup.select_one("#detailBullets_feature_div")
        if bullets_div:
            for li in bullets_div.select("li"):
                spans = li.select("span span")
                if len(spans) >= 2:
                    key = spans[0].get_text(strip=True).rstrip(" :\u200f\u200e")
                    val = spans[1].get_text(strip=True)
                    if key:
                        specs[key] = val

    return specs


def extract_product_overview(soup):
    """Product Overview (요약 속성)을 {키: 값}으로 추출합니다."""
    overview = {}
    container = soup.select_one("#productOverview_feature_div")
    if container:
        for row in container.select("tr"):
            cols = row.select("td")
            if len(cols) >= 2:
                key = cols[0].get_text(strip=True)
                val = cols[1].get_text(strip=True)
                if key:
                    overview[key] = val
    return overview


def extract_variations(soup, html):
    """베리에이션(색상, 사이즈 등)을 추출합니다."""
    variations = {"dimensions": [], "options": []}

    # twister 영역에서 dimension 이름 추출
    twister = soup.select_one("#twister")
    if twister:
        for label in twister.select(".a-form-label"):
            dim_text = label.get_text(strip=True).rstrip(":")
            if dim_text and dim_text not in variations["dimensions"]:
                variations["dimensions"].append(dim_text)

    # twisterModel JSON에서 옵션 추출
    twister_match = re.search(
        r'jQuery\.parseJSON\(\'(.*?)\'\)', html, re.DOTALL
    )
    if twister_match:
        try:
            data = json.loads(twister_match.group(1).replace("\\'", "'"))
            if "dimensions" in data:
                for dim in data["dimensions"]:
                    if dim not in variations["dimensions"]:
                        variations["dimensions"].append(dim)
        except (json.JSONDecodeError, Exception):
            pass

    # 옵션 버튼에서 개별 옵션 추출
    for option in soup.select("#twister li[data-defaultasin]"):
        opt = {
            "asin": option.get("data-defaultasin", ""),
            "label": option.get_text(strip=True),
            "available": "swatchAvailable" in option.get("class", []),
        }
        if opt["asin"]:
            variations["options"].append(opt)

    # colorToAsin에서 추출
    color_match = re.search(r'"colorToAsin"\s*:\s*(\{.*?\})\s*[,}]', html, re.DOTALL)
    if color_match and not variations["options"]:
        try:
            color_data = json.loads(color_match.group(1))
            for color_name, info in color_data.items():
                asin_val = info.get("asin", "")
                if asin_val:
                    variations["options"].append({
                        "asin": asin_val,
                        "label": color_name,
                        "available": True,
                    })
        except (json.JSONDecodeError, Exception):
            pass

    return variations


def extract_rating(soup):
    """평균 평점을 추출합니다."""
    # 방법 1: 별점 아이콘의 alt 텍스트 (가장 정확)
    icon = soup.select_one("#acrPopover i.a-icon-star span.a-icon-alt")
    if icon:
        text = icon.get_text(strip=True)
        match = re.search(r'([\d.]+)\s+out\s+of', text)
        if match:
            return float(match.group(1))

    # 방법 2: acrPopover title 속성
    popover = soup.select_one("#acrPopover")
    if popover:
        title = popover.get("title", "")
        match = re.search(r'([\d.]+)\s+out\s+of', title)
        if match:
            return float(match.group(1))

    # 방법 3: averageStarRating
    avg = soup.select_one("#averageCustomerReviews .a-icon-alt")
    if avg:
        text = avg.get_text(strip=True)
        match = re.search(r'([\d.]+)\s+out\s+of', text)
        if match:
            return float(match.group(1))

    # 방법 4: 최후 폴백 - 아무 별점 아이콘
    for alt_tag in soup.select("i.a-icon-star span.a-icon-alt, i.a-icon-star-small span.a-icon-alt"):
        text = alt_tag.get_text(strip=True)
        match = re.search(r'([\d.]+)\s+out\s+of', text)
        if match:
            return float(match.group(1))

    return 0.0


def extract_reviews_count(soup):
    """리뷰 수를 추출합니다."""
    tag = soup.select_one("#acrCustomerReviewText")
    if tag:
        text = tag.get_text(strip=True)
        match = re.search(r'[\d,]+', text)
        if match:
            return int(match.group().replace(",", ""))
    return 0


def extract_rating_distribution(soup):
    """별점별 비율을 추출합니다."""
    dist = {}

    # 방법 1: histogram 테이블
    table = soup.select_one("#histogramTable, #cm_cr_dp_d_rating_histogram, .cr-widget-Histogram")
    if table:
        for row in table.select("tr, .a-histogram-row, a.histogram-review-count"):
            text = row.get_text()
            match = re.search(r'(\d)\s*star.*?(\d+)%', text, re.IGNORECASE)
            if match:
                dist[match.group(1)] = int(match.group(2))

    # 방법 2: 개별 histogram 행
    if not dist:
        for row in soup.select('[data-hook="rating-histogram"] .a-meter'):
            aria = row.get("aria-label", "")
            match = re.search(r'(\d+)%', aria)
            star_match = re.search(r'(\d)\s*star', row.parent.get_text() if row.parent else "")
            if match and star_match:
                dist[star_match.group(1)] = int(match.group(1))

    # 방법 3: JavaScript에서 추출
    if not dist:
        html_str = str(soup)
        match = re.search(r'"ratingDistribution"\s*:\s*(\{[^}]+\})', html_str)
        if match:
            try:
                dist = json.loads(match.group(1))
            except (json.JSONDecodeError, TypeError):
                pass

    return dist


def extract_answered_questions(soup):
    """답변된 질문 수를 추출합니다."""
    # 방법 1: askATFLink
    tag = soup.select_one("#askATFLink")
    if tag:
        text = tag.get_text(strip=True)
        match = re.search(r'([\d,]+)', text)
        if match:
            return int(match.group(1).replace(",", ""))

    # 방법 2: 다른 QA 링크들
    for sel in ["#ask-btf_feature_div a", ".askTopQandALoadMoreQuestions", "#askDPSearchSecondaryView"]:
        tag = soup.select_one(sel)
        if tag:
            text = tag.get_text(strip=True)
            match = re.search(r'([\d,]+)\s*(?:answered|questions)', text, re.IGNORECASE)
            if match:
                return int(match.group(1).replace(",", ""))

    # 방법 3: 전체에서 패턴 검색
    html_str = str(soup)
    match = re.search(r'"totalQuestions"\s*:\s*(\d+)', html_str)
    if match:
        return int(match.group(1))

    return 0


def extract_availability(soup):
    """재고 상태를 추출합니다."""
    tag = soup.select_one("#availability")
    if tag:
        return tag.get_text(strip=True)
    return ""


def extract_seller_info(soup):
    """판매자 정보를 추출합니다."""
    seller = ""
    fulfilled_by = ""

    # 방법 1: tabular buybox (가장 정확)
    buybox_container = soup.select_one("#tabular-buybox")
    if buybox_container:
        rows = buybox_container.select(".tabular-buybox-text")
        i = 0
        while i < len(rows):
            label_text = rows[i].get_text(strip=True).lower()
            if i + 1 < len(rows):
                value_text = rows[i + 1].get_text(strip=True)
                # 빈 값이나 괄호만 있는 경우 건너뛰기
                clean_value = value_text.strip("() \t\n")
                if "ships from" in label_text and clean_value:
                    fulfilled_by = clean_value
                    i += 2
                    continue
                elif "sold by" in label_text and clean_value:
                    seller = clean_value
                    i += 2
                    continue
            i += 1

    # 방법 2: merchant-info
    if not seller:
        merchant = soup.select_one("#merchant-info")
        if merchant:
            text = merchant.get_text(strip=True)
            # "Ships from and sold by Amazon.com." 같은 텍스트 정리
            clean = text.strip("() \t\n")
            if clean:
                seller = clean

    # 방법 3: SFS (Ships from / Sold by) 영역
    if not seller:
        sfs = soup.select_one("#shipsFromSoldByInsideBuyBox_feature_div")
        if sfs:
            text = sfs.get_text(strip=True).strip("() \t\n")
            if text:
                seller = text

    # fulfilled 판별
    if not fulfilled_by:
        if seller and "amazon" in seller.lower():
            fulfilled_by = "Amazon"
        else:
            full_html = str(soup)
            if "Fulfilled by Amazon" in full_html or '"isAmazonFulfilled":true' in full_html:
                fulfilled_by = "Amazon (FBA)"
            elif seller:
                fulfilled_by = "Third Party"

    return seller, fulfilled_by


def extract_is_addon(soup):
    """Add-on Item 여부를 확인합니다."""
    return soup.select_one("#addOnItem_feature_div, .addOnItem") is not None


def extract_delivery_info(soup):
    """배송 정보를 추출합니다."""
    tag = soup.select_one(
        "#mir-layout-DELIVERY_BLOCK, "
        "#deliveryBlockMessage, "
        "#delivery-block-ags-dcp-block_0"
    )
    if tag:
        return tag.get_text(strip=True)
    return ""


def extract_schema_org(soup):
    """페이지의 JSON-LD (schema.org) 데이터를 추출합니다."""
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            text = script.string
            if not text:
                continue
            data = json.loads(text)
            if isinstance(data, dict):
                if data.get("@type") == "Product":
                    return data
                # 중첩된 경우
                if "@graph" in data:
                    for item in data["@graph"]:
                        if isinstance(item, dict) and item.get("@type") == "Product":
                            return item
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("@type") == "Product":
                        return item
        except (json.JSONDecodeError, TypeError):
            continue

    # 폴백: HTML에서 직접 Product schema 찾기
    html_str = str(soup)
    match = re.search(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html_str, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            if isinstance(data, dict) and data.get("@type") == "Product":
                return data
        except (json.JSONDecodeError, TypeError):
            pass

    return {}


def extract_meta_tags(soup):
    """주요 meta 태그를 추출합니다."""
    meta = {}
    for tag in soup.select("meta[property], meta[name]"):
        key = tag.get("property") or tag.get("name")
        value = tag.get("content", "")
        if key and value:
            meta[key] = value
    return meta


# ================================================================
# 메인 파싱 함수
# ================================================================

def parse_product_page(html, marketplace_domain="www.amazon.com"):
    """
    아마존 상세 페이지 HTML에서 모든 원본 데이터를 추출합니다.
    가공/필터/계산 없이 있는 그대로 저장합니다.

    Args:
        html: 제품 페이지 HTML 문자열.
        marketplace_domain: 마켓 도메인 (URL 생성용).

    Returns:
        dict: 전체 원본 데이터. HTML이 None이면 None 반환.
    """
    if not html:
        return None

    soup = BeautifulSoup(html, "lxml")

    asin = extract_asin(soup, html)
    price, currency = extract_price(soup)
    desc_text, desc_html = extract_description(soup)
    seller, fulfilled_by = extract_seller_info(soup)
    all_images = extract_all_images(html)

    product = {
        # 식별
        "asin": asin,
        "parent_asin": extract_parent_asin(soup),
        "url": "https://{}/dp/{}".format(marketplace_domain, asin) if asin else "",

        # 기본 정보
        "title": extract_title(soup),
        "brand": extract_brand(soup),
        "category_breadcrumb": extract_breadcrumb(soup),
        "bsr_ranks": extract_bsr(soup),
        "date_first_available": extract_date_first_available(soup),

        # 가격/프로모션
        "price": price,
        "currency": currency,
        "original_price": extract_original_price(soup),
        "discount_percent": extract_discount_percent(soup),
        "coupon_text": extract_coupon(soup),
        "deal_type": extract_deal_type(soup),
        "subscribe_save_price": extract_subscribe_save_price(soup),
        "is_prime": extract_is_prime(soup),

        # 이미지
        "main_image": all_images[0] if all_images else "",
        "all_images": all_images,
        "image_count": len(all_images),
        "has_video": extract_has_video(soup),

        # 콘텐츠
        "bullet_points": extract_bullet_points(soup),
        "description_text": desc_text,
        "description_html": desc_html,
        "aplus_html": extract_aplus_html(soup),

        # 기술 사양
        "specifications": extract_specifications(soup),
        "product_overview": extract_product_overview(soup),

        # 베리에이션
        "variations": extract_variations(soup, html),

        # 평점/리뷰
        "rating": extract_rating(soup),
        "reviews_count": extract_reviews_count(soup),
        "rating_distribution": extract_rating_distribution(soup),
        "answered_questions": extract_answered_questions(soup),

        # 배송/재고
        "availability": extract_availability(soup),
        "seller": seller,
        "fulfilled_by": fulfilled_by,
        "is_addon": extract_is_addon(soup),
        "delivery_info": extract_delivery_info(soup),

        # 구조화 데이터
        "schema_org": extract_schema_org(soup),
        "meta_tags": extract_meta_tags(soup),
    }

    return product


def parse_search_results(html):
    """
    검색 결과 HTML에서 ASIN 목록과 기본 정보를 추출합니다.

    Returns:
        list[dict]: 각 항목에 asin, title, price, rating, reviews_count,
                     thumbnail, is_prime, badge 포함.
    """
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    items = soup.select('[data-component-type="s-search-result"]')
    results = []

    for item in items:
        asin = item.get("data-asin", "").strip()
        if not asin:
            continue

        # 제목
        title_tag = item.select_one("h2 a span, h2 span")
        title = title_tag.get_text(strip=True) if title_tag else ""

        # 가격
        price = 0.0
        price_tag = item.select_one(".a-price .a-offscreen")
        if price_tag:
            match = re.search(r'[\d,]+\.?\d*', price_tag.get_text(strip=True))
            if match:
                price = float(match.group().replace(",", ""))

        # 평점
        rating = 0.0
        rating_tag = item.select_one(".a-icon-star-small span.a-icon-alt, i.a-icon-star-small")
        if rating_tag:
            match = re.search(r'([\d.]+)', rating_tag.get_text(strip=True))
            if match:
                rating = float(match.group(1))

        # 리뷰 수
        reviews_count = 0
        reviews_tag = item.select_one('[data-csa-c-slot-id="alf-reviews"] span.a-size-base, .a-size-base.s-underline-text')
        if reviews_tag:
            match = re.search(r'[\d,]+', reviews_tag.get_text(strip=True))
            if match:
                reviews_count = int(match.group().replace(",", ""))

        # 썸네일
        thumb_tag = item.select_one("img.s-image")
        thumbnail = thumb_tag.get("src", "") if thumb_tag else ""

        # Prime
        is_prime = item.select_one("i.a-icon-prime") is not None

        # 배지 (Best Seller 등)
        badge = ""
        badge_tag = item.select_one(".a-badge-text")
        if badge_tag:
            badge = badge_tag.get_text(strip=True)

        results.append({
            "asin": asin,
            "title": title,
            "price": price,
            "rating": rating,
            "reviews_count": reviews_count,
            "thumbnail": thumbnail,
            "is_prime": is_prime,
            "badge": badge,
        })

    return results
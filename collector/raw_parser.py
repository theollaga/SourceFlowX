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
    tag = soup.find("input", {"name": "ASIN"})
    if tag and tag.get("value"):
        return tag["value"].strip()

    match = re.search(r'/dp/([A-Z0-9]{10})', html)
    if match:
        return match.group(1)

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
    tag = soup.select_one("#bylineInfo")
    if tag:
        text = tag.get_text(strip=True)
        for prefix in ["Visit the ", "Brand: ", "Brand:", "Visit the"]:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
        text = text.replace(" Store", "").strip()
        if text:
            return text

    tag = soup.select_one("#brand")
    if tag:
        return tag.get_text(strip=True)

    return ""


def extract_breadcrumb(soup):
    """카테고리 경로(breadcrumb)를 추출합니다."""
    # 방법 1: wayfinding breadcrumbs (가장 정확)
    container = soup.select_one("#wayfinding-breadcrumbs_container")
    if container:
        links = container.select("a")
        crumbs = [a.get_text(strip=True) for a in links if a.get_text(strip=True)]
        if crumbs:
            return crumbs

    # 방법 2: a-breadcrumb (별도 셀렉터)
    container = soup.select_one(".a-breadcrumb")
    if container:
        links = container.select("a")
        crumbs = [a.get_text(strip=True) for a in links if a.get_text(strip=True)]
        if crumbs:
            return crumbs

    # 방법 3: nav-subnav (카테고리 서브네비게이션)
    subnav = soup.select_one("#nav-subnav")
    if subnav:
        # data-category 속성만 사용 (a 태그 전부 가져오면 너무 많음)
        cat = subnav.get("data-category", "")
        if cat:
            return [cat]

    # 방법 4: categoryPath JavaScript에서 추출
    match = re.search(r'"categoryPath"\s*:\s*"([^"]+)"', str(soup))
    if match:
        path = match.group(1)
        return [p.strip() for p in path.split("/") if p.strip()]

    return []


def extract_bsr(soup):
    """Best Sellers Rank를 추출합니다."""
    ranks = []
    seen = set()

    # 개별 BSR 항목에서 추출하는 함수
    def _parse_bsr_items(container):
        """BSR 행을 개별적으로 파싱합니다."""
        # 방법 A: 각 span/a 태그에서 개별 BSR 추출
        for span in container.select("span.a-list-item, li"):
            text = span.get_text(strip=True)
            # "#44 in Electronics" 패턴만 정확히 매칭
            m = re.match(r'#([\d,]+)\s+in\s+(.+?)(?:\s*\(|$)', text)
            if m:
                rank = int(m.group(1).replace(",", ""))
                cat = m.group(2).strip()
                key = (rank, cat)
                if key not in seen:
                    seen.add(key)
                    ranks.append({"rank": rank, "category": cat})

    # 방법 1: Product Details 테이블
    for table_id in ["#productDetails_detailBullets_sections1",
                      "#productDetails_db_sections"]:
        section = soup.select_one(table_id)
        if section:
            for row in section.select("tr"):
                header = row.select_one("th")
                if header and "best sellers rank" in header.get_text(strip=True).lower():
                    td = row.select_one("td")
                    if td:
                        _parse_bsr_items(td)

    if ranks:
        return ranks

    # 방법 2: SalesRank div
    sr = soup.select_one("#SalesRank")
    if sr:
        _parse_bsr_items(sr)

    if ranks:
        return ranks

    # 방법 3: Detail Bullets
    bullets_div = soup.select_one("#detailBullets_feature_div")
    if bullets_div:
        for li in bullets_div.select("li"):
            text = li.get_text()
            if "best sellers rank" in text.lower():
                _parse_bsr_items(li)

    if ranks:
        return ranks

    # 방법 4: prodDetails 전체에서 개별 행 추출
    prod_details = soup.select_one("#prodDetails")
    if prod_details:
        for row in prod_details.select("tr"):
            header = row.select_one("th")
            if header and "best sellers rank" in header.get_text(strip=True).lower():
                td = row.select_one("td")
                if td:
                    _parse_bsr_items(td)

    if ranks:
        return ranks

    # 최종 폴백: 정규식으로 개별 BSR 행 매칭
    # "#숫자 in 카테고리명" 뒤에 괄호나 줄바꿈이 오는 패턴
    html_text = str(soup)
    bsr_pattern = re.compile(r'#([\d,]+)\s+in\s+([A-Za-z][A-Za-z0-9 &\'\-]{2,50})(?:\s*[\(<\n]|$)')
    for m in bsr_pattern.finditer(html_text):
        rank = int(m.group(1).replace(",", ""))
        cat = m.group(2).strip()
        key = (rank, cat)
        if key not in seen:
            seen.add(key)
            ranks.append({"rank": rank, "category": cat})

    return ranks


def extract_date_first_available(soup):
    """출시일(Date First Available)을 추출합니다."""
    for table in soup.select("table"):
        for row in table.select("tr"):
            header = row.select_one("th")
            value = row.select_one("td")
            if header and value:
                if "date first available" in header.get_text(strip=True).lower():
                    return value.get_text(strip=True)

    bullets_div = soup.select_one("#detailBullets_feature_div")
    if bullets_div:
        for li in bullets_div.select("li"):
            text = li.get_text()
            if "date first available" in text.lower():
                parts = text.split(":")
                if len(parts) >= 2:
                    return ":".join(parts[1:]).strip()

    return ""


def extract_price(soup, html_text=""):
    """현재 가격과 통화를 추출합니다. MAP 정책 제품도 처리."""
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

    # 폴백 1: HTML에서 priceAmount 찾기
    search_text = html_text if html_text else str(soup)
    match = re.search(r'"priceAmount"\s*:\s*([\d.]+)', search_text)
    if match:
        try:
            p = float(match.group(1))
            if p > 0:
                return p, "$"
        except ValueError:
            pass

    # 폴백 2: MAP 정책 제품 감지
    # buybox나 apex 영역에서 "add this item to your cart" 문구 확인
    search_lower = search_text.lower()
    map_signals = [
        "to see product details, add this item to your cart",
        "add to cart to see price",
        "see price in cart",
    ]
    for signal in map_signals:
        if signal in search_lower:
            return 0.0, "MAP_POLICY"

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
    tag = soup.select_one(".savingsPercentage")
    if tag:
        text = tag.get_text(strip=True)
        match = re.search(r'(\d+)', text)
        if match:
            return int(match.group(1))

    for sel in [".priceBlockSavingsString", ".saving-percentage",
                "#dealprice_savings .priceBlockSavingsString"]:
        tag = soup.select_one(sel)
        if tag:
            text = tag.get_text(strip=True)
            match = re.search(r'(\d+)\s*%', text)
            if match:
                return int(match.group(1))

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
    if soup.select_one("#dealBadge, .lightning-deal-bxgy-container"):
        return "Lightning Deal"

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


# ★ 수정됨 ─────────────────────────────────────────────────────
def extract_is_prime(soup, html_text=""):
    """Prime 배송 여부를 확인합니다. (강화 버전)"""

    # 방법 1: Prime 아이콘 (다양한 셀렉터)
    prime_selectors = [
        "i.a-icon-prime",
        ".a-icon-prime",
        "#prime-tp",
        "#primeExclusiveBadge_feature_div",
        "#deliveryBlockMessage i.a-icon-prime",
        "#mir-layout-DELIVERY_BLOCK i.a-icon-prime",
        "#fast-track-message i.a-icon-prime",
        "#bbop-sbbop-container i.a-icon-prime",
        ".delivery-message i.a-icon-prime",
        "#price-shipping-message i.a-icon-prime",
        "#qualifiedBuybox i.a-icon-prime",
        "#buyBoxAccordion i.a-icon-prime",
    ]
    for sel in prime_selectors:
        if soup.select_one(sel):
            return True

    # 방법 2: aria-label에 prime 포함
    for el in soup.select("[aria-label]"):
        label = el.get("aria-label", "").lower()
        if "prime" in label and ("free delivery" in label or "free shipping" in label):
            return True

    # 방법 3: HTML 텍스트에서 직접 확인
    if not html_text:
        html_text = str(soup)

    prime_patterns = [
        r'"isPrimeExclusive"\s*:\s*true',
        r'"isPrime"\s*:\s*true',
        r'"isPrimeEligible"\s*:\s*true',
        r'"prime"\s*:\s*true',
        r'"hasPrime"\s*:\s*true',
        r'"isAmazonFulfilled"\s*:\s*true',
    ]
    for pat in prime_patterns:
        if re.search(pat, html_text, re.IGNORECASE):
            return True

    # 방법 4: delivery 메시지에서 "FREE delivery" 확인
    delivery = soup.select_one("#mir-layout-DELIVERY_BLOCK, #deliveryBlockMessage, #delivery-block-ags-dcp-block_0")
    if delivery:
        text = delivery.get_text(strip=True).lower()
        if "free delivery" in text or "free shipping" in text:
            return True

    # 방법 5: data-feature-name="prime498"
    if soup.select_one('[data-feature-name*="prime"]'):
        return True

    return False
# ★ 수정 끝 ────────────────────────────────────────────────────


def extract_all_images(html):
    """
    HTML에서 모든 이미지 URL을 추출합니다.
    """
    if not html:
        return []

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

    desc_div = soup.select_one("#productDescription")
    if desc_div:
        desc_text = desc_div.get_text(strip=True)
        desc_html = str(desc_div)

    if not desc_text:
        desc_div = soup.select_one("#productDescription_feature_div")
        if desc_div:
            desc_text = desc_div.get_text(strip=True)
            desc_html = str(desc_div)

    if not desc_text:
        desc_div = soup.select_one("#bookDescription_feature_div, #bookDesc_iframe_content")
        if desc_div:
            desc_text = desc_div.get_text(strip=True)
            desc_html = str(desc_div)

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


# ★ 수정됨 ─────────────────────────────────────────────────────
def extract_variations(soup, html_text=""):
    """베리에이션(색상, 사이즈 등) 추출 - 강화 버전"""
    result = {"dimensions": [], "options": []}

    # === 방법 1: dimensionValuesDisplayData (가장 정확) ===
    m = re.search(r'dimensionValuesDisplayData\s*:\s*(\{.+?\})\s*[,}]', html_text)
    if m:
        try:
            dim_data = json.loads(m.group(1))
            for asin_key, labels in dim_data.items():
                if isinstance(labels, list):
                    result["options"].append({
                        "asin": asin_key,
                        "labels": labels,
                        "available": True
                    })
        except (json.JSONDecodeError, Exception):
            pass

    # dimensionsDisplay
    m = re.search(r'dimensionsDisplay\s*:\s*\[([^\]]+)\]', html_text)
    if m:
        dims = re.findall(r'"([^"]+)"', m.group(1))
        if dims:
            result["dimensions"] = dims

    # === 방법 2: variationValues ===
    if not result["dimensions"]:
        m = re.search(r'"variationValues"\s*:\s*(\{[^}]+\})', html_text)
        if m:
            try:
                var_vals = json.loads(m.group(1))
                result["dimensions"] = list(var_vals.keys())
            except (json.JSONDecodeError, Exception):
                pass

    # === 방법 3: asinVariationValues ===
    if not result["options"]:
        m = re.search(r'"asinVariationValues"\s*:\s*(\{.+?\})\s*[,}]', html_text, re.DOTALL)
        if m:
            try:
                asin_vars = json.loads(m.group(1))
                for asin_key, vals in asin_vars.items():
                    if isinstance(vals, dict):
                        result["options"].append({
                            "asin": asin_key,
                            "labels": list(vals.values()),
                            "available": True
                        })
            except (json.JSONDecodeError, Exception):
                pass

    # === 방법 4: HTML twister 셀렉터 ===
    if not result["dimensions"]:
        for row in soup.select(
            "#variation_color_name, #variation_size_name, "
            "#variation_style_name, #variation_pattern_name, "
            "#variation_item_package_quantity"
        ):
            label_el = row.select_one(".a-form-label, .a-row label")
            if label_el:
                dim_name = label_el.get_text(strip=True).rstrip(":")
                if dim_name and dim_name not in result["dimensions"]:
                    result["dimensions"].append(dim_name)

    if not result["options"]:
        for li in soup.select("#twister li[data-defaultasin], .twisterSwatchWrapper li[data-defaultasin]"):
            opt_asin = li.get("data-defaultasin", "")
            title_attr = li.get("title", "")
            label = re.sub(r'^Click to select\s*', '', title_attr).strip()
            if opt_asin:
                classes = li.get("class", [])
                available = "swatchAvailable" in classes if isinstance(classes, list) else True
                result["options"].append({
                    "asin": opt_asin,
                    "labels": [label] if label else [],
                    "available": available
                })

    # === 방법 5: colorToAsin ===
    if not result["options"]:
        color_match = re.search(r'"colorToAsin"\s*:\s*(\{.*?\})\s*[,}]', html_text, re.DOTALL)
        if color_match:
            try:
                color_data = json.loads(color_match.group(1))
                for color_name, info in color_data.items():
                    asin_val = info.get("asin", "")
                    if asin_val:
                        result["options"].append({
                            "asin": asin_val,
                            "labels": [color_name],
                            "available": True,
                        })
            except (json.JSONDecodeError, Exception):
                pass

    return result
# ★ 수정 끝 ────────────────────────────────────────────────────


def extract_rating(soup):
    """평균 평점을 추출합니다."""
    icon = soup.select_one("#acrPopover i.a-icon-star span.a-icon-alt")
    if icon:
        text = icon.get_text(strip=True)
        match = re.search(r'([\d.]+)\s+out\s+of', text)
        if match:
            return float(match.group(1))

    popover = soup.select_one("#acrPopover")
    if popover:
        title = popover.get("title", "")
        match = re.search(r'([\d.]+)\s+out\s+of', title)
        if match:
            return float(match.group(1))

    avg = soup.select_one("#averageCustomerReviews .a-icon-alt")
    if avg:
        text = avg.get_text(strip=True)
        match = re.search(r'([\d.]+)\s+out\s+of', text)
        if match:
            return float(match.group(1))

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


# ★ 수정됨 ─────────────────────────────────────────────────────
def extract_rating_distribution(soup, html_text=""):
    """별점 분포 추출 - 강화 버전"""
    distribution = {}

    # === 방법 1: histogram 테이블 (#histogramTable) ===
    hist_table = soup.select_one("#histogramTable, #cm_cr_dp_d_hist_table")
    if hist_table:
        for row in hist_table.select("tr"):
            star_el = row.select_one("td:first-child a, td:first-child span")
            pct_el = row.select_one("td.a-text-right a, td:nth-child(3) a, .a-size-small a")
            if star_el and pct_el:
                star_text = star_el.get_text(strip=True)
                pct_text = pct_el.get_text(strip=True)
                star_m = re.search(r'(\d)', star_text)
                pct_m = re.search(r'(\d+)', pct_text)
                if star_m and pct_m:
                    distribution["{}_star".format(star_m.group(1))] = int(pct_m.group(1))

    if distribution:
        return distribution

    # === 방법 2: aria-label 방식 ===
    for link in soup.select('[data-hook="histogram-cell"], .cr-histogram-row a'):
        aria = link.get("aria-label", "") or link.get("title", "")
        m = re.search(r'(\d)\s*star[s]?\s*represent\s*(\d+)%', aria, re.IGNORECASE)
        if m:
            distribution["{}_star".format(m.group(1))] = int(m.group(2))

    if distribution:
        return distribution

    # === 방법 3: 리뷰 섹션의 a 태그에서 퍼센트 추출 ===
    review_section = soup.select_one("#reviewsMedley, #cm_cr-review_list")
    if review_section:
        for a_tag in review_section.select("a[title]"):
            title = a_tag.get("title", "")
            # "5 stars represent 73% of rating"
            m = re.search(r'(\d)\s*star[s]?\s*represent\s*(\d+)\s*%', title, re.IGNORECASE)
            if m:
                distribution["{}_star".format(m.group(1))] = int(m.group(2))

    if distribution:
        return distribution

    # === 방법 4: JavaScript 데이터 ===
    if not html_text:
        html_text = str(soup)

    m = re.search(r'"ratingDistribution"\s*:\s*(\[.+?\])', html_text)
    if m:
        try:
            dist_list = json.loads(m.group(1))
            for item in dist_list:
                if isinstance(item, dict):
                    star = item.get("star", item.get("rating", ""))
                    pct = item.get("percentage", item.get("percent", 0))
                    if star:
                        distribution["{}_star".format(star)] = int(pct)
        except (json.JSONDecodeError, Exception):
            pass

    if distribution:
        return distribution

    # === 방법 5: histogramBinLabels / counts ===
    labels_m = re.search(r'"histogramBinLabels"\s*:\s*\[([^\]]+)\]', html_text)
    counts_m = re.search(r'"histogramBinCounts"\s*:\s*\[([^\]]+)\]', html_text)
    if labels_m and counts_m:
        labels = re.findall(r'"([^"]+)"', labels_m.group(1))
        counts = re.findall(r'(\d+)', counts_m.group(1))
        for label, count in zip(labels, counts):
            star_m = re.search(r'(\d)', label)
            if star_m:
                distribution["{}_star".format(star_m.group(1))] = int(count)

    if distribution:
        return distribution

    # === 방법 6: 페이지 텍스트에서 "N star N%" 패턴 ===
    for star_num in range(5, 0, -1):
        patterns = [
            r'{}\s*star[s]?\s*(\d+)\s*%'.format(star_num),
            r'{}\s*star[s]?\s*\n?\s*(\d+)\s*%'.format(star_num),
        ]
        for pat in patterns:
            m = re.search(pat, html_text, re.IGNORECASE)
            if m:
                distribution["{}_star".format(star_num)] = int(m.group(1))

    return distribution
# ★ 수정 끝 ────────────────────────────────────────────────────


# ★ 수정됨 ─────────────────────────────────────────────────────
def extract_answered_questions(soup, html_text=""):
    """Q&A 답변 수 추출 - 강화 버전"""

    # === 방법 1: askATFLink (가장 일반적) ===
    qa_link = soup.select_one("#askATFLink")
    if qa_link:
        text = qa_link.get_text(strip=True)
        m = re.search(r'([\d,]+)', text)
        if m:
            return int(m.group(1).replace(",", ""))

    # === 방법 2: 다양한 Q&A 셀렉터 ===
    qa_selectors = [
        "#ask_feature_div a",
        "#ask-btf_feature_div a",
        '[data-csa-c-content-id="ask-dp-see-all-questions"] a',
        'a[href*="ask/questions/asin"]',
        '.askTopQandALoadMoreQuestions a',
    ]
    for sel in qa_selectors:
        for el in soup.select(sel):
            text = el.get_text(strip=True)
            m = re.search(r'([\d,]+)\s*(?:answered|questions?)', text, re.IGNORECASE)
            if m:
                return int(m.group(1).replace(",", ""))

    # === 방법 3: 페이지 전체 텍스트에서 검색 ===
    if not html_text:
        html_text = str(soup)

    patterns = [
        r'(\d[\d,]*)\s*answered\s*questions?',
        r'See\s+all\s+(\d[\d,]*)\s+questions?',
        r'"totalQuestions"\s*:\s*(\d+)',
        r'"questionsCount"\s*:\s*(\d+)',
        r'"askATFData".*?"count"\s*:\s*(\d+)',
    ]
    for pat in patterns:
        m = re.search(pat, html_text, re.IGNORECASE)
        if m:
            val = m.group(1).replace(",", "")
            return int(val)

    # === 방법 4: 텍스트 노드 검색 ===
    for el in soup.find_all(string=re.compile(r'\d+\s+answered', re.IGNORECASE)):
        m = re.search(r'(\d[\d,]*)\s*answered', el, re.IGNORECASE)
        if m:
            return int(m.group(1).replace(",", ""))

    return 0
# ★ 수정 끝 ────────────────────────────────────────────────────


def extract_availability(soup, html_text=""):
    """재고 상태를 추출합니다."""
    tag = soup.select_one("#availability")
    if tag:
        avail_text = tag.get_text(strip=True)
        if avail_text:
            return avail_text

    # buybox에서 재고 상태 추출
    buybox = soup.select_one("#buybox, #apex_desktop")
    if buybox:
        text = buybox.get_text(strip=True).lower()
        if "add this item to your cart" in text or "see price in cart" in text:
            return "In Stock (MAP Policy - price hidden until cart)"
        if "currently unavailable" in text:
            return "Currently unavailable"

    return ""


# ★ 수정됨 ─────────────────────────────────────────────────────
def extract_seller_info(soup, html_text=""):
    """판매자 정보 추출 - 강화 버전 (2025+ 신규 레이아웃 대응)"""
    seller = ""
    fulfilled_by = ""

    # === 방법 1: 신규 레이아웃 (offer-display-feature) ===
    # Sold by
    sold_by_div = soup.select_one(
        '.offer-display-feature-text[offer-display-feature-name="desktop-merchant-info"]'
    )
    if sold_by_div:
        a_tag = sold_by_div.select_one("a")
        if a_tag:
            seller = a_tag.get_text(strip=True)
        else:
            # a 태그 없으면 첫 번째 의미 있는 텍스트
            for span in sold_by_div.select("span"):
                t = span.get_text(strip=True)
                if t and t.lower() != "sold by":
                    seller = t
                    break

    # Ships from
    ships_from_div = soup.select_one(
        '.offer-display-feature-text[offer-display-feature-name="desktop-fulfiller-info"]'
    )
    if ships_from_div:
        a_tag = ships_from_div.select_one("a")
        if a_tag:
            fulfilled_by = a_tag.get_text(strip=True)
        else:
            for span in ships_from_div.select("span"):
                t = span.get_text(strip=True)
                if t and t.lower() != "ships from":
                    fulfilled_by = t
                    break

    # === 방법 2: tabular-buybox (구형 레이아웃) ===
    if not seller:
        buybox = soup.select_one("#tabular-buybox")
        if buybox:
            rows = buybox.select(".tabular-buybox-text")
            i = 0
            while i < len(rows):
                label_text = rows[i].get_text(strip=True).lower()
                if i + 1 < len(rows):
                    value_el = rows[i + 1]
                    a_tag = value_el.select_one("a")
                    span_tag = value_el.select_one("span")
                    value_text = ""
                    if a_tag:
                        value_text = a_tag.get_text(strip=True)
                    elif span_tag:
                        value_text = span_tag.get_text(strip=True)
                    else:
                        value_text = value_el.get_text(strip=True)

                    clean_value = value_text.strip("() \t\n\r")
                    if "ships from" in label_text and clean_value:
                        fulfilled_by = clean_value
                        i += 2
                        continue
                    elif "sold by" in label_text and clean_value:
                        seller = clean_value
                        i += 2
                        continue
                i += 1

    # === 방법 3: merchant-info ===
    if not seller:
        merchant = soup.select_one("#merchant-info")
        if merchant:
            text = merchant.get_text(strip=True)
            m = re.search(r'sold\s+by\s+(.+?)(?:\.|$)', text, re.IGNORECASE)
            if m:
                seller = m.group(1).strip()
            elif text.strip("() \t\n\r"):
                seller = text.strip("() \t\n\r")

    # === 방법 4: merchantID hidden input ===
    if not seller:
        mid = soup.select_one("#merchantID")
        if mid and mid.get("value"):
            merchant_id = mid["value"]
            # merchantName은 JS에서 따로 확인
            if not html_text:
                html_text = str(soup)
            m = re.search(r'"merchantName"\s*:\s*"([^"]+)"', html_text)
            if m:
                seller = m.group(1)
            else:
                seller = "merchant:{}".format(merchant_id)

    # === 방법 5: HTML 텍스트에서 판매자 정보 ===
    if not seller:
        if not html_text:
            html_text = str(soup)
        m = re.search(r'"merchantName"\s*:\s*"([^"]+)"', html_text)
        if m:
            seller = m.group(1)

    # === fulfilled 판별 보완 ===
    if not fulfilled_by:
        if seller and "amazon" in seller.lower():
            fulfilled_by = "Amazon"
        else:
            check_html = html_text if html_text else str(soup)
            if '"isAmazonFulfilled":true' in check_html or "Fulfilled by Amazon" in check_html:
                fulfilled_by = "Amazon (FBA)"
            elif seller:
                fulfilled_by = "Third Party"

    return seller, fulfilled_by
# ★ 수정 끝 ────────────────────────────────────────────────────


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


# ★ 수정됨 ─────────────────────────────────────────────────────
def extract_schema_org(soup, html_text=""):
    """JSON-LD schema.org 추출 - 강화 버전"""

    # === 방법 1: <script type="application/ld+json"> ===
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            text = script.string or script.get_text()
            if not text:
                continue
            data = json.loads(text)

            if isinstance(data, dict):
                if data.get("@type") == "Product":
                    return data
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

    # === 방법 2: HTML 원본에서 이스케이프된 JSON-LD ===
    if not html_text:
        html_text = str(soup)

    pattern = r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>'
    for m in re.finditer(pattern, html_text, re.DOTALL | re.IGNORECASE):
        try:
            text = m.group(1).strip()
            text = text.replace('\\"', '"').replace("\\'", "'")
            data = json.loads(text)
            if isinstance(data, dict) and data.get("@type") == "Product":
                return data
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("@type") == "Product":
                        return item
        except (json.JSONDecodeError, TypeError):
            continue

    # === 방법 3: JS 변수에 포함된 schema ===
    m = re.search(r'"schema:product"\s*:\s*(\{.+?\})\s*[,;]', html_text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except (json.JSONDecodeError, TypeError):
            pass

    # === 방법 4: 메타 태그에서 수동 구성 (최종 폴백) ===
    product_schema = {}
    og_title = soup.select_one('meta[property="og:title"]')
    if og_title:
        product_schema["name"] = og_title.get("content", "")
    og_image = soup.select_one('meta[property="og:image"]')
    if og_image:
        product_schema["image"] = og_image.get("content", "")
    og_desc = soup.select_one('meta[name="description"]')
    if og_desc:
        product_schema["description"] = og_desc.get("content", "")

    if product_schema:
        product_schema["@type"] = "Product"
        product_schema["_note"] = "constructed_from_meta_tags"
        return product_schema

    return {}
# ★ 수정 끝 ────────────────────────────────────────────────────


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
    """
    if not html:
        return None

    soup = BeautifulSoup(html, "lxml")
    html_text = html  # 원본 HTML 텍스트 보존 (JS 데이터 파싱용)

    asin = extract_asin(soup, html_text)
    price, currency = extract_price(soup, html_text)
    desc_text, desc_html = extract_description(soup)
    seller, fulfilled_by = extract_seller_info(soup, html_text)
    all_images = extract_all_images(html_text)

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
        "is_prime": extract_is_prime(soup, html_text),

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
        "variations": extract_variations(soup, html_text),

        # 평점/리뷰
        "rating": extract_rating(soup),
        "reviews_count": extract_reviews_count(soup),
        "rating_distribution": extract_rating_distribution(soup, html_text),
        "answered_questions": extract_answered_questions(soup, html_text),

        # 배송/재고
        "availability": extract_availability(soup, html_text),
        "seller": seller,
        "fulfilled_by": fulfilled_by,
        "is_addon": extract_is_addon(soup),
        "delivery_info": extract_delivery_info(soup),

        # 구조화 데이터
        "schema_org": extract_schema_org(soup, html_text),
        "meta_tags": extract_meta_tags(soup),
    }

    return product


def parse_search_results(html):
    """
    검색 결과 HTML에서 ASIN 목록과 기본 정보를 추출합니다.
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

        title_tag = item.select_one("h2 a span, h2 span")
        title = title_tag.get_text(strip=True) if title_tag else ""

        price = 0.0
        price_tag = item.select_one(".a-price .a-offscreen")
        if price_tag:
            match = re.search(r'[\d,]+\.?\d*', price_tag.get_text(strip=True))
            if match:
                price = float(match.group().replace(",", ""))

        rating = 0.0
        rating_tag = item.select_one(".a-icon-star-small span.a-icon-alt, i.a-icon-star-small")
        if rating_tag:
            match = re.search(r'([\d.]+)', rating_tag.get_text(strip=True))
            if match:
                rating = float(match.group(1))

        reviews_count = 0
        reviews_tag = item.select_one('[data-csa-c-slot-id="alf-reviews"] span.a-size-base, .a-size-base.s-underline-text')
        if reviews_tag:
            match = re.search(r'[\d,]+', reviews_tag.get_text(strip=True))
            if match:
                reviews_count = int(match.group().replace(",", ""))

        thumb_tag = item.select_one("img.s-image")
        thumbnail = thumb_tag.get("src", "") if thumb_tag else ""

        is_prime = item.select_one("i.a-icon-prime") is not None

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

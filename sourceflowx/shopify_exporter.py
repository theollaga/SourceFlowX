# pyre-unsafe
"""
SourceFlowX - 쇼피파이 CSV 내보내기 모듈
스크래핑 결과를 쇼피파이 정식 CSV 형식으로 변환하여 저장한다.
Title/Handle/SEO 자동 생성, 가격 계산, Collection Mapping을 지원한다.
"""

import os
import csv
import re
import math

import config
from utils import parse_price, sanitize_text, clean_html_body, setup_logger
from price_adjuster import calculate_price, apply_rounding, calculate_compare_at_price

# 파일 레벨 로거
logger = setup_logger("exporter")

# 쇼피파이 공식 CSV 컬럼 리스트 (정확히 25개)
COLUMNS = [
    "Handle",
    "Title",
    "Body (HTML)",
    "Vendor",
    "Product Category",
    "Type",
    "Tags",
    "Published",
    "Option1 Name",
    "Option1 Value",
    "Variant SKU",
    "Variant Grams",
    "Variant Inventory Tracker",
    "Variant Inventory Qty",
    "Variant Inventory Policy",
    "Variant Fulfillment Service",
    "Variant Price",
    "Variant Compare At Price",
    "Variant Requires Shipping",
    "Variant Taxable",
    "Image Src",
    "Image Position",
    "Image Alt Text",
    "SEO Title",
    "SEO Description",
    "Status",
    "product.metafields.descriptors.subtitle",
]


# ================================================================
# 헬퍼 함수
# ================================================================


def generate_handle(title):
    # type: (str) -> str
    """
    Shopify Handle을 생성한다.

    소문자 변환, 특수문자 제거, 공백→하이픈, 연속 하이픈 정리.
    최대 200자.
    """
    handle = title.lower().strip()
    # === 추가: 쉼표를 공백으로 먼저 변환 ===
    handle = handle.replace(",", " ")
    handle = re.sub(r"[^a-z0-9\s\-]", "", handle)
    handle = re.sub(r"\s+", "-", handle)
    handle = re.sub(r"-+", "-", handle)
    handle = handle.strip("-")
    return handle[:200]


def clean_title(title, brand, remove_brand, max_length):
    # type: (str, str, bool, int) -> str
    """
    Shopify용 타이틀을 정리한다.

    브랜드명 제거(옵션), 괄호 안 코드/모델번호 제거,
    max_length 초과 시 단어 단위 자름, 앞뒤 정리.
    """
    cleaned = title.strip()

    # 브랜드명 제거
    if remove_brand and brand:
        # 타이틀 시작 부분 브랜드명 제거
        pattern = re.compile(r"^" + re.escape(brand) + r"[\s\-,]+", re.IGNORECASE)
        cleaned = pattern.sub("", cleaned)

        # === 추가: 타이틀 중간/끝의 브랜드명도 제거 ===
        # ", Vtopmart" / " - Cisily" / " by Vtopmart" 등
        cleaned = re.sub(
            r",?\s*" + re.escape(brand) + r"\b", "", cleaned, flags=re.IGNORECASE
        )
        cleaned = re.sub(
            r"\s*-\s*" + re.escape(brand) + r"\b", "", cleaned, flags=re.IGNORECASE
        )
        cleaned = re.sub(
            r"\s+by\s+" + re.escape(brand) + r"\b", "", cleaned, flags=re.IGNORECASE
        )

        # 연속 공백 정리
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        # 쉼표가 연속되거나 앞뒤에 남은 경우 정리
        cleaned = re.sub(r",\s*,", ",", cleaned)
        cleaned = cleaned.strip("-,").strip()

    # 괄호 안 코드/모델번호 제거
    cleaned = re.sub(r"\([^)]*\d+[^)]*\)", "", cleaned)
    cleaned = re.sub(r"\[[^\]]*\d+[^\]]*\]", "", cleaned)
    cleaned = re.sub(r"【[^】]*】", "", cleaned)

    # === 추가: 쉼표 뒤 공백 보장 ===
    cleaned = re.sub(r",([^\s])", r", \1", cleaned)

    # 연속 공백 정리
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # 앞뒤 하이픈, 쉼표 제거
    cleaned = cleaned.strip("-,").strip()

    # 길이 제한 (단어 단위)
    if len(cleaned) > max_length:
        words = cleaned[:max_length].rsplit(" ", 1)
        cleaned = words[0] if len(words) > 1 else cleaned[:max_length]
        cleaned = cleaned.strip("-,").strip()

    # === 추가: 끝 단어가 불완전하면 제거 ===
    trailing_words = {
        "with",
        "for",
        "and",
        "or",
        "the",
        "a",
        "an",
        "in",
        "on",
        "at",
        "to",
        "of",
        "by",
        "is",
        "it",
        "as",
        "up",
        "from",
        "into",
        "that",
        "this",
        "but",
        "not",
        "no",
        "so",
        "if",
        "its",
        "our",
        "your",
        "&",
    }
    # 반복적으로 끝 단어 제거 (최대 3회)
    for _ in range(3):
        words = cleaned.rsplit(" ", 1)
        if len(words) == 2:
            last_word = words[1].strip(",-").lower()
            # 전치사/접속사/관사 또는 단독 숫자로 끝나면 제거
            if last_word in trailing_words or (
                last_word.isdigit() and len(last_word) <= 2
            ):
                cleaned = words[0].strip("-,").strip()
                continue
        break

    return cleaned


def extract_first_bullet(body_html):
    # type: (str) -> str
    """
    Body HTML에서 첫 번째 불릿포인트(<li>) 또는 단락의 첫 문장을 추출한다.
    subtitle_style이 'from_description'일 때 사용된다.
    """
    if not body_html:
        return ""

    # <li> 태그 찾기
    li_match = re.search(r"<li>(.*?)</li>", body_html, re.IGNORECASE | re.DOTALL)
    if li_match:
        text = li_match.group(1)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            # 첫 문장만 추출 (마침표 기준)
            parts = text.split(". ")
            return parts[0] + "." if len(parts) > 1 else text

    # 없으면 그냥 정규식으로 태그 날리고 첫 문장 추출
    text = re.sub(r"<[^>]+>", " ", body_html)
    text = re.sub(r"\s+", " ", text).strip()
    if text:
        parts = text.split(". ")
        return parts[0] + "." if len(parts) > 1 else text

    return ""


def generate_seo_title(
    cleaned_title, store_name, separator, max_length=60, benefit_feature=""
):
    # type: (str, str, str, int, str) -> str
    """
    SEO Title을 생성한다.

    형식: "{Cleaned Title} {separator} {Store Name}"
    max_length 초과 시 Cleaned Title을 단어 단위로 축소.
    benefit_feature가 있으면 제목 뒤에 em dash로 추가.
    """
    title_part = cleaned_title
    if benefit_feature:
        title_part = "{} \u2014 {}".format(cleaned_title, benefit_feature)

    if not store_name:
        return title_part[:max_length]

    suffix = " {} {}".format(separator, store_name)
    available = max_length - len(suffix)

    if available <= 10:
        return title_part[:max_length]

    if len(title_part) > available:
        words = title_part[:available].rsplit(" ", 1)
        shortened = words[0] if len(words) > 1 else title_part[:available]
        shortened = shortened.strip("-,").strip()

        # === 추가: trailing word 제거 ===
        trailing_words = {
            "with",
            "for",
            "and",
            "or",
            "the",
            "a",
            "an",
            "in",
            "on",
            "at",
            "to",
            "of",
            "by",
            "is",
            "it",
            "as",
            "up",
            "from",
            "into",
            "&",
        }
        for _ in range(3):
            parts = shortened.rsplit(" ", 1)
            if len(parts) == 2:
                last = parts[1].strip(",-").lower()
                if last in trailing_words or (last.isdigit() and len(last) <= 2):
                    shortened = parts[0].strip("-,").strip()
                    continue
            break

        return shortened + suffix

    result = title_part + suffix
    return result[:max_length]


def generate_seo_description(
    body_html, store_name, max_length=160, free_shipping_threshold=""
):
    # type: (str, str, int, str) -> str
    """
    SEO Description을 생성한다.

    Body HTML에서 텍스트를 추출하고 "Shop now at {Store Name}." 추가.
    max_length 초과 시 단어 단위 자름.
    """
    # HTML 태그 제거 (간단한 방식, BeautifulSoup 없이)
    text = re.sub(r"<[^>]+>", " ", body_html)
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return ""

    suffix = " Shop now at {}.".format(store_name) if store_name else ""
    if free_shipping_threshold:
        suffix = (
            " Free shipping over ${}. Shop at {}.".format(
                free_shipping_threshold, store_name
            )
            if store_name
            else ""
        )
    available = max_length - len(suffix)

    if available <= 20:
        return text[:max_length]

    if len(text) > available:
        # 단어 단위로 자르기
        words = text[:available].rsplit(" ", 1)
        shortened = words[0] if len(words) > 1 else text[:available]
        # 끝 구두점 정리 후 ... 추가
        shortened = shortened.rstrip(".,!?;: ")
        shortened += "..."
        # suffix 포함하여 max_length 초과하지 않도록 재확인
        if len(shortened) + len(suffix) > max_length:
            over = len(shortened) + len(suffix) - max_length
            shortened = shortened[: -(over + 3)].rstrip(" ") + "..."
        text = shortened

    result = text + suffix
    # 최종 길이 보장
    return result[:max_length]


def generate_image_alt(title_for_alt, store_name, position):
    # type: (str, str, int) -> str
    """
    이미지 Alt Text를 생성한다.

    position 1: "{Title} - {Store Name}"
    position 2+: "{Title} view {n} - {Store Name}"
    최대 125자.
    """
    if store_name:
        if position == 1:
            alt = "{} - {}".format(title_for_alt, store_name)
        else:
            alt = "{} view {} - {}".format(title_for_alt, position, store_name)
    else:
        if position == 1:
            alt = title_for_alt
        else:
            alt = "{} view {}".format(title_for_alt, position)

    return alt[:125]


def filter_product_images(images, max_images):
    # type: (list, object) -> list
    """
    이미지 목록을 필터링한다.

    브랜드 로고/배너/아이콘 이미지 URL을 제외하고
    max_images 제한을 적용한다.
    """
    filtered = []
    exclude_patterns = ["logo", "banner", "sprite", "icon", "badge", "grey-pixel"]

    for img_url in images:
        url_lower = img_url.lower()
        if any(pat in url_lower for pat in exclude_patterns):
            continue
        filtered.append(img_url)

    if isinstance(max_images, int) and max_images > 0:
        return filtered[:max_images]
    return filtered  # "all"인 경우


# ================================================================
# CSV 내보내기
# ================================================================


def export_shopify_csv(
    products,
    output_path=None,
    keyword="",
    shopify_settings=None,
    price_settings=None,
    collection_mapping=None,
):
    # type: (list, str, str, dict, dict, object) -> str
    """
    상품 데이터를 Shopify CSV로 내보낸다.

    25개 컬럼, 멀티 로우 이미지 처리, Title/Handle/SEO 자동 생성,
    가격 계산, Collection Mapping 적용.

    Args:
        products: 상품 딕셔너리 리스트.
        output_path: 저장 파일 경로. None이면 config 기본값 사용.
        keyword: 검색 키워드 (태그/매핑에 사용).
        shopify_settings: Shopify Output Settings 딕셔너리.
        price_settings: Price Settings 딕셔너리.
        collection_mapping: Collection Mapping 리스트 또는 딕셔너리.

    Returns:
        str: 저장된 파일 경로.
    """
    # 파일 경로 기본값
    if output_path is None:
        output_path = os.path.join(config.OUTPUT_DIR, config.CSV_FILENAME)

    # 기본값 설정
    if shopify_settings is None:
        shopify_settings = {
            "store_name": "",
            "default_vendor": "",
            "vendor_source": "amazon_brand",
            "published": True,
            "status": "draft",
            "inventory_qty": 999,
            "inventory_policy": "deny",
            "max_images": 5,
            "title_max_length": 60,
            "remove_brand": True,
            "seo_separator": "|",
            "price_rounding": ".99",
        }
    if price_settings is None:
        price_settings = {
            "method": "multiplier",
            "multiplier": 2.5,
            "margin_cost": 150.0,
            "margin_price": 60.0,
            "fixed_markup": 15.0,
            "compare_at_markup": 1.4,
            "rounding": ".99",
        }
    if collection_mapping is None:
        collection_mapping = {}

    # 설정 추출
    store_name = shopify_settings.get("store_name", "")
    default_vendor = shopify_settings.get("default_vendor", "")
    vendor_source = shopify_settings.get("vendor_source", "amazon_brand")
    published = "TRUE" if shopify_settings.get("published", True) else "FALSE"
    default_status = shopify_settings.get("status", "draft")
    inventory_qty = shopify_settings.get("inventory_qty", 999)
    inventory_policy = shopify_settings.get("inventory_policy", "deny")
    max_images = shopify_settings.get("max_images", 5)
    title_max_length = shopify_settings.get("title_max_length", 60)
    remove_brand = shopify_settings.get("remove_brand", True)
    seo_separator = shopify_settings.get("seo_separator", "|")
    title_style = shopify_settings.get("title_style", "clean")
    subtitle_style = shopify_settings.get("subtitle_style", "from_description")
    free_shipping_threshold = shopify_settings.get("free_shipping_threshold", "")

    # CSV 컬럼 순서
    fieldnames = COLUMNS

    rows = []
    current_product_count = 0
    file_index = 1
    saved_paths = []

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    base_name, ext = os.path.splitext(output_path)

    for p in products:
        # AI Polish에서 store_name, seo_separator 참조할 수 있도록 저장
        p["_store_name"] = store_name
        p["_seo_separator"] = seo_separator

        # 상품별 keyword 우선 사용 (통합 CSV 대응)
        product_keyword = p.get("_keyword", "") or keyword

        # collection_mapping에서 product_keyword에 해당하는 매핑 찾기
        mapping = {}
        if isinstance(collection_mapping, list):
            for m in collection_mapping:
                if m.get("keyword", "").lower() == product_keyword.lower():
                    mapping = m
                    break
        elif isinstance(collection_mapping, dict) and collection_mapping:
            mapping = collection_mapping

        # 매핑 기본값 생성
        if not mapping:
            tag = re.sub(r"[^a-z0-9\s]", "", product_keyword.lower()).strip()
            tag = re.sub(r"\s+", "-", tag)
            mapping = {
                "keyword": product_keyword,
                "tag": tag,
                "type": product_keyword.title() if product_keyword else "",
                "category": "",
            }

        asin = p.get("asin", "")
        raw_title = sanitize_text(p.get("detail_title") or p.get("title", ""))
        brand = p.get("detail_brand") or p.get("brand", "")

        # Vendor 결정
        if vendor_source == "amazon_brand" and brand:
            vendor = brand
        elif default_vendor:
            vendor = default_vendor
        else:
            vendor = brand or ""

        # Title 정리 (clean_title 적용)
        cleaned = clean_title(raw_title, brand, remove_brand, title_max_length)
        if not cleaned:
            cleaned = raw_title[:title_max_length]

        # AI Title 적용 (description_generator에서 생성된 경우)
        display_title = cleaned
        ai_title = p.get("_ai_title", "")
        if title_style == "ai_benefit" and ai_title:
            display_title = ai_title

        # Handle 생성 (SEO 키워드 유지를 위해 cleaned 기반)
        handle = generate_handle(cleaned)
        if not handle:
            handle = asin.lower()

        # Subtitle 생성
        ai_subtitle = p.get("_ai_subtitle", "")
        if subtitle_style == "ai_generate" and ai_subtitle:
            subtitle_value = ai_subtitle
        else:
            # from_description: body에서 첫 bullet 추출
            raw_body = p.get("body_html") or p.get("description", "")
            subtitle_value = extract_first_bullet(raw_body)

        # Body HTML
        body_html = p.get("body_html") or p.get("description", "")
        body_html = clean_html_body(body_html)

        # 가격 계산
        amazon_price = parse_price(p.get("price", "0"))
        if amazon_price and amazon_price > 0:
            sell_price = calculate_price(amazon_price, price_settings)
            sell_price = apply_rounding(
                sell_price, price_settings.get("rounding", ".99")
            )
            compare_price = calculate_compare_at_price(
                sell_price,
                price_settings.get("compare_at_markup", 1.4),
                price_settings.get("rounding", ".99"),
            )
        else:
            sell_price = 0
            compare_price = 0

        price_str = "{:.2f}".format(sell_price) if sell_price else ""
        compare_str = "{:.2f}".format(compare_price) if compare_price else ""

        # Tags 생성
        collection_tag = mapping.get("tag", "")

        # keyword_tag 생성: & → and, 특수문자 제거, 공백 → 하이픈, 연속 하이픈 제거
        keyword_tag = product_keyword.lower()
        keyword_tag = keyword_tag.replace("&", "and")
        keyword_tag = re.sub(r"[^a-z0-9\s\-]", "", keyword_tag)
        keyword_tag = re.sub(r"\s+", "-", keyword_tag).strip("-")
        keyword_tag = re.sub(r"-+", "-", keyword_tag)  # 연속 하이픈 제거

        asin_tag = "amazon-asin-{}".format(asin.upper()) if asin else ""
        tags_list = [
            t for t in ["amazon-import", collection_tag, keyword_tag, asin_tag] if t
        ]
        # 중복 제거
        seen = set()
        unique_tags = []
        for t in tags_list:
            if t not in seen:
                seen.add(t)
                unique_tags.append(t)
        tags_str = ",".join(unique_tags)

        # 이미지 처리
        images = p.get("all_images", [])
        images = filter_product_images(images, max_images)

        # SEO Title 생성: AI 생성 우선, 없으면 코드 생성 (최대 70자)
        seo_max_length = 70
        ai_seo_title = p.get("_ai_seo_title", "")
        # ai_seo_title이 1순위 (AI SEO가 만들어준 경우)
        if ai_seo_title:
            if store_name:
                seo_title = "{} {} {}".format(ai_seo_title, seo_separator, store_name)
            else:
                seo_title = ai_seo_title
            # 초과 시 자르기
            if len(seo_title) > seo_max_length and store_name:
                suffix_len = len(" {} {}".format(seo_separator, store_name))
                if seo_max_length - suffix_len > 10:
                    title_part = (
                        ai_seo_title[: seo_max_length - suffix_len]
                        .rsplit(" ", 1)[0]
                        .rstrip(",-&|")
                        .strip()
                    )
                    seo_title = "{} {} {}".format(title_part, seo_separator, store_name)
                else:
                    seo_title = seo_title[:seo_max_length]

        # ai_title이 2순위
        elif title_style == "ai_benefit" and ai_title:
            if store_name:
                seo_title = "{} {} {}".format(ai_title, seo_separator, store_name)
            else:
                seo_title = ai_title
            if len(seo_title) > seo_max_length and store_name:
                suffix_len = len(" {} {}".format(seo_separator, store_name))
                if seo_max_length - suffix_len > 10:
                    title_part = (
                        ai_title[: seo_max_length - suffix_len]
                        .rsplit(" ", 1)[0]
                        .rstrip(",-&|")
                        .strip()
                    )
                    seo_title = "{} {} {}".format(title_part, seo_separator, store_name)
                else:
                    seo_title = seo_title[:seo_max_length]

        # 다 없으면 generate_seo_title 호출 (기존 코드 생성 로직)
        else:
            seo_title = generate_seo_title(
                cleaned, store_name, seo_separator, max_length=seo_max_length
            )

        # SEO Description 생성: AI 생성 우선, 없으면 코드 생성
        ai_seo_desc = p.get("_ai_seo_description", "")
        if ai_seo_desc:
            # AI가 이미 완성된 문장을 반환하므로 그대로 사용
            seo_desc = ai_seo_desc[:160]
        else:
            seo_desc = generate_seo_description(
                body_html,
                store_name,
                max_length=160,
                free_shipping_threshold=free_shipping_threshold,
            )

        # 첫 번째 행 (모든 25개 컬럼)
        # Alt Text 용도의 title 결정
        # AI Generated Title이 있으면 첫 번째 em-dash(\u2014) 또는 하이픈(-) 이전 문자열만 사용
        title_for_alt = display_title
        if title_style == "ai_benefit" and ai_title:
            if "\u2014" in display_title:
                title_for_alt = display_title.split("\u2014")[0].strip()
            elif "-" in display_title:
                title_for_alt = display_title.split("-")[0].strip()
            else:
                title_for_alt = display_title
        else:
            title_for_alt = cleaned

        first_image = images[0] if images else ""
        first_alt = generate_image_alt(title_for_alt, store_name, 1) if images else ""

        first_row = {
            "Handle": handle,
            "Title": display_title,
            "Body (HTML)": body_html,
            "Vendor": vendor,
            "Product Category": "",
            "Type": mapping.get("type", ""),
            "Tags": tags_str,
            "Published": published,
            "Option1 Name": "Title",
            "Option1 Value": "Default Title",
            "Variant SKU": asin.upper(),
            "Variant Grams": "0",
            "Variant Inventory Tracker": "shopify",
            "Variant Inventory Qty": str(inventory_qty),
            "Variant Inventory Policy": inventory_policy,
            "Variant Fulfillment Service": "manual",
            "Variant Price": price_str,
            "Variant Compare At Price": compare_str,
            "Variant Requires Shipping": "TRUE",
            "Variant Taxable": "TRUE",
            "Image Src": first_image,
            "Image Position": "1" if first_image else "",
            "Image Alt Text": first_alt,
            "SEO Title": seo_title,
            "SEO Description": seo_desc,
            "Status": default_status,
            "product.metafields.descriptors.subtitle": subtitle_value,
        }
        rows.append(first_row)

        # 추가 이미지 행 (Handle, Image Src, Image Position, Image Alt Text만)
        for idx, img_url in enumerate(images[1:], start=2):
            img_row = {f: "" for f in fieldnames}
            img_row["Handle"] = handle
            img_row["Image Src"] = img_url
            img_row["Image Position"] = str(idx)
            img_row["Image Alt Text"] = generate_image_alt(
                title_for_alt, store_name, idx
            )
            rows.append(img_row)

        current_product_count += 1

        # 1000개마다 분할 저장
        if current_product_count == 1000:
            if len(products) > 1000:
                current_output_path = "{}_part{}{}".format(base_name, file_index, ext)
            else:
                current_output_path = output_path

            with open(current_output_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

            logger.info(
                "[CSV] %s: 1000개 상품, %d개 행 저장", current_output_path, len(rows)
            )
            saved_paths.append(current_output_path)

            rows = []
            current_product_count = 0
            file_index += 1

    # 남은 상품 저장
    if rows:
        if len(products) > 1000:
            current_output_path = "{}_part{}{}".format(base_name, file_index, ext)
        else:
            current_output_path = output_path

        with open(current_output_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        logger.info(
            "[CSV] %s: %d개 상품, %d개 행 저장",
            current_output_path,
            current_product_count,
            len(rows),
        )
        saved_paths.append(current_output_path)

    return ", ".join(saved_paths)


def extract_first_bullet(body_html):
    # type: (str) -> str
    """Body HTML에서 첫 번째 불릿 포인트를 추출하여 subtitle로 사용한다."""
    if not body_html:
        return ""
    # <li> 태그에서 첫 번째 항목 추출
    match = re.search(r"<li[^>]*>(.*?)</li>", body_html, re.IGNORECASE | re.DOTALL)
    if match:
        text = re.sub(r"<[^>]+>", "", match.group(1)).strip()
        return text[:255] if text else ""
    return ""

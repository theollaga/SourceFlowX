"""
Phase 2 - 데이터 변환기
아마존 raw 데이터를 Shopify 제품 형식으로 변환합니다.
"""

import re
import html
import json
import logging

from tag_engine import generate_all_tags
from price_engine import calculate_price

logger = logging.getLogger("processor.transformer")


# ================================================================
# 아마존 문구 클리닝 엔진 (AI 없는 규칙 기반)
# ================================================================

# --- 쓰레기 구절 제거 패턴 (구절 단위로 잘라냄, 문장 전체를 죽이지 않음) ---
REMOVE_PHRASES = [
    # 구매 유도
    r'click\s*(the\s*)?(add\s*to\s*cart|buy\s*now)\s*button\.?',
    r'add\s*to\s*(your\s*)?cart\s*(now|today)?\.?',
    r'order\s*(now|today|yours)\s*(and|to|for|!)?\.?',
    r'buy\s*with\s*confidence\.?',
    r'hurry\s*up!?',
    r'don\'?t\s*miss\s*(out|this)!?',
    r'while\s*supplies?\s*last\.?',
    r'limited\s*(time\s*)?(offer|stock|supply|deal)\.?',
    r'act\s*(now|fast|quickly)\.?',
    r'selling\s*fast\.?',
    # 보증/환불
    r'\d+[\s-]*(day|month|year)\s*(money[\s-]*back\s*)?(return|refund|guarantee|warranty)\.?',
    r'(hassle|worry|risk)[\s-]*free\s*(return|refund|replacement|purchase|guarantee|warranty)\.?',
    r'(100\s*%?\s*)?satisfaction\s*guarantee[d]?\.?',
    r'money[\s-]*back\s*guarantee\.?',
    r'full\s*refund\.?',
    r'no\s*questions?\s*asked\s*(return|refund)\.?',
    # 고객 서비스
    r'(please\s*)?(feel\s*free\s*to\s*)?(contact|reach|email)\s*(us|our\s*team)[^.]*\.?',
    r'(if\s*you\s*have\s*)?(any\s*)?(questions?|concerns?|issues?|problems?)\s*,?\s*(please\s*)?(feel\s*free\s*to\s*)?(contact|reach|email|let\s*us\s*know)[^.]*\.?',
    r'customer\s*(service|support|care)\s*(team\s*)?(is\s*)?(available|ready|here)[^.]*\.?',
    r'we\s*(will|\'ll)\s*(respond|reply|get\s*back)[^.]*\.?',
    r'please\s*(don\'?t\s*)?hesitate\s*to\s*(contact|reach|ask)[^.]*\.?',
    # 리뷰 요청
    r'(please\s*)?(leave|write|share|give)\s*(us\s*)?(a\s*)?(positive\s*)?(review|feedback|rating|star)[^.]*\.?',
    r'(your|any)\s*(feedback|review|rating)\s*(is\s*)?(greatly\s*)?(appreciated|welcome|important)[^.]*\.?',
    r'(5|five)[\s-]*star\s*(review|rating|feedback)[^.]*\.?',
    # 아마존 전용
    r'(exclusively\s*)?(available\s*)?(only\s*)?on\s*amazon\.?',
    r'fulfilled\s*by\s*amazon\.?',
    r'ships?\s*from\s*(and\s*sold\s*by\s*)?amazon\.?',
    r'amazon\s*(prime|choice|best[\s-]*seller|exclusive)\.?',
    r'amazon\s*verified\s*(purchase|review)\.?',
    r'prime\s*(eligible|shipping|delivery|member)\.?',
    # 패키지 내용물
    r'package\s*(includes?|contents?|contains?)\s*:',
    r'what\'?s?\s*in\s*the\s*(box|package)\s*:',
    r'box\s*contents?\s*:',
]

REMOVE_PATTERNS = [re.compile(p, re.IGNORECASE) for p in REMOVE_PHRASES]

# --- 불필요한 스펙 키 ---
SKIP_SPEC_KEYS = {
    'asin', 'date first available', 'date first listed on amazon',
    'customer reviews', 'best sellers rank', 'best seller rank',
    'manufacturer', 'is discontinued by manufacturer',
    'item model number', 'department', 'batteries',
    'domestic shipping', 'international shipping',
    'shipping weight', 'item weight',
}


# ================================================================
# 범용 텍스트 클리너 (모든 텍스트에 공통 적용)
# ================================================================

def universal_clean(text):
    """
    어떤 텍스트든 받아서 확실한 쓰레기만 제거하고 돌려줍니다.
    제품 설명 내용은 건드리지 않습니다.
    """
    if not text or not text.strip():
        return ""

    # HTML 엔티티 디코딩
    text = html.unescape(text)

    # script, style 태그 제거
    text = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', text, flags=re.DOTALL | re.IGNORECASE)

    # 불필요한 HTML 태그 제거 (기본 서식 태그는 유지)
    text = re.sub(r'<(?!/?(?:p|br|li|ul|ol|strong|b|em|i|h[1-6])\b)[^>]+>', '', text, flags=re.IGNORECASE)

    # 이모지/장식 기호 제거
    text = re.sub(
        r'[\U0001F300-\U0001F9FF\U00002600-\U000027BF\U0000FE00-\U0000FEFF'
        r'\U00002700-\U000027BF\u2705\u2714\u2713\u2611\u2B50\u2605\u2606'
        r'\u25CF\u25C6\u25C7\u25B6\u25BA\u25AA\u25B8\u27A4\u279C\u2728'
        r'\U0001F4A1\U0001F525\U0001F381\U0001F389\U0001F4AF\U0001F44D'
        r'\u2764\U0001F50B\U0001F3A7\U0001F3B5\U0001F50A\U0001F4F1'
        r'\U0001F4A7\u2192]',
        '', text
    )

    # 전각 → 반각 (기본 문장부호)
    text = text.replace('\uff0c', ',').replace('\uff1a', ':').replace('\uff1b', ';')
    text = text.replace('\uff08', '(').replace('\uff09', ')').replace('\uff01', '!')

    # 【Header】 → "Header: " (헤더 구분자로 통일)
    text = re.sub(r'\u3010([^\u3011]+)\u3011\s*[-\u2013\u2014]?\s*', r'\1: ', text)
    # 〖Header〗 → "Header: "
    text = re.sub(r'\u3016([^\u3017]+)\u3017\s*[-\u2013\u2014]?\s*', r'\1: ', text)
    # 「Header」 → "Header: "
    text = re.sub(r'\u300c([^\u300d]+)\u300d\s*[-\u2013\u2014]?\s*', r'\1: ', text)
    # 『Header』 → "Header: "
    text = re.sub(r'\u300e([^\u300f]+)\u300f\s*[-\u2013\u2014]?\s*', r'\1: ', text)
    # [ Header ] → "Header: " (공백 포함 대괄호)
    text = re.sub(r'\[\s*([^\]]+?)\s*\]\s*[-\u2013\u2014]?\s*', r'\1: ', text)

    # ® ™ © 제거
    text = re.sub(r'[\u00ae\u2122\u00a9]', '', text)

    # 쓰레기 구절 제거 (문장은 보존, 해당 구절만 잘라냄)
    for pattern in REMOVE_PATTERNS:
        text = pattern.sub('', text)

    # 정리: 빈 괄호, 고아 구두점, 연속 공백
    text = re.sub(r'\(\s*\)', '', text)
    text = re.sub(r'\[\s*\]', '', text)
    text = re.sub(r'\s*[,;]\s*$', '', text)
    text = re.sub(r'\s*[,;]\s*\.', '.', text)
    text = re.sub(r'\s{2,}', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


# ================================================================
# 1. 제목 변환
# ================================================================

def transform_title(product):
    """
    아마존 제목을 쇼피파이용으로 정리합니다.
    - 브랜드 + 핵심 제품명으로 축약
    - 과도한 키워드 스터핑 제거
    - 최대 80자
    """
    title = product.get("title", "")
    brand = product.get("brand", "")

    # 특수문자 정리
    title = re.sub(r'\u3010.*?\u3011', ' ', title)
    title = re.sub(r'\[.*?\]', ' ', title)
    title = re.sub(r'\(.*?\)', ' ', title)
    title = re.sub(r'\{.*?\}', ' ', title)

    # 쉼표로 분리된 부분 중 첫 2-3개만 유지
    parts = [p.strip() for p in title.split(",") if p.strip()]

    if len(parts) >= 3:
        clean_title = ", ".join(parts[:3])
    elif parts:
        clean_title = ", ".join(parts)
    else:
        clean_title = title

    # 브랜드가 제목 앞에 없으면 추가
    if brand and not clean_title.lower().startswith(brand.lower()):
        clean_title = f"{brand} {clean_title}"

    # 연속 공백 정리
    clean_title = re.sub(r'\s+', ' ', clean_title).strip()

    # 최대 80자
    if len(clean_title) > 80:
        words = clean_title[:80].rsplit(' ', 1)
        clean_title = words[0] if len(words) > 1 else clean_title[:80]

    return clean_title


# ================================================================
# 2. 설명(body_html) 구성 — 규칙 기반 클리닝
# ================================================================

def bullets_to_html(bullet_points):
    """
    bullet points를 <li>로 변환합니다.
    universal_clean이 모든 헤더 형식을 "Header: Body"로 통일했으므로
    헤더 감지는 ":" 하나로 충분합니다.
    """
    if not bullet_points:
        return ""

    # 고객서비스/보증 잔해 감지용 패턴
    SERVICE_PATTERNS = [
        re.compile(r'(we\s*(always|strive|try|aim)\s*(to|for))', re.IGNORECASE),
        re.compile(r'(your\s*satisfaction|user\s*comfort)', re.IGNORECASE),
        re.compile(r'(best\s*quality\s*(product|service))', re.IGNORECASE),
        re.compile(r'(if\s*you\s*have\s*any\s*(problems?|issues?|questions?))', re.IGNORECASE),
        re.compile(r'(warranty|guarantee)\s*(service|support|policy|period)', re.IGNORECASE),
        re.compile(r'(free\s*replacement|free\s*return)', re.IGNORECASE),
        re.compile(r'(customer\s*(service|support|care|satisfaction))', re.IGNORECASE),
        re.compile(r'(don\'?t\s*worry|no\s*worry|rest\s*assured)', re.IGNORECASE),
        re.compile(r'(we\'?ll\s*(help|assist|replace|refund|send))', re.IGNORECASE),
        re.compile(r'(gift\s*(for|idea|giving|occasion|box))', re.IGNORECASE),
        re.compile(r'(perfect\s*gift|ideal\s*gift|great\s*gift)', re.IGNORECASE),
        re.compile(r'(christmas|birthday|anniversary|valentine|mother\'?s?\s*day|father\'?s?\s*day)\s*gift', re.IGNORECASE),
    ]

    items = []
    for bp in bullet_points:
        text = universal_clean(bp)
        if not text or len(text) < 10:
            continue

        # 콜론으로 시작하는 잔해 제거 (헤더가 클리닝에서 사라진 경우)
        text = re.sub(r'^:\s*', '', text).strip()
        if not text or len(text) < 15:
            continue

        # 고객서비스/보증/선물 문구만 남은 bullet 필터링
        service_score = 0
        for pattern in SERVICE_PATTERNS:
            if pattern.search(text):
                service_score += 1
        if service_score >= 2:
            continue

        # 범용 헤더 감지: "짧은구절: 긴 설명"
        m = re.match(r'^([^:]{3,50}?)\s*:\s*(.{20,})$', text, re.DOTALL)

        if m:
            header = m.group(1).strip()
            body = m.group(2).strip()
            items.append(f'<li><strong>{header}</strong> \u2014 {body}</li>')
        else:
            items.append(f'<li>{text}</li>')

    if not items:
        return ""

    return (
        '<div class="sfx-features">'
        '<h3>Key Features</h3>'
        '<ul>' + ''.join(items) + '</ul>'
        '</div>'
    )


def description_to_html(desc_text, bullet_points=None):
    """
    description을 문단 단위로 HTML 변환.
    bullet_points와 80% 이상 겹치면 생략합니다.
    """
    text = universal_clean(desc_text)
    if not text or len(text) < 20:
        return ""

    # "About this item" 제거
    text = re.sub(r'^About this item\s*', '', text, flags=re.IGNORECASE)
    # "See more product details" 제거
    text = re.sub(r'See more product details\s*$', '', text, flags=re.IGNORECASE)
    # "Show more" 제거
    text = re.sub(r'Show more\s*$', '', text, flags=re.IGNORECASE)
    text = text.strip()

    if not text:
        return ""

    # --- 중복 감지: bullet points와 비교 ---
    if bullet_points:
        # bullet points 전체를 합쳐서 비교 텍스트 생성
        bullets_combined = ' '.join(universal_clean(bp) for bp in bullet_points if bp)
        if bullets_combined:
            # 공백/구두점 제거 후 비교 (순수 텍스트만)
            desc_clean = re.sub(r'[\s\W]+', '', text.lower())
            bullets_clean = re.sub(r'[\s\W]+', '', bullets_combined.lower())

            if desc_clean and bullets_clean:
                # description이 bullets에 얼마나 포함되는지 계산
                # 짧은 쪽의 80% 이상이 긴 쪽에 포함되면 중복으로 판단
                shorter = desc_clean if len(desc_clean) <= len(bullets_clean) else bullets_clean
                longer = bullets_clean if len(desc_clean) <= len(bullets_clean) else desc_clean

                # 200자 단위 청크로 비교 (정확한 substring 매칭)
                chunk_size = 200
                match_count = 0
                total_chunks = 0
                for i in range(0, len(shorter), chunk_size):
                    chunk = shorter[i:i + chunk_size]
                    if len(chunk) < 50:
                        continue
                    total_chunks += 1
                    if chunk in longer:
                        match_count += 1

                if total_chunks > 0:
                    overlap = match_count / total_chunks
                    if overlap >= 0.8:
                        return ""  # 80% 이상 중복 → Description 생략

    # 문단 분리
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip() and len(p.strip()) >= 15]

    if not paragraphs:
        return ""

    p_html = ''.join(f'<p>{p}</p>' for p in paragraphs)
    return (
        '<div class="sfx-description">'
        '<h3>Description</h3>'
        + p_html +
        '</div>'
    )


def specs_to_html(specifications):
    """specifications dict를 HTML 테이블로 변환"""
    if not specifications:
        return ""

    rows = []
    for key, value in specifications.items():
        if key.lower().strip() in SKIP_SPEC_KEYS:
            continue
        val = str(value).strip()
        if not val or val.lower() in ('n/a', '-', 'na', 'none', ''):
            continue
        clean_key = re.sub(r'\s+', ' ', key.strip())
        clean_val = re.sub(r'\s+', ' ', val)
        rows.append(f'<tr><td><strong>{clean_key}</strong></td><td>{clean_val}</td></tr>')

    if not rows:
        return ""

    return (
        '<div class="sfx-specs">'
        '<h3>Specifications</h3>'
        '<table class="sfx-spec-table">' + ''.join(rows) + '</table>'
        '</div>'
    )


def build_body_html(product):
    """
    아마존 raw 데이터 → Shopify body_html
    이미 구조화된 데이터를 그대로 활용하고,
    확실한 쓰레기만 제거합니다.
    """
    sections = []

    features = bullets_to_html(product.get("bullet_points", []))
    if features:
        sections.append(features)

    desc = description_to_html(product.get("description_text", ""), product.get("bullet_points", []))
    if desc:
        sections.append(desc)

    specs = specs_to_html(product.get("specifications", {}))
    if specs:
        sections.append(specs)

    if not sections:
        title = product.get("title", "")
        brand = product.get("brand", "")
        return f'<div class="sfx-fallback"><p>{brand} {title}</p></div>'

    return '\n'.join(sections)


# ================================================================
# 3. 이미지 정리
# ================================================================

def transform_images(product):
    """
    이미지 URL 목록을 Shopify 형식으로 정리합니다.
    - 고해상도 URL 유지
    - 중복 제거
    - 최대 20장
    """
    images = product.get("all_images", [])
    main_image = product.get("main_image", "")

    # 중복 제거 (순서 유지, main_image를 첫 번째로)
    seen = set()
    ordered = []

    if main_image:
        ordered.append(main_image)
        seen.add(main_image)

    for img in images:
        if img not in seen:
            seen.add(img)
            ordered.append(img)

    # 최대 20장
    return ordered[:20]


# ================================================================
# 4. vendor / product_type 매핑
# ================================================================

def get_vendor(product):
    """Shopify vendor = 브랜드"""
    return product.get("brand", "Unknown")


def get_product_type(product):
    """
    breadcrumb 마지막 항목을 product_type으로 사용.
    없으면 빈 문자열.
    """
    breadcrumb = product.get("category_breadcrumb", [])
    if breadcrumb:
        return breadcrumb[-1]
    return ""


# ================================================================
# 5. SKU 생성
# ================================================================

def generate_sku(product):
    """
    ASIN 기반으로 SKU를 생성합니다.
    형식: AMZ-{ASIN}
    """
    asin = product.get("asin", "")
    return f"AMZ-{asin}" if asin else ""


# ================================================================
# 6. 변형(Variants) 구성
# ================================================================

def build_variants(product, pricing):
    """
    Shopify 변형 데이터를 구성합니다.
    현재는 단일 변형 (Phase 1에서 variation options가 lazy-load 한계).
    """
    variant = {
        "title": "Default Title",
        "price": pricing.get("price", 0),
        "compare_at_price": pricing.get("compare_at_price", 0),
        "sku": generate_sku(product),
        "inventory_management": "shopify",
        "inventory_policy": "deny",
        "inventory_quantity": 100,
        "requires_shipping": True,
        "taxable": True,
        "weight": 0,
        "weight_unit": "lb",
    }

    # 무게 정보가 specs에 있으면 추출
    specs = product.get("specifications", {})
    for key in ["Item Weight", "Weight", "Package Weight"]:
        if key in specs:
            weight_str = specs[key]
            m = re.search(r'([\d.]+)\s*(lb|oz|kg|g)', weight_str.lower())
            if m:
                val = float(m.group(1))
                unit = m.group(2)
                if unit == "oz":
                    val = val / 16
                elif unit == "kg":
                    val = val * 2.205
                elif unit == "g":
                    val = val / 453.6
                variant["weight"] = round(val, 2)
                variant["weight_unit"] = "lb"
            break

    return [variant]


# ================================================================
# 7. 메타필드 구성
# ================================================================

def build_metafields(product, pricing):
    """
    Shopify metafields에 원본 아마존 데이터를 저장합니다.
    나중에 가격 동기화, 재고 관리 등에 활용.
    """
    metafields = {
        "amazon_asin": product.get("asin", ""),
        "amazon_url": product.get("url", ""),
        "amazon_price": product.get("price", 0),
        "amazon_rating": product.get("rating", 0),
        "amazon_reviews": product.get("reviews_count", 0),
        "amazon_bsr": json.dumps(product.get("bsr_ranks", [])),
        "amazon_seller": product.get("seller", ""),
        "amazon_fulfilled_by": product.get("fulfilled_by", ""),
        "amazon_date_first_available": product.get("date_first_available", ""),
        "cost_per_item": pricing.get("cost_per_item", 0),
        "margin_percent": pricing.get("margin_percent", 0),
    }
    return metafields


# ================================================================
# 8. 메인 변환 함수
# ================================================================

def transform_product(product):
    """
    아마존 raw 제품 데이터를 Shopify 형식으로 변환합니다.

    Args:
        product: raw JSONL에서 읽은 제품 딕셔너리

    Returns:
        dict: Shopify 제품 데이터
    """
    # 가격 계산
    pricing = calculate_price(product)

    # 태그 생성
    tags = generate_all_tags(product)

    # 이미지 정리
    images = transform_images(product)

    # Shopify 제품 구조
    shopify_product = {
        "title": transform_title(product),
        "body_html": build_body_html(product),
        "vendor": get_vendor(product),
        "product_type": get_product_type(product),
        "tags": ", ".join(tags),
        "status": "draft",
        "published": False,

        "variants": build_variants(product, pricing),

        "images": [{"src": url} for url in images],

        "metafields": build_metafields(product, pricing),

        # 원본 참조 (export 시 제외 가능)
        "_original_title": product.get("title", ""),
        "_original_asin": product.get("asin", ""),
        "_pricing": pricing,
        "_tag_list": tags,
    }

    return shopify_product


# ================================================================
# 테스트용
# ================================================================
if __name__ == "__main__":
    import glob
    import os

    files = sorted(glob.glob(os.path.join("..", "collector", "collector_output", "raw_*.jsonl")))
    if not files:
        files = sorted(glob.glob(os.path.join("collector", "collector_output", "raw_*.jsonl")))
    if not files:
        print("JSONL 파일을 찾을 수 없습니다.")
        exit()

    # 각 파일에서 첫 제품 1개씩 변환 테스트
    for fpath in files:
        fname = os.path.basename(fpath)
        with open(fpath, "r", encoding="utf-8") as f:
            line = f.readline()
            if not line:
                continue
            product = json.loads(line)

        result = transform_product(product)

        print(f"\n{'='*70}")
        print(f"파일: {fname}")
        print(f"{'='*70}")
        print(f"원본 제목: {product.get('title', '')[:70]}")
        print(f"변환 제목: {result['title']}")
        print(f"Vendor:    {result['vendor']}")
        print(f"Type:      {result['product_type']}")
        print(f"Status:    {result['status']}")
        print(f"태그 수:   {len(result['_tag_list'])}")
        print(f"이미지 수: {len(result['images'])}")

        v = result['variants'][0]
        p = result['_pricing']
        print(f"\n가격:")
        print(f"  원가(아마존): ${p['cost_per_item']:.2f}")
        print(f"  판매가:       ${v['price']:.2f}")
        print(f"  비교가:       ${v['compare_at_price']:.2f}")
        print(f"  마진:         {p['margin_percent']}%")
        print(f"  SKU:          {v['sku']}")
        print(f"  무게:         {v['weight']} {v['weight_unit']}")

        print(f"\n태그 (상위 15개):")
        for tag in result['_tag_list'][:15]:
            print(f"  {tag}")
        if len(result['_tag_list']) > 15:
            print(f"  ... 외 {len(result['_tag_list'])-15}개")

        print(f"\nbody_html 미리보기 (500자):")
        print(f"  {result['body_html'][:500]}")

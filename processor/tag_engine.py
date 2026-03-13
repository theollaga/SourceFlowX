"""
Phase 2 - 태그 자동 생성 엔진
아마존 raw 데이터에서 Shopify 컬렉션 매칭용 태그를 자동 생성합니다.
접두어 기반: Cat:, Brand:, Price:, Feature:, Use:, Keyword:, Bestseller:, NewArrival:, Rating:, Prime:, Source:
"""

import re
from datetime import datetime, timezone


# ================================================================
# 1. 카테고리 태그 (breadcrumb 기반)
# ================================================================
def generate_category_tags(product):
    """breadcrumb에서 카테고리 태그 생성"""
    tags = []
    breadcrumb = product.get("category_breadcrumb", [])
    for crumb in breadcrumb:
        clean = crumb.strip()
        if clean:
            tag = "Cat:" + clean.replace(" ", "-")
            if tag not in tags:
                tags.append(tag)
    return tags


# ================================================================
# 2. 브랜드 태그
# ================================================================
def generate_brand_tags(product):
    """브랜드 태그 생성"""
    brand = product.get("brand", "").strip()
    if brand:
        return ["Brand:" + brand.replace(" ", "-")]
    return []


# ================================================================
# 3. 가격대 태그
# ================================================================
def generate_price_tags(product):
    """가격 구간 태그 생성"""
    price = product.get("price", 0)
    if not price or price <= 0:
        return []

    tags = []
    if price < 25:
        tags.append("Price:Under-25")
    elif price < 50:
        tags.append("Price:25-50")
    elif price < 100:
        tags.append("Price:50-100")
    elif price < 200:
        tags.append("Price:100-200")
    elif price < 500:
        tags.append("Price:200-500")
    else:
        tags.append("Price:Over-500")

    return tags


# ================================================================
# 4. Feature 태그 (title + bullet points에서 패턴 추출)
# ================================================================

# 기술 스펙 패턴: (정규식, 태그명 또는 그룹 참조)
FEATURE_PATTERNS = [
    # Bluetooth
    (r'bluetooth\s*([\d.]+)', lambda m: f"Feature:Bluetooth-{m.group(1)}"),
    (r'bluetooth', lambda m: "Feature:Bluetooth"),
    # WiFi
    (r'wi-?fi\s*(\d+[a-z]*)', lambda m: f"Feature:WiFi-{m.group(1)}"),
    (r'wi-?fi', lambda m: "Feature:WiFi"),
    (r'5g\s*/?\s*2\.4g', lambda m: "Feature:Dual-Band-WiFi"),
    (r'dual[- ]?band', lambda m: "Feature:Dual-Band"),
    # Noise Cancelling
    (r'(?:active\s+)?noise\s+cancell?(?:ing|ation)', lambda m: "Feature:Noise-Cancelling"),
    (r'\banc\b', lambda m: "Feature:ANC"),
    (r'\benc\b', lambda m: "Feature:ENC"),
    # Waterproof / Dustproof
    (r'ip(?:x?)(\d+)', lambda m: f"Feature:IP{'X' if 'x' in m.group(0).lower() else ''}{m.group(1)}-Waterproof"),
    (r'waterproof', lambda m: "Feature:Waterproof"),
    (r'water[- ]?resistant', lambda m: "Feature:Water-Resistant"),
    (r'sweatproof', lambda m: "Feature:Sweatproof"),
    (r'dustproof', lambda m: "Feature:Dustproof"),
    # Audio
    (r'dolby\s*(?:audio|atmos|digital)?', lambda m: "Feature:Dolby-Audio"),
    (r'hi-?fi', lambda m: "Feature:HiFi"),
    (r'stereo', lambda m: "Feature:Stereo"),
    (r'deep\s*bass', lambda m: "Feature:Deep-Bass"),
    (r'surround\s*sound', lambda m: "Feature:Surround-Sound"),
    # Display / Resolution
    (r'4k', lambda m: "Feature:4K"),
    (r'1080p', lambda m: "Feature:1080P"),
    (r'720p', lambda m: "Feature:720P"),
    (r'full\s*hd', lambda m: "Feature:Full-HD"),
    (r'hdr(?:\d+)?', lambda m: "Feature:HDR"),
    (r'(\d+)\s*ansi', lambda m: f"Feature:{m.group(1)}-ANSI"),
    # Battery
    (r'(\d+)\s*(?:hrs?|hours?)\s*(?:battery|playtime|playback)',
     lambda m: f"Feature:{m.group(1)}Hr-Battery"),
    (r'(?:battery|playtime|playback)\s*(?:up\s*to\s*)?(\d+)\s*(?:hrs?|hours?)',
     lambda m: f"Feature:{m.group(1)}Hr-Battery"),
    # Charging
    (r'(?:usb[- ]?c|type[- ]?c)\s*(?:charg(?:ing|e))?', lambda m: "Feature:USB-C"),
    (r'fast\s*charg(?:ing|e)', lambda m: "Feature:Fast-Charging"),
    (r'wireless\s*charg(?:ing|e)', lambda m: "Feature:Wireless-Charging"),
    # Smart Features
    (r'auto[- ]?focus', lambda m: "Feature:Auto-Focus"),
    (r'auto[- ]?keystone', lambda m: "Feature:Auto-Keystone"),
    (r'voice\s*(?:control|assistant)', lambda m: "Feature:Voice-Control"),
    (r'touch\s*control', lambda m: "Feature:Touch-Control"),
    (r'smart\s*(?:home|projector|feeder)', lambda m: "Feature:Smart"),
    # Connectivity
    (r'wireless', lambda m: "Feature:Wireless"),
    (r'true\s*wireless', lambda m: "Feature:True-Wireless"),
    (r'\btws\b', lambda m: "Feature:TWS"),
    (r'hdmi', lambda m: "Feature:HDMI"),
    # Build
    (r'lightweight', lambda m: "Feature:Lightweight"),
    (r'portable', lambda m: "Feature:Portable"),
    (r'foldable', lambda m: "Feature:Foldable"),
    (r'ergonomic', lambda m: "Feature:Ergonomic"),
    (r'compact', lambda m: "Feature:Compact"),
    # Pet Feeder specifics
    (r'(\d+)\s*(?:l|liter|litre)\b', lambda m: f"Feature:{m.group(1)}L-Capacity"),
    (r'(\d+)\s*(?:cup|cups)\b', lambda m: f"Feature:{m.group(1)}-Cup"),
    (r'(\d+)\s*meals?', lambda m: f"Feature:{m.group(1)}-Meal"),
    (r'stainless\s*steel', lambda m: "Feature:Stainless-Steel"),
    (r'(?:2\.4g|5g)\s*(?:ghz)?\s*wifi', lambda m: "Feature:WiFi"),
    (r'camera|1080p\s*hd\s*video', lambda m: "Feature:Camera"),
    (r'voice\s*record', lambda m: "Feature:Voice-Recording"),
    (r'timer|timed|programmable', lambda m: "Feature:Programmable-Timer"),
    (r'rfid', lambda m: "Feature:RFID"),
    (r'microchip', lambda m: "Feature:Microchip"),
    # Projector specifics
    (r'roku', lambda m: "Feature:Roku-Built-In"),
    (r'android\s*tv', lambda m: "Feature:Android-TV"),
    (r'android\s*(\d+)\s*(?:os)?', lambda m: f"Feature:Android-{m.group(1)}"),
    (r'google\s*tv', lambda m: "Feature:Google-TV"),
    (r'netflix', lambda m: "Feature:Netflix-Built-In"),
    (r'built[- ]?in\s*(?:battery|rechargeable)', lambda m: "Feature:Built-In-Battery"),
    (r'short[- ]?throw', lambda m: "Feature:Short-Throw"),
    (r'tripod', lambda m: "Feature:Tripod-Compatible"),
    (r'screen\s*mirroring', lambda m: "Feature:Screen-Mirroring"),
]


def generate_feature_tags(product):
    """title + bullet_points에서 기능/스펙 태그 추출"""
    text = product.get("title", "")
    bullets = product.get("bullet_points", [])
    if bullets:
        text += " " + " ".join(bullets)
    text_lower = text.lower()

    tags = []
    seen = set()

    for pattern, tag_func in FEATURE_PATTERNS:
        m = re.search(pattern, text_lower)
        if m:
            tag = tag_func(m)
            tag_upper = tag.upper()
            if tag_upper not in seen:
                seen.add(tag_upper)
                tags.append(tag)
    # 중복 제거: 버전 있으면 일반 태그 제외
    final_tags = list(tags)  # 복사
    tag_values = [t.upper() for t in tags]

    if any("BLUETOOTH-" in t for t in tag_values):
        final_tags = [t for t in final_tags if t.upper() != "FEATURE:BLUETOOTH"]
    if any("IPX" in t and "WATERPROOF" in t for t in tag_values):
        final_tags = [t for t in final_tags if t.upper() != "FEATURE:WATERPROOF"]
    if any("WIFI-" in t for t in tag_values):
        final_tags = [t for t in final_tags if t.upper() != "FEATURE:WIFI"]
    if any("1080P" in t or "4K" in t or "720P" in t for t in tag_values):
        final_tags = [t for t in final_tags if t.upper() != "FEATURE:FULL-HD"]

    return final_tags


# ================================================================
# 5. Use (용도) 태그
# ================================================================

USE_PATTERNS = [
    (r'(?:for|ideal for|perfect for|designed for|great for)\s+(running)', "Use:Running"),
    (r'(?:for|ideal for|perfect for|designed for|great for)\s+(sports?)', "Use:Sports"),
    (r'(?:for|ideal for|perfect for|designed for|great for)\s+(gaming)', "Use:Gaming"),
    (r'(?:for|ideal for|perfect for|designed for|great for)\s+(travel(?:ing)?)', "Use:Travel"),
    (r'(?:for|ideal for|perfect for|designed for|great for)\s+(office)', "Use:Office"),
    (r'(?:for|ideal for|perfect for|designed for|great for)\s+(gym)', "Use:Gym"),
    (r'(?:for|ideal for|perfect for|designed for|great for)\s+(workout)', "Use:Workout"),
    (r'(?:for|ideal for|perfect for|designed for|great for)\s+(yoga)', "Use:Yoga"),
    (r'(?:for|ideal for|perfect for|designed for|great for)\s+(swim(?:ming)?)', "Use:Swimming"),
    (r'(?:for|ideal for|perfect for|designed for|great for)\s+(home\s*(?:theater|cinema)?)', "Use:Home-Theater"),
    (r'(?:for|ideal for|perfect for|designed for|great for)\s+(outdoor)', "Use:Outdoor"),
    (r'(?:for|ideal for|perfect for|designed for|great for)\s+(bedroom)', "Use:Bedroom"),
    (r'(?:for|ideal for|perfect for|designed for|great for)\s+(camping)', "Use:Camping"),
    (r'(?:for|ideal for|perfect for|designed for|great for)\s+(kids?|children)', "Use:Kids"),
    (r'(?:for|ideal for|perfect for|designed for|great for)\s+(cats?)', "Use:Cat"),
    (r'(?:for|ideal for|perfect for|designed for|great for)\s+(dogs?)', "Use:Dog"),
    (r'(?:for|ideal for|perfect for|designed for|great for)\s+(pets?)', "Use:Pet"),
    (r'(?:for|ideal for|perfect for|designed for|great for)\s+(small\s*dogs?)', "Use:Small-Dog"),
    (r'(?:for|ideal for|perfect for|designed for|great for)\s+(large\s*dogs?)', "Use:Large-Dog"),
    # 제목에 직접적으로 용도가 명시된 경우
    (r'\boutdoor\s*(?:projector|movie|speaker)', "Use:Outdoor"),
    (r'\bsports?\s*(?:earbuds|headphones|earphones)', "Use:Sports"),
    (r'\bgaming\s*(?:earbuds|headphones|earphones)', "Use:Gaming"),
    (r'\bworkout\s*(?:earbuds|headphones|earphones)', "Use:Workout"),
    # 제목에 직접적으로 용도가 명시된 경우 (기존 것에 추가)
    (r'\bsports?\b', "Use:Sports"),
    (r'\brunning\b', "Use:Running"),
    (r'\bgaming\b', "Use:Gaming"),
    (r'\bworkout\b', "Use:Workout"),
    (r'\bgym\b', "Use:Gym"),
    (r'\btravel\b', "Use:Travel"),
    (r'\boutdoor\b', "Use:Outdoor"),
    (r'\bcamping\b', "Use:Camping"),
    (r'\bcat\s*(?:feeder|food|bowl|treat)', "Use:Cat"),
    (r'\bdog\s*(?:feeder|food|bowl|treat)', "Use:Dog"),
    (r'\bpet\s*(?:feeder|food|bowl|treat|water)', "Use:Pet"),
]


def generate_use_tags(product):
    """title + bullet_points에서 용도 태그 추출"""
    text = product.get("title", "")
    bullets = product.get("bullet_points", [])
    if bullets:
        text += " " + " ".join(bullets)
    text_lower = text.lower()

    tags = []
    seen = set()

    for pattern, tag in USE_PATTERNS:
        if re.search(pattern, text_lower):
            tag_upper = tag.upper()
            if tag_upper not in seen:
                seen.add(tag_upper)
                tags.append(tag)

    return tags


# ================================================================
# 6. Keyword 태그 (title에서 의미 있는 단어 추출)
# ================================================================

STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "it", "as", "be", "was", "are",
    "this", "that", "these", "those", "has", "have", "had", "not", "no",
    "can", "will", "do", "does", "did", "its", "your", "our", "my",
    "up", "out", "if", "so", "just", "about", "into", "over", "after",
    "all", "also", "than", "then", "very", "too", "more", "most",
    "each", "every", "any", "both", "few", "many", "much", "own",
    "such", "only", "same", "other", "new", "old", "first", "last",
    "see", "product", "details", "item", "buy", "sale", "free",
    "shipping", "delivery", "pack", "pcs", "set", "pair", "compatible",
    "included", "includes", "include", "version", "latest", "newest",
    "upgraded", "update", "generation", "gen", "model", "series",
    "edition", "style", "type", "size", "color", "black", "white",
    "red", "blue", "green", "pink", "gray", "grey", "silver", "gold",
    # 추가: 의미 없는 단어
    "per", "day", "ring", "sealed", "hrs", "hour", "hours", "ear",
    "buds", "led", "ipx", "use", "full", "based", "via", "way",
    "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "max", "total", "ultra", "super", "plus", "real",
    "true", "like", "best", "good", "great", "high", "low", "top",
    "dual", "single", "double", "triple", "multi", "extra", "long",
    "short", "big", "small", "large", "medium", "case", "box", "bag",
    "cup", "cups", "power", "display", "control", "mode", "support",
    "supports", "feature", "features", "design", "built", "time",
    "quality", "sound", "audio", "music", "call", "calls", "voice",
    "hands", "hand", "life", "range", "level", "system", "device",
    "devices", "technology", "app", "apps", "smart", "advanced",
    "premium", "professional", "original", "official", "certified",
}


def generate_keyword_tags(product):
    """title에서 불용어 제외 후 의미 있는 키워드 태그 추출"""
    title = product.get("title", "")
    brand = product.get("brand", "").lower()

    # 특수문자 제거, 단어 분리
    words = re.findall(r'[a-zA-Z]+(?:-[a-zA-Z]+)*', title)

    tags = []
    seen = set()

    for word in words:
        w_lower = word.lower()

        # 필터링
        if len(w_lower) <= 2:
            continue
        if w_lower in STOP_WORDS:
            continue
        if w_lower == brand.lower():
            continue
        # Feature/Use에서 이미 잡히는 기술 용어는 제외
        if w_lower in {"bluetooth", "wireless", "wifi", "usb", "hdmi",
                        "waterproof", "portable", "mini", "pro",
                        "noise", "cancelling", "canceling"}:
            continue

        tag = "Keyword:" + word.capitalize()
        tag_upper = tag.upper()
        if tag_upper not in seen:
            seen.add(tag_upper)
            tags.append(tag)

    return tags


# ================================================================
# 7. Bestseller 태그 (BSR 기반)
# ================================================================
def generate_bestseller_tags(product):
    """BSR 순위 기반 베스트셀러 태그"""
    bsr_ranks = product.get("bsr_ranks", [])
    if not bsr_ranks:
        return []

    tags = []
    best_rank = min(r.get("rank", 999999) for r in bsr_ranks)

    if best_rank <= 10:
        tags.append("Bestseller:Top-10")
    if best_rank <= 50:
        tags.append("Bestseller:Top-50")
    if best_rank <= 100:
        tags.append("Bestseller:Top-100")
    if best_rank <= 500:
        tags.append("Bestseller:Top-500")
    if best_rank <= 1000:
        tags.append("Bestseller:Top-1000")

    return tags


# ================================================================
# 8. New Arrival 태그 (date_first_available 기반)
# ================================================================

DATE_FORMATS = [
    "%B %d, %Y",      # "March 13, 2026"
    "%b %d, %Y",      # "Mar 13, 2026"
    "%Y-%m-%d",        # "2026-03-13"
    "%d %B %Y",        # "13 March 2026"
    "%B %Y",           # "March 2026"
]


def generate_newarrival_tags(product):
    """출시일 기준 신상품 태그"""
    date_str = product.get("date_first_available", "")
    if not date_str:
        return []

    release_date = None
    for fmt in DATE_FORMATS:
        try:
            release_date = datetime.strptime(date_str.strip(), fmt)
            break
        except ValueError:
            continue

    if not release_date:
        return []

    now = datetime.now()
    days_since = (now - release_date).days

    tags = []
    if days_since <= 30:
        tags.append("NewArrival:30days")
    if days_since <= 90:
        tags.append("NewArrival:90days")
    if days_since <= 180:
        tags.append("NewArrival:180days")

    return tags


# ================================================================
# 9. Rating 태그
# ================================================================
def generate_rating_tags(product):
    """평점 기반 태그"""
    rating = product.get("rating", 0)
    if not rating or rating <= 0:
        return []

    tags = []
    if rating >= 4.5:
        tags.append("Rating:4.5+")
    if rating >= 4.0:
        tags.append("Rating:4.0+")
    if rating >= 3.5:
        tags.append("Rating:3.5+")

    return tags


# ================================================================
# 10. Prime / Source 태그
# ================================================================
def generate_prime_tags(product):
    """Prime 여부 태그"""
    if product.get("is_prime"):
        return ["Prime:Yes"]
    return []


def generate_source_tags(product):
    """수집 소스 태그"""
    marketplace = product.get("marketplace", "")
    if "amazon.com" in marketplace:
        return ["Source:Amazon-US"]
    elif "amazon.co.uk" in marketplace:
        return ["Source:Amazon-UK"]
    elif "amazon.de" in marketplace:
        return ["Source:Amazon-DE"]
    elif "amazon.co.jp" in marketplace:
        return ["Source:Amazon-JP"]
    return ["Source:Amazon"]


# ================================================================
# 메인: 전체 태그 생성
# ================================================================
def generate_all_tags(product):
    """
    제품 하나에 대해 모든 태그를 생성합니다.

    Args:
        product: raw JSONL에서 읽은 제품 딕셔너리

    Returns:
        list: 태그 문자열 리스트
    """
    all_tags = []

    all_tags.extend(generate_category_tags(product))
    all_tags.extend(generate_brand_tags(product))
    all_tags.extend(generate_price_tags(product))
    all_tags.extend(generate_feature_tags(product))
    all_tags.extend(generate_use_tags(product))
    all_tags.extend(generate_keyword_tags(product))
    all_tags.extend(generate_bestseller_tags(product))
    all_tags.extend(generate_newarrival_tags(product))
    all_tags.extend(generate_rating_tags(product))
    all_tags.extend(generate_prime_tags(product))
    all_tags.extend(generate_source_tags(product))

    # 중복 제거 (순서 유지)
    seen = set()
    unique_tags = []
    for tag in all_tags:
        if tag.upper() not in seen:
            seen.add(tag.upper())
            unique_tags.append(tag)

    return unique_tags


# ================================================================
# 테스트용: 단일 제품 태그 미리보기
# ================================================================
if __name__ == "__main__":
    import json
    import glob
    import os

    files = sorted(glob.glob(os.path.join("..", "collector", "collector_output", "raw_*.jsonl")))
    if not files:
        files = sorted(glob.glob(os.path.join("collector", "collector_output", "raw_*.jsonl")))
    if not files:
        print("JSONL 파일을 찾을 수 없습니다.")
        exit()

    # 각 키워드 파일에서 첫 제품 1개씩 테스트
    for fpath in files:
        fname = os.path.basename(fpath)
        with open(fpath, "r", encoding="utf-8") as f:
            line = f.readline()
            if not line:
                continue
            product = json.loads(line)

        tags = generate_all_tags(product)

        print(f"\n{'='*60}")
        print(f"파일: {fname}")
        print(f"제품: {product.get('title', '')[:60]}")
        print(f"태그 수: {len(tags)}")
        print(f"{'='*60}")

        # 접두어별 그룹핑
        groups = {}
        for tag in tags:
            prefix = tag.split(":")[0] if ":" in tag else "Other"
            if prefix not in groups:
                groups[prefix] = []
            groups[prefix].append(tag)

        for prefix, tag_list in groups.items():
            print(f"\n  [{prefix}] ({len(tag_list)}개)")
            for t in tag_list:
                print(f"    {t}")

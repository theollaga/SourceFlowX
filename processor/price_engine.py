"""
Phase 2 - 가격 계산 엔진
아마존 가격에 마진을 적용하고 .99로 반올림합니다.
"""

import math


# ================================================================
# 기본 마진율 설정
# ================================================================

# 카테고리별 마진율 (%). 키는 breadcrumb 첫 번째 항목 기준.
# 여기에 없는 카테고리는 DEFAULT_MARGIN 적용.
CATEGORY_MARGINS = {
    "Electronics": 40,
    "Pet Supplies": 35,
    "Home & Kitchen": 40,
    "Sports & Outdoors": 45,
    "Tools & Home Improvement": 40,
    "Toys & Games": 45,
    "Beauty & Personal Care": 50,
    "Health & Household": 45,
    "Office Products": 40,
    "Automotive": 40,
    "Garden & Outdoor": 40,
    "Baby": 45,
    "Clothing, Shoes & Jewelry": 50,
}

DEFAULT_MARGIN = 40  # 기본 마진율 (%)

# 최소 판매가 (이 이하로는 안 팔음)
MIN_PRICE = 9.99

# compare_at_price 마크업 (원래 가격 대비 %)
# 쇼피파이에서 할인 표시를 위해 사용
COMPARE_AT_MARKUP = 20  # 판매가 대비 20% 높게 설정


# ================================================================
# 가격 계산 함수
# ================================================================

def round_to_99(price):
    """
    가격을 .99로 반올림합니다.
    예: 41.586 → 41.99, 12.3 → 12.99, 9.2 → 9.99
    """
    whole = math.floor(price)
    return whole + 0.99


def calculate_price(product):
    """
    아마존 가격에 마진을 적용하여 쇼피파이 판매가를 계산합니다.

    Args:
        product: raw JSONL에서 읽은 제품 딕셔너리

    Returns:
        dict: {
            "price": 판매가 (xx.99),
            "compare_at_price": 비교가 (할인 전 가격, xx.99),
            "cost_per_item": 원가 (아마존 가격),
            "margin_percent": 적용된 마진율,
            "currency": "USD"
        }
    """
    amazon_price = product.get("price", 0)
    currency = product.get("currency", "")

    # MAP 정책 또는 가격 없음
    if not amazon_price or amazon_price <= 0 or currency == "MAP_POLICY":
        return {
            "price": 0,
            "compare_at_price": 0,
            "cost_per_item": 0,
            "margin_percent": 0,
            "currency": "USD",
            "note": "MAP_POLICY" if currency == "MAP_POLICY" else "NO_PRICE",
        }

    # 카테고리별 마진율 결정
    breadcrumb = product.get("category_breadcrumb", [])
    margin = DEFAULT_MARGIN

    if breadcrumb:
        top_category = breadcrumb[0]
        margin = CATEGORY_MARGINS.get(top_category, DEFAULT_MARGIN)

    # 마진 적용
    raw_price = amazon_price * (1 + margin / 100)

    # .99 반올림
    selling_price = round_to_99(raw_price)

    # 최소가 보장
    if selling_price < MIN_PRICE:
        selling_price = MIN_PRICE

    # compare_at_price (할인 전 가격)
    compare_raw = selling_price * (1 + COMPARE_AT_MARKUP / 100)
    compare_at_price = round_to_99(compare_raw)

    return {
        "price": selling_price,
        "compare_at_price": compare_at_price,
        "cost_per_item": amazon_price,
        "margin_percent": margin,
        "currency": "USD",
    }


# ================================================================
# 테스트용
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

    print(f"{'ASIN':<14} {'아마존가':<10} {'마진%':<7} {'판매가':<10} {'비교가':<10} {'제품명'}")
    print("-" * 90)

    for fpath in files:
        with open(fpath, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= 5:  # 파일당 5개만
                    break
                product = json.loads(line)
                result = calculate_price(product)

                print(
                    f"{product.get('asin', ''):<14} "
                    f"${product.get('price', 0):<9.2f} "
                    f"{result['margin_percent']:<6}% "
                    f"${result['price']:<9.2f} "
                    f"${result['compare_at_price']:<9.2f} "
                    f"{product.get('title', '')[:40]}"
                )
        print()

"""
SourceFlowX - 가격 마진 조정 모듈
아마존 원가에 마진을 적용하여 쇼피파이 판매가와 비교가를 설정한다.
"""

import config
from utils import parse_price, setup_logger

# 파일 레벨 로거
logger = setup_logger("price")


def adjust_prices(products, margin_percent=None, compare_markup=None):
    # type: (list, float, float) -> list
    """
    아마존 가격에 마진을 적용하여 쇼피파이 판매가와 비교가를 설정한다.

    각 상품의 price 필드에 마진 적용 판매가를,
    original_price 필드에 비교가(취소선 가격)를 설정한다.
    가격이 0 이하인 상품은 건너뛴다.

    Examples:
        아마존 $10 상품, 마진 30%, 비교가 배율 1.2:
        → 판매가 $13.0, 비교가 $15.6

    Args:
        products: 상품 딕셔너리 리스트. 원본이 직접 수정된다.
        margin_percent: 마진율 (%). None이면 config.MARGIN_PERCENT.
        compare_markup: 비교가 배율. None이면 config.COMPARE_PRICE_MARKUP.

    Returns:
        list: 가격이 수정된 상품 리스트 (원본과 동일 참조).
    """
    if margin_percent is None:
        margin_percent = config.MARGIN_PERCENT
    if compare_markup is None:
        compare_markup = config.COMPARE_PRICE_MARKUP

    adjusted_count = 0

    for p in products:
        amazon_price = parse_price(p.get("price", "0"))

        if amazon_price <= 0:
            continue

        sell_price = round(amazon_price * (1 + margin_percent / 100), 2)
        compare_price = round(sell_price * compare_markup, 2)

        p["price"] = str(sell_price)
        p["original_price"] = str(compare_price)
        adjusted_count += 1

    logger.info("[가격] %d개 상품 마진 %s%% 적용 완료", adjusted_count, margin_percent)

    return products


def calculate_price(amazon_price, price_settings):
    # type: (float, dict) -> float
    """
    아마존 가격과 설정에 따라 판매 가격을 계산한다.

    4가지 가격 계산 방식을 지원한다:
    - multiplier: 아마존 가격 × 배수
    - margin_cost: 원가 기준 마진율
    - margin_price: 판매가 기준 마진율
    - fixed_markup: 고정 금액 추가

    Args:
        amazon_price: 아마존 원가 (float).
        price_settings: get_price_settings()에서 반환된 딕셔너리.

    Returns:
        계산된 판매가 (float, 반올림 적용 전).
    """
    method = price_settings.get("method", "multiplier")

    if method == "multiplier":
        # 판매가 = 아마존 가격 × 배수
        return amazon_price * price_settings.get("multiplier", 2.5)
    elif method == "margin_cost":
        # 판매가 = 아마존 가격 × (1 + 마진율/100)
        margin = price_settings.get("margin_cost", 150.0)
        return amazon_price * (1 + margin / 100)
    elif method == "margin_price":
        # 판매가 = 아마존 가격 / (1 - 마진율/100)
        margin = price_settings.get("margin_price", 60.0)
        if margin >= 100:
            margin = 99.0  # 100% 이상 방지
        return amazon_price / (1 - margin / 100)
    elif method == "fixed_markup":
        # 판매가 = 아마존 가격 + 고정 금액
        return amazon_price + price_settings.get("fixed_markup", 15.0)
    elif method == "tiered":
        # === 새로 추가: 가격대별 차등 마크업 ===
        tiers = price_settings.get(
            "tiered_rates",
            [
                (20, 3.0),  # $0~$20 → 3.0x
                (50, 2.5),  # $20~$50 → 2.5x
                (100, 2.0),  # $50~$100 → 2.0x
                (float("inf"), 1.6),  # $100+ → 1.6x
            ],
        )
        for threshold, rate in tiers:
            if amazon_price <= threshold:
                return amazon_price * rate
        return amazon_price * 1.6  # fallback
    else:
        return amazon_price * 2.5  # fallback


def apply_rounding(price, rounding):
    # type: (float, str) -> float
    """
    가격에 라운딩 규칙을 적용한다.

    Args:
        price: 원래 가격.
        rounding: ".99", ".95", ".00", "none" 중 하나.

    Returns:
        라운딩 적용된 가격.
    """
    import math

    if rounding == ".99":
        return math.floor(price) + 0.99
    elif rounding == ".95":
        return math.floor(price) + 0.95
    elif rounding == ".00":
        return float(math.ceil(price))
    else:  # "none"
        return round(price, 2)


def calculate_compare_at_price(sell_price, markup, rounding):
    # type: (float, float, str) -> float
    """
    Compare At Price를 계산한다.

    Args:
        sell_price: 판매가 (라운딩 적용 후).
        markup: Compare At 배수 (예: 1.4).
        rounding: 라운딩 규칙.

    Returns:
        Compare At Price (라운딩 적용됨).
    """
    raw = sell_price * markup
    return apply_rounding(raw, rounding)

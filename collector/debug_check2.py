import re

with open("debug_B0FG2PMNS2.html", "r", encoding="utf-8") as f:
    html = f.read()

print("=== VARIATION 심층 분석 ===")

# 1. colorToAsin 정확한 위치 찾기
for m in re.finditer(r'"colorToAsin"', html):
    start = max(0, m.start() - 20)
    end = min(len(html), m.end() + 500)
    ctx = html[start:end]
    print("[colorToAsin 위치:{}] {}".format(m.start(), ctx[:400]))
    print("---")

# 2. variation 관련 키워드 전체 탐색
print("\n=== VARIATION 키워드 탐색 ===")
var_patterns = [
    r'"selected_color_name"\s*:\s*"([^"]*)"',
    r'"color_name"\s*:\s*\[([^\]]+)\]',
    r'"variation_color_name"',
    r'"dimensionToAsinMap"\s*:\s*(\{.+?\})',
    r'"parentAsin"\s*:\s*"([^"]+)"',
    r'"twisterData"',
]
for pat in var_patterns:
    m = re.search(pat, html, re.DOTALL)
    if m:
        g = m.group(1) if m.lastindex else m.group(0)
        print("  [{}] 발견: {}".format(pat[:40], g[:200]))
    else:
        print("  [{}] 없음".format(pat[:40]))

# 3. seller 관련 키워드 심층 탐색
print("\n=== SELLER 심층 탐색 ===")
seller_patterns = [
    r'"merchant"',
    r'"sellerInfo"',
    r'"buyingOption"',
    r'"soldBy"',
    r'"fulfilledBy"',
    r'Ships from',
    r'Sold by',
    r'"isAmazonFulfilled"',
    r'"merchantId"',
]
for pat in seller_patterns:
    m = re.search(pat, html, re.IGNORECASE)
    if m:
        ctx = html[max(0, m.start() - 20):min(len(html), m.end() + 150)]
        print("  [{}] 발견: {}".format(pat, ctx[:200]))
    else:
        print("  [{}] 없음".format(pat))

# 4. buybox 영역 ID 전체 탐색
print("\n=== BUYBOX 영역 탐색 ===")
buybox_patterns = [
    r'id="buybox',
    r'id="addToCart',
    r'id="buy-now',
    r'id="qualifiedBuybox',
    r'data-feature-name="buybox"',
]
for pat in buybox_patterns:
    m = re.search(pat, html, re.IGNORECASE)
    if m:
        ctx = html[max(0, m.start() - 10):min(len(html), m.end() + 100)]
        print("  [{}] 발견: {}".format(pat, ctx[:150]))
    else:
        print("  [{}] 없음".format(pat))

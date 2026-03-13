"""
raw_parser 단독 테스트.
실제 아마존 페이지 HTML 없이, 파싱 함수들이 에러 없이 동작하는지 확인합니다.
"""

from raw_parser import parse_product_page, parse_search_results

# 빈 HTML 테스트 (None/빈값이 정상 반환되는지)
print("=" * 50)
print("테스트 1: 빈 HTML 처리")
result = parse_product_page("")
print("  결과:", result)
print("  → None이면 정상")

print()
print("테스트 2: 최소 HTML 처리")
minimal_html = """
<html>
<body>
<span id="productTitle">Test Product Title</span>
<a id="bylineInfo">Brand: TestBrand</a>
<span class="a-offscreen">$29.99</span>
</body>
</html>
"""
result = parse_product_page(minimal_html)
if result:
    print("  ASIN:", result.get("asin"))
    print("  제목:", result.get("title"))
    print("  브랜드:", result.get("brand"))
    print("  가격:", result.get("price"))
    print("  필드 수:", len(result))
    print("  → 제목='Test Product Title', 브랜드='TestBrand', 가격=29.99면 정상")
else:
    print("  → result가 None — 파싱 실패!")

print()
print("테스트 3: 검색 결과 파싱")
search_html = """
<div data-component-type="s-search-result" data-asin="B0TEST1234">
  <h2><a><span>Test Search Product</span></a></h2>
  <span class="a-price"><span class="a-offscreen">$19.99</span></span>
</div>
"""
results = parse_search_results(search_html)
print("  검색 결과 수:", len(results))
if results:
    print("  첫 번째 ASIN:", results[0].get("asin"))
    print("  첫 번째 제목:", results[0].get("title"))
    print("  → ASIN='B0TEST1234', 제목='Test Search Product'면 정상")

print()
print("=" * 50)
print("파서 테스트 완료!")
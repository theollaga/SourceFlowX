from bs4 import BeautifulSoup
import re

with open("debug_B0FG2PMNS2.html", "r", encoding="utf-8") as f:
    html = f.read()
soup = BeautifulSoup(html, "lxml")

print("=== 1. SELLER 영역 ===")
for sel in ["#tabular-buybox", "#merchant-info", "#buyBoxAccordion", "#shipsFromSoldByInsideBuyBox_feature_div"]:
    el = soup.select_one(sel)
    if el:
        print("  [{}] 발견! 텍스트: {}".format(sel, el.get_text(strip=True)[:200]))
    else:
        print("  [{}] 없음".format(sel))

# seller 관련 추가 탐색
print("\n  --- seller 추가 탐색 ---")
for pat in [r'"merchantName"\s*:\s*"([^"]+)"', r'"sellerName"\s*:\s*"([^"]+)"', r'sold\s+by\s+([A-Za-z0-9 .]+)', r'"seller"\s*:\s*"([^"]+)"']:
    m = re.search(pat, html, re.IGNORECASE)
    if m:
        print("  [regex:{}] 발견: {}".format(pat[:30], m.group(1)[:100]))

print("\n=== 2. VARIATIONS 옵션 ===")
for pat_name, pat in [
    ("dimensionValuesDisplayData", r"dimensionValuesDisplayData\s*[=:]\s*(\{.+?\})"),
    ("asinVariationValues", r'"asinVariationValues"\s*:\s*(\{.+?\})'),
    ("colorToAsin", r'"colorToAsin"\s*:\s*(\{.+?\})'),
    ("variationDisplayLabels", r'"variationDisplayLabels"\s*:\s*(\{.+?\})'),
]:
    m = re.search(pat, html, re.DOTALL)
    if m:
        print("  [{}] 발견! 길이: {}자, 미리보기: {}".format(pat_name, len(m.group(1)), m.group(1)[:300]))
    else:
        print("  [{}] 없음".format(pat_name))

# twister 버튼 확인
twister_items = soup.select("#twister li[data-defaultasin]")
print("  [twister li] {}개 발견".format(len(twister_items)))
for li in twister_items[:3]:
    print("    asin={}, title={}".format(li.get("data-defaultasin", ""), li.get("title", "")[:60]))

print("\n=== 3. Q&A 영역 ===")
for sel in ["#askATFLink", "#ask_feature_div", "#ask-btf_feature_div"]:
    el = soup.select_one(sel)
    if el:
        print("  [{}] 발견! 텍스트: {}".format(sel, el.get_text(strip=True)[:100]))
    else:
        print("  [{}] 없음".format(sel))

for pat in [r"answered\s*questions", r"totalQuestions", r"questionsCount", r"askATFData"]:
    m = re.search(pat, html, re.IGNORECASE)
    if m:
        ctx = html[max(0, m.start() - 30):m.end() + 80]
        print("  [regex:{}] 발견! 컨텍스트: {}".format(pat, ctx[:150]))
    else:
        print("  [regex:{}] 없음".format(pat))

print("\n=== 4. RATING DISTRIBUTION ===")
for sel in ["#histogramTable", "#cm_cr_dp_d_hist_table", "#reviewsMedley", '[data-hook="rating-histogram"]']:
    el = soup.select_one(sel)
    if el:
        print("  [{}] 발견! 길이: {}자".format(sel, len(str(el))))
    else:
        print("  [{}] 없음".format(sel))

for pat in [r"ratingDistribution", r"histogramBinLabels", r"represent\s*\d+%", r"reviewSummary", r'"starRating"']:
    m = re.search(pat, html, re.IGNORECASE)
    if m:
        ctx = html[max(0, m.start() - 30):m.end() + 80]
        print("  [regex:{}] 발견! 컨텍스트: {}".format(pat, ctx[:150]))
    else:
        print("  [regex:{}] 없음".format(pat))

# histogram 관련 a 태그 전체 탐색
print("\n  --- histogram a 태그 탐색 ---")
for a in soup.select("a[title]"):
    title = a.get("title", "")
    if "star" in title.lower() and "%" in title:
        print("  발견: title='{}'".format(title))

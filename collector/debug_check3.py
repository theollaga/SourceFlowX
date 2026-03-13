import re
from bs4 import BeautifulSoup

with open("debug_B0FG2PMNS2.html", "r", encoding="utf-8") as f:
    html = f.read()
soup = BeautifulSoup(html, "lxml")

print("=== SELLER: offer-display-feature 구조 ===")
# Ships from
for el in soup.select('[offer-display-feature-name="desktop-fulfiller-info"]'):
    print("  [Ships from] 텍스트: '{}'".format(el.get_text(strip=True)))
    a_tag = el.select_one("a")
    span_tag = el.select_one("span")
    if a_tag:
        print("  [Ships from] a 태그: '{}'".format(a_tag.get_text(strip=True)))
    if span_tag:
        print("  [Ships from] span 태그: '{}'".format(span_tag.get_text(strip=True)))
    print("  [Ships from] HTML: {}".format(str(el)[:300]))

print()

# Sold by
for el in soup.select('[offer-display-feature-name="desktop-merchant-info"]'):
    print("  [Sold by] 텍스트: '{}'".format(el.get_text(strip=True)))
    a_tag = el.select_one("a")
    span_tag = el.select_one("span")
    if a_tag:
        print("  [Sold by] a 태그: '{}'".format(a_tag.get_text(strip=True)))
    if span_tag:
        print("  [Sold by] span 태그: '{}'".format(span_tag.get_text(strip=True)))
    print("  [Sold by] HTML: {}".format(str(el)[:300]))

print()

# merchantID hidden input
mid = soup.select_one("#merchantID")
if mid:
    print("  [merchantID] value: '{}'".format(mid.get("value", "")))

print()

# buybox 영역 전체 텍스트
buybox = soup.select_one("#buybox")
if buybox:
    text = buybox.get_text(separator=" | ", strip=True)
    print("  [#buybox 전체 텍스트 (300자)] {}".format(text[:300]))

print()
print("=== SELLER: Ships from / Sold by 라벨 주변 ===")
for el in soup.find_all("span", string=re.compile(r"Ships from|Sold by", re.IGNORECASE)):
    parent = el.parent
    if parent:
        grandparent = parent.parent
        if grandparent:
            sibling = grandparent.find_next_sibling()
            if sibling:
                print("  라벨: '{}' → 다음 형제 텍스트: '{}'".format(
                    el.get_text(strip=True),
                    sibling.get_text(strip=True)[:100]
                ))
                print("  다음 형제 HTML: {}".format(str(sibling)[:300]))

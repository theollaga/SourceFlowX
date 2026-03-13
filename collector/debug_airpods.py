from fetcher import fetch_product_html
from proxy_manager import ProxyManager
from bs4 import BeautifulSoup
import re

pm = ProxyManager()
html = fetch_product_html("B0FQFB8FMG", proxy_mgr=pm)

if not html:
    print("수집 실패!")
    exit()

with open("debug_airpods.html", "w", encoding="utf-8") as f:
    f.write(html)

soup = BeautifulSoup(html, "lxml")

print("=== AIRPODS PRO 3 심층 분석 ===")

# 배송 불가 메시지 확인
print("\n--- GEO CHECK ---")
buybox = soup.select_one("#buybox")
if buybox:
    text = buybox.get_text(strip=True)[:300]
    print("  buybox: {}".format(text))

avail = soup.select_one("#availability")
if avail:
    print("  availability: {}".format(avail.get_text(strip=True)))

# 가격 전체 탐색
print("\n--- PRICE 심층 ---")
for sel in ["#corePrice_desktop", "#corePriceDisplay_desktop_feature_div",
            "#apex_desktop", "#apex_offerDisplay_desktop",
            "#newAccordionRow", "#qualifiedBuybox"]:
    el = soup.select_one(sel)
    if el:
        t = el.get_text(strip=True)[:200]
        print("  [{}] {}".format(sel, t if t else "(빈 텍스트)"))

# JS 가격 데이터
for pat in [r'"priceAmount"\s*:\s*([\d.]+)', r'"price"\s*:\s*"?\$?([\d.]+)',
            r'"buyingPrice"\s*:\s*([\d.]+)', r'"ourPrice"\s*:\s*"([^"]+)"',
            r'"priceToPay"\s*:\s*"([^"]+)"', r'"desktop_buybox_group_1".*?"price".*?"value"\s*:\s*([\d.]+)']:
    m = re.search(pat, html, re.DOTALL)
    if m:
        print("  [regex:{}] {}".format(pat[:40], m.group(1)[:50]))

# Breadcrumb 심층
print("\n--- BREADCRUMB 심층 ---")
for pat in [r'"categoryPath"\s*:\s*"([^"]+)"', r'"breadcrumb"\s*:\s*"([^"]+)"',
            r'"productCategory"\s*:\s*"([^"]+)"', r'"category"\s*:\s*"([^"]+)"']:
    m = re.search(pat, html)
    if m:
        print("  [regex:{}] {}".format(pat[:30], m.group(1)[:100]))

# BSR 심층
print("\n--- BSR 심층 ---")
tables = soup.select("table")
print("  테이블 수: {}".format(len(tables)))
for t in tables:
    text = t.get_text()
    if "best seller" in text.lower():
        print("  BSR 포함 테이블 발견!")
        # 해당 행 출력
        for row in t.select("tr"):
            if "best seller" in row.get_text().lower():
                print("    행: {}".format(row.get_text(strip=True)[:200]))

# productDetails 영역 전체 확인
print("\n--- PRODUCT DETAILS 영역 ---")
for sel in ["#productDetails_feature_div", "#detailBullets_feature_div",
            "#productDetails_detailBullets_sections1", "#prodDetails"]:
    el = soup.select_one(sel)
    if el:
        print("  [{}] 길이: {}자".format(sel, len(str(el))))
    else:
        print("  [{}] 없음".format(sel))

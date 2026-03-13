import re, json
from bs4 import BeautifulSoup

# 최신 수집 결과에서 HTML을 다시 받을 필요 없이, 
# 저장된 JSON에서 빈 필드들의 원인을 파악하기 위해 ASIN별로 HTML 수집
from fetcher import fetch_product_html
from proxy_manager import ProxyManager

pm = ProxyManager()

# AirPods Pro 3 (가장 많이 비어있는 제품)
print("=== B0FQFB8FMG (AirPods Pro 3) HTML 분석 ===")
html = fetch_product_html("B0FQFB8FMG", proxy_mgr=pm)
if not html:
    print("HTML 수집 실패!")
else:
    soup = BeautifulSoup(html, "lxml")
    
    # Price
    print("\n--- PRICE ---")
    for sel in ["#corePriceDisplay_desktop_feature_div", "#corePrice_desktop", 
                "#price", "#buybox", ".a-price"]:
        el = soup.select_one(sel)
        if el:
            print("  [{}] 텍스트: {}".format(sel, el.get_text(strip=True)[:150]))
    # JS에서 가격
    for pat in [r'"priceAmount"\s*:\s*([\d.]+)', r'"price"\s*:\s*"?([\d.]+)', 
                r'"buyingPrice"\s*:\s*([\d.]+)']:
        m = re.search(pat, html)
        if m:
            print("  [regex:{}] 값: {}".format(pat[:30], m.group(1)))

    # Seller (신규 레이아웃)
    print("\n--- SELLER ---")
    for sel in ['[offer-display-feature-name="desktop-merchant-info"]',
                '[offer-display-feature-name="desktop-fulfiller-info"]',
                '#tabular-buybox', '#merchant-info']:
        el = soup.select_one(sel)
        if el:
            a = el.select_one("a")
            print("  [{}] a태그: {} / 텍스트: {}".format(
                sel[:50], 
                a.get_text(strip=True) if a else "없음",
                el.get_text(strip=True)[:100]))
        else:
            print("  [{}] 없음".format(sel[:50]))
    
    # Breadcrumb
    print("\n--- BREADCRUMB ---")
    for sel in ["#wayfinding-breadcrumbs_container", ".a-breadcrumb", "#nav-subnav"]:
        el = soup.select_one(sel)
        if el:
            print("  [{}] 텍스트: {}".format(sel, el.get_text(strip=True)[:200]))
        else:
            print("  [{}] 없음".format(sel))
    m = re.search(r'"categoryPath"\s*:\s*"([^"]+)"', html)
    if m:
        print("  [categoryPath] {}".format(m.group(1)))

    # BSR
    print("\n--- BSR ---")
    for sel in ["#productDetails_detailBullets_sections1", "#SalesRank", 
                "#detailBullets_feature_div"]:
        el = soup.select_one(sel)
        if el:
            text = el.get_text()
            if "best seller" in text.lower() or "#" in text:
                print("  [{}] BSR 관련 텍스트 발견".format(sel))
            else:
                print("  [{}] 있지만 BSR 없음".format(sel))
        else:
            print("  [{}] 없음".format(sel))

    # Discount
    print("\n--- DISCOUNT ---")
    for sel in [".savingsPercentage", ".priceBlockSavingsString"]:
        el = soup.select_one(sel)
        if el:
            print("  [{}] {}".format(sel, el.get_text(strip=True)))
        else:
            print("  [{}] 없음".format(sel))

print("\n\n=== B0BTYCRJSS (Anker P20i) PRICE 분석 ===")
html2 = fetch_product_html("B0BTYCRJSS", proxy_mgr=pm)
if html2:
    soup2 = BeautifulSoup(html2, "lxml")
    print("\n--- PRICE ---")
    for sel in ["#corePriceDisplay_desktop_feature_div .a-offscreen",
                "#corePrice_desktop .a-offscreen", 
                ".a-price .a-offscreen",
                "#price .a-offscreen"]:
        els = soup2.select(sel)
        for el in els[:3]:
            print("  [{}] '{}'".format(sel, el.get_text(strip=True)))
    
    # 전체 가격 영역
    price_div = soup2.select_one("#corePriceDisplay_desktop_feature_div, #corePrice_desktop")
    if price_div:
        print("  [price_div 전체] {}".format(price_div.get_text(strip=True)[:200]))
    
    for pat in [r'"priceAmount"\s*:\s*([\d.]+)']:
        m = re.search(pat, html2)
        if m:
            print("  [regex priceAmount] {}".format(m.group(1)))

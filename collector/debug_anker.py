from fetcher import fetch_product_html
from proxy_manager import ProxyManager
from bs4 import BeautifulSoup
import re

pm = ProxyManager()
html = fetch_product_html("B0BTYCRJSS", proxy_mgr=pm)

if not html:
    print("수집 실패!")
    exit()

soup = BeautifulSoup(html, "lxml")

# Breadcrumb
print("=== BREADCRUMB ===")
container = soup.select_one("#wayfinding-breadcrumbs_container")
if container:
    links = container.select("a")
    print("  wayfinding: {}개".format(len(links)))
    for a in links:
        print("    '{}'".format(a.get_text(strip=True)))
else:
    print("  wayfinding: 없음")

container2 = soup.select_one(".a-breadcrumb")
if container2:
    links = container2.select("a")
    print("  a-breadcrumb: {}개".format(len(links)))
    for a in links[:5]:
        print("    '{}'".format(a.get_text(strip=True)))
else:
    print("  a-breadcrumb: 없음")

nav = soup.select_one("#nav-subnav")
if nav:
    links = nav.select("a")
    print("  nav-subnav: {}개 a태그".format(len(links)))
    for a in links[:5]:
        print("    '{}'".format(a.get_text(strip=True)))
else:
    print("  nav-subnav: 없음")

# BSR
print("\n=== BSR ===")
for sel in ["#productDetails_detailBullets_sections1",
            "#detailBullets_feature_div", "#prodDetails"]:
    el = soup.select_one(sel)
    if el:
        text = el.get_text()
        if "best seller" in text.lower():
            bsr_pattern = re.compile(r'#([\d,]+)\s+in\s+([A-Za-z][A-Za-z0-9 &,\'\-]+)')
            matches = bsr_pattern.findall(text)
            print("  [{}] BSR 발견: {}".format(sel, matches))
        else:
            print("  [{}] 있지만 BSR 없음 (길이:{}자)".format(sel, len(text)))
    else:
        print("  [{}] 없음".format(sel))

# Detail Bullets에서 BSR 직접 탐색
print("\n=== DETAIL BULLETS BSR 탐색 ===")
for li in soup.select("#detailBullets_feature_div li, #prodDetails li"):
    text = li.get_text()
    if "#" in text and ("in " in text.lower()):
        print("  발견: {}".format(text.strip()[:200]))

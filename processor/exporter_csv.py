"""
Phase 2.5 - Shopify CSV Exporter
transformed_products.jsonl → Shopify 임포트용 CSV 파일 생성

Shopify CSV 스펙:
- 제품당 첫 행: 전체 필드
- 추가 이미지: Handle만 + Image Src/Position/Alt Text
- variant 없는 단일 제품: Option1 Name="Title", Option1 Value="Default Title"
- 15MB/파일 제한 → 1,000행 단위 배치 분할
"""

import csv
import json
import os
import re
import glob
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============================================================
# 설정
# ============================================================
BATCH_SIZE = 10000          # Shopify 15MB 제한 대응, 행 기준
MAX_IMAGES = 20            # 제품당 최대 이미지 수
OUTPUT_DIR = "processor_output"
INPUT_FILE = os.path.join(OUTPUT_DIR, "transformed_products.jsonl")

# Shopify CSV 컬럼 순서 (공식 스펙 기준)
CSV_COLUMNS = [
    "Handle",
    "Title",
    "Body (HTML)",
    "Vendor",
    "Product Category",
    "Type",
    "Tags",
    "Published",
    "Option1 Name",
    "Option1 Value",
    "Option2 Name",
    "Option2 Value",
    "Option3 Name",
    "Option3 Value",
    "Variant SKU",
    "Variant Grams",
    "Variant Inventory Tracker",
    "Variant Inventory Qty",
    "Variant Inventory Policy",
    "Variant Fulfillment Service",
    "Variant Price",
    "Variant Compare At Price",
    "Variant Requires Shipping",
    "Variant Taxable",
    "Variant Barcode",
    "Image Src",
    "Image Position",
    "Image Alt Text",
    "Gift Card",
    "SEO Title",
    "SEO Description",
    "Google Shopping / Google Product Category",
    "Variant Image",
    "Variant Weight Unit",
    "Variant Tax Code",
    "Cost per item",
    "Included / United States",
    "Included / International",
    "Price / International",
    "Compare At Price / International",
    "Status",
]


# ============================================================
# 핵심 함수
# ============================================================

def generate_handle(title, asin=""):
    """
    Shopify URL handle 생성
    예: "ANDOLL HOME Automatic Cat Feeder, 4L" → "andoll-home-automatic-cat-feeder-4l"
    """
    handle = title.lower().strip()
    # 특수문자 → 하이픈
    handle = re.sub(r'[^a-z0-9\s-]', '', handle)
    handle = re.sub(r'[\s]+', '-', handle)
    handle = re.sub(r'-{2,}', '-', handle)
    handle = handle.strip('-')
    # 너무 길면 80자 내에서 단어 단위로 자름
    if len(handle) > 80:
        handle = handle[:80].rsplit('-', 1)[0]
    return handle


def generate_seo_title(title, vendor=""):
    """
    SEO Title 생성 (최대 70자)
    - 전치사/접속사로 끝나지 않도록 처리
    """
    seo = title.strip()
    if vendor and vendor.lower() not in seo.lower():
        candidate = f"{seo} | {vendor}"
        if len(candidate) <= 70:
            seo = candidate

    if len(seo) > 70:
        seo = seo[:70]
        # 단어 단위로 자르기
        if ' ' in seo:
            seo = seo.rsplit(' ', 1)[0]
        # 전치사/접속사로 끝나면 한 단어 더 제거
        WEAK_ENDINGS = {'with', 'and', 'for', 'the', 'a', 'an', 'of', 'in', 'on', 'to', 'by', 'or', 'at', 'its'}
        while seo and seo.rsplit(' ', 1)[-1].lower() in WEAK_ENDINGS:
            seo = seo.rsplit(' ', 1)[0]
        # 쉼표/하이픈으로 끝나면 제거
        seo = seo.rstrip(',-– ')

    return seo


def generate_seo_description(product):
    """
    SEO Description 생성 (최대 320자)
    body_html의 <strong> 헤더와 <li> 항목에서 기능 키워드 추출
    """
    title = product.get("title", "")
    vendor = product.get("vendor", "")
    product_type = product.get("product_type", "")
    body_html = product.get("body_html", "")

    # body_html에서 기능 추출
    features = []

    # 1순위: <strong>Header</strong> 태그에서 헤더 추출
    headers = re.findall(r'<strong>([^<]{3,50})</strong>', body_html)
    for h in headers:
        clean = h.strip().rstrip(':–— -')
        if clean and len(clean) >= 3:
            features.append(clean)

    # 2순위: 헤더가 부족하면 <li>에서 앞 40자 추출
    if len(features) < 3:
        lis = re.findall(r'<li>([^<]{10,})', body_html)
        for li in lis:
            snippet = li.strip()[:40]
            if ' ' in snippet and len(snippet) > 30:
                snippet = snippet.rsplit(' ', 1)[0]
            if snippet and snippet not in features:
                features.append(snippet)
            if len(features) >= 5:
                break

    # 조합
    parts = []

    # 1) 제목 축약 (60자 이내)
    short_title = title[:60]
    if len(title) > 60:
        short_title = title[:60].rsplit(' ', 1)[0]
        WEAK = {'with', 'and', 'for', 'the', 'a', 'an', 'of', 'in', 'on', 'to', 'by', 'or', 'at'}
        while short_title and short_title.rsplit(' ', 1)[-1].lower() in WEAK:
            short_title = short_title.rsplit(' ', 1)[0]
        short_title = short_title.rstrip(',-– ')
    parts.append(short_title)

    # 2) 핵심 기능
    if features:
        feat_str = "Features: " + ", ".join(features[:5])
        if len(feat_str) > 160:
            feat_str = "Features: " + ", ".join(features[:3])
        parts.append(feat_str)

    # 3) 브랜드 + 타입
    if vendor:
        shop_line = f"Shop {vendor}"
        if product_type:
            shop_line += f" {product_type}"
        parts.append(shop_line)

    desc = ". ".join(parts) + "."

    if len(desc) > 320:
        if features:
            parts[1] = "Features: " + ", ".join(features[:2])
            desc = ". ".join(parts) + "."
    if len(desc) > 320:
        desc = desc[:317].rsplit(' ', 1)[0] + "..."

    return desc


def filter_images(images, title=""):
    """
    이미지 필터링:
    - 중복 URL 제거
    - 로고/배너 패턴 제외
    - 최대 MAX_IMAGES개
    """
    if not images:
        return []

    EXCLUDE_PATTERNS = [
        re.compile(r'logo', re.IGNORECASE),
        re.compile(r'banner', re.IGNORECASE),
        re.compile(r'icon', re.IGNORECASE),
        re.compile(r'badge', re.IGNORECASE),
        re.compile(r'sprite', re.IGNORECASE),
        re.compile(r'_SX[0-9]{2,3}_'),      # 아마존 아주 작은 이미지
        re.compile(r'_SS[0-9]{2,3}_'),
    ]

    seen = set()
    filtered = []
    for img in images:
        url = img.get("src", "") if isinstance(img, dict) else str(img)
        if not url or url in seen:
            continue
        seen.add(url)

        # 제외 패턴 체크
        skip = False
        for pattern in EXCLUDE_PATTERNS:
            if pattern.search(url):
                skip = True
                break
        if skip:
            continue

        filtered.append(url)
        if len(filtered) >= MAX_IMAGES:
            break

    return filtered


def generate_image_alt(title, vendor, position):
    """
    이미지 위치별 alt text 생성
    1번: "Title - Vendor"
    2~5번: "Title - View 2" 등
    6번+: "Title - Detail View"
    """
    base = title[:100] if title else "Product"
    if position == 1:
        alt = f"{base} - {vendor}" if vendor else base
    elif position <= 5:
        alt = f"{base} - View {position}"
    else:
        alt = f"{base} - Detail View"
    # 512자 제한
    return alt[:512]


def product_to_csv_rows(product):
    """
    변환된 제품 1개 → Shopify CSV 행(들)로 변환
    첫 행: 제품 전체 정보 + 첫 이미지
    추가 행: Handle + 추가 이미지
    """
    title = product.get("title", "Untitled")
    vendor = product.get("vendor", "")
    product_type = product.get("product_type", "")
    body_html = product.get("body_html", "")
    tags_list = product.get("tags", [])
    status = product.get("status", "draft")
    images_raw = product.get("images", [])

    # Handle 생성
    asin = ""
    metafields = product.get("metafields", {})
    if isinstance(metafields, dict):
        asin = metafields.get("asin", "")
    elif isinstance(metafields, list):
        for mf in metafields:
            if mf.get("key") == "asin":
                asin = mf.get("value", "")
                break

    handle = generate_handle(title, asin)

    # Tags → 쉼표 구분 문자열
    if isinstance(tags_list, list):
        tags_str = ", ".join(str(t) for t in tags_list)
    else:
        tags_str = str(tags_list)

    # Variant 정보 추출
    variants = product.get("variants", [])
    variant = variants[0] if variants else {}

    sku = variant.get("sku", "")
    price = variant.get("price", "0.00")
    compare_price = variant.get("compare_at_price", "")
    grams = variant.get("grams", 0)
    weight_unit = variant.get("weight_unit", "lb")
    inventory_qty = variant.get("inventory_quantity", 0)

    # Cost per item (metafields에서)
    cost_per_item = ""
    if isinstance(metafields, dict):
        cost_per_item = metafields.get("cost_per_item", "")
    elif isinstance(metafields, list):
        for mf in metafields:
            if mf.get("key") == "cost_per_item":
                cost_per_item = mf.get("value", "")
                break

    # 이미지 필터링 및 alt text 생성
    images = filter_images(images_raw, title)

    # SEO
    seo_title = generate_seo_title(title, vendor)
    seo_desc = generate_seo_description(product)

    # 첫 번째 행 (제품 정보 + 첫 이미지)
    first_image_url = images[0] if images else ""
    first_image_alt = generate_image_alt(title, vendor, 1) if images else ""

    rows = []

    first_row = {
        "Handle": handle,
        "Title": title,
        "Body (HTML)": body_html,
        "Vendor": vendor,
        "Product Category": "",
        "Type": product_type,
        "Tags": tags_str,
        "Published": "FALSE",           # draft 상태이므로
        "Option1 Name": "Title",
        "Option1 Value": "Default Title",
        "Option2 Name": "",
        "Option2 Value": "",
        "Option3 Name": "",
        "Option3 Value": "",
        "Variant SKU": sku,
        "Variant Grams": str(int(grams)) if grams else "0",
        "Variant Inventory Tracker": "shopify",
        "Variant Inventory Qty": str(inventory_qty),
        "Variant Inventory Policy": "deny",
        "Variant Fulfillment Service": "manual",
        "Variant Price": str(price),
        "Variant Compare At Price": str(compare_price) if compare_price else "",
        "Variant Requires Shipping": "TRUE",
        "Variant Taxable": "TRUE",
        "Variant Barcode": "",
        "Image Src": first_image_url,
        "Image Position": "1" if first_image_url else "",
        "Image Alt Text": first_image_alt,
        "Gift Card": "FALSE",
        "SEO Title": seo_title,
        "SEO Description": seo_desc,
        "Google Shopping / Google Product Category": "",
        "Variant Image": first_image_url,
        "Variant Weight Unit": weight_unit,
        "Variant Tax Code": "",
        "Cost per item": str(cost_per_item) if cost_per_item else "",
        "Included / United States": "TRUE",
        "Included / International": "TRUE",
        "Price / International": "",
        "Compare At Price / International": "",
        "Status": status,
    }
    rows.append(first_row)

    # 추가 이미지 행 (Handle + Image 정보만)
    for idx, img_url in enumerate(images[1:], start=2):
        img_row = {col: "" for col in CSV_COLUMNS}
        img_row["Handle"] = handle
        img_row["Image Src"] = img_url
        img_row["Image Position"] = str(idx)
        img_row["Image Alt Text"] = generate_image_alt(title, vendor, idx)
        rows.append(img_row)

    return rows


def write_csv_batch(rows, batch_num, output_dir):
    """
    CSV 배치 파일 하나를 작성
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"shopify_import_{timestamp}_batch{batch_num:03d}.csv"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    return filepath, len(rows)


def export_to_shopify_csv(input_file=INPUT_FILE, output_dir=OUTPUT_DIR, batch_size=BATCH_SIZE):
    """
    메인 내보내기 함수
    transformed_products.jsonl → Shopify CSV 파일(들)
    """
    os.makedirs(output_dir, exist_ok=True)

    # 변환된 제품 로드
    products = []
    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                products.append(json.loads(line))

    logger.info(f"로드된 제품: {len(products)}개")

    # 전체 CSV 행 생성
    all_rows = []
    product_count = 0
    image_count = 0
    seo_count = 0

    for product in products:
        rows = product_to_csv_rows(product)
        all_rows.extend(rows)
        product_count += 1
        image_count += len(rows)  # 첫 행 + 추가 이미지 행
        if rows and rows[0].get("SEO Title"):
            seo_count += 1

    logger.info(f"생성된 CSV 행: {len(all_rows)}개 (제품 {product_count}개, 이미지 행 포함)")

    # 배치 분할 & 저장
    batch_files = []
    for i in range(0, len(all_rows), batch_size):
        batch_rows = all_rows[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        filepath, row_count = write_csv_batch(batch_rows, batch_num, output_dir)
        batch_files.append((filepath, row_count))
        logger.info(f"배치 {batch_num}: {filepath} ({row_count}행)")

    # 리포트 생성
    report_lines = [
        "=" * 60,
        "Shopify CSV Export Report",
        "=" * 60,
        f"입력 파일: {input_file}",
        f"총 제품 수: {product_count}",
        f"총 CSV 행 수: {len(all_rows)}",
        f"SEO 생성: {seo_count}/{product_count}",
        f"배치 파일 수: {len(batch_files)}",
        "",
        "배치 파일 목록:",
    ]
    for fpath, count in batch_files:
        size_kb = os.path.getsize(fpath) / 1024
        report_lines.append(f"  {os.path.basename(fpath)}: {count}행, {size_kb:.1f}KB")

    report_lines.extend([
        "",
        "Shopify 임포트 방법:",
        "  1. Shopify Admin → Products → Import",
        "  2. CSV 파일 선택 (배치별로 업로드)",
        "  3. 'Overwrite products with matching handles' 체크",
        "  4. Import 클릭",
        "",
        f"생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
    ])

    report_text = "\n".join(report_lines)
    report_path = os.path.join(output_dir, "csv_export_report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    print(report_text)

    return batch_files


# ============================================================
# 실행
# ============================================================
if __name__ == "__main__":
    # 샘플 확인 모드: 첫 2개 제품의 CSV 행을 미리보기
    if os.path.exists(INPUT_FILE):
        print("=" * 60)
        print("Shopify CSV 미리보기 (첫 2개 제품)")
        print("=" * 60)

        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= 2:
                    break
                product = json.loads(line.strip())
                rows = product_to_csv_rows(product)

                print(f"\n제품 {i+1}: {product.get('title', '?')[:60]}")
                print(f"  Handle: {rows[0]['Handle']}")
                print(f"  SEO Title: {rows[0]['SEO Title']}")
                print(f"  SEO Desc: {rows[0]['SEO Description'][:100]}...")
                print(f"  Price: ${rows[0]['Variant Price']}")
                print(f"  Compare: ${rows[0]['Variant Compare At Price']}")
                print(f"  Cost: ${rows[0]['Cost per item']}")
                print(f"  SKU: {rows[0]['Variant SKU']}")
                print(f"  Images: {len(rows)}행 (1 제품행 + {len(rows)-1} 추가이미지)")
                print(f"  Tags: {rows[0]['Tags'][:80]}...")
                print(f"  Status: {rows[0]['Status']}")
                print(f"  Published: {rows[0]['Published']}")

        print("\n" + "=" * 60)
        print("전체 CSV 내보내기를 실행하시겠습니까?")
        print("실행: python exporter_csv.py --export")
        print("=" * 60)

    else:
        print(f"입력 파일 없음: {INPUT_FILE}")
        print("먼저 python transformer.py 또는 python batch_test.py를 실행하세요.")

    # --export 옵션이 있으면 전체 내보내기 실행
    import sys
    if "--export" in sys.argv:
        export_to_shopify_csv()

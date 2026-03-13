"""CSV 필터 - 가격 없는 제품만 제거"""
import csv
import os

INPUT = os.path.join("processor_output", "shopify_import_20260313_231115_batch001.csv")
OUTPUT_CLEAN = os.path.join("processor_output", "shopify_import_CLEAN.csv")
OUTPUT_REJECTED = os.path.join("processor_output", "shopify_import_REJECTED.csv")

with open(INPUT, "r", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    rows = list(reader)

clean = []
rejected = []
current_rejected = False

for row in rows:
    if row.get("Title"):
        current_rejected = False
        
        price = float(row.get("Variant Price", "0") or "0")
        cost = float(row.get("Cost per item", "0") or "0")

        if price == 0 or cost == 0:
            current_rejected = True
            print(f"REJECTED: {row['Title'][:60]}")
            if price == 0:
                print(f"          → Price is $0")
            if cost == 0:
                print(f"          → Cost is $0")

    if current_rejected:
        rejected.append(row)
    else:
        clean.append(row)

clean_count = sum(1 for r in clean if r.get("Title"))
rejected_count = sum(1 for r in rejected if r.get("Title"))

for filepath, data in [(OUTPUT_CLEAN, clean), (OUTPUT_REJECTED, rejected)]:
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in data:
            writer.writerow(row)

print(f"\n통과: {clean_count}개 → {OUTPUT_CLEAN}")
print(f"제외: {rejected_count}개 → {OUTPUT_REJECTED}")
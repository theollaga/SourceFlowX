import json, glob

f = sorted(glob.glob("collector_output/raw_*.json"))[-1]
d = json.load(open(f, "r", encoding="utf-8"))

for p in d["products"]:
    if p.get("asin") == "B0FQFB8FMG":
        print("=== AirPods Pro 3 상세 ===")
        print("price:", p.get("price"))
        print("currency:", p.get("currency"))
        print("availability:", p.get("availability"))
        print("seller:", p.get("seller"))
        print("delivery_info:", p.get("delivery_info", "")[:200])
        print("buybox 관련 meta:", p.get("meta_tags", {}).get("og:title", ""))
        break
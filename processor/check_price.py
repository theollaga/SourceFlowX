# check_price.py 내용 교체
import csv

with open('processor_output/shopify_import_CLEAN.csv', 'r', encoding='utf-8-sig') as f:
    for r in csv.DictReader(f):
        if r.get('Title'):
            cost = float(r.get('Cost per item', '0') or '0')
            price = float(r.get('Variant Price', '0') or '0')
            ptype = r.get('Type', '')
            brand = r.get('Vendor', '')

            flag = ""

            # 무명 브랜드 이어버드 $100 이상이면 의심
            KNOWN_AUDIO = ['Samsung', 'Sony', 'Beats', 'JBL', 'Bose', 'Marshall',
                           'Skullcandy', 'Soundcore', 'OnePlus', 'Raycon']
            if ptype in ['Earbud Headphones', 'On-Ear Headphones', 'Open-Ear Headphones']:
                if brand not in KNOWN_AUDIO and cost > 100:
                    flag = "*** SUSPICIOUS ***"
                if brand not in KNOWN_AUDIO and cost > 50:
                    flag = flag or "* CHECK *"

            if flag:
                print(f"{flag:20s} ${cost:>7.2f} > ${price:>7.2f}  [{brand}] {r['Title'][:50]}")

"""147개 전체 변환 테스트 + 품질 리포트"""
import json, glob, os
from transformer import transform_product

files = sorted(glob.glob(os.path.join("..", "collector", "collector_output", "raw_*.jsonl")))
if not files:
    files = sorted(glob.glob(os.path.join("collector", "collector_output", "raw_*.jsonl")))

total = 0
success = 0
errors = []
no_features = []
no_strong = 0
has_strong = 0
results = []  # 변환 결과 저장용

for fpath in files:
    with open(fpath, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            total += 1
            try:
                product = json.loads(line)
                result = transform_product(product)
                success += 1
                results.append(result)

                body = result["body_html"]
                asin = product.get("asin", "???")

                if "sfx-features" not in body:
                    no_features.append(asin)

                if "<strong>" in body:
                    has_strong += 1
                else:
                    no_strong += 1

            except Exception as e:
                errors.append(f"[{os.path.basename(fpath)}:{line_no}] {e}")

# ---- 변환된 제품 데이터 저장 ----
output_dir = "processor_output"
os.makedirs(output_dir, exist_ok=True)

# 전체 변환 결과 JSONL
output_file = os.path.join(output_dir, "transformed_products.jsonl")
with open(output_file, "w", encoding="utf-8") as f:
    for r in results:
        # 내부 참조 필드 제거 후 저장
        save = {k: v for k, v in r.items() if not k.startswith("_")}
        f.write(json.dumps(save, ensure_ascii=False) + "\n")

# ---- 리포트 생성 및 저장 ----
report_lines = []
report_lines.append("=" * 60)
report_lines.append("전체 변환 테스트 결과")
report_lines.append("=" * 60)
report_lines.append(f"총 제품: {total}")
report_lines.append(f"변환 성공: {success} ({success/total*100:.1f}%)")
report_lines.append(f"변환 실패: {len(errors)}")
report_lines.append("")
report_lines.append("헤더 감지:")
report_lines.append(f"  <strong> 있음: {has_strong}/{success} ({has_strong/success*100:.1f}%)")
report_lines.append(f"  <strong> 없음: {no_strong}/{success} ({no_strong/success*100:.1f}%)")
report_lines.append("")
report_lines.append(f"Features 섹션 없음: {len(no_features)}개")
if no_features:
    report_lines.append(f"  ASIN: {', '.join(no_features[:10])}")
if errors:
    report_lines.append("")
    report_lines.append("오류 목록:")
    for e in errors[:10]:
        report_lines.append(f"  {e}")
report_lines.append("=" * 60)
report_lines.append("")
report_lines.append(f"변환 데이터 저장: {output_file}")
report_lines.append(f"리포트 저장: {os.path.join(output_dir, 'batch_report.txt')}")

report_text = "\n".join(report_lines)

# 화면 출력
print(report_text)

# 파일 저장
report_file = os.path.join(output_dir, "batch_report.txt")
with open(report_file, "w", encoding="utf-8") as f:
    f.write(report_text)

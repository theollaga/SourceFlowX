"""
SourceFlowX - 결과 탭
수집된 상품 데이터를 테이블로 표시하고, 통계 요약,
필터링, 정렬, 상세 보기, CSV 내보내기를 제공하는 탭.
"""

import tkinter as tk
from tkinter import ttk
from tkinter import filedialog
from tkinter import messagebox
from tkinter import scrolledtext
import os
import subprocess
import platform
import json
import csv
import glob


class ResultsTab(ttk.Frame):
    """
    결과 탭 프레임.

    수집 완료된 상품 목록을 Treeview로 표시하고,
    통계 요약, 키워드/상태 필터, 컬럼 정렬, 상세 팝업,
    CSV 내보내기, output 폴더 열기 등을 제공한다.
    """

    def __init__(self, parent):
        # type: (tk.Widget) -> None
        """
        결과 탭을 초기화한다.

        Args:
            parent: 부모 위젯 (Notebook).
        """
        super().__init__(parent)
        self.all_products = []
        self.passed_products = []
        self.rejected_products = []
        self._sort_reverse = {}  # 컬럼별 정렬 방향
        self._create_widgets()

    def _create_widgets(self):
        # type: () -> None
        """통계, 필터, 테이블, 버튼 영역을 배치한다."""
        # ── 상단: 통계 요약 ──
        self._create_stats_section()

        # ── 상단: 필터 ──
        self._create_filter_section()

        # ── 탈락 사유 요약 ──
        self._create_reject_summary_section()

        # ── 중간: 상품 테이블 ──
        self._create_table_section()

        # ── 하단: 버튼 ──
        self._create_buttons_section()

    # ================================================================
    # 통계 요약
    # ================================================================

    def _create_stats_section(self):
        # type: () -> None
        """수집 결과 통계 카드들을 생성한다."""
        section = ttk.LabelFrame(self, text="수집 결과 요약", padding=10)
        section.pack(fill="x", padx=10, pady=5)

        cards = [
            ("전체 수집", "lbl_total", "0", "#333333"),
            ("통과", "lbl_passed", "0", "#28a745"),
            ("탈락", "lbl_rejected", "0", "#dc3545"),
            ("통과율", "lbl_pass_rate", "0%", "#007bff"),
            ("총 이미지", "lbl_images", "0", "#6f42c1"),
        ]

        for label_text, attr_name, default, color in cards:
            card = ttk.Frame(section)
            card.pack(side="left", fill="x", expand=True, padx=5)

            ttk.Label(card, text=label_text, font=("Segoe UI", 9)).pack()

            lbl = tk.Label(card, text=default, font=("Segoe UI", 18, "bold"), fg=color)
            lbl.pack()
            setattr(self, attr_name, lbl)

    # ================================================================
    # 필터
    # ================================================================

    def _create_filter_section(self):
        # type: () -> None
        """키워드 및 상태 필터 콤보박스를 생성한다."""
        filter_frame = ttk.Frame(self)
        filter_frame.pack(fill="x", padx=10, pady=2)

        # 키워드 필터
        ttk.Label(filter_frame, text="키워드 필터:", font=("Segoe UI", 9)).pack(
            side="left", padx=(5, 2)
        )

        self.keyword_filter_var = tk.StringVar(value="전체")
        self.keyword_filter = ttk.Combobox(
            filter_frame,
            textvariable=self.keyword_filter_var,
            values=["전체"],
            state="readonly",
            width=25,
        )
        self.keyword_filter.pack(side="left", padx=(0, 15))
        self.keyword_filter.bind("<<ComboboxSelected>>", self._filter_products)

        # 상태 필터
        ttk.Label(filter_frame, text="상태 필터:", font=("Segoe UI", 9)).pack(
            side="left", padx=(5, 2)
        )

        self.status_filter_var = tk.StringVar(value="전체")
        self.status_filter = ttk.Combobox(
            filter_frame,
            textvariable=self.status_filter_var,
            values=["전체", "통과", "탈락"],
            state="readonly",
            width=10,
        )
        self.status_filter.pack(side="left", padx=(0, 5))
        self.status_filter.bind("<<ComboboxSelected>>", self._filter_products)

        # 필터된 건수 라벨
        self.lbl_filter_count = ttk.Label(filter_frame, text="", font=("Segoe UI", 9))
        self.lbl_filter_count.pack(side="right", padx=5)

    # ================================================================
    # 탈락 사유 요약
    # ================================================================

    def _create_reject_summary_section(self):
        # type: () -> None
        """탈락 사유 분석 텍스트 영역을 생성한다."""
        section = ttk.LabelFrame(self, text="탈락 사유 분석", padding=5)
        section.pack(fill="x", padx=10, pady=2)

        self.reject_text = tk.Text(
            section,
            height=2,
            state="disabled",
            wrap="word",
            font=("Segoe UI", 9),
            relief="flat",
        )
        self.reject_text.pack(fill="x")

    # ================================================================
    # 상품 테이블
    # ================================================================

    def _create_table_section(self):
        # type: () -> None
        """상품 목록 Treeview와 스크롤바를 생성한다."""
        section = ttk.LabelFrame(self, text="상품 목록", padding=5)
        section.pack(fill="both", expand=True, padx=10, pady=2)

        # Treeview
        columns = (
            "num",
            "asin",
            "title",
            "price",
            "rating",
            "reviews",
            "images",
            "brand",
            "status",
        )
        self.tree = ttk.Treeview(
            section, columns=columns, show="headings", selectmode="extended", height=12
        )

        headings = {
            "num": ("#", 40),
            "asin": ("ASIN", 100),
            "title": ("제목", 350),
            "price": ("가격($)", 70),
            "rating": ("평점", 50),
            "reviews": ("리뷰", 70),
            "images": ("이미지", 50),
            "brand": ("브랜드", 100),
            "status": ("상태", 60),
        }

        for col, (text, width) in headings.items():
            anchor = "w" if col == "title" else "center"
            self.tree.heading(
                col,
                text=text,
                command=lambda c=col: self._sort_by_column(
                    c, self._sort_reverse.get(c, False)
                ),
            )
            self.tree.column(col, width=width, anchor=anchor)
            self._sort_reverse[col] = False

        # 행 색상 태그
        self.tree.tag_configure("passed", background="#d4edda")
        self.tree.tag_configure("rejected", background="#f8d7da")

        # 스크롤바
        y_scroll = ttk.Scrollbar(section, orient="vertical", command=self.tree.yview)
        x_scroll = ttk.Scrollbar(section, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        section.rowconfigure(0, weight=1)
        section.columnconfigure(0, weight=1)

        # 더블클릭 이벤트
        self.tree.bind("<Double-1>", self._show_product_detail)

    # ================================================================
    # 하단 버튼
    # ================================================================

    def _create_buttons_section(self):
        # type: () -> None
        """하단 액션 버튼들을 생성한다."""
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=10, pady=5)

        ttk.Button(
            btn_frame,
            text="output 폴더 열기",
            width=15,
            command=self.open_output_folder,
        ).pack(side="left", padx=2)

        ttk.Button(
            btn_frame, text="통합 CSV 열기", width=15, command=self.open_csv
        ).pack(side="left", padx=2)

        ttk.Button(
            btn_frame,
            text="품질 리포트 보기",
            width=15,
            command=self.show_quality_report,
        ).pack(side="left", padx=2)

        ttk.Button(
            btn_frame, text="결과 새로고침", width=15, command=self.load_from_files
        ).pack(side="left", padx=2)

        ttk.Button(
            btn_frame,
            text="선택 상품 CSV 내보내기",
            width=20,
            command=self.export_selected_csv,
        ).pack(side="right", padx=2)

    # ================================================================
    # 데이터 로드
    # ================================================================

    def load_results(self, passed, rejected, all_products):
        # type: (list, list, list) -> None
        """
        외부에서 호출하여 결과 데이터를 설정한다.

        Args:
            passed: 통과 상품 리스트.
            rejected: 탈락 상품 리스트.
            all_products: 전체 상품 리스트.
        """
        self.passed_products = passed
        self.rejected_products = rejected
        self.all_products = all_products

        self._update_statistics()
        self._update_reject_summary()
        self._update_keyword_filter()
        self._populate_table()

    def load_from_files(self):
        # type: () -> None
        """
        output 폴더에서 JSON 결과 파일들을 읽어 결과를 로드한다.

        products_backup_*.json 파일들을 자동 감지하여 병합한다.
        """
        output_dir = os.path.abspath("output")

        if not os.path.exists(output_dir):
            messagebox.showinfo("알림", "output 폴더가 존재하지 않습니다.")
            return

        all_products = []
        passed = []
        rejected = []

        # products_backup 파일들 검색
        backup_pattern = os.path.join(output_dir, "products_backup_*.json")
        backup_files = glob.glob(backup_pattern)

        # 일반 products 파일들
        product_pattern = os.path.join(output_dir, "products_*.json")
        product_files = glob.glob(product_pattern)

        json_files = list(set(backup_files + product_files))

        if not json_files:
            messagebox.showinfo("알림", "output 폴더에 결과 파일이 없습니다.")
            return

        for filepath in json_files:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if isinstance(data, list):
                    all_products.extend(data)
                elif isinstance(data, dict):
                    if "products" in data:
                        all_products.extend(data["products"])
                    elif "passed" in data:
                        passed.extend(data.get("passed", []))
                        rejected.extend(data.get("rejected", []))
                        all_products.extend(
                            data.get("passed", []) + data.get("rejected", [])
                        )

            except Exception as e:
                pass  # 파싱 실패한 파일은 무시

        # 품질 리포트에서 탈락 정보 보완
        report_pattern = os.path.join(output_dir, "quality_report_*.json")
        report_files = glob.glob(report_pattern)

        for filepath in report_files:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    report = json.load(f)

                if isinstance(report, dict):
                    rj = report.get("rejected", [])
                    if rj and not rejected:
                        rejected = rj

            except Exception:
                pass

        # 통과/탈락 분류 (구분 정보가 없으면 전체를 통과로)
        if not passed and not rejected:
            passed = all_products

        self.load_results(passed, rejected, all_products)

        messagebox.showinfo(
            "로드 완료",
            "{}개 파일에서 {}개 상품을 로드했습니다.".format(
                len(json_files), len(all_products)
            ),
        )

    # ================================================================
    # 통계 / 탈락 사유
    # ================================================================

    def _update_statistics(self):
        # type: () -> None
        """통계 라벨들을 업데이트한다."""
        total = len(self.all_products)
        passed = len(self.passed_products)
        rejected = len(self.rejected_products)
        rate = "{:.0f}%".format((passed / total * 100) if total > 0 else 0)

        total_images = sum(p.get("image_count", 0) for p in self.all_products)

        self.lbl_total.configure(text=str(total))
        self.lbl_passed.configure(text=str(passed))
        self.lbl_rejected.configure(text=str(rejected))
        self.lbl_pass_rate.configure(text=rate)
        self.lbl_images.configure(text=str(total_images))

    def _update_reject_summary(self):
        # type: () -> None
        """탈락 사유를 집계하여 텍스트 위젯에 표시한다."""
        reasons = {}

        for p in self.rejected_products:
            # _reject_reasons 필드 또는 _reasons 필드
            product_reasons = p.get("_reject_reasons", p.get("_reasons", []))

            if isinstance(product_reasons, str):
                product_reasons = [product_reasons]

            for reason in product_reasons:
                reasons[reason] = reasons.get(reason, 0) + 1

        self.reject_text.configure(state="normal")
        self.reject_text.delete("1.0", "end")

        if reasons:
            parts = [
                "{}: {}건".format(reason, count)
                for reason, count in sorted(
                    reasons.items(), key=lambda x: x[1], reverse=True
                )
            ]
            self.reject_text.insert("1.0", " | ".join(parts))
        else:
            if self.rejected_products:
                self.reject_text.insert(
                    "1.0",
                    "탈락 {}건 (상세 사유 정보 없음)".format(
                        len(self.rejected_products)
                    ),
                )
            else:
                self.reject_text.insert("1.0", "탈락 없음")

        self.reject_text.configure(state="disabled")

    def _update_keyword_filter(self):
        # type: () -> None
        """상품 데이터에서 키워드 목록을 추출하여 필터 콤보박스를 업데이트한다."""
        keywords = set()
        for p in self.all_products:
            kw = p.get("_keyword", p.get("_tags", ""))
            if isinstance(kw, list):
                for k in kw:
                    keywords.add(str(k))
            elif kw:
                keywords.add(str(kw))

        values = ["전체"] + sorted(keywords)
        self.keyword_filter.configure(values=values)
        self.keyword_filter_var.set("전체")

    # ================================================================
    # 테이블 채우기 / 필터링
    # ================================================================

    def _populate_table(self):
        # type: () -> None
        """현재 필터에 맞는 상품으로 Treeview를 채운다."""
        # 기존 삭제
        for item in self.tree.get_children():
            self.tree.delete(item)

        # 필터 적용
        products = self._get_filtered_products()

        # 통과/탈락 ASIN 세트
        passed_asins = set(p.get("asin", "") for p in self.passed_products)

        for i, p in enumerate(products):
            asin = p.get("asin", "")
            title = p.get("title", p.get("detail_title", ""))
            if len(title) > 60:
                title = title[:57] + "..."

            price = p.get("price", "")
            rating = p.get("rating", p.get("detail_rating", ""))
            reviews = p.get("reviews_count", "")
            images = p.get("image_count", 0)
            brand = p.get("brand", p.get("detail_brand", ""))

            if asin in passed_asins:
                status = "통과"
                tag = "passed"
            elif p in self.rejected_products:
                status = "탈락"
                tag = "rejected"
            else:
                status = "통과"
                tag = "passed"

            self.tree.insert(
                "",
                "end",
                values=(
                    i + 1,
                    asin,
                    title,
                    price,
                    rating,
                    reviews,
                    images,
                    brand,
                    status,
                ),
                tags=(tag,),
            )

        # 필터 건수 업데이트
        self.lbl_filter_count.configure(text="표시: {}건".format(len(products)))

    def _get_filtered_products(self):
        # type: () -> list
        """
        현재 필터 조합에 맞는 상품 리스트를 반환한다.

        Returns:
            list: 필터링된 상품 리스트.
        """
        kw_filter = self.keyword_filter_var.get()
        status_filter = self.status_filter_var.get()

        # 상태 필터
        if status_filter == "통과":
            products = list(self.passed_products)
        elif status_filter == "탈락":
            products = list(self.rejected_products)
        else:
            products = list(self.all_products)

        # 키워드 필터
        if kw_filter != "전체":
            filtered = []
            for p in products:
                kw = p.get("_keyword", p.get("_tags", ""))
                if isinstance(kw, list):
                    if kw_filter in kw:
                        filtered.append(p)
                elif str(kw) == kw_filter:
                    filtered.append(p)
            products = filtered

        return products

    def _filter_products(self, event=None):
        # type: (tk.Event) -> None
        """필터 변경 이벤트 핸들러. 테이블을 다시 채운다."""
        self._populate_table()

    # ================================================================
    # 정렬
    # ================================================================

    def _sort_by_column(self, col, reverse):
        # type: (str, bool) -> None
        """
        지정 컬럼 기준으로 Treeview를 정렬한다.

        숫자 컬럼은 숫자 정렬, 문자 컬럼은 문자열 정렬.
        클릭할 때마다 오름차순/내림차순 토글.

        Args:
            col: 정렬 기준 컬럼 ID.
            reverse: True이면 내림차순.
        """
        numeric_cols = {"num", "price", "rating", "reviews", "images"}

        data = []
        for item_id in self.tree.get_children():
            values = self.tree.item(item_id, "values")
            tags = self.tree.item(item_id, "tags")
            col_index = list(self.tree["columns"]).index(col)
            val = values[col_index]

            if col in numeric_cols:
                try:
                    sort_key = float(str(val).replace(",", ""))
                except (ValueError, TypeError):
                    sort_key = -1 if reverse else float("inf")
            else:
                sort_key = str(val).lower()

            data.append((sort_key, item_id, values, tags))

        data.sort(key=lambda x: x[0], reverse=reverse)

        for i, (_, item_id, values, tags) in enumerate(data):
            self.tree.delete(item_id)

        for i, (_, _, values, tags) in enumerate(data):
            # 행 번호 재할당
            new_values = list(values)
            new_values[0] = i + 1
            self.tree.insert("", "end", values=new_values, tags=tags)

        # 방향 토글
        self._sort_reverse[col] = not reverse

    # ================================================================
    # 상세 팝업
    # ================================================================

    def _show_product_detail(self, event):
        # type: (tk.Event) -> None
        """
        더블클릭한 상품의 상세 정보를 팝업으로 표시한다.

        Args:
            event: 더블클릭 이벤트.
        """
        selected = self.tree.selection()
        if not selected:
            return

        item = selected[0]
        values = self.tree.item(item, "values")
        asin = values[1]

        # 전체 상품에서 해당 ASIN 찾기
        product = None
        for p in self.all_products:
            if p.get("asin") == asin:
                product = p
                break

        if product is None:
            return

        # 팝업 생성
        popup = tk.Toplevel(self)
        popup.title("상품 상세 - {}".format(asin))
        popup.geometry("500x450")
        popup.resizable(True, True)
        popup.grab_set()

        content = scrolledtext.ScrolledText(
            popup, wrap="word", font=("Segoe UI", 10), state="normal"
        )
        content.pack(fill="both", expand=True, padx=10, pady=10)

        # 상세 정보 구성
        lines = [
            "ASIN: {}".format(product.get("asin", "")),
            "",
            "제목: {}".format(product.get("detail_title", product.get("title", ""))),
            "브랜드: {}".format(product.get("detail_brand", product.get("brand", ""))),
            "",
            "가격: ${} {}".format(
                product.get("price", ""), product.get("currency", "")
            ),
            "원래 가격: ${}".format(product.get("original_price", "-")),
            "평점: {}".format(product.get("detail_rating", product.get("rating", ""))),
            "리뷰 수: {}".format(product.get("reviews_count", "")),
            "",
            "이미지 수: {}".format(product.get("image_count", 0)),
            "Prime: {}".format("예" if product.get("prime") else "아니오"),
            "",
            "URL: https://www.amazon.com/dp/{}".format(product.get("asin", "")),
            "",
            "─── 설명 미리보기 ───",
            (product.get("description", "")[:500] or "(설명 없음)"),
        ]

        # 탈락 사유
        reasons = product.get("_reject_reasons", product.get("_reasons", []))
        if reasons:
            lines.append("")
            lines.append("─── 탈락 사유 ───")
            if isinstance(reasons, list):
                for r in reasons:
                    lines.append("• {}".format(r))
            else:
                lines.append("• {}".format(reasons))

        content.insert("1.0", "\n".join(lines))
        content.configure(state="disabled")

        # 닫기 버튼
        ttk.Button(popup, text="닫기", width=10, command=popup.destroy).pack(
            pady=(0, 10)
        )

    # ================================================================
    # 외부 프로그램 열기
    # ================================================================

    def open_output_folder(self):
        # type: () -> None
        """output 폴더를 시스템 탐색기에서 연다."""
        path = os.path.abspath("output")

        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)

        try:
            system = platform.system()
            if system == "Windows":
                os.startfile(path)
            elif system == "Darwin":
                subprocess.run(["open", path])
            else:
                subprocess.run(["xdg-open", path])
        except Exception as e:
            messagebox.showerror("오류", "폴더를 열 수 없습니다:\n{}".format(e))

    def open_csv(self):
        # type: () -> None
        """통합 CSV 파일을 기본 프로그램으로 연다."""
        output_dir = os.path.abspath("output")

        # shopify_import_all.csv 우선 시도
        csv_path = os.path.join(output_dir, "shopify_import_all.csv")

        if not os.path.exists(csv_path):
            # 가장 최근 CSV 파일 찾기
            csv_files = glob.glob(os.path.join(output_dir, "*.csv"))
            if csv_files:
                csv_path = max(csv_files, key=os.path.getmtime)
            else:
                messagebox.showinfo("알림", "output 폴더에 CSV 파일이 없습니다.")
                return

        try:
            system = platform.system()
            if system == "Windows":
                os.startfile(csv_path)
            elif system == "Darwin":
                subprocess.run(["open", csv_path])
            else:
                subprocess.run(["xdg-open", csv_path])
        except Exception as e:
            messagebox.showerror("오류", "CSV 파일을 열 수 없습니다:\n{}".format(e))

    def show_quality_report(self):
        # type: () -> None
        """품질 리포트 JSON을 팝업으로 표시한다."""
        output_dir = os.path.abspath("output")
        pattern = os.path.join(output_dir, "quality_report_*.json")
        report_files = glob.glob(pattern)

        if not report_files:
            messagebox.showinfo("알림", "output 폴더에 품질 리포트 파일이 없습니다.")
            return

        # 가장 최근 파일
        latest = max(report_files, key=os.path.getmtime)

        try:
            with open(latest, "r", encoding="utf-8") as f:
                report = json.load(f)
        except Exception as e:
            messagebox.showerror("오류", "리포트 파일 읽기 실패:\n{}".format(e))
            return

        # 팝업
        popup = tk.Toplevel(self)
        popup.title("품질 리포트 - {}".format(os.path.basename(latest)))
        popup.geometry("600x500")
        popup.grab_set()

        content = scrolledtext.ScrolledText(
            popup, wrap="word", font=("Consolas", 9), state="normal"
        )
        content.pack(fill="both", expand=True, padx=10, pady=10)

        # 보기 좋은 형식으로 표시
        if isinstance(report, dict):
            lines = []
            summary = report.get("summary", {})
            if summary:
                lines.append("═══ 요약 ═══")
                for key, val in summary.items():
                    lines.append("  {}: {}".format(key, val))
                lines.append("")

            checks = report.get("checks", {})
            if checks:
                lines.append("═══ 검사 결과 ═══")
                for check_name, result in checks.items():
                    if isinstance(result, dict):
                        lines.append(
                            "  {} - 탈락: {}건".format(
                                check_name, result.get("rejected", 0)
                            )
                        )
                    else:
                        lines.append("  {}: {}".format(check_name, result))
                lines.append("")

            if not lines:
                lines.append(json.dumps(report, ensure_ascii=False, indent=2))

            content.insert("1.0", "\n".join(lines))
        else:
            content.insert("1.0", json.dumps(report, ensure_ascii=False, indent=2))

        content.configure(state="disabled")

        ttk.Button(popup, text="닫기", width=10, command=popup.destroy).pack(
            pady=(0, 10)
        )

    # ================================================================
    # CSV 내보내기
    # ================================================================

    def export_selected_csv(self):
        # type: () -> None
        """Treeview에서 선택된 상품을 CSV 파일로 내보낸다."""
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo(
                "알림", "내보낼 상품을 선택해주세요.\n" "(Ctrl+클릭으로 다중 선택 가능)"
            )
            return

        # 선택된 ASIN 수집
        selected_asins = set()
        for item in selected:
            values = self.tree.item(item, "values")
            selected_asins.add(values[1])  # ASIN 컬럼

        # 전체 상품에서 매칭
        export_products = [
            p for p in self.all_products if p.get("asin") in selected_asins
        ]

        if not export_products:
            messagebox.showinfo("알림", "내보낼 데이터가 없습니다.")
            return

        filepath = filedialog.asksaveasfilename(
            title="CSV 내보내기",
            defaultextension=".csv",
            initialdir="output",
            filetypes=[("CSV 파일", "*.csv"), ("모든 파일", "*.*")],
        )

        if not filepath:
            return

        try:
            # Shopify 형식 CSV 헤더
            headers = [
                "Handle",
                "Title",
                "Body (HTML)",
                "Vendor",
                "Type",
                "Tags",
                "Published",
                "Option1 Name",
                "Option1 Value",
                "Variant SKU",
                "Variant Price",
                "Variant Compare At Price",
                "Image Src",
                "Image Position",
                "SEO Title",
                "SEO Description",
            ]

            with open(filepath, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(headers)

                for p in export_products:
                    asin = p.get("asin", "")
                    title = p.get("detail_title", p.get("title", ""))
                    desc = p.get("description", "")
                    brand = p.get("detail_brand", p.get("brand", ""))
                    price = p.get("price", "")
                    images = p.get("all_images", [])
                    main_img = images[0] if images else p.get("main_image", "")

                    writer.writerow(
                        [
                            asin,
                            title,
                            desc,
                            brand,
                            "",
                            "",
                            "TRUE",
                            "Title",
                            "Default Title",
                            asin,
                            price,
                            "",
                            main_img,
                            "1",
                            title[:70] if title else "",
                            desc[:160] if desc else "",
                        ]
                    )

                    # 추가 이미지
                    for idx, img in enumerate(images[1:], start=2):
                        writer.writerow(
                            [
                                asin,
                                "",
                                "",
                                "",
                                "",
                                "",
                                "",
                                "",
                                "",
                                "",
                                "",
                                "",
                                img,
                                str(idx),
                                "",
                                "",
                            ]
                        )

            messagebox.showinfo(
                "내보내기 완료",
                "{}개 상품을 CSV로 내보냈습니다:\n{}".format(
                    len(export_products), filepath
                ),
            )

        except Exception as e:
            messagebox.showerror("내보내기 실패", "CSV 저장 중 오류:\n{}".format(e))

"""
SourceFlowX - 설정 탭
스크래핑 설정(키워드, 페이지 수, 품질 필터, HTTP, 출력 등)을
GUI로 관리하는 탭. 설정 저장/불러오기/기본값 복원을 지원한다.
"""

# pyre-unsafe

import tkinter as tk
from tkinter import ttk
from tkinter import filedialog
from tkinter import messagebox
import json
import os


class SettingsTab(ttk.Frame):
    """
    설정 탭 프레임.

    6개 섹션(키워드, 스크래핑, 가격, 품질, HTTP, 출력)으로 구성되며,
    스크롤 가능한 캔버스 위에 배치된다.
    get_settings() / set_settings()로 config.py 변수와 연동한다.
    """

    # 기본값 상수
    DEFAULTS = {
        "CATEGORY_KEYWORDS": [],
        "MAX_PAGES": 20,
        "ENRICH_LIMIT": "",
        "MAX_WORKERS": 5,
        "CHECKPOINT_INTERVAL": 100,
        "MARGIN_PERCENT": 30.0,
        "COMPARE_PRICE_MARKUP": 1.2,
        "MIN_PRICE": 5.0,
        "MAX_PRICE": 500.0,
        "MIN_RATING": 3.5,
        "MIN_REVIEWS": 10,
        "MIN_IMAGES": 1,
        "MIN_TITLE_LENGTH": 10,
        "REQUEST_TIMEOUT": 25,
        "MAX_RETRIES": 3,
        "RETRY_BACKOFF": 5,
        "DELAY_MIN": 3.0,
        "DELAY_MAX": 7.0,
        "KEYWORD_DELAY": 10,
        "IMPERSONATE": "chrome119",
        "MERGE_CSV": True,
        "OUTPUT_DIR": "output",
    }

    def __init__(self, parent):
        # type: (tk.Widget) -> None
        """
        설정 탭을 초기화한다.

        Args:
            parent: 부모 위젯 (Notebook).
        """
        super().__init__(parent)
        self._create_widgets()

    def _create_widgets(self):
        # type: () -> None
        """설정 탭 위젯을 생성합니다. 스크롤 가능한 구조."""
        # 스크롤 가능한 Canvas 생성
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(
            self, orient="vertical", command=self.canvas.yview
        )
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )

        self.canvas_window = self.canvas.create_window(
            (0, 0), window=self.scrollable_frame, anchor="nw"
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        # Canvas 크기에 맞게 내부 프레임 너비 조절
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # 마우스 휠 바인딩
        self.canvas.bind("<Enter>", self._bind_mousewheel)
        self.canvas.bind("<Leave>", self._unbind_mousewheel)

        # 레이아웃
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # 기존 위젯들을 self.scrollable_frame에 생성
        self._create_keyword_section(self.scrollable_frame)
        self._create_scraping_section(self.scrollable_frame)
        self._create_price_settings(self.scrollable_frame)
        self._create_quality_section(self.scrollable_frame)
        self._create_http_section(self.scrollable_frame)
        self._create_output_section(self.scrollable_frame)
        self._create_bottom_buttons(self.scrollable_frame)

    def _on_canvas_configure(self, event):
        # type: (tk.Event) -> None
        """Canvas 크기 변경 시 내부 프레임 너비를 맞춥니다."""
        self.canvas.itemconfig(self.canvas_window, width=event.width)

    def _bind_mousewheel(self, event):
        # type: (tk.Event) -> None
        """마우스가 Canvas 위에 있을 때 휠 스크롤을 바인딩합니다."""
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, event):
        # type: (tk.Event) -> None
        """마우스가 Canvas를 벗어나면 휠 스크롤을 해제합니다."""
        self.canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event):
        # type: (tk.Event) -> None
        """마우스 휠 스크롤을 처리합니다."""
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ================================================================
    # 섹션 1: 키워드 설정
    # ================================================================

    def _create_keyword_section(self, parent):
        # type: (ttk.Frame) -> None
        """검색 키워드 입력/관리 섹션을 생성한다."""
        section = ttk.LabelFrame(
            parent,
            text="검색 키워드 (URL 스크래핑 시 '키워드::https://...' 형식)",
            padding=10,
        )
        section.pack(fill="x", padx=10, pady=5)

        # Listbox + 스크롤바
        list_frame = ttk.Frame(section)
        list_frame.pack(fill="x", pady=(0, 5))

        self.keyword_listbox = tk.Listbox(
            list_frame, height=6, width=40, selectmode="single", font=("Segoe UI", 10)
        )
        list_scrollbar = ttk.Scrollbar(
            list_frame, orient="vertical", command=self.keyword_listbox.yview
        )
        self.keyword_listbox.configure(yscrollcommand=list_scrollbar.set)

        self.keyword_listbox.pack(side="left", fill="x", expand=True)
        list_scrollbar.pack(side="right", fill="y")

        # 입력 + 버튼
        input_frame = ttk.Frame(section)
        input_frame.pack(fill="x")

        self.keyword_entry = ttk.Entry(input_frame, font=("Segoe UI", 10))
        self.keyword_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.keyword_entry.bind("<Return>", lambda e: self.add_keyword())

        ttk.Button(input_frame, text="추가", width=8, command=self.add_keyword).pack(
            side="left", padx=2
        )

        ttk.Button(input_frame, text="삭제", width=8, command=self.remove_keyword).pack(
            side="left", padx=2
        )

        ttk.Button(
            input_frame, text="전체 삭제", width=10, command=self.clear_keywords
        ).pack(side="left", padx=2)

    # ================================================================
    # 섹션 2: 스크래핑 설정
    # ================================================================

    def _create_scraping_section(self, parent):
        # type: (ttk.Frame) -> None
        """스크래핑 관련 설정 섹션을 생성한다."""
        section = ttk.LabelFrame(parent, text="스크래핑 설정", padding=10)
        section.pack(fill="x", padx=10, pady=5)

        # 페이지 수 (Scale)
        row = 0
        ttk.Label(section, text="페이지 수:").grid(
            row=row, column=0, sticky="w", padx=5, pady=3
        )
        self.pages_var = tk.IntVar(value=self.DEFAULTS["MAX_PAGES"])
        self.pages_label = ttk.Label(
            section, text=str(self.DEFAULTS["MAX_PAGES"]), width=5
        )
        self.pages_label.grid(row=row, column=2, padx=5)
        self.pages_scale = ttk.Scale(
            section,
            from_=1,
            to=50,
            orient="horizontal",
            variable=self.pages_var,
            command=lambda v: self.pages_label.configure(text=str(int(float(v)))),
        )
        self.pages_scale.grid(row=row, column=1, sticky="we", padx=5, pady=3)

        # 수집 제한
        row += 1
        ttk.Label(section, text="수집 제한 (빈칸=전체):").grid(
            row=row, column=0, sticky="w", padx=5, pady=3
        )
        self.enrich_limit_var = tk.StringVar(value=str(self.DEFAULTS["ENRICH_LIMIT"]))
        ttk.Entry(section, textvariable=self.enrich_limit_var, width=15).grid(
            row=row, column=1, sticky="w", padx=5, pady=3
        )

        # 병렬 워커
        row += 1
        ttk.Label(section, text="병렬 워커:").grid(
            row=row, column=0, sticky="w", padx=5, pady=3
        )
        self.workers_var = tk.IntVar(value=self.DEFAULTS["MAX_WORKERS"])
        ttk.Spinbox(
            section, from_=1, to=20, textvariable=self.workers_var, width=10
        ).grid(row=row, column=1, sticky="w", padx=5, pady=3)

        # 체크포인트 간격
        row += 1
        ttk.Label(section, text="체크포인트 간격:").grid(
            row=row, column=0, sticky="w", padx=5, pady=3
        )
        self.checkpoint_var = tk.IntVar(value=self.DEFAULTS["CHECKPOINT_INTERVAL"])
        ttk.Spinbox(
            section,
            from_=10,
            to=500,
            increment=10,
            textvariable=self.checkpoint_var,
            width=10,
        ).grid(row=row, column=1, sticky="w", padx=5, pady=3)

        section.columnconfigure(1, weight=1)

    # ================================================================
    # 섹션 3: 가격 설정
    # ================================================================

    def _create_price_settings(self, parent):
        # type: (ttk.Frame) -> None
        """가격 계산 방식, 라운딩, Compare At, 미리보기 섹션을 생성한다."""
        section = ttk.LabelFrame(parent, text="Price Settings", padding=10)
        section.pack(fill="x", padx=10, pady=5)

        # ── 하위 호환용 변수 (기존 get_settings에서 참조) ──
        self.margin_var = tk.StringVar(value=str(self.DEFAULTS["MARGIN_PERCENT"]))
        self.markup_var = tk.StringVar(value=str(self.DEFAULTS["COMPARE_PRICE_MARKUP"]))

        row = 0

        # ── 가격 계산 방식 ──
        ttk.Label(section, text="가격 계산 방식", font=("Segoe UI", 9, "bold")).grid(
            row=row, column=0, columnspan=3, sticky="w", padx=5, pady=(5, 2)
        )
        row += 1

        self.price_method_var = tk.StringVar(value="multiplier")
        self.price_method_var.trace_add("write", self._on_price_method_change)

        # Multiplier
        ttk.Radiobutton(
            section,
            text="Multiplier (Amazon Price × 배수)",
            variable=self.price_method_var,
            value="multiplier",
        ).grid(row=row, column=0, sticky="w", padx=(20, 5), pady=2)
        self.multiplier_var = tk.DoubleVar(value=2.5)
        self.multiplier_entry = ttk.Spinbox(
            section,
            textvariable=self.multiplier_var,
            from_=1.0,
            to=10.0,
            increment=0.1,
            width=8,
        )
        self.multiplier_entry.grid(row=row, column=1, sticky="w", padx=5, pady=2)
        self.multiplier_var.trace_add("write", self._update_price_preview)
        row += 1

        # Margin on Cost
        ttk.Radiobutton(
            section,
            text="Margin on Cost % (원가 기준 마진율)",
            variable=self.price_method_var,
            value="margin_cost",
        ).grid(row=row, column=0, sticky="w", padx=(20, 5), pady=2)
        self.margin_cost_var = tk.DoubleVar(value=150.0)
        self.margin_cost_entry = ttk.Spinbox(
            section,
            textvariable=self.margin_cost_var,
            from_=1.0,
            to=1000.0,
            increment=5.0,
            width=8,
        )
        self.margin_cost_entry.grid(row=row, column=1, sticky="w", padx=5, pady=2)
        ttk.Label(section, text="%").grid(row=row, column=2, sticky="w", padx=0, pady=2)
        self.margin_cost_var.trace_add("write", self._update_price_preview)
        row += 1

        # Margin on Price
        ttk.Radiobutton(
            section,
            text="Margin on Price % (판매가 기준 마진율)",
            variable=self.price_method_var,
            value="margin_price",
        ).grid(row=row, column=0, sticky="w", padx=(20, 5), pady=2)
        self.margin_price_var = tk.DoubleVar(value=60.0)
        self.margin_price_entry = ttk.Spinbox(
            section,
            textvariable=self.margin_price_var,
            from_=1.0,
            to=99.0,
            increment=1.0,
            width=8,
        )
        self.margin_price_entry.grid(row=row, column=1, sticky="w", padx=5, pady=2)
        ttk.Label(section, text="%").grid(row=row, column=2, sticky="w", padx=0, pady=2)
        self.margin_price_var.trace_add("write", self._update_price_preview)
        row += 1

        # Fixed Markup
        ttk.Radiobutton(
            section,
            text="Fixed Markup (고정 금액 추가)",
            variable=self.price_method_var,
            value="fixed_markup",
        ).grid(row=row, column=0, sticky="w", padx=(20, 5), pady=2)
        self.fixed_markup_var = tk.DoubleVar(value=15.0)
        self.fixed_markup_entry = ttk.Spinbox(
            section,
            textvariable=self.fixed_markup_var,
            from_=0.0,
            to=500.0,
            increment=1.0,
            width=8,
        )
        self.fixed_markup_entry.grid(row=row, column=1, sticky="w", padx=5, pady=2)
        ttk.Label(section, text="$").grid(row=row, column=2, sticky="w", padx=0, pady=2)
        self.fixed_markup_var.trace_add("write", self._update_price_preview)
        row += 1

        # Tiered Markup
        ttk.Radiobutton(
            section,
            text="Tiered Markup (가격대별 차등 배수)",
            variable=self.price_method_var,
            value="tiered",
        ).grid(row=row, column=0, sticky="w", padx=(20, 5), pady=2)
        self.tiered_label = ttk.Label(
            section,
            text="$0-20: ×3.0 | $20-50: ×2.5 | $50-100: ×2.0 | $100+: ×1.6",
            font=("", 8),
            foreground="gray",
        )
        self.tiered_label.grid(
            row=row, column=1, columnspan=2, sticky="w", padx=5, pady=2
        )
        row += 1

        # ── 구분선 ──
        ttk.Separator(section, orient="horizontal").grid(
            row=row, column=0, columnspan=3, sticky="ew", padx=5, pady=8
        )
        row += 1

        # ── Compare At Price 배수 ──
        ttk.Label(section, text="Compare At Price Markup (판매가 × 배수)").grid(
            row=row, column=0, sticky="w", padx=5, pady=3
        )
        self.compare_at_markup_var = tk.DoubleVar(value=1.4)
        ttk.Spinbox(
            section,
            textvariable=self.compare_at_markup_var,
            from_=1.0,
            to=3.0,
            increment=0.1,
            width=8,
        ).grid(row=row, column=1, sticky="w", padx=5, pady=3)
        self.compare_at_markup_var.trace_add("write", self._update_price_preview)
        row += 1

        # ── Price Rounding ──
        ttk.Label(section, text="Price Rounding", font=("Segoe UI", 9, "bold")).grid(
            row=row, column=0, columnspan=3, sticky="w", padx=5, pady=(8, 2)
        )
        row += 1

        self.price_rounding_var = tk.StringVar(value=".99")
        rounding_frame = ttk.Frame(section)
        rounding_frame.grid(
            row=row, column=0, columnspan=3, sticky="w", padx=20, pady=2
        )
        for text, val in [
            ("$XX.99", ".99"),
            ("$XX.95", ".95"),
            ("$XX.00", ".00"),
            ("No Rounding", "none"),
        ]:
            ttk.Radiobutton(
                rounding_frame, text=text, variable=self.price_rounding_var, value=val
            ).pack(side="left", padx=8)
        self.price_rounding_var.trace_add("write", self._update_price_preview)
        row += 1

        # ── 구분선 ──
        ttk.Separator(section, orient="horizontal").grid(
            row=row, column=0, columnspan=3, sticky="ew", padx=5, pady=8
        )
        row += 1

        # ── 미리보기 ──
        preview = ttk.LabelFrame(section, text="Price Preview", padding=5)
        preview.grid(row=row, column=0, columnspan=3, sticky="ew", padx=5, pady=3)
        self.preview_labels = []
        for _ in range(3):
            lbl = ttk.Label(preview, text="", font=("Consolas", 9))
            lbl.pack(anchor="w", padx=5, pady=1)
            self.preview_labels.append(lbl)

        section.columnconfigure(1, weight=1)

        # 초기 상태 설정
        self._on_price_method_change()
        self._update_price_preview()

    def _on_price_method_change(self, *args):
        # type: (*str) -> None
        """가격 계산 방식 변경 시 관련 입력 필드를 활성/비활성 토글한다."""
        method = self.price_method_var.get()
        entries = {
            "multiplier": self.multiplier_entry,
            "margin_cost": self.margin_cost_entry,
            "margin_price": self.margin_price_entry,
            "fixed_markup": self.fixed_markup_entry,
        }
        for key, entry in entries.items():
            if key == method:
                entry.configure(state="normal")
            else:
                entry.configure(state="disabled")
        self._update_price_preview()

    def _update_price_preview(self, *args):
        # type: (*str) -> None
        """미리보기 라벨을 현재 설정값으로 업데이트한다."""
        try:
            from price_adjuster import calculate_price, apply_rounding

            ps = self.get_price_settings()
            for i, amazon_price in enumerate([10.0, 25.0, 50.0]):
                sell = calculate_price(amazon_price, ps)
                sell_rounded = apply_rounding(sell, ps.get("rounding", ".99"))
                compare = sell_rounded * ps.get("compare_at_markup", 1.4)
                compare_rounded = apply_rounding(compare, ps.get("rounding", ".99"))
                self.preview_labels[i].config(
                    text="Amazon ${:.2f}  \u2192  Sell ${:.2f}  /  Compare ${:.2f}".format(
                        amazon_price, sell_rounded, compare_rounded
                    )
                )
        except Exception:
            pass  # 초기화 중 또는 모듈 없을 때 무시

    # ================================================================
    # 섹션 4: 품질 필터
    # ================================================================

    def _create_quality_section(self, parent):
        # type: (ttk.Frame) -> None
        """품질 필터 설정 섹션을 생성한다."""
        section = ttk.LabelFrame(parent, text="품질 필터", padding=10)
        section.pack(fill="x", padx=10, pady=5)

        # 최소 가격
        ttk.Label(section, text="최소 가격 ($):").grid(
            row=0, column=0, sticky="w", padx=5, pady=3
        )
        self.min_price_var = tk.StringVar(value=str(self.DEFAULTS["MIN_PRICE"]))
        ttk.Entry(section, textvariable=self.min_price_var, width=12).grid(
            row=0, column=1, sticky="w", padx=5, pady=3
        )

        # 최대 가격
        ttk.Label(section, text="최대 가격 ($):").grid(
            row=0, column=2, sticky="w", padx=5, pady=3
        )
        self.max_price_var = tk.StringVar(value=str(self.DEFAULTS["MAX_PRICE"]))
        ttk.Entry(section, textvariable=self.max_price_var, width=12).grid(
            row=0, column=3, sticky="w", padx=5, pady=3
        )

        # 최소 평점
        ttk.Label(section, text="최소 평점:").grid(
            row=1, column=0, sticky="w", padx=5, pady=3
        )
        self.min_rating_var = tk.StringVar(value=str(self.DEFAULTS["MIN_RATING"]))
        ttk.Entry(section, textvariable=self.min_rating_var, width=12).grid(
            row=1, column=1, sticky="w", padx=5, pady=3
        )

        # 최소 리뷰 수
        ttk.Label(section, text="최소 리뷰 수:").grid(
            row=1, column=2, sticky="w", padx=5, pady=3
        )
        self.min_reviews_var = tk.StringVar(value=str(self.DEFAULTS["MIN_REVIEWS"]))
        ttk.Entry(section, textvariable=self.min_reviews_var, width=12).grid(
            row=1, column=3, sticky="w", padx=5, pady=3
        )

        # 최소 이미지 수
        ttk.Label(section, text="최소 이미지 수:").grid(
            row=2, column=0, sticky="w", padx=5, pady=3
        )
        self.min_images_var = tk.IntVar(value=self.DEFAULTS["MIN_IMAGES"])
        ttk.Spinbox(
            section, from_=1, to=20, textvariable=self.min_images_var, width=10
        ).grid(row=2, column=1, sticky="w", padx=5, pady=3)

        # 최소 제목 길이
        ttk.Label(section, text="최소 제목 길이:").grid(
            row=2, column=2, sticky="w", padx=5, pady=3
        )
        self.min_title_var = tk.IntVar(value=self.DEFAULTS["MIN_TITLE_LENGTH"])
        ttk.Spinbox(
            section, from_=1, to=100, textvariable=self.min_title_var, width=10
        ).grid(row=2, column=3, sticky="w", padx=5, pady=3)

        section.columnconfigure(1, weight=1)
        section.columnconfigure(3, weight=1)

    # ================================================================
    # 섹션 5: HTTP / 네트워크 설정
    # ================================================================

    def _create_http_section(self, parent):
        # type: (ttk.Frame) -> None
        """HTTP 요청 관련 설정 섹션을 생성한다."""
        section = ttk.LabelFrame(parent, text="HTTP / 네트워크 설정", padding=10)
        section.pack(fill="x", padx=10, pady=5)

        # 요청 타임아웃
        ttk.Label(section, text="요청 타임아웃 (초):").grid(
            row=0, column=0, sticky="w", padx=5, pady=3
        )
        self.timeout_var = tk.IntVar(value=self.DEFAULTS["REQUEST_TIMEOUT"])
        ttk.Spinbox(
            section, from_=5, to=60, textvariable=self.timeout_var, width=10
        ).grid(row=0, column=1, sticky="w", padx=5, pady=3)

        # 최대 재시도
        ttk.Label(section, text="최대 재시도:").grid(
            row=0, column=2, sticky="w", padx=5, pady=3
        )
        self.retries_var = tk.IntVar(value=self.DEFAULTS["MAX_RETRIES"])
        ttk.Spinbox(
            section, from_=1, to=10, textvariable=self.retries_var, width=10
        ).grid(row=0, column=3, sticky="w", padx=5, pady=3)

        # 재시도 대기
        ttk.Label(section, text="재시도 대기 (초):").grid(
            row=1, column=0, sticky="w", padx=5, pady=3
        )
        self.backoff_var = tk.IntVar(value=self.DEFAULTS["RETRY_BACKOFF"])
        ttk.Spinbox(
            section, from_=1, to=30, textvariable=self.backoff_var, width=10
        ).grid(row=1, column=1, sticky="w", padx=5, pady=3)

        # 최소 딜레이
        ttk.Label(section, text="최소 딜레이 (초):").grid(
            row=1, column=2, sticky="w", padx=5, pady=3
        )
        self.delay_min_var = tk.StringVar(value=str(self.DEFAULTS["DELAY_MIN"]))
        ttk.Entry(section, textvariable=self.delay_min_var, width=10).grid(
            row=1, column=3, sticky="w", padx=5, pady=3
        )

        # 최대 딜레이
        ttk.Label(section, text="최대 딜레이 (초):").grid(
            row=2, column=0, sticky="w", padx=5, pady=3
        )
        self.delay_max_var = tk.StringVar(value=str(self.DEFAULTS["DELAY_MAX"]))
        ttk.Entry(section, textvariable=self.delay_max_var, width=10).grid(
            row=2, column=1, sticky="w", padx=5, pady=3
        )

        # 키워드 간 대기
        ttk.Label(section, text="키워드 간 대기 (초):").grid(
            row=2, column=2, sticky="w", padx=5, pady=3
        )
        self.kw_delay_var = tk.IntVar(value=self.DEFAULTS["KEYWORD_DELAY"])
        ttk.Spinbox(
            section, from_=0, to=60, textvariable=self.kw_delay_var, width=10
        ).grid(row=2, column=3, sticky="w", padx=5, pady=3)

        # TLS 핑거프린트
        ttk.Label(section, text="TLS 핑거프린트:").grid(
            row=3, column=0, sticky="w", padx=5, pady=3
        )
        self.impersonate_var = tk.StringVar(value=self.DEFAULTS["IMPERSONATE"])
        ttk.Combobox(
            section,
            textvariable=self.impersonate_var,
            values=["chrome119", "chrome120", "safari15", "safari17", "firefox115"],
            state="readonly",
            width=15,
        ).grid(row=3, column=1, sticky="w", padx=5, pady=3)

        section.columnconfigure(1, weight=1)
        section.columnconfigure(3, weight=1)

    # ================================================================
    # 섹션 6: 출력 설정
    # ================================================================

    def _create_output_section(self, parent):
        # type: (ttk.Frame) -> None
        """출력 관련 설정 섹션을 생성한다."""
        section = ttk.LabelFrame(parent, text="출력 설정", padding=10)
        section.pack(fill="x", padx=10, pady=5)

        # 통합 CSV 생성
        self.merge_csv_var = tk.BooleanVar(value=self.DEFAULTS["MERGE_CSV"])
        ttk.Checkbutton(
            section, text="통합 CSV 생성", variable=self.merge_csv_var
        ).grid(row=0, column=0, sticky="w", padx=5, pady=3, columnspan=2)

        # 출력 폴더
        ttk.Label(section, text="출력 폴더:").grid(
            row=1, column=0, sticky="w", padx=5, pady=3
        )
        output_frame = ttk.Frame(section)
        output_frame.grid(row=1, column=1, sticky="we", padx=5, pady=3, columnspan=2)

        self.output_dir_var = tk.StringVar(value=self.DEFAULTS["OUTPUT_DIR"])
        ttk.Entry(output_frame, textvariable=self.output_dir_var).pack(
            side="left", fill="x", expand=True, padx=(0, 5)
        )

        ttk.Button(
            output_frame, text="찾아보기", width=10, command=self._browse_output_dir
        ).pack(side="right")

        section.columnconfigure(1, weight=1)

    # ================================================================
    # 하단 버튼
    # ================================================================

    def _create_bottom_buttons(self, parent):
        # type: (ttk.Frame) -> None
        """설정 저장/불러오기/기본값 복원 버튼을 생성한다."""
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill="x", padx=10, pady=15)

        ttk.Button(
            btn_frame, text="설정 저장", width=15, command=self.save_settings
        ).pack(side="left", padx=5)

        ttk.Button(
            btn_frame, text="설정 불러오기", width=15, command=self.load_settings
        ).pack(side="left", padx=5)

        ttk.Button(
            btn_frame, text="기본값 복원", width=15, command=self.restore_defaults
        ).pack(side="right", padx=5)

    # ================================================================
    # 키워드 관리 메서드
    # ================================================================

    def add_keyword(self):
        # type: () -> None
        """
        Entry에서 키워드를 읽어 Listbox에 추가한다.

        빈 값은 무시하고, 중복 키워드는 경고 후 무시한다.
        추가 후 Entry를 비운다.
        """
        keyword = self.keyword_entry.get().strip()

        if not keyword:
            return

        # 중복 체크
        existing = self.keyword_listbox.get(0, "end")
        if keyword in existing:
            messagebox.showwarning(
                "중복", "이미 추가된 키워드입니다: {}".format(keyword)
            )
            return

        self.keyword_listbox.insert("end", keyword)
        self.keyword_entry.delete(0, "end")

    def remove_keyword(self):
        # type: () -> None
        """선택된 키워드를 Listbox에서 삭제한다."""
        selection = self.keyword_listbox.curselection()
        if selection:
            self.keyword_listbox.delete(selection[0])
        else:
            messagebox.showinfo("알림", "삭제할 키워드를 선택해주세요.")

    def clear_keywords(self):
        # type: () -> None
        """확인 다이얼로그 후 모든 키워드를 삭제한다."""
        if self.keyword_listbox.size() == 0:
            return

        if messagebox.askyesno("확인", "모든 키워드를 삭제하시겠습니까?"):
            self.keyword_listbox.delete(0, "end")

    # ================================================================
    # 설정 가져오기 / 설정하기
    # ================================================================

    def get_settings(self):
        # type: () -> dict
        """
        모든 설정값을 딕셔너리로 반환한다.

        키 이름은 config.py의 변수명과 동일하다.
        숫자 필드는 적절한 타입(int/float)으로 변환하며,
        변환 실패 시 기본값을 사용한다.

        Returns:
            dict: 설정 딕셔너리.
        """

        def safe_int(val, default):
            """안전한 정수 변환."""
            try:
                return int(val)
            except (ValueError, TypeError):
                return default

        def safe_float(val, default):
            """안전한 실수 변환."""
            try:
                return float(val)
            except (ValueError, TypeError):
                return default

        # 키워드 리스트 및 URL 구성
        raw_keywords = list(self.keyword_listbox.get(0, "end"))
        keywords = []
        category_urls = {}
        for k in raw_keywords:
            if "::" in k:
                parts = [p.strip() for p in k.split("::", 1)]
                kw = parts[0]
                url = parts[1]
                if kw.lower().startswith("http"):
                    kw, url = url, kw
                keywords.append(kw)
                if url:
                    category_urls[kw] = url
            else:
                keywords.append(k.strip())

        # 수집 제한 (빈칸이면 None)
        enrich_text = self.enrich_limit_var.get().strip()
        enrich_limit = safe_int(enrich_text, None) if enrich_text else None

        return {
            "CATEGORY_KEYWORDS": keywords,
            "CATEGORY_URLS": category_urls,
            "MAX_PAGES": safe_int(self.pages_var.get(), self.DEFAULTS["MAX_PAGES"]),
            "ENRICH_LIMIT": enrich_limit,
            "MAX_WORKERS": safe_int(
                self.workers_var.get(), self.DEFAULTS["MAX_WORKERS"]
            ),
            "CHECKPOINT_INTERVAL": safe_int(
                self.checkpoint_var.get(), self.DEFAULTS["CHECKPOINT_INTERVAL"]
            ),
            "MARGIN_PERCENT": safe_float(
                self.margin_var.get(), self.DEFAULTS["MARGIN_PERCENT"]
            ),
            "COMPARE_PRICE_MARKUP": safe_float(
                self.markup_var.get(), self.DEFAULTS["COMPARE_PRICE_MARKUP"]
            ),
            "MIN_PRICE": safe_float(
                self.min_price_var.get(), self.DEFAULTS["MIN_PRICE"]
            ),
            "MAX_PRICE": safe_float(
                self.max_price_var.get(), self.DEFAULTS["MAX_PRICE"]
            ),
            "MIN_RATING": safe_float(
                self.min_rating_var.get(), self.DEFAULTS["MIN_RATING"]
            ),
            "MIN_REVIEWS": safe_int(
                self.min_reviews_var.get(), self.DEFAULTS["MIN_REVIEWS"]
            ),
            "MIN_IMAGES": safe_int(
                self.min_images_var.get(), self.DEFAULTS["MIN_IMAGES"]
            ),
            "MIN_TITLE_LENGTH": safe_int(
                self.min_title_var.get(), self.DEFAULTS["MIN_TITLE_LENGTH"]
            ),
            "REQUEST_TIMEOUT": safe_int(
                self.timeout_var.get(), self.DEFAULTS["REQUEST_TIMEOUT"]
            ),
            "MAX_RETRIES": safe_int(
                self.retries_var.get(), self.DEFAULTS["MAX_RETRIES"]
            ),
            "RETRY_BACKOFF": safe_int(
                self.backoff_var.get(), self.DEFAULTS["RETRY_BACKOFF"]
            ),
            "DELAY_MIN": safe_float(
                self.delay_min_var.get(), self.DEFAULTS["DELAY_MIN"]
            ),
            "DELAY_MAX": safe_float(
                self.delay_max_var.get(), self.DEFAULTS["DELAY_MAX"]
            ),
            "KEYWORD_DELAY": safe_int(
                self.kw_delay_var.get(), self.DEFAULTS["KEYWORD_DELAY"]
            ),
            "IMPERSONATE": self.impersonate_var.get(),
            "MERGE_CSV": self.merge_csv_var.get(),
            "OUTPUT_DIR": self.output_dir_var.get().strip()
            or self.DEFAULTS["OUTPUT_DIR"],
            "PRICE_SETTINGS": self.get_price_settings(),
        }

    def set_settings(self, settings_dict):
        # type: (dict) -> None
        """
        딕셔너리를 받아 모든 위젯에 값을 설정한다.

        Args:
            settings_dict: config.py 변수명을 키로 갖는 설정 딕셔너리.
        """
        # 키워드 리스트 및 URL 복원
        keywords = settings_dict.get(
            "CATEGORY_KEYWORDS", self.DEFAULTS["CATEGORY_KEYWORDS"]
        )
        category_urls = settings_dict.get("CATEGORY_URLS", {})
        self.keyword_listbox.delete(0, "end")
        for kw in keywords:
            url = category_urls.get(kw, "")
            if url:
                self.keyword_listbox.insert("end", "{}::{}".format(kw, url))
            else:
                self.keyword_listbox.insert("end", kw)

        # 스크래핑 설정
        self.pages_var.set(settings_dict.get("MAX_PAGES", self.DEFAULTS["MAX_PAGES"]))
        self.pages_label.configure(
            text=str(settings_dict.get("MAX_PAGES", self.DEFAULTS["MAX_PAGES"]))
        )

        enrich = settings_dict.get("ENRICH_LIMIT", self.DEFAULTS["ENRICH_LIMIT"])
        self.enrich_limit_var.set("" if enrich is None else str(enrich))

        self.workers_var.set(
            settings_dict.get("MAX_WORKERS", self.DEFAULTS["MAX_WORKERS"])
        )
        self.checkpoint_var.set(
            settings_dict.get(
                "CHECKPOINT_INTERVAL", self.DEFAULTS["CHECKPOINT_INTERVAL"]
            )
        )

        # 가격 설정 (레거시)
        self.margin_var.set(
            str(settings_dict.get("MARGIN_PERCENT", self.DEFAULTS["MARGIN_PERCENT"]))
        )
        self.markup_var.set(
            str(
                settings_dict.get(
                    "COMPARE_PRICE_MARKUP", self.DEFAULTS["COMPARE_PRICE_MARKUP"]
                )
            )
        )

        # 새 가격 설정
        if "PRICE_SETTINGS" in settings_dict:
            self.set_price_settings(settings_dict["PRICE_SETTINGS"])

        # 품질 필터
        self.min_price_var.set(
            str(settings_dict.get("MIN_PRICE", self.DEFAULTS["MIN_PRICE"]))
        )
        self.max_price_var.set(
            str(settings_dict.get("MAX_PRICE", self.DEFAULTS["MAX_PRICE"]))
        )
        self.min_rating_var.set(
            str(settings_dict.get("MIN_RATING", self.DEFAULTS["MIN_RATING"]))
        )
        self.min_reviews_var.set(
            str(settings_dict.get("MIN_REVIEWS", self.DEFAULTS["MIN_REVIEWS"]))
        )
        self.min_images_var.set(
            settings_dict.get("MIN_IMAGES", self.DEFAULTS["MIN_IMAGES"])
        )
        self.min_title_var.set(
            settings_dict.get("MIN_TITLE_LENGTH", self.DEFAULTS["MIN_TITLE_LENGTH"])
        )

        # HTTP 설정
        self.timeout_var.set(
            settings_dict.get("REQUEST_TIMEOUT", self.DEFAULTS["REQUEST_TIMEOUT"])
        )
        self.retries_var.set(
            settings_dict.get("MAX_RETRIES", self.DEFAULTS["MAX_RETRIES"])
        )
        self.backoff_var.set(
            settings_dict.get("RETRY_BACKOFF", self.DEFAULTS["RETRY_BACKOFF"])
        )
        self.delay_min_var.set(
            str(settings_dict.get("DELAY_MIN", self.DEFAULTS["DELAY_MIN"]))
        )
        self.delay_max_var.set(
            str(settings_dict.get("DELAY_MAX", self.DEFAULTS["DELAY_MAX"]))
        )
        self.kw_delay_var.set(
            settings_dict.get("KEYWORD_DELAY", self.DEFAULTS["KEYWORD_DELAY"])
        )
        self.impersonate_var.set(
            settings_dict.get("IMPERSONATE", self.DEFAULTS["IMPERSONATE"])
        )

        # 출력 설정
        self.merge_csv_var.set(
            settings_dict.get("MERGE_CSV", self.DEFAULTS["MERGE_CSV"])
        )
        self.output_dir_var.set(
            settings_dict.get("OUTPUT_DIR", self.DEFAULTS["OUTPUT_DIR"])
        )

    # ================================================================
    # 저장 / 불러오기 / 기본값 복원
    # ================================================================

    def save_settings(self):
        # type: () -> None
        """설정을 JSON 파일로 저장한다. profiles/ 폴더를 기본 경로로 사용."""
        filepath = filedialog.asksaveasfilename(
            title="설정 저장",
            initialdir="profiles",
            defaultextension=".json",
            filetypes=[("JSON 파일", "*.json"), ("모든 파일", "*.*")],
        )

        if not filepath:
            return

        try:
            settings = self.get_settings()
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
            messagebox.showinfo(
                "저장 완료", "설정이 저장되었습니다:\n{}".format(filepath)
            )
        except Exception as e:
            messagebox.showerror("저장 실패", "설정 저장 중 오류:\n{}".format(e))

    def load_settings(self):
        # type: () -> None
        """JSON 파일에서 설정을 불러와 위젯에 적용한다."""
        filepath = filedialog.askopenfilename(
            title="설정 불러오기",
            initialdir="profiles",
            filetypes=[("JSON 파일", "*.json"), ("모든 파일", "*.*")],
        )

        if not filepath:
            return

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                settings = json.load(f)
            self.set_settings(settings)
            messagebox.showinfo(
                "불러오기 완료", "설정을 불러왔습니다:\n{}".format(filepath)
            )
        except Exception as e:
            messagebox.showerror(
                "불러오기 실패", "설정 불러오기 중 오류:\n{}".format(e)
            )

    def restore_defaults(self):
        # type: () -> None
        """확인 다이얼로그 후 모든 필드를 기본값으로 복원한다."""
        if messagebox.askyesno("확인", "모든 설정을 기본값으로 복원하시겠습니까?"):
            self.set_settings(self.DEFAULTS)

    def _browse_output_dir(self):
        # type: () -> None
        """폴더 선택 다이얼로그를 열고 출력 폴더를 설정한다."""
        folder = filedialog.askdirectory(
            title="출력 폴더 선택", initialdir=self.output_dir_var.get()
        )
        if folder:
            self.output_dir_var.set(folder)

    # ================================================================
    # Price Settings – getter / setter
    # ================================================================

    def get_price_settings(self):
        # type: () -> dict
        """현재 가격 설정을 딕셔너리로 반환한다."""
        settings = {
            "method": self.price_method_var.get(),
            "multiplier": self.multiplier_var.get(),
            "margin_cost": self.margin_cost_var.get(),
            "margin_price": self.margin_price_var.get(),
            "fixed_markup": self.fixed_markup_var.get(),
            "compare_at_markup": self.compare_at_markup_var.get(),
            "rounding": self.price_rounding_var.get(),
        }
        if settings["method"] == "tiered":
            settings["tiered_rates"] = [
                (20, 3.0),
                (50, 2.5),
                (100, 2.0),
                (float("inf"), 1.6),
            ]
        return settings

    def set_price_settings(self, settings):
        # type: (dict) -> None
        """저장된 가격 설정을 위젯에 복원한다."""
        if "method" in settings:
            self.price_method_var.set(settings["method"])
        if "multiplier" in settings:
            self.multiplier_var.set(settings["multiplier"])
        if "margin_cost" in settings:
            self.margin_cost_var.set(settings["margin_cost"])
        if "margin_price" in settings:
            self.margin_price_var.set(settings["margin_price"])
        if "fixed_markup" in settings:
            self.fixed_markup_var.set(settings["fixed_markup"])
        if "compare_at_markup" in settings:
            self.compare_at_markup_var.set(settings["compare_at_markup"])
        if "rounding" in settings:
            self.price_rounding_var.set(settings["rounding"])
        self._on_price_method_change()

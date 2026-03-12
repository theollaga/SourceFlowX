"""
SourceFlowX - Shopify 연동 탭
Shopify Admin API를 통한 상품 업로드, CSV 내보내기,
연결 테스트, 스토어 관리를 제공하는 탭.
"""

import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
from tkinter import filedialog
from tkinter import scrolledtext
import threading
import os
import json
import glob
import csv
import re
from datetime import datetime


class ShopifyTab(ttk.Frame):
    """
    Shopify 연동 탭 프레임.

    스토어 연결, API 업로드, CSV 내보내기,
    업로드 통계, 전체 삭제를 제공한다.
    """

    def __init__(self, parent):
        # type: (tk.Widget) -> None
        """
        Shopify 탭을 초기화한다.

        Args:
            parent: 부모 위젯 (Notebook).
        """
        super().__init__(parent)
        self.app = None  # gui_app.py에서 연결
        self.shopify_client = None  # ShopifyClient 인스턴스
        self.is_uploading = False
        self._create_widgets()

    def _create_widgets(self):
        # type: () -> None
        """스크롤 가능한 Canvas 안에 전체 위젯을 배치한다."""
        # ── 스크롤 가능한 Canvas 구조 ──
        self._canvas = tk.Canvas(self, highlightthickness=0)
        self._scrollbar = ttk.Scrollbar(
            self, orient="vertical", command=self._canvas.yview
        )
        self._scroll_frame = ttk.Frame(self._canvas)

        self._scroll_frame.bind(
            "<Configure>",
            lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")),
        )

        self._canvas_window = self._canvas.create_window(
            (0, 0), window=self._scroll_frame, anchor="nw"
        )
        self._canvas.configure(yscrollcommand=self._scrollbar.set)

        self._scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        # Canvas 너비에 내부 프레임 맞추기
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        # 마우스 휠 바인딩
        self._canvas.bind("<Enter>", self._bind_mousewheel)
        self._canvas.bind("<Leave>", self._unbind_mousewheel)

        # ── 상단: Shopify Output Settings ──
        self._create_output_settings(self._scroll_frame)

        # ── Collection Mapping ──
        self._create_collection_mapping(self._scroll_frame)

        # ── 구분선 ──
        ttk.Separator(self._scroll_frame, orient="horizontal").pack(
            fill="x", padx=10, pady=10
        )

        # ── 연결 설정 ──
        self._create_connection_section(self._scroll_frame)

        # ── 중간: 설정 + 통계 (좌우 배치) ──
        mid_frame = ttk.Frame(self._scroll_frame)
        mid_frame.pack(fill="x", padx=5, pady=2)

        self._create_upload_settings(mid_frame)
        self._create_upload_stats(mid_frame)

        # ── 중간: 진행률 ──
        self._create_progress_section(self._scroll_frame)

        # ── 하단: 버튼 ──
        self._create_buttons_section(self._scroll_frame)

        # ── 하단: 로그 ──
        self._create_log_section(self._scroll_frame)

    def _on_canvas_configure(self, event):
        # type: (tk.Event) -> None
        """Canvas 크기 변경 시 내부 프레임 너비를 맞춘다."""
        self._canvas.itemconfig(self._canvas_window, width=event.width)

    def _bind_mousewheel(self, event):
        # type: (tk.Event) -> None
        """마우스가 Canvas 위에 있을 때 휠 스크롤을 바인딩한다."""
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, event):
        # type: (tk.Event) -> None
        """마우스가 Canvas를 벗어나면 휠 스크롤을 해제한다."""
        self._canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event):
        # type: (tk.Event) -> None
        """마우스 휠 스크롤을 처리한다."""
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ================================================================
    # Shopify Output Settings
    # ================================================================

    def _create_output_settings(self, parent):
        # type: (ttk.Frame) -> None
        """Shopify CSV 출력 설정 영역을 생성한다."""
        section = ttk.LabelFrame(parent, text="Shopify Output Settings", padding=10)
        section.pack(fill="x", padx=10, pady=5)

        row = 0

        # ── Store Name ──
        ttk.Label(section, text="Store Name").grid(
            row=row, column=0, sticky="w", padx=10, pady=5
        )
        self.store_name_var = tk.StringVar(value="")
        ttk.Entry(section, textvariable=self.store_name_var, width=30).grid(
            row=row, column=1, sticky="ew", padx=10, pady=5
        )
        row += 1

        # Store Name 설명
        tk.Label(
            section,
            text="Used for SEO title suffix and image alt text",
            fg="#888888",
            font=("", 8),
        ).grid(row=row, column=1, sticky="w", padx=10, pady=(0, 5))
        row += 1

        # ── Default Vendor ──
        ttk.Label(section, text="Default Vendor").grid(
            row=row, column=0, sticky="w", padx=10, pady=5
        )
        self.default_vendor_var = tk.StringVar(value="")
        ttk.Entry(section, textvariable=self.default_vendor_var, width=30).grid(
            row=row, column=1, sticky="ew", padx=10, pady=5
        )
        row += 1

        # ── Vendor Source ──
        ttk.Label(section, text="Vendor Source").grid(
            row=row, column=0, sticky="nw", padx=10, pady=5
        )
        vendor_frame = ttk.Frame(section)
        vendor_frame.grid(row=row, column=1, sticky="w", padx=10, pady=5)
        self.vendor_source_var = tk.StringVar(value="amazon_brand")
        ttk.Radiobutton(
            vendor_frame,
            text="Amazon Brand (fallback to Default Vendor)",
            variable=self.vendor_source_var,
            value="amazon_brand",
        ).pack(anchor="w", padx=20)
        ttk.Radiobutton(
            vendor_frame,
            text="Fixed Value (always use Default Vendor)",
            variable=self.vendor_source_var,
            value="fixed",
        ).pack(anchor="w", padx=20)
        row += 1

        # ── Published ──
        self.published_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            section,
            text="Published (assign to Online Store sales channel)",
            variable=self.published_var,
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=10, pady=5)
        row += 1

        # ── Default Status ──
        ttk.Label(section, text="Default Status").grid(
            row=row, column=0, sticky="w", padx=10, pady=5
        )
        self.status_var = tk.StringVar(value="draft")
        ttk.Combobox(
            section,
            textvariable=self.status_var,
            values=["draft", "active"],
            state="readonly",
            width=15,
        ).grid(row=row, column=1, sticky="w", padx=10, pady=5)
        row += 1

        # ── Inventory Qty ──
        ttk.Label(section, text="Inventory Qty").grid(
            row=row, column=0, sticky="w", padx=10, pady=5
        )
        self.inventory_qty_var = tk.IntVar(value=999)
        ttk.Spinbox(
            section,
            textvariable=self.inventory_qty_var,
            from_=0,
            to=9999,
            increment=1,
            width=10,
        ).grid(row=row, column=1, sticky="w", padx=10, pady=5)
        row += 1

        # ── Inventory Policy ──
        ttk.Label(section, text="Inventory Policy").grid(
            row=row, column=0, sticky="w", padx=10, pady=5
        )
        self.inventory_policy_var = tk.StringVar(value="deny")
        ttk.Combobox(
            section,
            textvariable=self.inventory_policy_var,
            values=["deny", "continue"],
            state="readonly",
            width=15,
        ).grid(row=row, column=1, sticky="w", padx=10, pady=5)
        row += 1

        # ── Max Images ──
        ttk.Label(section, text="Max Images per Product").grid(
            row=row, column=0, sticky="w", padx=10, pady=5
        )
        self.max_images_var = tk.StringVar(value="5")
        ttk.Combobox(
            section,
            textvariable=self.max_images_var,
            values=["3", "5", "7", "10", "all"],
            state="readonly",
            width=10,
        ).grid(row=row, column=1, sticky="w", padx=10, pady=5)
        row += 1

        # ── Title Max Length ──
        ttk.Label(section, text="Title Max Length (characters)").grid(
            row=row, column=0, sticky="w", padx=10, pady=5
        )
        self.title_max_length_var = tk.IntVar(value=60)
        ttk.Spinbox(
            section,
            textvariable=self.title_max_length_var,
            from_=20,
            to=200,
            increment=5,
            width=10,
        ).grid(row=row, column=1, sticky="w", padx=10, pady=5)
        row += 1

        # ── Remove Brand from Title ──
        self.remove_brand_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            section,
            text="Remove original brand name from product title",
            variable=self.remove_brand_var,
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=10, pady=5)
        row += 1

        # ── SEO Title Separator ──
        ttk.Label(section, text="SEO Title Separator").grid(
            row=row, column=0, sticky="w", padx=10, pady=5
        )
        self.seo_separator_var = tk.StringVar(value="|")
        ttk.Combobox(
            section,
            textvariable=self.seo_separator_var,
            values=["|", "-", "\u2013", "\u00b7", "\u2014"],
            state="readonly",
            width=10,
        ).grid(row=row, column=1, sticky="w", padx=10, pady=5)
        row += 1

        # ── Price Rounding ──
        ttk.Label(section, text="Price Rounding").grid(
            row=row, column=0, sticky="nw", padx=10, pady=5
        )
        price_frame = ttk.Frame(section)
        price_frame.grid(row=row, column=1, sticky="w", padx=10, pady=5)
        self.price_rounding_var = tk.StringVar(value=".99")
        ttk.Radiobutton(
            price_frame,
            text=".99 ending ($24.99)",
            variable=self.price_rounding_var,
            value=".99",
        ).pack(anchor="w", padx=20)
        ttk.Radiobutton(
            price_frame,
            text=".95 ending ($24.95)",
            variable=self.price_rounding_var,
            value=".95",
        ).pack(anchor="w", padx=20)
        ttk.Radiobutton(
            price_frame,
            text=".00 ending ($25.00)",
            variable=self.price_rounding_var,
            value=".00",
        ).pack(anchor="w", padx=20)
        ttk.Radiobutton(
            price_frame,
            text="No rounding",
            variable=self.price_rounding_var,
            value="none",
        ).pack(anchor="w", padx=20)
        row += 1

        # 2열 grid 가중치 설정
        section.columnconfigure(1, weight=1)

    # ================================================================
    # 상단: 연결 설정
    # ================================================================

    def _create_connection_section(self, parent):
        # type: (ttk.Frame) -> None
        """Shopify 스토어 연결 설정 영역을 생성한다."""
        section = ttk.LabelFrame(parent, text="Shopify 스토어 연결", padding=10)
        section.pack(fill="x", padx=10, pady=5)

        # 스토어 URL
        url_frame = ttk.Frame(section)
        url_frame.pack(fill="x", pady=2)

        ttk.Label(url_frame, text="스토어 URL:", width=15, anchor="w").pack(side="left")

        self.store_url_var = tk.StringVar()
        self.store_url_entry = ttk.Entry(
            url_frame, textvariable=self.store_url_var, width=40, font=("Segoe UI", 10)
        )
        self.store_url_entry.pack(side="left", fill="x", expand=True, padx=5)
        self.store_url_entry.insert(0, "your-store.myshopify.com")
        self.store_url_entry.configure(foreground="#999999")
        self.store_url_entry.bind("<FocusIn>", self._on_url_focus_in)
        self.store_url_entry.bind("<FocusOut>", self._on_url_focus_out)

        # API 키
        key_frame = ttk.Frame(section)
        key_frame.pack(fill="x", pady=2)

        ttk.Label(key_frame, text="Admin API 키:", width=15, anchor="w").pack(
            side="left"
        )

        self.api_key_var = tk.StringVar()
        self.api_key_entry = ttk.Entry(
            key_frame,
            textvariable=self.api_key_var,
            show="*",
            width=40,
            font=("Segoe UI", 10),
        )
        self.api_key_entry.pack(side="left", fill="x", expand=True, padx=5)

        # 연결 테스트 버튼 + 상태 라벨
        status_frame = ttk.Frame(section)
        status_frame.pack(fill="x", pady=2)

        self.btn_test_conn = ttk.Button(
            status_frame, text="연결 테스트", width=12, command=self.test_connection
        )
        self.btn_test_conn.pack(side="left")

        self.lbl_connection = tk.Label(
            status_frame,
            text="  ● 연결 안됨",
            fg="#dc3545",
            font=("Segoe UI", 9, "bold"),
        )
        self.lbl_connection.pack(side="left", padx=10)

        # 안내 텍스트
        guide_frame = ttk.Frame(section)
        guide_frame.pack(fill="x", pady=(5, 0))

        ttk.Label(
            guide_frame,
            text="Shopify Admin → Settings → Apps and sales channels → "
            "Develop apps → Create app → API credentials",
            font=("Segoe UI", 8),
            foreground="#888888",
        ).pack(anchor="w")

        ttk.Label(
            guide_frame,
            text="필요 권한: write_products, read_products",
            font=("Segoe UI", 8),
            foreground="#888888",
        ).pack(anchor="w")

    def _on_url_focus_in(self, event):
        # type: (tk.Event) -> None
        """URL 입력 포커스 시 placeholder 제거."""
        if self.store_url_var.get() == "your-store.myshopify.com":
            self.store_url_entry.delete(0, "end")
            self.store_url_entry.configure(foreground="#000000")

    def _on_url_focus_out(self, event):
        # type: (tk.Event) -> None
        """URL 입력 비어있으면 placeholder 복원."""
        if not self.store_url_var.get().strip():
            self.store_url_entry.insert(0, "your-store.myshopify.com")
            self.store_url_entry.configure(foreground="#999999")

    # ================================================================
    # 중간 좌측: 업로드 설정
    # ================================================================

    def _create_upload_settings(self, parent):
        # type: (ttk.Frame) -> None
        """업로드 옵션 설정 영역을 생성한다."""
        section = ttk.LabelFrame(parent, text="업로드 설정", padding=10)
        section.pack(side="left", fill="both", expand=True, padx=(5, 2), pady=2)

        # 중복 상품 처리
        ttk.Label(section, text="중복 상품 처리:").grid(
            row=0, column=0, sticky="w", padx=5, pady=3
        )
        self.duplicate_var = tk.StringVar(value="건너뛰기 (skip)")
        ttk.Combobox(
            section,
            textvariable=self.duplicate_var,
            values=["건너뛰기 (skip)", "업데이트 (update)"],
            state="readonly",
            width=20,
        ).grid(row=0, column=1, sticky="w", padx=5, pady=3)

        # 상품 상태
        ttk.Label(section, text="상품 상태:").grid(
            row=1, column=0, sticky="w", padx=5, pady=3
        )
        self.product_status_var = tk.StringVar(value="Draft (비공개)")
        ttk.Combobox(
            section,
            textvariable=self.product_status_var,
            values=["Draft (비공개)", "Active (공개)"],
            state="readonly",
            width=20,
        ).grid(row=1, column=1, sticky="w", padx=5, pady=3)

        # 태그 추가
        ttk.Label(section, text="태그 추가:").grid(
            row=2, column=0, sticky="w", padx=5, pady=3
        )
        self.tags_var = tk.StringVar(value="amazon-import")
        ttk.Entry(section, textvariable=self.tags_var, width=22).grid(
            row=2, column=1, sticky="w", padx=5, pady=3
        )

        # 기존 상품 수
        ttk.Label(section, text="기존 상품 수:").grid(
            row=3, column=0, sticky="w", padx=5, pady=3
        )
        self.lbl_existing = ttk.Label(section, text="-", font=("Segoe UI", 9, "bold"))
        self.lbl_existing.grid(row=3, column=1, sticky="w", padx=5, pady=3)

        section.columnconfigure(1, weight=1)

    # ================================================================
    # 중간 우측: 업로드 통계
    # ================================================================

    def _create_upload_stats(self, parent):
        # type: (ttk.Frame) -> None
        """업로드 현황 통계 라벨들을 생성한다."""
        section = ttk.LabelFrame(parent, text="업로드 현황", padding=10)
        section.pack(side="right", fill="both", expand=True, padx=(2, 5), pady=2)

        stats = [
            ("전체:", "lbl_upload_total", "0", "#333333"),
            ("등록:", "lbl_upload_created", "0", "#28a745"),
            ("업데이트:", "lbl_upload_updated", "0", "#007bff"),
            ("건너뜀:", "lbl_upload_skipped", "0", "#6c757d"),
            ("실패:", "lbl_upload_failed", "0", "#dc3545"),
        ]

        for i, (label_text, attr_name, default, color) in enumerate(stats):
            ttk.Label(section, text=label_text, font=("Segoe UI", 9)).grid(
                row=i, column=0, sticky="w", padx=5, pady=2
            )

            lbl = tk.Label(
                section, text=default, font=("Segoe UI", 14, "bold"), fg=color
            )
            lbl.grid(row=i, column=1, sticky="w", padx=5, pady=2)
            setattr(self, attr_name, lbl)

        section.columnconfigure(1, weight=1)

    # ================================================================
    # 중간: 진행률
    # ================================================================

    def _create_progress_section(self, parent):
        # type: (ttk.Frame) -> None
        """업로드 진행률 바와 라벨을 생성한다."""
        section = ttk.Frame(parent)
        section.pack(fill="x", padx=10, pady=2)

        self.upload_progress = ttk.Progressbar(section, mode="determinate", length=400)
        self.upload_progress.pack(fill="x", pady=2)

        label_frame = ttk.Frame(section)
        label_frame.pack(fill="x")

        self.lbl_upload_progress = ttk.Label(
            label_frame, text="대기 중", font=("Segoe UI", 9)
        )
        self.lbl_upload_progress.pack(side="left")

        self.lbl_current_product = ttk.Label(
            label_frame, text="", font=("Segoe UI", 9), foreground="#666666"
        )
        self.lbl_current_product.pack(side="right")

    # ================================================================
    # 하단: 버튼
    # ================================================================

    def _create_buttons_section(self, parent):
        # type: (ttk.Frame) -> None
        """업로드, CSV 내보내기, 삭제, 중지 버튼을 생성한다."""
        section = ttk.Frame(parent)
        section.pack(fill="x", padx=10, pady=5)

        self.btn_upload = ttk.Button(
            section, text="API로 업로드", width=20, command=self.start_upload
        )
        self.btn_upload.pack(side="left", padx=3)

        self.btn_csv = ttk.Button(
            section, text="CSV 내보내기", width=20, command=self.export_csv
        )
        self.btn_csv.pack(side="left", padx=3)

        self.btn_stop = ttk.Button(
            section,
            text="업로드 중지",
            width=15,
            command=self.stop_upload,
            state="disabled",
        )
        self.btn_stop.pack(side="left", padx=3)

        self.btn_delete_all = ttk.Button(
            section, text="전체 상품 삭제", width=15, command=self.delete_all
        )
        self.btn_delete_all.pack(side="right", padx=3)

    # ================================================================
    # 하단: 업로드 로그
    # ================================================================

    def _create_log_section(self, parent):
        # type: (ttk.Frame) -> None
        """업로드 로그 텍스트 영역을 생성한다."""
        section = ttk.LabelFrame(parent, text="업로드 로그", padding=5)
        section.pack(fill="both", expand=True, padx=10, pady=(2, 5))

        self.log_text = scrolledtext.ScrolledText(
            section, height=8, state="disabled", wrap="word", font=("Consolas", 9)
        )
        self.log_text.pack(fill="both", expand=True)

    # ================================================================
    # 연결 테스트
    # ================================================================

    def test_connection(self):
        # type: () -> None
        """
        Shopify 스토어 연결을 별도 스레드에서 테스트한다.

        성공 시 기존 상품 수를 조회하여 표시한다.
        """
        store_url = self.store_url_var.get().strip()
        api_key = self.api_key_var.get().strip()

        if store_url == "your-store.myshopify.com":
            store_url = ""

        if not store_url or not api_key:
            messagebox.showwarning("경고", "스토어 URL과 API 키를 모두 입력해주세요.")
            return

        self.btn_test_conn.configure(state="disabled")
        self.lbl_connection.configure(text="  ● 연결 중...", fg="#ffc107")
        self._log("연결 테스트 시작: {}".format(store_url))

        def _test():
            try:
                from shopify_api import ShopifyClient

                client = ShopifyClient(store_url, api_key)
                success, message = client.test_connection()

                if success:
                    # 기존 상품 조회
                    existing = client.get_existing_products()
                    count = len(existing)

                    self.shopify_client = client

                    self.after(
                        0,
                        lambda: self.lbl_connection.configure(
                            text="  ● {}".format(message), fg="#28a745"
                        ),
                    )
                    self.after(
                        0,
                        lambda: self.lbl_existing.configure(text="{}개".format(count)),
                    )
                    self.after(
                        0, lambda: self._log("연결 성공! 기존 상품: {}개".format(count))
                    )
                else:
                    self.after(
                        0,
                        lambda: self.lbl_connection.configure(
                            text="  ● {}".format(message), fg="#dc3545"
                        ),
                    )
                    self.after(0, lambda: self._log("연결 실패: {}".format(message)))

            except ImportError:
                self.after(
                    0,
                    lambda: self.lbl_connection.configure(
                        text="  ● shopify_api 모듈 없음", fg="#dc3545"
                    ),
                )
                self.after(
                    0, lambda: self._log("오류: shopify_api 모듈을 찾을 수 없습니다")
                )
            except Exception as e:
                self.after(
                    0,
                    lambda: self.lbl_connection.configure(
                        text="  ● 오류", fg="#dc3545"
                    ),
                )
                self.after(0, lambda: self._log("연결 오류: {}".format(e)))
            finally:
                self.after(0, lambda: self.btn_test_conn.configure(state="normal"))

        threading.Thread(target=_test, daemon=True).start()

    # ================================================================
    # 업로드
    # ================================================================

    def start_upload(self):
        # type: () -> None
        """
        상품 데이터를 Shopify 스토어에 업로드한다.

        별도 스레드에서 실행하며 진행률과 통계를 업데이트한다.
        """
        if self.shopify_client is None:
            messagebox.showwarning("경고", "먼저 연결 테스트를 실행해주세요.")
            return

        if self.is_uploading:
            messagebox.showinfo("알림", "업로드가 이미 진행 중입니다.")
            return

        # 상품 데이터 로드
        products = self._load_products()
        if not products:
            messagebox.showinfo(
                "알림",
                "업로드할 상품이 없습니다.\n"
                "먼저 스크래핑을 실행하거나 output 폴더에 결과 파일을 넣어주세요.",
            )
            return

        # 확인 다이얼로그
        if not messagebox.askyesno(
            "업로드 확인",
            "{}개 상품을 Shopify에 업로드하시겠습니까?".format(len(products)),
        ):
            return

        # 상태 설정
        self.is_uploading = True
        self._reset_stats()
        self.lbl_upload_total.configure(text=str(len(products)))
        self.btn_upload.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.upload_progress["value"] = 0

        self._log("업로드 시작: {}개 상품".format(len(products)))

        def _run():
            self._run_upload(products)

        threading.Thread(target=_run, daemon=True).start()

    def _run_upload(self, products):
        # type: (list) -> None
        """
        업로드를 실행한다 (별도 스레드).

        Args:
            products: 상품 리스트.
        """
        # 중복 처리 설정
        dup_text = self.duplicate_var.get()
        on_dup = "update" if "update" in dup_text.lower() else "skip"

        try:
            result = self.shopify_client.upload_products(
                products, on_duplicate=on_dup, progress_callback=self._upload_progress
            )
            self.after(0, lambda: self._on_upload_complete(result))

        except Exception as e:
            self.after(0, lambda: self._log("업로드 오류: {}".format(e)))
            self.after(0, self._restore_buttons)

    def _upload_progress(self, current, total, title, status):
        # type: (int, int, str, str) -> None
        """
        업로드 진행 콜백. UI를 업데이트한다.

        Args:
            current: 현재 처리 수.
            total: 전체 수.
            title: 현재 상품명.
            status: 처리 상태.
        """
        if not self.is_uploading:
            return

        pct = int((current / total) * 100) if total > 0 else 0
        short_title = title[:40] + "..." if len(title) > 40 else title

        def _update():
            self.upload_progress["value"] = pct
            self.lbl_upload_progress.configure(
                text="{}/{} ({}%)".format(current, total, pct)
            )
            self.lbl_current_product.configure(
                text="{}: {}".format(status, short_title)
            )
            self._log("[{}/{}] {} – {}".format(current, total, status, short_title))

        self.after(0, _update)

    def _on_upload_complete(self, result):
        # type: (dict) -> None
        """
        업로드 완료 시 UI를 업데이트하고 결과를 표시한다.

        Args:
            result: 업로드 결과 딕셔너리.
        """
        self.is_uploading = False
        self._restore_buttons()

        # 통계 업데이트
        self.lbl_upload_created.configure(text=str(result.get("created", 0)))
        self.lbl_upload_updated.configure(text=str(result.get("updated", 0)))
        self.lbl_upload_skipped.configure(text=str(result.get("skipped", 0)))
        self.lbl_upload_failed.configure(text=str(result.get("failed", 0)))

        self.lbl_upload_progress.configure(text="완료")
        self.upload_progress["value"] = 100

        # 로그 요약
        self._log("=" * 40)
        self._log("업로드 완료!")
        self._log("  등록: {}개".format(result.get("created", 0)))
        self._log("  업데이트: {}개".format(result.get("updated", 0)))
        self._log("  건너뜀: {}개".format(result.get("skipped", 0)))
        self._log("  실패: {}개".format(result.get("failed", 0)))

        errors = result.get("errors", [])
        if errors:
            self._log("  에러:")
            for err in errors[:10]:
                self._log("    - {}".format(err))

        messagebox.showinfo(
            "업로드 완료",
            "등록: {}개\n업데이트: {}개\n건너뜀: {}개\n실패: {}개".format(
                result.get("created", 0),
                result.get("updated", 0),
                result.get("skipped", 0),
                result.get("failed", 0),
            ),
        )

    def stop_upload(self):
        # type: () -> None
        """업로드를 중지한다."""
        self.is_uploading = False
        self._log("업로드 중지 요청됨")
        self._restore_buttons()

    def _restore_buttons(self):
        # type: () -> None
        """버튼 상태를 복원한다."""
        self.btn_upload.configure(state="normal")
        self.btn_stop.configure(state="disabled")

    def _reset_stats(self):
        # type: () -> None
        """업로드 통계를 초기화한다."""
        self.lbl_upload_total.configure(text="0")
        self.lbl_upload_created.configure(text="0")
        self.lbl_upload_updated.configure(text="0")
        self.lbl_upload_skipped.configure(text="0")
        self.lbl_upload_failed.configure(text="0")
        self.lbl_upload_progress.configure(text="대기 중")
        self.lbl_current_product.configure(text="")
        self.upload_progress["value"] = 0

    # ================================================================
    # CSV 내보내기
    # ================================================================

    def export_csv(self):
        # type: () -> None
        """output 폴더의 상품을 Shopify CSV 형식으로 내보낸다."""
        products = self._load_products()
        if not products:
            messagebox.showinfo(
                "알림", "내보낼 상품이 없습니다.\n" "먼저 스크래핑을 실행해주세요."
            )
            return

        self._log("CSV 내보내기 시작: {}개 상품".format(len(products)))

        try:
            from shopify_exporter import export_shopify_csv

            export_shopify_csv(products)

            output_dir = os.path.abspath("output")
            self._log("CSV 내보내기 완료: {} 폴더".format(output_dir))

            messagebox.showinfo(
                "완료",
                "{}개 상품을 CSV로 내보냈습니다.\n"
                "output 폴더를 확인하세요.".format(len(products)),
            )

        except ImportError:
            messagebox.showerror("오류", "shopify_exporter 모듈을 찾을 수 없습니다.")
        except Exception as e:
            self._log("CSV 내보내기 오류: {}".format(e))
            messagebox.showerror("오류", "CSV 내보내기 실패:\n{}".format(e))

    # ================================================================
    # 전체 삭제
    # ================================================================

    def delete_all(self):
        # type: () -> None
        """2중 확인 후 Shopify 스토어의 모든 상품을 삭제한다."""
        if self.shopify_client is None:
            messagebox.showwarning("경고", "먼저 연결 테스트를 실행해주세요.")
            return

        # 1차 확인
        if not messagebox.askyesno(
            "경고",
            "정말로 모든 상품을 삭제하시겠습니까?\n"
            "이 작업은 Shopify 스토어의 모든 상품을 삭제합니다.",
        ):
            return

        # 2차 확인
        if not messagebox.askyesno(
            "최종 확인", "이 작업은 되돌릴 수 없습니다.\n" "계속하시겠습니까?"
        ):
            return

        self._log("전체 상품 삭제 시작...")
        self.btn_delete_all.configure(state="disabled")

        def _run():
            try:

                def _progress(current, total):
                    pct = int((current / total) * 100) if total > 0 else 0
                    self.after(
                        0, lambda: self.upload_progress.__setitem__("value", pct)
                    )
                    self.after(
                        0,
                        lambda: self.lbl_upload_progress.configure(
                            text="삭제 중 {}/{} ({}%)".format(current, total, pct)
                        ),
                    )

                deleted, failed = self.shopify_client.delete_all_products(
                    progress_callback=_progress
                )

                self.after(
                    0,
                    lambda: self._log(
                        "삭제 완료: {}개 삭제, {}개 실패".format(deleted, failed)
                    ),
                )
                self.after(0, lambda: self.lbl_existing.configure(text="0개"))
                self.after(
                    0,
                    lambda: messagebox.showinfo(
                        "삭제 완료", "{}개 상품 삭제, {}개 실패".format(deleted, failed)
                    ),
                )

            except Exception as e:
                self.after(0, lambda: self._log("삭제 오류: {}".format(e)))
                self.after(
                    0, lambda: messagebox.showerror("오류", "삭제 실패:\n{}".format(e))
                )
            finally:
                self.after(0, lambda: self.btn_delete_all.configure(state="normal"))

        threading.Thread(target=_run, daemon=True).start()

    # ================================================================
    # 유틸리티
    # ================================================================

    def _load_products(self):
        # type: () -> list
        """output 폴더에서 상품 데이터를 로드한다."""
        output_dir = os.path.abspath("output")
        all_products = []

        if not os.path.exists(output_dir):
            return all_products

        # 설명 적용된 파일 우선
        desc_file = os.path.join(output_dir, "products_with_descriptions.json")
        if os.path.exists(desc_file):
            try:
                with open(desc_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    return data
            except Exception:
                pass

        # 백업 파일들
        patterns = [
            os.path.join(output_dir, "products_backup_*.json"),
            os.path.join(output_dir, "products_*.json"),
        ]

        seen = set()
        for pattern in patterns:
            for filepath in glob.glob(pattern):
                if filepath in seen:
                    continue
                seen.add(filepath)

                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, list):
                        all_products.extend(data)
                except Exception:
                    pass

        return all_products

    def _log(self, message):
        # type: (str) -> None
        """
        타임스탬프를 추가하여 로그 텍스트에 메시지를 추가한다.

        Args:
            message: 로그 메시지.
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_msg = "[{}] {}\n".format(timestamp, message)

        self.log_text.configure(state="normal")
        self.log_text.insert("end", log_msg)
        self.log_text.configure(state="disabled")
        self.log_text.see("end")

    # ================================================================
    # Shopify Output Settings – getter / setter
    # ================================================================

    def get_shopify_settings(self):
        # type: () -> dict
        """Shopify 출력 설정값을 딕셔너리로 반환한다."""
        max_img = self.max_images_var.get()
        return {
            "store_name": self.store_name_var.get().strip(),
            "default_vendor": self.default_vendor_var.get().strip(),
            "vendor_source": self.vendor_source_var.get(),
            "published": self.published_var.get(),
            "status": self.status_var.get(),
            "inventory_qty": self.inventory_qty_var.get(),
            "inventory_policy": self.inventory_policy_var.get(),
            "max_images": 999 if max_img == "all" else int(max_img),
            "title_max_length": self.title_max_length_var.get(),
            "remove_brand": self.remove_brand_var.get(),
            "seo_separator": self.seo_separator_var.get(),
            "price_rounding": self.price_rounding_var.get(),
        }

    def set_shopify_settings(self, settings):
        # type: (dict) -> None
        """딕셔너리에서 Shopify 출력 설정값을 위젯에 복원한다."""
        if "store_name" in settings:
            self.store_name_var.set(settings["store_name"])
        if "default_vendor" in settings:
            self.default_vendor_var.set(settings["default_vendor"])
        if "vendor_source" in settings:
            self.vendor_source_var.set(settings["vendor_source"])
        if "published" in settings:
            self.published_var.set(settings["published"])
        if "status" in settings:
            self.status_var.set(settings["status"])
        if "inventory_qty" in settings:
            self.inventory_qty_var.set(settings["inventory_qty"])
        if "inventory_policy" in settings:
            self.inventory_policy_var.set(settings["inventory_policy"])
        if "max_images" in settings:
            val = settings["max_images"]
            self.max_images_var.set("all" if val >= 999 else str(val))
        if "title_max_length" in settings:
            self.title_max_length_var.set(settings["title_max_length"])
        if "remove_brand" in settings:
            self.remove_brand_var.set(settings["remove_brand"])
        if "seo_separator" in settings:
            self.seo_separator_var.set(settings["seo_separator"])
        if "price_rounding" in settings:
            self.price_rounding_var.set(settings["price_rounding"])

    # ================================================================
    # Collection Mapping UI
    # ================================================================

    def _create_collection_mapping(self, parent):
        # type: (ttk.Frame) -> None
        """키워드별 Collection/Type/Category 매핑 테이블 영역을 생성한다."""
        section = ttk.LabelFrame(parent, text="Collection Mapping", padding=10)
        section.pack(fill="x", padx=10, pady=5)

        # ── 상단 버튼 프레임 ──
        btn_frame = ttk.Frame(section)
        btn_frame.pack(fill="x", pady=(0, 5))

        ttk.Button(
            btn_frame, text="Add Mapping", width=14, command=self._add_mapping
        ).pack(side="left", padx=2)

        ttk.Button(
            btn_frame, text="Delete Selected", width=14, command=self._delete_mapping
        ).pack(side="left", padx=2)

        ttk.Button(
            btn_frame, text="Auto Generate", width=14, command=self._auto_generate
        ).pack(side="left", padx=2)

        ttk.Button(
            btn_frame, text="Import CSV", width=12, command=self._import_mapping_csv
        ).pack(side="left", padx=2)

        ttk.Button(
            btn_frame, text="Export CSV", width=12, command=self._export_mapping_csv
        ).pack(side="left", padx=2)

        # ── Treeview ──
        tree_frame = ttk.Frame(section)
        tree_frame.pack(fill="x", pady=2)

        columns = ("keyword", "tag", "type", "category")
        self.mapping_tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings", height=6
        )

        self.mapping_tree.heading("keyword", text="Search Keyword")
        self.mapping_tree.heading("tag", text="Collection Tag")
        self.mapping_tree.heading("type", text="Product Type")
        self.mapping_tree.heading("category", text="Product Category")

        self.mapping_tree.column("keyword", width=150, anchor="w")
        self.mapping_tree.column("tag", width=150, anchor="w")
        self.mapping_tree.column("type", width=150, anchor="w")
        self.mapping_tree.column("category", width=250, anchor="w")

        tree_scroll = ttk.Scrollbar(
            tree_frame, orient="vertical", command=self.mapping_tree.yview
        )
        self.mapping_tree.configure(yscrollcommand=tree_scroll.set)

        self.mapping_tree.pack(side="left", fill="x", expand=True)
        tree_scroll.pack(side="right", fill="y")

        # 선택/더블클릭 이벤트
        self.mapping_tree.bind("<<TreeviewSelect>>", self._on_mapping_select)
        self.mapping_tree.bind("<Double-1>", self._on_mapping_double_click)

        # ── 편집 프레임 ──
        edit_frame = ttk.Frame(section)
        edit_frame.pack(fill="x", pady=(5, 2))

        # 1행: Keyword, Tag
        ttk.Label(edit_frame, text="Search Keyword").grid(
            row=0, column=0, sticky="w", padx=5, pady=3
        )
        self.map_keyword_var = tk.StringVar(value="")
        ttk.Entry(edit_frame, textvariable=self.map_keyword_var, width=20).grid(
            row=0, column=1, sticky="ew", padx=5, pady=3
        )

        ttk.Label(edit_frame, text="Collection Tag").grid(
            row=0, column=2, sticky="w", padx=5, pady=3
        )
        self.map_tag_var = tk.StringVar(value="")
        ttk.Entry(edit_frame, textvariable=self.map_tag_var, width=20).grid(
            row=0, column=3, sticky="ew", padx=5, pady=3
        )

        # 2행: Type, Category
        ttk.Label(edit_frame, text="Product Type").grid(
            row=1, column=0, sticky="w", padx=5, pady=3
        )
        self.map_type_var = tk.StringVar(value="")
        ttk.Entry(edit_frame, textvariable=self.map_type_var, width=20).grid(
            row=1, column=1, sticky="ew", padx=5, pady=3
        )

        ttk.Label(edit_frame, text="Product Category").grid(
            row=1, column=2, sticky="w", padx=5, pady=3
        )
        self.map_category_var = tk.StringVar(value="")
        ttk.Entry(edit_frame, textvariable=self.map_category_var, width=30).grid(
            row=1, column=3, sticky="ew", padx=5, pady=3
        )

        # Save / Update 버튼
        ttk.Button(
            edit_frame, text="Save / Update", width=14, command=self._update_mapping
        ).grid(row=0, column=4, rowspan=2, sticky="ns", padx=(10, 5), pady=3)

        edit_frame.columnconfigure(1, weight=1)
        edit_frame.columnconfigure(3, weight=1)

        # ── 안내 Label ──
        tk.Label(
            section,
            text="매핑되지 않은 키워드는 자동 변환됩니다: "
            "Tag=keyword-hyphenated, Type=keyword(Title Case), "
            "Category=빈값",
            fg="#888888",
            font=("", 8),
        ).pack(anchor="w", pady=(2, 0))

    # ================================================================
    # Collection Mapping – 버튼 동작
    # ================================================================

    def _generate_tag(self, keyword):
        # type: (str) -> str
        """키워드에서 Collection Tag를 자동 생성한다."""
        tag = keyword.lower().replace(" ", "-").replace("&", "and")
        tag = re.sub(r"[^a-z0-9\-]", "", tag)
        tag = re.sub(r"-+", "-", tag).strip("-")
        return tag

    def _add_mapping(self):
        # type: () -> None
        """편집 프레임의 값을 Treeview에 새 행으로 추가한다."""
        keyword = self.map_keyword_var.get().strip()
        if not keyword:
            messagebox.showwarning("경고", "Search Keyword를 입력해주세요.")
            return

        # 중복 확인
        for item in self.mapping_tree.get_children():
            values = self.mapping_tree.item(item, "values")
            if values[0].lower() == keyword.lower():
                messagebox.showwarning(
                    "경고", "이미 등록된 키워드입니다: {}".format(keyword)
                )
                return

        tag = self.map_tag_var.get().strip()
        ptype = self.map_type_var.get().strip()
        category = self.map_category_var.get().strip()

        # 자동 생성
        if not tag:
            tag = self._generate_tag(keyword)
        if not ptype:
            ptype = keyword.title()

        self.mapping_tree.insert("", "end", values=(keyword, tag, ptype, category))

        # 입력 필드 초기화
        self.map_keyword_var.set("")
        self.map_tag_var.set("")
        self.map_type_var.set("")
        self.map_category_var.set("")

    def _delete_mapping(self):
        # type: () -> None
        """Treeview에서 선택된 행을 삭제한다."""
        selected = self.mapping_tree.selection()
        if not selected:
            messagebox.showwarning("경고", "삭제할 항목을 선택해주세요.")
            return
        for item in selected:
            self.mapping_tree.delete(item)

    def _auto_generate(self):
        # type: () -> None
        """설정 탭의 키워드 목록에서 자동으로 매핑을 생성한다."""
        if self.app is None:
            messagebox.showwarning("경고", "앱 참조가 설정되지 않았습니다.")
            return

        try:
            settings = self.app.settings_tab.get_settings()
            keywords_raw = settings.get("CATEGORY_KEYWORDS", "")
        except Exception as e:
            messagebox.showerror("오류", "키워드를 가져올 수 없습니다: {}".format(e))
            return

        # 키워드 파싱 (줄바꿈 또는 쉼표 구분)
        if isinstance(keywords_raw, list):
            keywords = keywords_raw
        else:
            keywords = [
                kw.strip()
                for kw in keywords_raw.replace(",", "\n").split("\n")
                if kw.strip()
            ]

        if not keywords:
            messagebox.showinfo("알림", "설정 탭에 키워드가 없습니다.")
            return

        # 기존 키워드 수집
        existing = set()
        for item in self.mapping_tree.get_children():
            values = self.mapping_tree.item(item, "values")
            existing.add(values[0].lower())

        added = 0
        for kw in keywords:
            if kw.lower() in existing:
                continue
            tag = self._generate_tag(kw)
            ptype = kw.title()
            self.mapping_tree.insert("", "end", values=(kw, tag, ptype, ""))
            added += 1

        messagebox.showinfo(
            "자동 생성 완료", "{}개 매핑이 추가되었습니다.".format(added)
        )

    def _import_mapping_csv(self):
        # type: () -> None
        """CSV 파일에서 매핑 데이터를 읽어 Treeview에 추가한다."""
        filepath = filedialog.askopenfilename(
            title="Import Collection Mapping CSV",
            filetypes=[("CSV 파일", "*.csv"), ("모든 파일", "*.*")],
        )
        if not filepath:
            return

        # 기존 키워드 → item_id 매핑
        existing_map = {}
        for item in self.mapping_tree.get_children():
            values = self.mapping_tree.item(item, "values")
            existing_map[values[0].lower()] = item

        added = 0
        updated = 0
        try:
            with open(filepath, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    kw = row.get("keyword", "").strip()
                    if not kw:
                        continue
                    tag = row.get("tag", "").strip()
                    ptype = row.get("type", "").strip()
                    category = row.get("category", "").strip()

                    if kw.lower() in existing_map:
                        # 기존 행 업데이트
                        item_id = existing_map[kw.lower()]
                        self.mapping_tree.item(
                            item_id, values=(kw, tag, ptype, category)
                        )
                        updated += 1
                    else:
                        self.mapping_tree.insert(
                            "", "end", values=(kw, tag, ptype, category)
                        )
                        existing_map[kw.lower()] = None
                        added += 1

            messagebox.showinfo(
                "Import 완료", "추가: {}개, 업데이트: {}개".format(added, updated)
            )
        except Exception as e:
            messagebox.showerror("오류", "CSV Import 실패:\n{}".format(e))

    def _export_mapping_csv(self):
        # type: () -> None
        """Treeview 데이터를 CSV 파일로 내보낸다."""
        children = self.mapping_tree.get_children()
        if not children:
            messagebox.showinfo("알림", "내보낼 매핑 데이터가 없습니다.")
            return

        filepath = filedialog.asksaveasfilename(
            title="Export Collection Mapping CSV",
            defaultextension=".csv",
            filetypes=[("CSV 파일", "*.csv")],
        )
        if not filepath:
            return

        try:
            with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["keyword", "tag", "type", "category"])
                for item in children:
                    values = self.mapping_tree.item(item, "values")
                    writer.writerow(
                        [
                            values[0],
                            values[1],
                            values[2],
                            values[3] if len(values) > 3 else "",
                        ]
                    )
            messagebox.showinfo(
                "Export 완료", "{}개 매핑이 저장되었습니다.".format(len(children))
            )
        except Exception as e:
            messagebox.showerror("오류", "CSV Export 실패:\n{}".format(e))

    def _on_mapping_select(self, event):
        # type: (tk.Event) -> None
        """Treeview 행 선택 시 편집 프레임에 값을 채운다."""
        selected = self.mapping_tree.selection()
        if not selected:
            return
        values = self.mapping_tree.item(selected[0], "values")
        self.map_keyword_var.set(values[0])
        self.map_tag_var.set(values[1])
        self.map_type_var.set(values[2])
        self.map_category_var.set(values[3] if len(values) > 3 else "")

    def _on_mapping_double_click(self, event):
        # type: (tk.Event) -> None
        """Treeview 행 더블클릭 시 편집 프레임에 값을 채운다."""
        selected = self.mapping_tree.selection()
        if not selected:
            return
        values = self.mapping_tree.item(selected[0], "values")
        self.map_keyword_var.set(values[0])
        self.map_tag_var.set(values[1])
        self.map_type_var.set(values[2])
        self.map_category_var.set(values[3] if len(values) > 3 else "")

    def _update_mapping(self):
        # type: () -> None
        """편집 프레임의 값으로 선택된 Treeview 행을 업데이트한다."""
        selected = self.mapping_tree.selection()
        keyword = self.map_keyword_var.get().strip()
        if not keyword:
            messagebox.showwarning("경고", "Search Keyword를 입력해주세요.")
            return

        tag = self.map_tag_var.get().strip()
        ptype = self.map_type_var.get().strip()
        category = self.map_category_var.get().strip()

        if not tag:
            tag = self._generate_tag(keyword)
        if not ptype:
            ptype = keyword.title()

        if selected:
            # 기존 행 업데이트
            self.mapping_tree.item(selected[0], values=(keyword, tag, ptype, category))
        else:
            # 선택 없으면 새로 추가 (중복 확인)
            for item in self.mapping_tree.get_children():
                values = self.mapping_tree.item(item, "values")
                if values[0].lower() == keyword.lower():
                    self.mapping_tree.item(item, values=(keyword, tag, ptype, category))
                    return
            self.mapping_tree.insert("", "end", values=(keyword, tag, ptype, category))

    # ================================================================
    # Collection Mapping – getter / setter / lookup
    # ================================================================

    def get_collection_mapping(self):
        # type: () -> list
        """Collection Mapping 데이터를 리스트로 반환한다.

        Returns:
            list of dict: [{'keyword': '', 'tag': '', 'type': '', 'category': ''}, ...]
        """
        mappings = []
        for item in self.mapping_tree.get_children():
            values = self.mapping_tree.item(item, "values")
            mappings.append(
                {
                    "keyword": values[0],
                    "tag": values[1],
                    "type": values[2],
                    "category": values[3] if len(values) > 3 else "",
                }
            )
        return mappings

    def set_collection_mapping(self, mappings):
        # type: (list) -> None
        """리스트에서 Collection Mapping 데이터를 Treeview에 복원한다."""
        # 기존 데이터 삭제
        for item in self.mapping_tree.get_children():
            self.mapping_tree.delete(item)
        # 새 데이터 추가
        for m in mappings:
            self.mapping_tree.insert(
                "",
                "end",
                values=(
                    m.get("keyword", ""),
                    m.get("tag", ""),
                    m.get("type", ""),
                    m.get("category", ""),
                ),
            )

    def get_mapping_for_keyword(self, keyword):
        # type: (str) -> dict
        """특정 키워드에 대한 매핑을 반환한다. 없으면 자동 생성된 기본값을 반환한다."""
        for item in self.mapping_tree.get_children():
            values = self.mapping_tree.item(item, "values")
            if values[0].lower() == keyword.lower():
                return {
                    "keyword": values[0],
                    "tag": values[1],
                    "type": values[2],
                    "category": values[3] if len(values) > 3 else "",
                }
        # 매핑 없으면 기본값 생성
        tag = self._generate_tag(keyword)
        return {"keyword": keyword, "tag": tag, "type": keyword.title(), "category": ""}

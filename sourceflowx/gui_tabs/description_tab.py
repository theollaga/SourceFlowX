"""
SourceFlowX - 상품 설명 탭
AI(OpenAI), 리치 HTML, 원본 텍스트 3가지 방식으로
상품 설명을 생성하고 미리보기를 제공하는 탭.
"""

import tkinter as tk
from tkinter import ttk
from tkinter import scrolledtext
from tkinter import messagebox
from tkinter import filedialog
import threading
import os
import json
import glob


class DescriptionTab(ttk.Frame):
    """
    상품 설명 탭 프레임.

    설명 생성 방식 선택(원본/리치HTML/AI), AI 설정(API키/모델/프롬프트),
    미리보기, 전체 상품 적용 기능을 제공한다.
    """

    def __init__(self, parent):
        # type: (tk.Widget) -> None
        """
        상품 설명 탭을 초기화한다.

        Args:
            parent: 부모 위젯 (Notebook).
        """
        super().__init__(parent)
        self.app = None  # gui_app.py에서 연결
        self._create_widgets()

    def _create_widgets(self):
        # type: () -> None
        """스타일 선택, AI 설정, 미리보기, 적용 버튼을 배치한다."""
        # ── 상단: 설명 스타일 선택 ──
        self._create_style_section()

        # ── 중간: AI 설정 + 미리보기 (좌우 배치) ──
        mid_frame = ttk.Frame(self)
        mid_frame.pack(fill="both", expand=True, padx=5, pady=2)

        self._create_ai_section(mid_frame)
        self._create_preview_section(mid_frame)

        # ── 하단: 적용 버튼 + 진행률 ──
        self._create_apply_section()

    # ================================================================
    # 상단: 설명 스타일 선택
    # ================================================================

    def _create_style_section(self):
        # type: () -> None
        """설명 생성 방식 라디오 버튼을 생성한다."""
        section = ttk.LabelFrame(self, text="설명 생성 방식", padding=10)
        section.pack(fill="x", padx=10, pady=5)

        self.style_var = tk.StringVar(value="original")

        options = [
            (
                "original",
                "아마존 원본 텍스트 (현재 방식)",
                "아마존에서 가져온 설명을 그대로 사용합니다",
            ),
            (
                "rich_html",
                "아마존 원본 + 이미지 삽입 (리치 HTML)",
                "이미지가 중간에 삽입된 보기 좋은 HTML을 자동 생성합니다 (추가 비용 없음)",
            ),
            (
                "clean_shopify",
                "Clean (Shopify Optimized) – 아마존 HTML 정리 + Features/Specs 구조화",
                "10단계 클리닝 파이프라인으로 불필요 요소 제거 후 구조화된 HTML 생성 (추가 비용 없음)",
            ),
            (
                "clean_ai_polish",
                "Clean + AI Polish – Clean 구조화 후 AI가 브랜드명 제거, 문법 수정, SEO 최적화",
                "10단계 클리닝 파이프라인으로 불필요 요소 제거 및 AI가 후처리합니다 (API 비용 발생)",
            ),
            (
                "ai_seo",
                "AI 생성 (SEO 최적화)",
                "OpenAI API로 SEO 최적화된 새 설명을 생성합니다 (API 비용 발생)",
            ),
            (
                "decluttly",
                "Decluttly 스타일 (AI Title + Subtitle + Body 생성)",
                "AI가 Title, Subtitle, Body HTML을 Decluttly 스토어에 맞게 생성합니다 (API 비용 발생)",
            ),
        ]

        for value, text, desc in options:
            frame = ttk.Frame(section)
            frame.pack(fill="x", pady=1)

            ttk.Radiobutton(
                frame,
                text=text,
                variable=self.style_var,
                value=value,
                command=self._on_style_change,
            ).pack(anchor="w")

            ttk.Label(
                frame, text="    " + desc, font=("Segoe UI", 8), foreground="#888888"
            ).pack(anchor="w")

    # ================================================================
    # 중간 좌측: AI 설정
    # ================================================================

    def _create_ai_section(self, parent):
        # type: (ttk.Frame) -> None
        """OpenAI 및 OpenRouter AI 설정 영역을 생성한다."""
        self.ai_section = ttk.LabelFrame(parent, text="AI 설정", padding=10)
        self.ai_section.pack(side="left", fill="both", expand=True, padx=(5, 2), pady=2)

        self.ai_frame = self.ai_section

        # Row 0: API Provider 선택
        ttk.Label(self.ai_frame, text="API Provider:").grid(
            row=0, column=0, sticky="w", padx=5, pady=3
        )
        self.api_provider_var = tk.StringVar(value="openrouter")
        provider_frame = ttk.Frame(self.ai_frame)
        provider_frame.grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(
            provider_frame,
            text="OpenRouter (권장)",
            variable=self.api_provider_var,
            value="openrouter",
            command=self._on_provider_change,
        ).pack(side="left", padx=5)
        ttk.Radiobutton(
            provider_frame,
            text="OpenAI",
            variable=self.api_provider_var,
            value="openai",
            command=self._on_provider_change,
        ).pack(side="left", padx=5)

        # Row 1: API 키
        ttk.Label(self.ai_frame, text="API Key:").grid(
            row=1, column=0, sticky="w", padx=5, pady=3
        )
        self.api_key_var = tk.StringVar()
        self.api_key_entry = ttk.Entry(
            self.ai_frame, textvariable=self.api_key_var, show="*", width=50
        )
        self.api_key_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=3)

        # Row 2: 모델 선택
        model_row = ttk.Frame(self.ai_frame)
        model_row.grid(row=2, column=0, columnspan=2, sticky="ew", padx=5, pady=3)

        ttk.Label(model_row, text="Model:").pack(side="left", padx=5)
        self.model_var = tk.StringVar(value="google/gemini-2.5-flash-lite")
        self.model_combo = ttk.Combobox(
            model_row, textvariable=self.model_var, state="readonly", width=30
        )
        self.model_combo.pack(side="left", padx=5, fill="x", expand=True)
        self.model_combo["values"] = ["google/gemini-2.5-flash-lite"]
        self.model_combo.bind(
            "<<ComboboxSelected>>", lambda e: self._update_cost_estimate()
        )

        self.load_models_btn = ttk.Button(
            model_row, text="모델 로드", command=self._load_models
        )
        self.load_models_btn.pack(side="left", padx=5)

        # Row 3: 모델 정보 라벨
        self.model_info_label = ttk.Label(
            self.ai_frame,
            text="API 키 입력 후 '모델 로드'를 클릭하세요",
            font=("", 8),
            foreground="gray",
        )
        self.model_info_label.grid(row=3, column=0, columnspan=2, sticky="w", padx=10)

        # 내부 모델 데이터 저장
        self._openrouter_models = []

        # 예상 비용
        cost_frame = ttk.Frame(self.ai_frame)
        cost_frame.grid(row=4, column=0, columnspan=2, sticky="ew", padx=5, pady=3)

        ttk.Label(cost_frame, text="예상 비용 (OpenAI만):").pack(side="left")
        self.lbl_cost = ttk.Label(
            cost_frame, text="$0.00 (상품 0개)", font=("Segoe UI", 9, "bold")
        )
        self.lbl_cost.pack(side="left", padx=5)

        # 커스텀 프롬프트
        prompt_frame = ttk.Frame(self.ai_frame)
        prompt_frame.grid(row=5, column=0, columnspan=2, sticky="nsew", padx=5, pady=3)

        ttk.Label(prompt_frame, text="커스텀 프롬프트:").pack(anchor="w")

        self.prompt_text = scrolledtext.ScrolledText(
            prompt_frame, height=4, width=50, font=("Segoe UI", 9), wrap="word"
        )
        self.prompt_text.pack(fill="both", expand=True)
        self.prompt_text.insert(
            "1.0",
            "비워두면 기본 프롬프트를 사용합니다.\n"
            "커스텀 프롬프트를 입력하면 AI가 이 지시를 따릅니다.",
        )
        self.prompt_text.configure(foreground="#999999")
        self.prompt_text.bind("<FocusIn>", self._on_prompt_focus_in)
        self.prompt_text.bind("<FocusOut>", self._on_prompt_focus_out)

        self.ai_frame.columnconfigure(1, weight=1)
        self.ai_frame.rowconfigure(5, weight=1)

        # 초기 상태: AI 위젯 비활성화
        self._set_ai_widgets_state("disabled")

    def _on_prompt_focus_in(self, event):
        # type: (tk.Event) -> None
        """프롬프트 텍스트 포커스 시 placeholder 제거."""
        content = self.prompt_text.get("1.0", "end").strip()
        if content.startswith("비워두면 기본 프롬프트"):
            self.prompt_text.delete("1.0", "end")
            self.prompt_text.configure(foreground="#000000")

    def _on_prompt_focus_out(self, event):
        # type: (tk.Event) -> None
        """프롬프트 텍스트 비어있으면 placeholder 복원."""
        content = self.prompt_text.get("1.0", "end").strip()
        if not content:
            self.prompt_text.insert(
                "1.0",
                "비워두면 기본 프롬프트를 사용합니다.\n"
                "커스텀 프롬프트를 입력하면 AI가 이 지시를 따릅니다.",
            )
            self.prompt_text.configure(foreground="#999999")

    # ================================================================
    # 중간 우측: 미리보기
    # ================================================================

    def _create_preview_section(self, parent):
        # type: (ttk.Frame) -> None
        """설명 미리보기 영역을 생성한다."""
        section = ttk.LabelFrame(parent, text="설명 미리보기", padding=10)
        section.pack(side="right", fill="both", expand=True, padx=(2, 5), pady=2)

        self.preview_text = tk.Text(
            section, height=15, state="disabled", wrap="word", font=("Segoe UI", 9)
        )
        self.preview_text.pack(fill="both", expand=True)

        ttk.Button(
            section, text="샘플 미리보기", width=15, command=self.preview_description
        ).pack(pady=(5, 0))

    # ================================================================
    # 하단: 적용 버튼 + 진행률
    # ================================================================

    def _create_apply_section(self):
        # type: () -> None
        """전체 적용 버튼과 진행률 바를 생성한다."""
        section = ttk.Frame(self)
        section.pack(fill="x", padx=10, pady=5)

        self.btn_apply = ttk.Button(
            section, text="전체 상품에 적용", width=25, command=self.apply_descriptions
        )
        self.btn_apply.pack(side="left", padx=5)

        self.apply_progress = ttk.Progressbar(section, mode="determinate", length=300)
        self.apply_progress.pack(side="left", fill="x", expand=True, padx=5)

        self.lbl_apply_status = ttk.Label(section, text="", font=("Segoe UI", 9))
        self.lbl_apply_status.pack(side="right", padx=5)

    # ================================================================
    # 스타일 변경
    # ================================================================

    def _on_style_change(self):
        # type: () -> None
        """
        라디오 버튼 변경 시 AI 설정 위젯의 활성/비활성 상태를 전환한다.
        """
        style = self.style_var.get()

        if style in ("ai_seo", "clean_ai_polish", "decluttly"):
            self._set_ai_widgets_state("normal")
            self._update_cost_estimate()
        else:
            self._set_ai_widgets_state("disabled")

        # 미리보기 초기화
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.configure(state="disabled")

    def _set_ai_widgets_state(self, state):
        # type: (str) -> None
        """
        AI 관련 위젯들의 상태를 변경한다.

        Args:
            state: "normal" 또는 "disabled".
        """
        self.api_key_entry.configure(state=state)
        self.load_models_btn.configure(
            state=state if self.api_provider_var.get() == "openrouter" else "disabled"
        )

        combo_state = "readonly" if state == "normal" else "disabled"
        self.model_combo.configure(state=combo_state)

        prompt_state = "normal" if state == "normal" else "disabled"
        self.prompt_text.configure(state=prompt_state)

    def _on_provider_change(self):
        """API Provider 변경 시 모델 목록 초기화"""
        provider = self.api_provider_var.get()
        if provider == "openrouter":
            self.model_combo["values"] = ["google/gemini-2.5-flash-lite"]
            self.model_var.set("google/gemini-2.5-flash-lite")
            self.model_combo.config(state="readonly")
            self.load_models_btn.config(
                state=(
                    "normal"
                    if self.style_var.get()
                    in ("ai_seo", "clean_ai_polish", "decluttly")
                    else "disabled"
                )
            )
            self.model_info_label.config(
                text="API 키 입력 후 '모델 로드'를 클릭하세요", foreground="gray"
            )
        else:
            self.model_combo["values"] = [
                "gpt-4o-mini",
                "gpt-4o",
                "gpt-4-turbo",
                "gpt-3.5-turbo",
            ]
            self.model_var.set("gpt-4o-mini")
            self.model_combo.config(state="readonly")
            self.load_models_btn.config(state="disabled")
            self.model_info_label.config(
                text="OpenAI 모델 (API 키: sk-...)", foreground="gray"
            )

    def _load_models(self):
        """OpenRouter에서 모델 목록을 로드합니다."""
        api_key = self.api_key_var.get().strip()
        if not api_key:
            self.model_info_label.config(
                text="❌ API 키를 먼저 입력하세요", foreground="red"
            )
            return

        self.load_models_btn.config(state="disabled", text="로딩 중...")
        self.model_info_label.config(
            text="모델 목록을 불러오는 중...", foreground="gray"
        )
        self.ai_frame.update()

        # 백그라운드에서 로드 (UI 멈춤 방지)
        def _fetch():
            from description_generator import fetch_openrouter_models

            models = fetch_openrouter_models(api_key)

            # UI 스레드에서 업데이트
            self.after(0, lambda: self._update_model_list(models))

        threading.Thread(target=_fetch, daemon=True).start()

    def _update_model_list(self, models):
        """모델 목록 UI를 업데이트합니다."""
        self.load_models_btn.config(
            state=(
                "normal"
                if self.style_var.get() in ("ai_seo", "clean_ai_polish", "decluttly")
                else "disabled"
            ),
            text="모델 로드",
        )

        if not models:
            self.model_info_label.config(
                text="❌ 모델 로드 실패. API 키를 확인하세요.", foreground="red"
            )
            return

        self._openrouter_models = models
        id_list = [m["id"] for m in models]

        self.model_combo["values"] = id_list

        default_model = "google/gemini-2.5-flash-lite"
        if default_model in id_list:
            self.model_var.set(default_model)
        elif id_list:
            self.model_var.set(id_list[0])

        self.model_info_label.config(
            text=f"✅ {len(models)}개 모델 로드 완료. 기본: {self.model_var.get()}",
            foreground="green",
        )

    # ================================================================
    # API 키 테스트 (제거됨 - OpenRouter 모델 로드로 대체)
    # ================================================================

    def test_api_key(self):
        # legacy override (no op)
        pass

    # ================================================================
    # 비용 추정
    # ================================================================

    def _update_cost_estimate(self):
        # type: () -> None
        """선택된 모델과 상품 수로 예상 비용을 계산하여 라벨에 표시한다."""
        model = self.model_var.get()
        cost_per_product = {
            "gpt-4o-mini": 0.01,
            "gpt-4o": 0.03,
            "gpt-3.5-turbo": 0.005,
        }

        rate = cost_per_product.get(model, 0.01)

        # 상품 수 추정 (output 폴더에서)
        product_count = self._get_product_count()

        total_cost = rate * product_count
        self.lbl_cost.configure(
            text="${:.2f} (상품 {}개 × ${:.3f}/건)".format(
                total_cost, product_count, rate
            )
        )

    def _get_product_count(self):
        # type: () -> int
        """output 폴더의 상품 수를 추정한다."""
        output_dir = os.path.abspath("output")
        count = 0

        if os.path.exists(output_dir):
            pattern = os.path.join(output_dir, "products_backup_*.json")
            for filepath in glob.glob(pattern):
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, list):
                        count += len(data)
                except Exception:
                    pass

        return count if count > 0 else 0

    # ================================================================
    # 미리보기
    # ================================================================

    def preview_description(self):
        # type: () -> None
        """
        첫 번째 상품으로 선택된 스타일의 설명을 미리보기 생성하여 표시한다.

        AI 스타일은 별도 스레드에서 실행한다.
        """
        product = self._get_sample_product()
        if product is None:
            messagebox.showinfo(
                "알림",
                "미리보기할 상품이 없습니다.\n"
                "먼저 스크래핑을 실행하거나 output 폴더에 결과 파일을 넣어주세요.",
            )
            return

        style = self.style_var.get()

        if style in ("ai_seo", "clean_ai_polish", "decluttly"):
            api_key = self.api_key_var.get().strip()
            if not api_key:
                messagebox.showwarning("경고", "AI 미리보기에는 API 키가 필요합니다.")
                return

            self._set_preview_text("AI 설명 생성 중...")

            def _generate():
                try:
                    from description_generator import (
                        generate_ai_description,
                        generate_clean_description,
                        ai_polish_description,
                        generate_decluttly_description,
                    )

                    custom = self._get_custom_prompt()
                    provider = getattr(
                        self, "api_provider_var", tk.StringVar(value="openrouter")
                    ).get()

                    if style == "clean_ai_polish":
                        clean_html = generate_clean_description(product)
                        if provider == "openrouter":
                            res = ai_polish_description(
                                product, clean_html, api_key, model=self.model_var.get()
                            )
                            result = res.get("body_html", clean_html)
                        else:
                            result = generate_ai_description(
                                product,
                                api_key,
                                model=self.model_var.get(),
                                custom_prompt=custom,
                            )
                    elif style == "decluttly":
                        res = generate_decluttly_description(
                            product, api_key, model=self.model_var.get()
                        )
                        # 미리보기는 body_html과 기타 생성 정보를 텍스트로 보여준다
                        ai_t = res.get("ai_title", "")
                        ai_s = res.get("ai_subtitle", "")
                        body = res.get("body_html", "")
                        result = "=== AI Title ===\n{}\n\n=== AI Subtitle ===\n{}\n\n=== Body HTML ===\n{}".format(
                            ai_t, ai_s, body
                        )
                    else:
                        result = generate_ai_description(
                            product,
                            api_key,
                            model=self.model_var.get(),
                            custom_prompt=custom,
                        )
                    self.after(0, lambda: self._set_preview_text(result))
                except Exception as e:
                    self.after(0, lambda: self._set_preview_text("오류: {}".format(e)))

            threading.Thread(target=_generate, daemon=True).start()
        else:
            try:
                if style == "rich_html":
                    from description_generator import generate_rich_html

                    result = generate_rich_html(product)
                elif style == "clean_shopify":
                    from description_generator import generate_clean_description

                    result = generate_clean_description(product)
                else:
                    from description_generator import generate_original_text

                    result = generate_original_text(product)

                self._set_preview_text(result)
            except Exception as e:
                self._set_preview_text("오류: {}".format(e))

    def _get_sample_product(self):
        # type: () -> dict or None
        """output 폴더에서 첫 번째 상품을 가져온다."""
        output_dir = os.path.abspath("output")

        if os.path.exists(output_dir):
            pattern = os.path.join(output_dir, "products_backup_*.json")
            files = glob.glob(pattern)

            if not files:
                pattern = os.path.join(output_dir, "products_*.json")
                files = glob.glob(pattern)

            for filepath in files:
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, list) and data:
                        return data[0]
                except Exception:
                    pass

        return None

    def _set_preview_text(self, text):
        # type: (str) -> None
        """미리보기 Text 위젯에 텍스트를 설정한다."""
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", text)
        self.preview_text.configure(state="disabled")

    def _get_custom_prompt(self):
        # type: () -> str or None
        """
        커스텀 프롬프트를 반환한다.

        placeholder이거나 비어있으면 None을 반환한다.
        """
        content = self.prompt_text.get("1.0", "end").strip()
        if not content or content.startswith("비워두면 기본 프롬프트"):
            return None
        return content

    # ================================================================
    # 전체 적용
    # ================================================================

    def apply_descriptions(self, products=None):
        # type: (list) -> None
        """
        선택된 스타일과 설정으로 전체 상품의 설명을 생성한다.

        별도 스레드에서 실행하며 진행률 바를 업데이트한다.

        Args:
            products: 상품 리스트. None이면 output 폴더에서 로드.
        """
        style = self.style_var.get()

        if style in ("ai_seo", "clean_ai_polish", "decluttly"):
            api_key = self.api_key_var.get().strip()
            if not api_key:
                messagebox.showwarning("경고", "AI 설명 생성에는 API 키가 필요합니다.")
                return

        self.btn_apply.configure(state="disabled")
        self.apply_progress["value"] = 0
        self.lbl_apply_status.configure(text="준비 중...")

        def _run():
            try:
                # 상품 로드
                if products is None:
                    loaded = self._load_all_products()
                else:
                    loaded = list(products)

                if not loaded:
                    self.after(
                        0,
                        lambda: messagebox.showinfo("알림", "적용할 상품이 없습니다."),
                    )
                    return

                total = len(loaded)
                self.after(
                    0,
                    lambda: self.lbl_apply_status.configure(text="0/{}".format(total)),
                )

                from description_generator import (
                    generate_original_text,
                    generate_rich_html,
                    generate_ai_description,
                    generate_clean_description,
                    ai_polish_description,
                    generate_decluttly_description,
                )

                api_key = self.api_key_var.get().strip()
                provider = getattr(
                    self, "api_provider_var", tk.StringVar(value="openrouter")
                ).get()
                model = self.model_var.get()
                custom = self._get_custom_prompt()

                for i, product in enumerate(loaded):
                    try:
                        if style == "original":
                            body = generate_original_text(product)
                        elif style == "rich_html":
                            body = generate_rich_html(product)
                        elif style == "clean_shopify":
                            body = generate_clean_description(product)
                        elif style == "clean_ai_polish":
                            clean_html = generate_clean_description(product)
                            if provider == "openrouter":
                                res = ai_polish_description(
                                    product, clean_html, api_key, model=model
                                )
                                body = res.get("body_html", clean_html)
                                if res.get("seo_description"):
                                    product["_ai_seo_description"] = res.get(
                                        "seo_description"
                                    )
                            else:
                                body = generate_ai_description(
                                    product, api_key, model=model, custom_prompt=custom
                                )
                        elif style == "decluttly":
                            res = generate_decluttly_description(
                                product, api_key, model=model
                            )
                            body = res.get("body_html", "")
                            if res.get("ai_title"):
                                product["_ai_title"] = res["ai_title"]
                            if res.get("ai_subtitle"):
                                product["_ai_subtitle"] = res["ai_subtitle"]
                            if res.get("seo_title"):
                                product["_ai_seo_title"] = res["seo_title"]
                            if res.get("seo_description"):
                                product["_ai_seo_description"] = res["seo_description"]
                            if not body:
                                body = generate_clean_description(product)
                        elif style == "ai_seo":
                            body = generate_ai_description(
                                product, api_key, model=model, custom_prompt=custom
                            )
                        else:
                            body = generate_original_text(product)

                        product["body_html"] = body

                    except Exception:
                        pass

                    # 진행률 업데이트
                    pct = int(((i + 1) / total) * 100)
                    status = "{}/{}".format(i + 1, total)
                    self.after(
                        0, lambda p=pct, s=status: self._update_apply_progress(p, s)
                    )

                # 결과 저장
                self._save_processed_products(loaded)

                self.after(
                    0,
                    lambda: messagebox.showinfo(
                        "완료",
                        "{}개 상품의 설명을 생성했습니다.\n"
                        "스타일: {}".format(total, style),
                    ),
                )

            except Exception as e:
                self.after(
                    0,
                    lambda err=str(e): messagebox.showerror(
                        "오류", "설명 생성 중 오류:\n{}".format(err)
                    ),
                )
            finally:
                self.after(0, lambda: self.btn_apply.configure(state="normal"))
                self.after(0, lambda: self.lbl_apply_status.configure(text="완료"))

        threading.Thread(target=_run, daemon=True).start()

    def _update_apply_progress(self, pct, status_text):
        # type: (int, str) -> None
        """적용 진행률을 업데이트한다."""
        self.apply_progress["value"] = pct
        self.lbl_apply_status.configure(text=status_text)

    def _load_all_products(self):
        # type: () -> list
        """output 폴더에서 모든 상품을 로드한다."""
        output_dir = os.path.abspath("output")
        all_products = []

        if not os.path.exists(output_dir):
            return all_products

        patterns = [
            os.path.join(output_dir, "products_backup_*.json"),
            os.path.join(output_dir, "products_*.json"),
        ]

        seen_files = set()
        for pattern in patterns:
            for filepath in glob.glob(pattern):
                if filepath in seen_files:
                    continue
                seen_files.add(filepath)

                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, list):
                        all_products.extend(data)
                except Exception:
                    pass

        return all_products

    def _save_processed_products(self, products):
        # type: (list) -> None
        """설명이 업데이트된 상품을 파일로 저장한다."""
        output_dir = os.path.abspath("output")
        os.makedirs(output_dir, exist_ok=True)

        filepath = os.path.join(output_dir, "products_with_descriptions.json")
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(products, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ================================================================
    # 외부 접근 메서드
    # ================================================================

    def get_style(self):
        # type: () -> str
        """현재 선택된 설명 스타일을 반환한다."""
        return self.style_var.get()

    def get_ai_settings(self):
        # type: () -> dict
        """
        AI 관련 설정을 딕셔너리로 반환한다.

        Returns:
            dict: provider, api_key, model, custom_prompt 포함.
        """
        return {
            "provider": self.api_provider_var.get(),
            "api_key": self.api_key_var.get().strip(),
            "model": self.model_var.get(),
            "custom_prompt": self._get_custom_prompt(),
        }

    def set_ai_settings(self, settings):
        # type: (dict) -> None
        """AI 설정을 복원합니다."""
        if "provider" in settings and hasattr(self, "api_provider_var"):
            self.api_provider_var.set(settings["provider"])
        if "api_key" in settings:
            self.api_key_var.set(settings["api_key"])
        if "model" in settings:
            self.model_var.set(settings["model"])
            self.model_combo["values"] = [settings["model"]]
        if hasattr(self, "_on_provider_change"):
            self._on_provider_change()

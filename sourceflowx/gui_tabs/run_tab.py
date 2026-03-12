"""
SourceFlowX - 실행 탭
스크래핑 작업의 시작/일시정지/중지, 진행률 표시,
실시간 로그, 키워드별 결과 요약을 제공하는 핵심 탭.
실제 스크래핑 엔진과 연결되어 파이프라인을 실행한다.
"""

import tkinter as tk
from tkinter import ttk
from tkinter import scrolledtext
from tkinter import filedialog
from tkinter import messagebox
import threading
import time
import os
import json
import sys
import logging
from datetime import datetime
import queue


class QueueLogHandler(logging.Handler):
    """
    logging.Handler를 상속하여 로그 메시지를 Queue에 넣는 핸들러.

    모든 모듈의 로거에 추가하면 GUI 로그창에 로그가 표시된다.
    """

    def __init__(self, log_queue):
        # type: (queue.Queue) -> None
        """
        QueueLogHandler를 초기화한다.

        Args:
            log_queue: 로그 메시지를 넣을 Queue.
        """
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        # type: (logging.LogRecord) -> None
        """
        로그 레코드를 포맷하여 큐에 넣는다.

        Args:
            record: logging.LogRecord 객체.
        """
        try:
            msg = self.format(record)
            self.log_queue.put(msg)
        except Exception:
            pass


class RunTab(ttk.Frame):
    """
    실행 탭 프레임.

    스크래핑 파이프라인의 시작/일시정지/중지 제어,
    전체/키워드별 진행률 표시, 실시간 로그, 키워드별 결과 테이블을 제공한다.
    실제 scraper, quality_checker, price_adjuster, shopify_exporter,
    description_generator 모듈과 연결된다.
    """

    def __init__(self, parent):
        # type: (tk.Widget) -> None
        """
        실행 탭을 초기화한다.

        Args:
            parent: 부모 위젯 (Notebook).
        """
        super().__init__(parent)

        # 외부 연결 (gui_app.py에서 설정)
        self.app = None

        # 실행 상태
        self.is_running = False
        self.is_paused = False
        self.worker_thread = None
        self.start_time = None

        # 카운터
        self.total_products = 0
        self.processed_count = 0
        self.passed_count = 0
        self.failed_count = 0
        self.image_count = 0

        # 키워드 정보
        self.current_keyword = ""
        self.current_keyword_index = 0
        self.total_keywords = 0

        # 로그 큐 (스레드 안전)
        self.log_queue = queue.Queue()

        # 실패 키워드 추적
        self.failed_keywords = []

        self._create_widgets()
        self._poll_log_queue()

    def _create_widgets(self):
        # type: () -> None
        """컨트롤, 통계, 진행률, 키워드 결과, 로그 영역을 배치한다."""
        # ── 상단: 컨트롤 + 통계 (좌우 배치) ──
        top_frame = ttk.Frame(self)
        top_frame.pack(fill="x", padx=5, pady=2)

        self._create_control_section(top_frame)
        self._create_stats_section(top_frame)

        # ── 중간: 진행률 바 ──
        self._create_progress_section()

        # ── 중간: 키워드별 결과 ──
        self._create_keyword_results_section()

        # ── 하단: 실시간 로그 ──
        self._create_log_section()

    # ================================================================
    # 상단 좌측: 실행 제어
    # ================================================================

    def _create_control_section(self, parent):
        # type: (ttk.Frame) -> None
        """시작/일시정지/중지 버튼을 생성한다."""
        section = ttk.LabelFrame(parent, text="실행 제어", padding=10)
        section.pack(side="left", fill="y", padx=(5, 2), pady=2)

        self.btn_start = ttk.Button(
            section, text="▶ 시작", width=15, command=self.start_scraping
        )
        self.btn_start.pack(side="left", padx=5, pady=2)

        self.btn_pause = ttk.Button(
            section,
            text="⏸ 일시정지",
            width=15,
            command=self.toggle_pause,
            state="disabled",
        )
        self.btn_pause.pack(side="left", padx=5, pady=2)

        self.btn_stop = ttk.Button(
            section,
            text="⏹ 중지",
            width=15,
            command=self.stop_scraping,
            state="disabled",
        )
        self.btn_stop.pack(side="left", padx=5, pady=2)

    # ================================================================
    # 상단 우측: 실시간 통계
    # ================================================================

    def _create_stats_section(self, parent):
        # type: (ttk.Frame) -> None
        """실시간 현황 라벨들을 생성한다."""
        section = ttk.LabelFrame(parent, text="실시간 현황", padding=10)
        section.pack(side="left", fill="both", expand=True, padx=(2, 5), pady=2)

        labels = [
            ("현재 키워드:", "lbl_current_keyword", "-"),
            ("진행 상태:", "lbl_progress_text", "대기 중"),
            ("처리 속도:", "lbl_speed", "- 상품/분"),
            ("예상 잔여:", "lbl_eta", "-"),
            ("경과 시간:", "lbl_elapsed", "0:00:00"),
        ]

        for i, (label_text, attr_name, default) in enumerate(labels):
            row = i // 3
            col = (i % 3) * 2

            ttk.Label(section, text=label_text, font=("Segoe UI", 9)).grid(
                row=row, column=col, sticky="w", padx=(5, 2), pady=1
            )

            lbl = ttk.Label(section, text=default, font=("Segoe UI", 9, "bold"))
            lbl.grid(row=row, column=col + 1, sticky="w", padx=(0, 15), pady=1)
            setattr(self, attr_name, lbl)

        for c in range(6):
            section.columnconfigure(c, weight=1 if c % 2 == 1 else 0)

    # ================================================================
    # 중간: 진행률 바
    # ================================================================

    def _create_progress_section(self):
        # type: () -> None
        """전체/키워드별 진행률 바를 생성한다."""
        # 전체 진행률
        total_section = ttk.LabelFrame(self, text="전체 진행률", padding=5)
        total_section.pack(fill="x", padx=10, pady=2)

        progress_frame = ttk.Frame(total_section)
        progress_frame.pack(fill="x")

        self.total_progress = ttk.Progressbar(
            progress_frame, mode="determinate", length=400
        )
        self.total_progress.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.lbl_total_percent = ttk.Label(
            progress_frame, text="0%", width=6, anchor="e", font=("Segoe UI", 9, "bold")
        )
        self.lbl_total_percent.pack(side="right")

        # 키워드별 진행률
        kw_section = ttk.LabelFrame(self, text="현재 키워드 진행률", padding=5)
        kw_section.pack(fill="x", padx=10, pady=2)

        kw_progress_frame = ttk.Frame(kw_section)
        kw_progress_frame.pack(fill="x")

        self.keyword_progress = ttk.Progressbar(
            kw_progress_frame, mode="determinate", length=400
        )
        self.keyword_progress.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.lbl_keyword_percent = ttk.Label(
            kw_progress_frame,
            text="0%",
            width=6,
            anchor="e",
            font=("Segoe UI", 9, "bold"),
        )
        self.lbl_keyword_percent.pack(side="right")

        self.lbl_current_asin = ttk.Label(
            kw_section, text="현재 처리: -", font=("Segoe UI", 9)
        )
        self.lbl_current_asin.pack(anchor="w", pady=(2, 0))

    # ================================================================
    # 중간: 키워드별 결과 Treeview
    # ================================================================

    def _create_keyword_results_section(self):
        # type: () -> None
        """키워드별 결과 요약 테이블을 생성한다."""
        section = ttk.LabelFrame(self, text="키워드별 결과", padding=5)
        section.pack(fill="x", padx=10, pady=2)

        columns = (
            "keyword",
            "searched",
            "collected",
            "passed",
            "rejected",
            "images",
            "status",
        )
        self.kw_tree = ttk.Treeview(
            section, columns=columns, show="headings", height=4, selectmode="none"
        )

        self.kw_tree.heading("keyword", text="키워드")
        self.kw_tree.heading("searched", text="검색")
        self.kw_tree.heading("collected", text="수집")
        self.kw_tree.heading("passed", text="통과")
        self.kw_tree.heading("rejected", text="탈락")
        self.kw_tree.heading("images", text="이미지")
        self.kw_tree.heading("status", text="상태")

        self.kw_tree.column("keyword", width=180, anchor="w")
        self.kw_tree.column("searched", width=60, anchor="center")
        self.kw_tree.column("collected", width=60, anchor="center")
        self.kw_tree.column("passed", width=60, anchor="center")
        self.kw_tree.column("rejected", width=60, anchor="center")
        self.kw_tree.column("images", width=60, anchor="center")
        self.kw_tree.column("status", width=80, anchor="center")

        # 행 색상 태그
        self.kw_tree.tag_configure("done", background="#d4edda")
        self.kw_tree.tag_configure("fail", background="#f8d7da")
        self.kw_tree.tag_configure("running", background="#cce5ff")
        self.kw_tree.tag_configure("waiting", background="")

        kw_scroll = ttk.Scrollbar(
            section, orient="vertical", command=self.kw_tree.yview
        )
        self.kw_tree.configure(yscrollcommand=kw_scroll.set)

        self.kw_tree.pack(side="left", fill="x", expand=True)
        kw_scroll.pack(side="right", fill="y")

        # 우클릭 메뉴 바인딩
        self.kw_tree.bind("<Button-3>", self._on_keyword_right_click)

        # 실패 키워드 재실행 버튼
        kw_btn_frame = ttk.Frame(section)
        kw_btn_frame.pack(fill="x", pady=(5, 0))

        self.btn_retry_failed = ttk.Button(
            kw_btn_frame,
            text="🔄 실패 키워드 재실행",
            width=22,
            command=self.retry_failed_keywords,
            state="disabled",
        )
        self.btn_retry_failed.pack(side="left", padx=2)

    # ================================================================
    # 하단: 실시간 로그
    # ================================================================

    def _create_log_section(self):
        # type: () -> None
        """실행 로그 textarea와 관련 버튼을 생성한다."""
        section = ttk.LabelFrame(self, text="실행 로그", padding=5)
        section.pack(fill="both", expand=True, padx=10, pady=(2, 5))

        self.log_text = scrolledtext.ScrolledText(
            section,
            height=12,
            state="disabled",
            wrap="word",
            font=("Consolas", 9),
            bg="#1e1e1e",
            fg="#00ff00",
            insertbackground="#00ff00",
        )
        self.log_text.pack(fill="both", expand=True)

        log_btn_frame = ttk.Frame(section)
        log_btn_frame.pack(fill="x", pady=(5, 0))

        ttk.Button(
            log_btn_frame, text="로그 지우기", width=12, command=self.clear_log
        ).pack(side="left", padx=2)

        ttk.Button(
            log_btn_frame, text="로그 저장", width=12, command=self.save_log
        ).pack(side="left", padx=2)

    # ================================================================
    # 실행 제어
    # ================================================================

    def start_scraping(self):
        # type: () -> None
        """
        스크래핑 파이프라인을 시작한다.

        설정 탭에서 설정을 가져오고, 프록시 탭에서 프록시를 가져와
        별도 스레드에서 파이프라인을 실행한다.
        """
        if self.app is None:
            messagebox.showerror("오류", "앱이 초기화되지 않았습니다.")
            return

        # 설정 가져오기
        settings = self.app.settings_tab.get_settings()
        keywords = settings.get("CATEGORY_KEYWORDS", [])

        if not keywords:
            messagebox.showwarning("키워드 없음", "설정 탭에서 키워드를 추가해주세요.")
            return

        # 프록시 가져오기
        proxies = self.app.proxy_tab.get_active_proxies()

        # 카운터 초기화
        self.reset()
        self.failed_keywords = []
        self.btn_retry_failed.configure(state="disabled")

        # 총 상품 수 추정 (키워드당 max_pages * 48)
        max_pages = settings.get("MAX_PAGES", 20)
        self.total_products = len(keywords) * max_pages * 48

        # 키워드별 결과 Treeview 초기화
        for item in self.kw_tree.get_children():
            self.kw_tree.delete(item)

        for keyword in keywords:
            self.kw_tree.insert(
                "",
                "end",
                values=(keyword, "-", "-", "-", "-", "-", "대기"),
                tags=("waiting",),
            )

        # 상태 설정
        self.is_running = True
        self.is_paused = False
        self.total_keywords = len(keywords)
        self.start_time = time.time()

        # 버튼 상태 변경
        self.btn_start.configure(state="disabled")
        self.btn_pause.configure(state="normal")
        self.btn_stop.configure(state="normal")

        # 진행 상태 업데이트
        self.lbl_progress_text.configure(text="실행 중")

        import config

        config.RUNTIME_STOPPED = False
        config.RUNTIME_PAUSED = False

        self._log("SourceFlowX 시작")
        self._log("키워드 {}개, 프록시 {}개".format(len(keywords), len(proxies)))

        # 설명 스타일/AI 설정을 메인 스레드에서 미리 읽기
        desc_style = "original"
        desc_ai_settings = {}
        if self.app and hasattr(self.app, "description_tab"):
            desc_style = self.app.description_tab.get_style()
            desc_ai_settings = self.app.description_tab.get_ai_settings()

        # 워커 스레드 시작
        self.worker_thread = threading.Thread(
            target=self._run_pipeline,
            args=(settings, proxies, desc_style, desc_ai_settings),
            daemon=True,
        )
        self.worker_thread.start()

        # 경과 시간 업데이트 시작
        self._update_elapsed_time()

    def toggle_pause(self):
        # type: () -> None
        """일시정지와 재개를 토글한다."""
        self.is_paused = not self.is_paused

        import config

        config.RUNTIME_PAUSED = self.is_paused

        if self.is_paused:
            self.btn_pause.configure(text="▶ 재개")
            self.lbl_progress_text.configure(text="일시정지")
            self._log("⏸ 일시정지됨")
        else:
            self.btn_pause.configure(text="⏸ 일시정지")
            self.lbl_progress_text.configure(text="실행 중")
            self._log("▶ 재개됨")

    def stop_scraping(self):
        # type: () -> None
        """
        확인 후 스크래핑을 중지한다.

        현재까지 수집된 데이터는 보존된다.
        """
        if not messagebox.askokcancel(
            "중지",
            "진행 중인 작업을 중지하시겠습니까?\n"
            "현재까지 수집된 데이터는 저장됩니다.",
        ):
            return

        self.is_running = False
        self.is_paused = False

        import config

        config.RUNTIME_STOPPED = True
        config.RUNTIME_PAUSED = False

        self._log("⏹ 사용자에 의해 중지됨")
        self.lbl_progress_text.configure(text="중지됨")

        # 버튼 복원
        self.btn_start.configure(state="normal")
        self.btn_pause.configure(state="disabled", text="⏸ 일시정지")
        self.btn_stop.configure(state="disabled")

    # ================================================================
    # 파이프라인 (별도 스레드) – 실제 스크래퍼 연결
    # ================================================================

    def _run_pipeline(
        self, settings, proxies, desc_style="original", desc_ai_settings=None
    ):
        # type: (dict, list, str, dict) -> None
        """
        실제 스크래핑 파이프라인을 실행한다 (별도 스레드).

        config 값을 GUI 설정으로 오버라이드한 뒤,
        scraper → price_adjuster → description_generator →
        quality_checker → shopify_exporter 순서로 처리한다.

        Args:
            settings: 설정 딕셔너리.
            proxies: 프록시 리스트.
            desc_style: 설명 생성 스타일 ("original"/"rich"/"ai").
            desc_ai_settings: AI 설명 설정 딕셔너리.
        """
        if desc_ai_settings is None:
            desc_ai_settings = {}
        queue_handler = None

        try:
            import config
            from scraper import AmazonFullScraper
            from price_adjuster import adjust_prices
            from quality_checker import QualityChecker
            from shopify_exporter import export_shopify_csv
            from description_generator import generate_descriptions

            # 설정 수집
            try:
                self._shopify_settings = self.app.shopify_tab.get_shopify_settings()
            except Exception:
                self._shopify_settings = {}
            if self._shopify_settings is None:
                self._shopify_settings = {}

            # config.py의 SHOPIFY_EXTENDED와 병합
            if hasattr(config, "SHOPIFY_EXTENDED"):
                for k, v in config.SHOPIFY_EXTENDED.items():
                    if k not in self._shopify_settings:
                        self._shopify_settings[k] = v

            # description_style에 'decluttly'가 선택된 경우 오버라이드
            if desc_style == "decluttly":
                self._shopify_settings["description_style"] = "decluttly"
                self._shopify_settings["title_style"] = "ai_benefit"
                self._shopify_settings["subtitle_style"] = "ai_generate"
                self._shopify_settings["vendor_override"] = "Decluttly"
            else:
                self._shopify_settings["description_style"] = desc_style

            try:
                self._price_settings = self.app.settings_tab.get_price_settings()
            except Exception:
                self._price_settings = None

            try:
                self._collection_mapping = self.app.shopify_tab.get_collection_mapping()
            except Exception:
                self._collection_mapping = None

            keywords = settings.get("CATEGORY_KEYWORDS", [])
            self.total_keywords = len(keywords)

            # ── 1. config.py 값을 GUI 설정으로 오버라이드 ──
            config.MAX_PAGES = settings.get("MAX_PAGES", 20)
            config.ENRICH_LIMIT = settings.get("ENRICH_LIMIT") or None
            config.MAX_WORKERS = settings.get("MAX_WORKERS", 5)
            config.CHECKPOINT_INTERVAL = settings.get("CHECKPOINT_INTERVAL", 100)
            config.MARGIN_PERCENT = settings.get("MARGIN_PERCENT", 30.0)
            config.COMPARE_PRICE_MARKUP = settings.get("COMPARE_PRICE_MARKUP", 1.2)
            config.MIN_PRICE = settings.get("MIN_PRICE", 5.0)
            config.MAX_PRICE = settings.get("MAX_PRICE", 500.0)
            config.MIN_RATING = settings.get("MIN_RATING", 3.5)
            config.MIN_REVIEWS = settings.get("MIN_REVIEWS", 10)
            config.MIN_IMAGES = settings.get("MIN_IMAGES", 1)
            config.MIN_TITLE_LENGTH = settings.get("MIN_TITLE_LENGTH", 10)
            config.REQUEST_TIMEOUT = settings.get("REQUEST_TIMEOUT", 25)
            config.MAX_RETRIES = settings.get("MAX_RETRIES", 3)
            config.RETRY_BACKOFF = settings.get("RETRY_BACKOFF", 5)
            config.DELAY_MIN = settings.get("DELAY_MIN", 3.0)
            config.DELAY_MAX = settings.get("DELAY_MAX", 7.0)
            config.KEYWORD_DELAY = settings.get("KEYWORD_DELAY", 10)
            config.IMPERSONATE = settings.get("IMPERSONATE", "chrome119")
            config.MERGE_CSV = settings.get("MERGE_CSV", True)
            config.OUTPUT_DIR = settings.get("OUTPUT_DIR", "output")

            os.makedirs(config.OUTPUT_DIR, exist_ok=True)

            # ── 2. QueueLogHandler를 로거들에 추가 ──
            queue_handler = QueueLogHandler(self.log_queue)
            queue_handler.setFormatter(
                logging.Formatter("[%(asctime)s] %(message)s", datefmt="%H:%M:%S")
            )

            logger_names = [
                "sourceflowx",
                "scraper",
                "proxy",
                "checkpoint",
                "extractor",
                "price",
                "quality",
                "exporter",
                "description",
            ]
            for name in logger_names:
                sub_logger = logging.getLogger(name)
                # 기존 QueueLogHandler 제거 (중복 출력 방지)
                for h in list(sub_logger.handlers):
                    if type(h).__name__ == "QueueLogHandler":
                        sub_logger.removeHandler(h)
                sub_logger.addHandler(queue_handler)

            # ── 3. 프록시 파일 생성 ──
            if proxies:
                with open("proxies.txt", "w", encoding="utf-8") as f:
                    for p in proxies:
                        line = "{}:{}".format(p["host"], p["port"])
                        if p.get("username"):
                            line += ":{}:{}".format(p["username"], p["password"])
                        f.write(line + "\n")
                self._log("프록시 {}개 → proxies.txt 저장 완료".format(len(proxies)))

            # 하나의 ProxyManager 인스턴스 공유 (이미 실패/차단된 IP 재사용 방지)
            from proxy_manager import ProxyManager

            global_proxy_mgr = ProxyManager("proxies.txt" if proxies else None)

            all_passed = []
            all_rejected = []
            all_products = []

            # ── 4. 키워드별 처리 ──
            for i, keyword in enumerate(keywords):
                from utils import check_state

                try:
                    check_state()
                except RuntimeError as e:
                    self._log(str(e))
                    break

                if not self.is_running:
                    break

                result = self._process_keyword(
                    keyword,
                    i,
                    len(keywords),
                    settings,
                    desc_style,
                    desc_ai_settings,
                    all_passed,
                    all_rejected,
                    all_products,
                    global_proxy_mgr,
                )

                # 전체 진행률 업데이트
                self.after(0, self._update_progress)

                # 키워드 간 대기
                if i < len(keywords) - 1 and self.is_running:
                    delay = settings.get("KEYWORD_DELAY", 10)
                    if delay > 0:
                        self._log("다음 키워드까지 {}초 대기...".format(delay))
                        for _ in range(int(delay * 2)):
                            if not self.is_running:
                                break
                            time.sleep(0.5)

            # ── 4-1. 실패 키워드 자동 재순회 ──
            if self.failed_keywords and self.is_running:
                retry_keywords = self.failed_keywords.copy()
                self.failed_keywords = []
                self._log("=" * 50)
                self._log(
                    "[자동 재시도] 실패 키워드 {}개 재시도 시작 (20초 대기)".format(
                        len(retry_keywords)
                    )
                )
                self._log("=" * 50)

                # 차단/실패되었던 프록시 이력 모두 초기화하여 재도전
                global_proxy_mgr.reset_failed()

                # 프록시 쿨다운 대기
                for _ in range(40):
                    if not self.is_running:
                        break
                    time.sleep(0.5)

                # Treeview에 재시도 키워드 추가
                retry_start_idx = len(self.kw_tree.get_children())
                for kw in retry_keywords:
                    self.kw_tree.insert(
                        "",
                        "end",
                        values=(kw, "-", "-", "-", "-", "-", "재시도"),
                        tags=("running",),
                    )

                for j, keyword in enumerate(retry_keywords):
                    from utils import check_state

                    try:
                        check_state()
                    except RuntimeError as e:
                        self._log(str(e))
                        break

                    if not self.is_running:
                        break

                    tree_idx = retry_start_idx + j
                    result = self._process_keyword(
                        keyword,
                        tree_idx,
                        len(retry_keywords),
                        settings,
                        desc_style,
                        desc_ai_settings,
                        all_passed,
                        all_rejected,
                        all_products,
                        global_proxy_mgr,
                    )

                    self.after(0, self._update_progress)

                    # 키워드 간 대기
                    if j < len(retry_keywords) - 1 and self.is_running:
                        delay = settings.get("KEYWORD_DELAY", 10)
                        if delay > 0:
                            for _ in range(int(delay * 2)):
                                from utils import check_state

                                try:
                                    check_state()
                                except RuntimeError as e:
                                    self._log(str(e))
                                    break

                                if not self.is_running:
                                    break
                                time.sleep(0.5)

            # ── 5. 통합 CSV 생성 ──
            if config.MERGE_CSV and all_passed and self.is_running:
                try:
                    merged_file = os.path.join(
                        config.OUTPUT_DIR, config.MERGED_CSV_FILENAME
                    )
                    export_shopify_csv(
                        all_passed,
                        output_path=merged_file,
                        keyword="all",
                        shopify_settings=getattr(self, "_shopify_settings", None),
                        price_settings=getattr(self, "_price_settings", None),
                        collection_mapping=getattr(self, "_collection_mapping", None),
                    )
                    self._log(
                        "[통합 CSV] {} 생성 완료 ({}개 상품)".format(
                            merged_file, len(all_passed)
                        )
                    )
                except Exception as e:
                    self._log("[통합 CSV 오류] {}".format(e))

            # ── 6. 결과 탭에 데이터 전달 ──
            if self.app:
                try:
                    results_tab = self.app.results_tab
                    self.after(
                        0,
                        lambda: results_tab.load_results(
                            all_passed, all_rejected, all_products
                        ),
                    )
                except Exception:
                    pass

            # ── 7. 완료 로그 ──
            self._log("=" * 50)
            if self.is_running:
                self._log("✅ SourceFlowX 완료!")
            else:
                self._log("⏹ 중지됨. 현재까지 결과가 저장되었습니다.")
            self._log(
                "총 통과: {}개 / 총 탈락: {}개 / 총 이미지: {}장".format(
                    self.passed_count, self.failed_count, self.image_count
                )
            )

        except ImportError as ie:
            self._log("[모듈 오류] 필요한 모듈을 찾을 수 없습니다: {}".format(ie))
            self._log("pip install curl_cffi beautifulsoup4 lxml amzpy 실행 필요")
        except RuntimeError as re_err:
            # check_state()에 의한 사용자 중지 - 정상 종료 처리
            self._log("⏹ {}".format(str(re_err)))
        except Exception as e:
            self._log("[치명적 오류] {}".format(str(e)))
        finally:
            # 로거 핸들러 정리
            if queue_handler:
                logger_names = [
                    "sourceflowx",
                    "scraper",
                    "proxy",
                    "checkpoint",
                    "extractor",
                    "price",
                    "quality",
                    "exporter",
                    "description",
                ]
                for name in logger_names:
                    try:
                        logging.getLogger(name).removeHandler(queue_handler)
                    except Exception:
                        pass

            self.is_running = False
            self.after(0, self._on_complete)

    # ================================================================
    # 키워드 1개 처리 (재사용 가능)
    # ================================================================

    def _process_keyword(
        self,
        keyword,
        tree_index,
        total_count,
        settings,
        desc_style,
        desc_ai_settings,
        all_passed,
        all_rejected,
        all_products,
        global_proxy_mgr=None,
    ):
        # type: (str, int, int, dict, str, dict, list, list, list, object) -> dict
        """
        단일 키워드에 대한 전체 파이프라인(검색→수집→가격→설명→품질→CSV)을 실행한다.

        Args:
            keyword: 검색 키워드.
            tree_index: Treeview 내 행 인덱스.
            total_count: 전체 키워드 수.
            settings: 설정 딕셔너리.
            desc_style: 설명 생성 스타일.
            desc_ai_settings: AI 설명 설정.
            all_passed: 통과 상품 누적 리스트 (in-place append).
            all_rejected: 탈락 상품 누적 리스트 (in-place append).
            all_products: 전체 상품 누적 리스트 (in-place append).
            global_proxy_mgr: 이전 키워드부터 유지된 ProxyManager.

        Returns:
            dict: {'success': True/False, 'passed': n, 'failed': n, 'images': n}
        """
        import config
        from scraper import AmazonFullScraper
        from price_adjuster import adjust_prices
        from quality_checker import QualityChecker
        from shopify_exporter import export_shopify_csv
        from description_generator import generate_descriptions

        self.current_keyword_index = tree_index
        self.current_keyword = keyword
        self.after(0, lambda kw=keyword: self.lbl_current_keyword.configure(text=kw))
        self._update_keyword_status(tree_index, "진행중")

        self._log("=" * 50)
        self._log(
            '[키워드 {}/{}] "{}" 시작'.format(tree_index + 1, total_count, keyword)
        )

        safe_keyword = keyword.replace(" ", "_")
        config.CATEGORY_KEYWORD = keyword

        try:
            # ── STEP 1: 카테고리 검색 ──
            scraper = AmazonFullScraper(proxy_mgr=global_proxy_mgr)
            search_url = settings.get("CATEGORY_URLS", {}).get(keyword)
            products = scraper.search_category(
                query=keyword, search_url=search_url, max_pages=config.MAX_PAGES
            )

            search_count = len(products) if products else 0
            self._log("[STEP 1] 검색 결과: {}개".format(search_count))

            if not products:
                # 15초 후 1회 재시도
                self._log(
                    '[재시도] "{}" 검색 결과 없음, 15초 후 재시도...'.format(keyword)
                )
                time.sleep(15)
                if not self.is_running:
                    return {"success": False}
                products = scraper.search_category(
                    query=keyword, search_url=search_url, max_pages=config.MAX_PAGES
                )
                search_count = len(products) if products else 0
                self._log("[재시도] 결과: {}개".format(search_count))

                if not products:
                    self._log(
                        '[실패] "{}" 검색 결과 없음 (재시도 실패)'.format(keyword)
                    )
                    self._update_keyword_status(tree_index, "검색 실패")
                    self._update_keyword_row(tree_index, 0, 0, 0, 0, 0, "검색 실패")
                    self.failed_keywords.append(keyword)
                    return {"success": False}

            # 키워드 진행률 초기화
            self.after(0, lambda: self._set_keyword_progress(0))

            # ── STEP 2: 상세 수집 (enrich) ──
            scraper.enrich_all(products, limit=config.ENRICH_LIMIT)
            enriched = scraper.results
            enrich_count = len(enriched)

            self._log("[STEP 2] 상세 수집 완료: {}개".format(enrich_count))

            # 총 상품 수 보정 (실제 수집 기반)
            self.processed_count += enrich_count
            self.total_products = max(self.processed_count, self.total_products)
            self.after(0, self._update_progress)

            # 키워드 진행률 50%
            self.after(0, lambda: self._set_keyword_progress(50))

            # ── STEP 3: 가격 마진 적용 ──
            # export_shopify_csv 내에서 새로 계산하므로 기존 가격 필드 조작은 주석 처리합니다.
            # enriched = adjust_prices(enriched)
            self._log("[STEP 3] 새 가격 로직 적용을 위해 아마존 원본 가격 유지")

            # ── 설명 스타일 적용 ──
            if desc_style != "original":
                try:
                    enriched = generate_descriptions(
                        enriched,
                        style=desc_style,
                        api_key=(
                            desc_ai_settings.get("api_key")
                            if desc_ai_settings
                            else None
                        ),
                        model=(
                            desc_ai_settings.get("model", "gpt-4o-mini")
                            if desc_ai_settings
                            else "gpt-4o-mini"
                        ),
                        custom_prompt=(
                            desc_ai_settings.get("custom_prompt")
                            if desc_ai_settings
                            else None
                        ),
                    )
                    self._log("[설명] {} 스타일 적용 완료".format(desc_style))
                except Exception as desc_err:
                    self._log("[설명 경고] {}".format(desc_err))

            # 키워드 진행률 70%
            self.after(0, lambda: self._set_keyword_progress(70))

            # ── STEP 4: 품질 검사 ──
            for p in enriched:
                p["_keyword"] = keyword

            checker = QualityChecker(enriched)
            passed = checker.run_all_checks()

            report_file = os.path.join(
                config.OUTPUT_DIR, "quality_report_{}.json".format(safe_keyword)
            )
            checker.export_report(filename=report_file)

            passed_count = len(passed)
            rejected_count = len(checker.rejected)
            img_count = sum(p.get("image_count", 0) for p in passed)

            self._log(
                "[STEP 4] 품질 검사: 통과 {}개, 탈락 {}개".format(
                    passed_count, rejected_count
                )
            )

            # 키워드 진행률 85%
            self.after(0, lambda: self._set_keyword_progress(85))

            # ── STEP 5: CSV 내보내기 ──
            if passed:
                csv_file = os.path.join(
                    config.OUTPUT_DIR, "shopify_import_{}.csv".format(safe_keyword)
                )
                export_shopify_csv(
                    passed,
                    output_path=csv_file,
                    keyword=keyword,
                    shopify_settings=getattr(self, "_shopify_settings", None),
                    price_settings=getattr(self, "_price_settings", None),
                    collection_mapping=getattr(self, "_collection_mapping", None),
                )
                self._log("[STEP 5] CSV 저장: {}".format(csv_file))

            # JSON 백업
            backup_file = os.path.join(
                config.OUTPUT_DIR, "products_backup_{}.json".format(safe_keyword)
            )
            with open(backup_file, "w", encoding="utf-8") as f:
                json.dump(enriched, f, ensure_ascii=False, indent=2)

            # 체크포인트 정리
            try:
                scraper.checkpoint_mgr.cleanup_old(keyword)
            except Exception:
                pass

            # 누적 결과
            all_passed.extend(passed)
            all_rejected.extend(checker.rejected)
            all_products.extend(enriched)

            self.passed_count += passed_count
            self.failed_count += rejected_count
            self.image_count += img_count

            # Treeview 업데이트
            self._update_keyword_row(
                tree_index,
                search_count,
                enrich_count,
                passed_count,
                rejected_count,
                img_count,
                "완료",
            )
            self._update_keyword_status(tree_index, "완료")

            # 키워드 진행률 100%
            self.after(0, lambda: self._set_keyword_progress(100))

            self._log(
                '[키워드 {}/{}] "{}" 완료: 통과 {}개 / 탈락 {}개 / 이미지 {}장'.format(
                    tree_index + 1,
                    total_count,
                    keyword,
                    passed_count,
                    rejected_count,
                    img_count,
                )
            )

            return {
                "success": True,
                "passed": passed_count,
                "failed": rejected_count,
                "images": img_count,
            }

        except RuntimeError:
            # check_state()에 의한 사용자 중지 - 상위로 전파
            raise
        except Exception as e:
            self._log('[오류] 키워드 "{}" 처리 실패: {}'.format(keyword, str(e)))
            self._update_keyword_status(tree_index, "실패")
            self._update_keyword_row(tree_index, 0, 0, 0, 0, 0, "실패")
            return {"success": False}

    # ================================================================
    # 로그
    # ================================================================

    def _log(self, message):
        # type: (str) -> None
        """
        타임스탬프를 추가하여 로그 큐에 메시지를 넣는다.

        스레드에서 안전하게 호출 가능.

        Args:
            message: 로그 메시지.
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_queue.put("[{}] {}".format(timestamp, message))

    def _poll_log_queue(self):
        # type: () -> None
        """로그 큐에서 메시지를 꺼내 ScrolledText에 추가한다."""
        while not self.log_queue.empty():
            try:
                message = self.log_queue.get_nowait()
                self.log_text.configure(state="normal")
                self.log_text.insert("end", message + "\n")
                self.log_text.configure(state="disabled")
                self.log_text.see("end")
            except queue.Empty:
                break

        self.after(100, self._poll_log_queue)

    def clear_log(self):
        # type: () -> None
        """로그 텍스트를 지운다."""
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def save_log(self):
        # type: () -> None
        """로그 텍스트를 파일로 저장한다."""
        filepath = filedialog.asksaveasfilename(
            title="로그 저장",
            defaultextension=".txt",
            filetypes=[("텍스트 파일", "*.txt"), ("모든 파일", "*.*")],
        )

        if not filepath:
            return

        try:
            content = self.log_text.get("1.0", "end")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            messagebox.showinfo("저장 완료", "로그가 저장되었습니다.")
        except Exception as e:
            messagebox.showerror("저장 실패", "로그 저장 중 오류:\n{}".format(e))

    # ================================================================
    # 진행률 / UI 업데이트
    # ================================================================

    def _update_progress(self):
        # type: () -> None
        """전체 진행률과 속도/ETA를 업데이트한다."""
        if self.total_products > 0:
            pct = min(int((self.processed_count / self.total_products) * 100), 100)
        else:
            pct = 0

        # 처리 속도 계산
        if self.start_time and self.processed_count > 0:
            elapsed = time.time() - self.start_time
            speed = (self.processed_count / elapsed) * 60 if elapsed > 0 else 0
            remaining = self.total_products - self.processed_count
            eta_seconds = (
                (remaining / (self.processed_count / elapsed))
                if elapsed > 0 and self.processed_count > 0
                else 0
            )
            eta_min = int(eta_seconds // 60)
            eta_sec = int(eta_seconds % 60)
            speed_text = "{:.1f} 상품/분".format(speed)
            eta_text = "{}분 {}초".format(eta_min, eta_sec)
        else:
            speed_text = "- 상품/분"
            eta_text = "-"

        self.after(0, lambda: self._apply_progress_ui(pct, speed_text, eta_text))

    def _apply_progress_ui(self, pct, speed_text, eta_text):
        # type: (int, str, str) -> None
        """
        진행률 UI를 업데이트한다 (메인 스레드에서 호출).

        Args:
            pct: 전체 진행률 퍼센트.
            speed_text: 처리 속도 텍스트.
            eta_text: 예상 잔여 시간 텍스트.
        """
        self.total_progress["value"] = pct
        self.lbl_total_percent.configure(text="{}%".format(pct))
        self.lbl_speed.configure(text=speed_text)
        self.lbl_eta.configure(text=eta_text)
        self.lbl_progress_text.configure(
            text="처리 중 ({}/{})".format(self.processed_count, self.total_products)
        )

    def _set_keyword_progress(self, pct):
        # type: (int) -> None
        """
        키워드별 진행률을 업데이트한다.

        Args:
            pct: 키워드별 진행률 퍼센트.
        """
        self.keyword_progress["value"] = pct
        self.lbl_keyword_percent.configure(text="{}%".format(pct))

    def _update_keyword_status(self, index, status):
        # type: (int, str) -> None
        """
        키워드별 결과 Treeview의 상태를 업데이트한다.

        Args:
            index: 키워드 인덱스.
            status: 새 상태 ("대기"/"진행중"/"완료"/"실패").
        """
        tag_map = {
            "완료": "done",
            "실패": "fail",
            "진행중": "running",
            "대기": "waiting",
        }
        tag = tag_map.get(status, "waiting")

        def _update():
            children = self.kw_tree.get_children()
            if index < len(children):
                item_id = children[index]
                values = list(self.kw_tree.item(item_id, "values"))
                values[6] = status  # 상태 컬럼
                self.kw_tree.item(item_id, values=values, tags=(tag,))

        self.after(0, _update)

    def _update_keyword_row(
        self, index, searched, collected, passed, rejected, images, status
    ):
        # type: (int, int, int, int, int, int, str) -> None
        """
        키워드별 결과 행 전체를 업데이트한다.

        Args:
            index: 키워드 인덱스.
            searched: 검색된 상품 수.
            collected: 수집된 상품 수.
            passed: 통과 상품 수.
            rejected: 탈락 상품 수.
            images: 이미지 수.
            status: 상태 문자열.
        """
        tag_map = {
            "완료": "done",
            "실패": "fail",
            "진행중": "running",
            "대기": "waiting",
        }
        tag = tag_map.get(status, "waiting")

        def _update():
            children = self.kw_tree.get_children()
            if index < len(children):
                item_id = children[index]
                keyword = self.kw_tree.item(item_id, "values")[0]
                self.kw_tree.item(
                    item_id,
                    values=(
                        keyword,
                        searched,
                        collected,
                        passed,
                        rejected,
                        images,
                        status,
                    ),
                    tags=(tag,),
                )

        self.after(0, _update)

    def _update_elapsed_time(self):
        # type: () -> None
        """경과 시간을 1초마다 업데이트한다."""
        if self.start_time and self.is_running:
            elapsed = time.time() - self.start_time
            hours = int(elapsed // 3600)
            minutes = int((elapsed % 3600) // 60)
            seconds = int(elapsed % 60)
            self.lbl_elapsed.configure(
                text="{}:{:02d}:{:02d}".format(hours, minutes, seconds)
            )
            self.after(1000, self._update_elapsed_time)

    def _on_complete(self):
        # type: () -> None
        """파이프라인 완료 시 UI를 복원한다."""
        self.btn_start.configure(state="normal")
        self.btn_pause.configure(state="disabled", text="⏸ 일시정지")
        self.btn_stop.configure(state="disabled")
        self.lbl_progress_text.configure(text="완료")
        self.lbl_current_asin.configure(text="현재 처리: -")

        # 실패 키워드가 있으면 재실행 버튼 활성화
        if self.failed_keywords:
            self.btn_retry_failed.configure(state="normal")

        messagebox.showinfo(
            "완료",
            "스크래핑이 완료되었습니다!\n\n"
            "처리: {}개\n통과: {}개\n탈락: {}개\n이미지: {}장{}".format(
                self.processed_count,
                self.passed_count,
                self.failed_count,
                self.image_count,
                (
                    "\n\n실패 키워드: {}개".format(len(self.failed_keywords))
                    if self.failed_keywords
                    else ""
                ),
            ),
        )

    # ================================================================
    # 리셋
    # ================================================================

    def reset(self):
        # type: () -> None
        """모든 카운터, 라벨, 진행률바, Treeview를 초기화한다."""
        self.total_products = 0
        self.processed_count = 0
        self.passed_count = 0
        self.failed_count = 0
        self.image_count = 0
        self.current_keyword = ""
        self.current_keyword_index = 0
        self.total_keywords = 0

        self.total_progress["value"] = 0
        self.keyword_progress["value"] = 0
        self.lbl_total_percent.configure(text="0%")
        self.lbl_keyword_percent.configure(text="0%")
        self.lbl_current_keyword.configure(text="-")
        self.lbl_progress_text.configure(text="대기 중")
        self.lbl_speed.configure(text="- 상품/분")
        self.lbl_eta.configure(text="-")
        self.lbl_elapsed.configure(text="0:00:00")
        self.lbl_current_asin.configure(text="현재 처리: -")

        for item in self.kw_tree.get_children():
            self.kw_tree.delete(item)

    # ================================================================
    # 실패 키워드 재실행 / 우클릭 메뉴
    # ================================================================

    def retry_failed_keywords(self):
        # type: () -> None
        """
        검색에 실패한 키워드들만 모아서 파이프라인을 재실행한다.

        self.failed_keywords 리스트의 키워드로 새 워커 스레드를 시작한다.
        """
        if not self.failed_keywords:
            messagebox.showinfo("재실행", "재실행할 키워드가 없습니다.")
            return

        if self.is_running:
            messagebox.showwarning("실행 중", "이미 실행 중입니다.")
            return

        if self.app is None:
            return

        settings = self.app.settings_tab.get_settings()
        settings["CATEGORY_KEYWORDS"] = list(self.failed_keywords)
        proxies = self.app.proxy_tab.get_active_proxies()

        retry_keywords = list(self.failed_keywords)
        self.failed_keywords = []
        self.btn_retry_failed.configure(state="disabled")

        # Treeview에 재실행 키워드 추가
        for keyword in retry_keywords:
            self.kw_tree.insert(
                "",
                "end",
                values=(keyword, "-", "-", "-", "-", "-", "재시도"),
                tags=("running",),
            )

        self.is_running = True
        self.is_paused = False
        self.start_time = time.time()

        self.btn_start.configure(state="disabled")
        self.btn_pause.configure(state="normal")
        self.btn_stop.configure(state="normal")
        self.lbl_progress_text.configure(text="재실행 중")

        self._log("[재실행] 실패 키워드 {}개 재실행 시작".format(len(retry_keywords)))

        desc_style = "original"
        desc_ai_settings = {}
        if self.app and hasattr(self.app, "description_tab"):
            desc_style = self.app.description_tab.get_style()
            desc_ai_settings = self.app.description_tab.get_ai_settings()

        self.worker_thread = threading.Thread(
            target=self._run_pipeline,
            args=(settings, proxies, desc_style, desc_ai_settings),
            daemon=True,
        )
        self.worker_thread.start()
        self._update_elapsed_time()

    def retry_single_keyword(self, keyword):
        # type: (str) -> None
        """
        단일 키워드만 선택하여 파이프라인을 재실행한다.

        Args:
            keyword: 재실행할 키워드 문자열.
        """
        if self.is_running:
            messagebox.showwarning("실행 중", "이미 실행 중입니다.")
            return

        if self.app is None:
            return

        settings = self.app.settings_tab.get_settings()
        settings["CATEGORY_KEYWORDS"] = [keyword]
        proxies = self.app.proxy_tab.get_active_proxies()

        # 실패 목록에서 제거
        if keyword in self.failed_keywords:
            self.failed_keywords.remove(keyword)

        # Treeview에 추가
        self.kw_tree.insert(
            "",
            "end",
            values=(keyword, "-", "-", "-", "-", "-", "재시도"),
            tags=("running",),
        )

        self.is_running = True
        self.is_paused = False
        self.start_time = time.time()

        self.btn_start.configure(state="disabled")
        self.btn_pause.configure(state="normal")
        self.btn_stop.configure(state="normal")
        self.lbl_progress_text.configure(text="재실행 중")

        self._log('[재실행] "{}" 키워드 재실행 시작'.format(keyword))

        desc_style = "original"
        desc_ai_settings = {}
        if self.app and hasattr(self.app, "description_tab"):
            desc_style = self.app.description_tab.get_style()
            desc_ai_settings = self.app.description_tab.get_ai_settings()

        self.worker_thread = threading.Thread(
            target=self._run_pipeline,
            args=(settings, proxies, desc_style, desc_ai_settings),
            daemon=True,
        )
        self.worker_thread.start()
        self._update_elapsed_time()

    def _on_keyword_right_click(self, event):
        # type: (tk.Event) -> None
        """
        키워드 Treeview 우클릭 시 컨텍스트 메뉴를 표시한다.

        실패 상태인 행에서만 '이 키워드만 재실행' 메뉴를 표시한다.

        Args:
            event: 마우스 이벤트.
        """
        row_id = self.kw_tree.identify_row(event.y)
        if not row_id:
            return

        values = self.kw_tree.item(row_id, "values")
        if not values:
            return

        keyword = values[0]
        status = values[6]

        if status in ("검색 실패", "실패"):
            menu = tk.Menu(self, tearoff=0)
            menu.add_command(
                label='"{}" 재실행'.format(keyword),
                command=lambda kw=keyword: self.retry_single_keyword(kw),
            )
            menu.tk_popup(event.x_root, event.y_root)

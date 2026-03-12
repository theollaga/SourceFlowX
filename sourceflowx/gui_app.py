#!/usr/bin/env python3
"""
SourceFlowX – GUI 메인 애플리케이션
Tkinter 기반 데스크탑 GUI. 6개 탭으로 구성된 Amazon → Shopify 소싱 도구.
"""

import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import os
import sys
import json

from gui_tabs.settings_tab import SettingsTab
from gui_tabs.proxy_tab import ProxyTab
from gui_tabs.run_tab import RunTab
from gui_tabs.results_tab import ResultsTab
from gui_tabs.description_tab import DescriptionTab
from gui_tabs.shopify_tab import ShopifyTab


class SourceFlowXApp:
    """
    SourceFlowX GUI 메인 애플리케이션 클래스.

    Tkinter 루트 윈도우 위에 메뉴바, 헤더, 6개 탭(Notebook),
    상태바를 배치하고, 다크/라이트 테마 전환을 지원한다.
    """

    def __init__(self, root):
        # type: (tk.Tk) -> None
        """
        GUI 애플리케이션을 초기화한다.

        Args:
            root: Tkinter 루트 윈도우.
        """
        self.root = root
        self.root.title("SourceFlowX - Amazon Product Sourcing Tool")

        # 창 크기 및 최소 크기
        window_width = 1200
        window_height = 800
        self.root.minsize(900, 600)

        # 화면 중앙 배치
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.root.geometry("{}x{}+{}+{}".format(window_width, window_height, x, y))

        # 다크 모드 상태
        self.is_dark_mode = False

        # 필요한 폴더 자동 생성
        os.makedirs("assets", exist_ok=True)
        os.makedirs("profiles", exist_ok=True)

        # UI 구성
        self._create_menu_bar()
        self._create_header()
        self._create_tabs()
        self._create_status_bar()

        # 테마 적용
        self._apply_theme()

        # 자동 저장 복원
        self._auto_load()

    def _create_menu_bar(self):
        # type: () -> None
        """
        상단 메뉴바를 생성한다.

        파일, 보기, 도움말 3개 메뉴로 구성.
        """
        menubar = tk.Menu(self.root)

        # 파일 메뉴
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="설정 저장", command=self._save_settings)
        file_menu.add_command(label="설정 불러오기", command=self._load_settings)
        file_menu.add_separator()
        file_menu.add_command(label="종료", command=self.root.quit)
        menubar.add_cascade(label="파일", menu=file_menu)

        # 보기 메뉴
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="다크 모드 전환", command=self._toggle_theme)
        menubar.add_cascade(label="보기", menu=view_menu)

        # 도움말 메뉴
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="사용법", command=self._show_help)
        help_menu.add_command(label="정보", command=self._show_about)
        menubar.add_cascade(label="도움말", menu=help_menu)

        self.root.config(menu=menubar)
        self.menubar = menubar

    def _create_header(self):
        # type: () -> None
        """
        상단 헤더 영역을 생성한다.

        앱 이름과 부제목을 표시.
        """
        self.header_frame = tk.Frame(self.root)
        self.header_frame.pack(fill="x", padx=10, pady=(10, 0))

        self.title_label = tk.Label(
            self.header_frame, text="SourceFlowX", font=("Segoe UI", 20, "bold")
        )
        self.title_label.pack(anchor="w")

        self.subtitle_label = tk.Label(
            self.header_frame,
            text="Amazon → Shopify 자동 소싱 도구",
            font=("Segoe UI", 10),
            fg="#888888",
        )
        self.subtitle_label.pack(anchor="w")

    def _create_tabs(self):
        # type: () -> None
        """
        6개 탭이 있는 Notebook 위젯을 생성한다.

        탭 순서: 설정, 프록시, 상품 설명, 실행, 결과, Shopify.
        """
        self.notebook = ttk.Notebook(self.root)

        # 각 탭 인스턴스 생성
        self.settings_tab = SettingsTab(self.notebook)
        self.proxy_tab = ProxyTab(self.notebook)
        self.run_tab = RunTab(self.notebook)
        self.results_tab = ResultsTab(self.notebook)
        self.description_tab = DescriptionTab(self.notebook)
        self.shopify_tab = ShopifyTab(self.notebook)

        # Notebook에 탭 추가
        self.notebook.add(self.settings_tab, text="  설정  ")
        self.notebook.add(self.proxy_tab, text="  프록시  ")
        self.notebook.add(self.description_tab, text="  상품 설명  ")
        self.notebook.add(self.run_tab, text="  실행  ")
        self.notebook.add(self.results_tab, text="  결과  ")
        self.notebook.add(self.shopify_tab, text="  Shopify  ")

        self.notebook.pack(fill="both", expand=True, padx=10, pady=5)

        # 탭에 앱 참조 연결 (다른 탭 접근용)
        self.run_tab.app = self
        self.description_tab.app = self
        self.shopify_tab.app = self

    def _create_status_bar(self):
        # type: () -> None
        """
        하단 상태바를 생성한다.

        좌측에 상태 메시지, 우측에 버전 정보 표시.
        """
        self.status_frame = tk.Frame(self.root, bd=1, relief="sunken")
        self.status_frame.pack(fill="x", side="bottom", padx=5, pady=2)

        self.status_label = tk.Label(
            self.status_frame, text="준비 완료", anchor="w", font=("Segoe UI", 9)
        )
        self.status_label.pack(side="left", padx=5)

        self.version_label = tk.Label(
            self.status_frame,
            text="v1.0.0",
            anchor="e",
            font=("Segoe UI", 9),
            fg="#888888",
        )
        self.version_label.pack(side="right", padx=5)

    def _toggle_theme(self):
        # type: () -> None
        """다크 모드와 라이트 모드를 토글한다."""
        self.is_dark_mode = not self.is_dark_mode
        self._apply_theme()

    def _apply_theme(self):
        # type: () -> None
        """
        현재 테마(다크/라이트)를 전체 위젯에 적용한다.

        ttk.Style과 재귀 색상 설정을 사용.
        """
        style = ttk.Style()

        if self.is_dark_mode:
            bg = "#2b2b2b"
            fg = "#ffffff"
            tab_bg = "#3c3c3c"
            tab_selected = "#4a4a4a"
            status_bg = "#1e1e1e"
            subtitle_fg = "#aaaaaa"
        else:
            bg = "#f0f0f0"
            fg = "#000000"
            tab_bg = "#e8e8e8"
            tab_selected = "#ffffff"
            status_bg = "#f5f5f5"
            subtitle_fg = "#888888"

        # ttk 스타일 설정
        style.configure("TNotebook", background=bg)
        style.configure(
            "TNotebook.Tab", background=tab_bg, foreground=fg, padding=[12, 4]
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", tab_selected)],
            foreground=[("selected", fg)],
        )
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=fg)
        style.configure("TButton", background=tab_bg, foreground=fg)
        style.configure("TEntry", fieldbackground=tab_selected)
        style.configure("TCheckbutton", background=bg, foreground=fg)
        style.configure("TRadiobutton", background=bg, foreground=fg)
        style.configure("TLabelframe", background=bg, foreground=fg)
        style.configure("TLabelframe.Label", background=bg, foreground=fg)

        # tk 위젯 색상 설정
        self.root.configure(bg=bg)
        self.header_frame.configure(bg=bg)
        self.title_label.configure(bg=bg, fg=fg)
        self.subtitle_label.configure(bg=bg, fg=subtitle_fg)
        self.status_frame.configure(bg=status_bg)
        self.status_label.configure(bg=status_bg, fg=fg)
        self.version_label.configure(bg=status_bg, fg=subtitle_fg)

        # 모든 탭 프레임에 재귀적으로 색상 적용
        self._apply_colors_recursive(self.notebook, bg, fg)

    def _apply_colors_recursive(self, widget, bg, fg):
        # type: (tk.Widget, str, str) -> None
        """
        위젯과 그 하위 위젯에 재귀적으로 배경/전경 색상을 적용한다.

        Args:
            widget: 대상 위젯.
            bg: 배경색.
            fg: 전경색 (글자색).
        """
        try:
            if isinstance(widget, (tk.Frame, tk.Label, tk.LabelFrame)):
                widget.configure(bg=bg, fg=fg)
            elif isinstance(widget, tk.Frame):
                widget.configure(bg=bg)
        except tk.TclError:
            pass

        for child in widget.winfo_children():
            self._apply_colors_recursive(child, bg, fg)

    def _save_settings(self):
        # type: () -> None
        """설정 탭의 저장 기능을 호출한다."""
        self.settings_tab.save_settings()

    def _load_settings(self):
        # type: () -> None
        """설정 탭의 불러오기 기능을 호출한다."""
        self.settings_tab.load_settings()

    def _show_help(self):
        # type: () -> None
        """사용법 안내 다이얼로그를 표시한다."""
        messagebox.showinfo(
            "사용법",
            "SourceFlowX 사용법\n\n"
            "1. 설정 탭에서 키워드 입력\n"
            "2. 프록시 탭에서 프록시 설정\n"
            "3. 실행 탭에서 시작 클릭",
        )

    def _show_about(self):
        # type: () -> None
        """앱 정보 다이얼로그를 표시한다."""
        messagebox.showinfo(
            "정보",
            "SourceFlowX v1.0.0\n\n"
            "Amazon → Shopify 자동 소싱 도구\n\n"
            "© 2026 SourceFlowX",
        )

    def _auto_save(self):
        # type: () -> None
        """
        현재 설정, 프록시, 설명 스타일을 profiles/auto_save.json에 저장한다.

        각 항목은 try/except로 감싸서 하나가 실패해도 나머지는 저장된다.
        """
        save_data = {}

        try:
            save_data["settings"] = self.settings_tab.get_settings()
        except Exception:
            pass

        try:
            save_data["proxies"] = self.proxy_tab.get_proxies()
        except Exception:
            pass

        try:
            save_data["description"] = {
                "style": self.description_tab.get_style(),
                "ai_settings": self.description_tab.get_ai_settings(),
            }
        except Exception:
            pass

        try:
            save_data["ai_settings"] = self.description_tab.get_ai_settings()
        except Exception:
            pass

        # Shopify Output Settings 저장
        try:
            save_data["shopify_output"] = self.shopify_tab.get_shopify_settings()
        except Exception:
            pass

        # Collection Mapping 저장
        try:
            save_data["collection_mapping"] = self.shopify_tab.get_collection_mapping()
        except Exception:
            pass

        # Price Settings 저장
        try:
            save_data["price_settings"] = self.settings_tab.get_price_settings()
        except Exception:
            pass

        try:
            os.makedirs("profiles", exist_ok=True)
            with open(
                os.path.join("profiles", "auto_save.json"), "w", encoding="utf-8"
            ) as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _auto_load(self):
        # type: () -> None
        """
        profiles/auto_save.json에서 설정을 읽어 각 탭에 복원한다.

        파일이 없거나 오류 시 무시한다.
        """
        save_path = os.path.join("profiles", "auto_save.json")
        if not os.path.exists(save_path):
            return

        try:
            with open(save_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return

        # 설정 복원
        try:
            if "settings" in data:
                self.settings_tab.set_settings(data["settings"])
        except Exception:
            pass

        # 프록시 복원
        try:
            if "proxies" in data and data["proxies"]:
                for proxy in data["proxies"]:
                    self.proxy_tab.proxies.append(proxy)
                self.proxy_tab._update_treeview()
                self.proxy_tab._update_count_label()
        except Exception:
            pass

        # 설명 스타일 복원
        try:
            if "description" in data:
                desc_data = data["description"]
                style = desc_data.get("style", "original")
                self.description_tab.style_var.set(style)
                self.description_tab._on_style_change()

                ai_settings = desc_data.get("ai_settings", {})
                self.description_tab.set_ai_settings(ai_settings)
        except Exception:
            pass

        if "ai_settings" in data:
            try:
                self.description_tab.set_ai_settings(data["ai_settings"])
            except Exception:
                pass

        # Shopify Output Settings 복원
        if "shopify_output" in data:
            try:
                self.shopify_tab.set_shopify_settings(data["shopify_output"])
            except Exception:
                pass

        # Collection Mapping 복원
        if "collection_mapping" in data:
            try:
                self.shopify_tab.set_collection_mapping(data["collection_mapping"])
            except Exception:
                pass

        # Price Settings 복원
        if "price_settings" in data:
            try:
                self.settings_tab.set_price_settings(data["price_settings"])
            except Exception:
                pass

    def _on_closing(self):
        # type: () -> None
        """
        앱 종료 시 자동 저장 후 확인 다이얼로그를 표시하고 종료한다.

        스크래핑 진행 중이면 추가 경고를 표시하고,
        워커 스레드가 안전히 중단된 후 종료한다.
        """
        if self.run_tab.is_running:
            if not messagebox.askokcancel(
                "경고",
                "스크래핑이 진행 중입니다.\n"
                "종료하면 현재 작업이 중단됩니다.\n\n"
                "종료하시겠습니까?",
            ):
                return
            self.run_tab.is_running = False
            self.run_tab.is_paused = False
            self._auto_save()
            self.root.after(1000, self.root.destroy)
        else:
            if messagebox.askokcancel("종료", "SourceFlowX를 종료하시겠습니까?"):
                self._auto_save()
                self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = SourceFlowXApp(root)
    root.protocol("WM_DELETE_WINDOW", app._on_closing)
    root.mainloop()

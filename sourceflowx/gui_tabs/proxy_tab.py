"""
SourceFlowX - 프록시 탭
프록시 리스트 추가/삭제/테스트/저장을 GUI로 관리하는 탭.
일괄 입력, 파일 불러오기, 개별/전체 연결 테스트를 지원한다.
"""

import tkinter as tk
from tkinter import ttk
from tkinter import filedialog
from tkinter import messagebox
from tkinter import scrolledtext
import threading
import os
import time as _time


class ProxyTab(ttk.Frame):
    """
    프록시 탭 프레임.

    프록시 추가(한 줄/일괄/파일), Treeview 목록 관리,
    연결 테스트(curl_cffi), proxies.txt 저장을 담당한다.
    """

    def __init__(self, parent):
        # type: (tk.Widget) -> None
        """
        프록시 탭을 초기화한다.

        Args:
            parent: 부모 위젯 (Notebook).
        """
        super().__init__(parent)
        self.proxies = []  # 프록시 딕셔너리 리스트
        self._testing = False  # 테스트 진행 중 여부
        self._create_widgets()

    def _create_widgets(self):
        # type: () -> None
        """상단 입력 영역과 하단 목록/관리 영역을 배치한다."""
        # ── 상단: 프록시 입력 ──
        self._create_input_section()

        # ── 하단: 프록시 목록 + 관리 ──
        self._create_list_section()

    # ================================================================
    # 상단: 프록시 입력
    # ================================================================

    def _create_input_section(self):
        # type: () -> None
        """프록시 추가 입력 영역을 생성한다."""
        section = ttk.LabelFrame(self, text="프록시 추가", padding=10)
        section.pack(fill="x", padx=10, pady=5)

        # 형식 안내
        ttk.Label(
            section,
            text="형식: ip:port:username:password 또는 ip:port",
            font=("Segoe UI", 9),
            foreground="#888888",
        ).pack(anchor="w", pady=(0, 5))

        # 입력 행
        input_frame = ttk.Frame(section)
        input_frame.pack(fill="x")

        self.proxy_entry = ttk.Entry(input_frame, width=60, font=("Segoe UI", 10))
        self.proxy_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.proxy_entry.bind("<Return>", lambda e: self.add_proxy())

        ttk.Button(input_frame, text="추가", width=8, command=self.add_proxy).pack(
            side="left", padx=2
        )

        ttk.Button(
            input_frame, text="일괄 입력", width=10, command=self.add_bulk_proxies
        ).pack(side="left", padx=2)

        ttk.Button(
            input_frame, text="파일 불러오기", width=12, command=self.load_from_file
        ).pack(side="left", padx=2)

    # ================================================================
    # 하단: 프록시 목록 + 관리
    # ================================================================

    def _create_list_section(self):
        # type: () -> None
        """프록시 Treeview 목록과 관리 버튼을 생성한다."""
        section = ttk.LabelFrame(self, text="프록시 목록", padding=10)
        section.pack(fill="both", expand=True, padx=10, pady=5)

        # Treeview
        columns = ("#", "ip_port", "auth", "status", "response_time")
        self.tree = ttk.Treeview(
            section, columns=columns, show="headings", selectmode="extended", height=12
        )

        self.tree.heading("#", text="#")
        self.tree.heading("ip_port", text="IP:Port")
        self.tree.heading("auth", text="인증")
        self.tree.heading("status", text="상태")
        self.tree.heading("response_time", text="응답시간")

        self.tree.column("#", width=40, anchor="center", stretch=False)
        self.tree.column("ip_port", width=200, anchor="w")
        self.tree.column("auth", width=100, anchor="center")
        self.tree.column("status", width=80, anchor="center")
        self.tree.column("response_time", width=100, anchor="center")

        # 행 색상 태그
        self.tree.tag_configure("active", background="#d4edda")
        self.tree.tag_configure("blocked", background="#f8d7da")
        self.tree.tag_configure("error", background="#fff3cd")
        self.tree.tag_configure("waiting", background="")

        # 스크롤바
        tree_scroll = ttk.Scrollbar(section, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)

        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")

        # 버튼 행
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=10, pady=5)

        self.btn_remove_sel = ttk.Button(
            btn_frame, text="선택 삭제", width=10, command=self.remove_selected
        )
        self.btn_remove_sel.pack(side="left", padx=2)

        self.btn_remove_all = ttk.Button(
            btn_frame, text="전체 삭제", width=10, command=self.remove_all
        )
        self.btn_remove_all.pack(side="left", padx=2)

        ttk.Separator(btn_frame, orient="vertical").pack(
            side="left", fill="y", padx=8, pady=2
        )

        self.btn_test_sel = ttk.Button(
            btn_frame, text="선택 테스트", width=10, command=self.test_selected
        )
        self.btn_test_sel.pack(side="left", padx=2)

        self.btn_test_all = ttk.Button(
            btn_frame, text="전체 테스트", width=10, command=self.test_all
        )
        self.btn_test_all.pack(side="left", padx=2)

        ttk.Separator(btn_frame, orient="vertical").pack(
            side="left", fill="y", padx=8, pady=2
        )

        self.btn_save = ttk.Button(
            btn_frame, text="proxies.txt 저장", width=14, command=self.save_to_file
        )
        self.btn_save.pack(side="left", padx=2)

        # 프록시 수 라벨
        self.count_label = ttk.Label(
            btn_frame, text="총 0개 | 활성 0개 | 차단 0개", font=("Segoe UI", 9)
        )
        self.count_label.pack(side="right", padx=5)

    # ================================================================
    # 파싱
    # ================================================================

    def _parse_proxy_line(self, line):
        # type: (str) -> dict or None
        """
        한 줄의 프록시 문자열을 파싱한다.

        지원 형식:
        - ip:port:username:password (인증 프록시)
        - ip:port (비인증 프록시)

        Args:
            line: 프록시 문자열.

        Returns:
            dict: 파싱된 프록시 정보. 유효하지 않으면 None.
        """
        line = line.strip()

        # 빈 줄, 주석 무시
        if not line or line.startswith("#"):
            return None

        parts = line.split(":")

        if len(parts) == 4:
            return {
                "host": parts[0],
                "port": parts[1],
                "username": parts[2],
                "password": parts[3],
                "status": "대기",
                "response_time": "",
            }
        elif len(parts) == 2:
            return {
                "host": parts[0],
                "port": parts[1],
                "username": "",
                "password": "",
                "status": "대기",
                "response_time": "",
            }
        else:
            return None

    def _is_duplicate(self, proxy_dict):
        # type: (dict) -> bool
        """
        ip:port 조합이 이미 존재하는지 확인한다.

        Args:
            proxy_dict: 확인할 프록시 딕셔너리.

        Returns:
            bool: 중복이면 True.
        """
        key = "{}:{}".format(proxy_dict["host"], proxy_dict["port"])
        for p in self.proxies:
            if "{}:{}".format(p["host"], p["port"]) == key:
                return True
        return False

    # ================================================================
    # 추가 메서드
    # ================================================================

    def add_proxy(self):
        # type: () -> None
        """Entry에서 프록시를 읽어 파싱 후 리스트에 추가한다."""
        text = self.proxy_entry.get().strip()
        if not text:
            return

        proxy = self._parse_proxy_line(text)
        if proxy is None:
            messagebox.showwarning(
                "형식 오류",
                "유효하지 않은 형식입니다.\n" "ip:port 또는 ip:port:username:password",
            )
            return

        if self._is_duplicate(proxy):
            messagebox.showwarning(
                "중복",
                "이미 추가된 프록시입니다: {}:{}".format(proxy["host"], proxy["port"]),
            )
            return

        self.proxies.append(proxy)
        self.proxy_entry.delete(0, "end")
        self._update_treeview()
        self._update_count_label()

    def add_bulk_proxies(self):
        # type: () -> None
        """일괄 입력 팝업 창을 열어 여러 프록시를 한 번에 추가한다."""
        popup = tk.Toplevel(self)
        popup.title("일괄 프록시 입력")
        popup.geometry("500x350")
        popup.resizable(False, False)
        popup.grab_set()

        ttk.Label(
            popup,
            text="한 줄에 하나씩 입력 (ip:port 또는 ip:port:user:pass):",
            font=("Segoe UI", 9),
        ).pack(padx=10, pady=(10, 5), anchor="w")

        text_widget = scrolledtext.ScrolledText(
            popup, width=50, height=12, font=("Consolas", 10)
        )
        text_widget.pack(padx=10, fill="both", expand=True)

        btn_frame = ttk.Frame(popup)
        btn_frame.pack(fill="x", padx=10, pady=10)

        ttk.Button(
            btn_frame,
            text="적용",
            width=10,
            command=lambda: self._apply_bulk(text_widget.get("1.0", "end"), popup),
        ).pack(side="left", padx=5)

        ttk.Button(btn_frame, text="취소", width=10, command=popup.destroy).pack(
            side="left", padx=5
        )

    def _apply_bulk(self, text, popup):
        # type: (str, tk.Toplevel) -> None
        """
        일괄 입력 텍스트를 줄 단위로 파싱하여 프록시를 추가한다.

        Args:
            text: 줄 단위 프록시 텍스트.
            popup: 닫을 팝업 창.
        """
        added = 0
        skipped = 0

        for line in text.strip().splitlines():
            proxy = self._parse_proxy_line(line)
            if proxy is None:
                continue
            if self._is_duplicate(proxy):
                skipped += 1
                continue
            self.proxies.append(proxy)
            added += 1

        popup.destroy()
        self._update_treeview()
        self._update_count_label()

        msg = "{}개 추가됨".format(added)
        if skipped > 0:
            msg += " (중복 {}개 제외)".format(skipped)
        messagebox.showinfo("일괄 추가 완료", msg)

    def load_from_file(self):
        # type: () -> None
        """파일에서 프록시 리스트를 읽어 추가한다."""
        filepath = filedialog.askopenfilename(
            title="프록시 파일 불러오기",
            filetypes=[("텍스트 파일", "*.txt"), ("모든 파일", "*.*")],
        )

        if not filepath:
            return

        try:
            added = 0
            skipped = 0
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    proxy = self._parse_proxy_line(line)
                    if proxy is None:
                        continue
                    if self._is_duplicate(proxy):
                        skipped += 1
                        continue
                    self.proxies.append(proxy)
                    added += 1

            self._update_treeview()
            self._update_count_label()

            msg = "{}개 추가됨".format(added)
            if skipped > 0:
                msg += " (중복 {}개 제외)".format(skipped)
            messagebox.showinfo("파일 불러오기 완료", msg)

        except Exception as e:
            messagebox.showerror("불러오기 실패", "파일 읽기 중 오류:\n{}".format(e))

    # ================================================================
    # 삭제 메서드
    # ================================================================

    def remove_selected(self):
        # type: () -> None
        """Treeview에서 선택된 프록시를 삭제한다."""
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("알림", "삭제할 프록시를 선택해주세요.")
            return

        # 인덱스 역순으로 삭제 (인덱스 꼬임 방지)
        indices = sorted([self.tree.index(item) for item in selected], reverse=True)
        for idx in indices:
            if idx < len(self.proxies):
                del self.proxies[idx]

        self._update_treeview()
        self._update_count_label()

    def remove_all(self):
        # type: () -> None
        """확인 다이얼로그 후 모든 프록시를 삭제한다."""
        if not self.proxies:
            return

        if messagebox.askyesno("확인", "모든 프록시를 삭제하시겠습니까?"):
            self.proxies.clear()
            self._update_treeview()
            self._update_count_label()

    # ================================================================
    # 테스트 메서드
    # ================================================================

    def test_selected(self):
        # type: () -> None
        """선택된 프록시를 별도 스레드에서 테스트한다."""
        if self._testing:
            messagebox.showinfo("알림", "테스트가 이미 진행 중입니다.")
            return

        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("알림", "테스트할 프록시를 선택해주세요.")
            return

        indices = [self.tree.index(item) for item in selected]
        thread = threading.Thread(target=self._run_tests, args=(indices,), daemon=True)
        thread.start()

    def test_all(self):
        # type: () -> None
        """모든 프록시를 별도 스레드에서 테스트한다."""
        if self._testing:
            messagebox.showinfo("알림", "테스트가 이미 진행 중입니다.")
            return

        if not self.proxies:
            messagebox.showinfo("알림", "테스트할 프록시가 없습니다.")
            return

        indices = list(range(len(self.proxies)))
        thread = threading.Thread(target=self._run_tests, args=(indices,), daemon=True)
        thread.start()

    def _test_proxy(self, proxy_dict, index):
        # type: (dict, int) -> bool
        """
        단일 프록시의 연결을 테스트한다.

        curl_cffi로 httpbin.org/ip에 요청하여 응답을 확인한다.
        curl_cffi 실패 시 requests를 대안으로 사용한다.

        Args:
            proxy_dict: 테스트할 프록시 딕셔너리.
            index: 프록시 리스트 내 인덱스.

        Returns:
            bool: 연결 성공 시 True.
        """
        # 프록시 URL 구성
        if proxy_dict["username"]:
            proxy_url = "http://{}:{}@{}:{}".format(
                proxy_dict["username"],
                proxy_dict["password"],
                proxy_dict["host"],
                proxy_dict["port"],
            )
        else:
            proxy_url = "http://{}:{}".format(proxy_dict["host"], proxy_dict["port"])

        proxies = {"http": proxy_url, "https": proxy_url}
        test_url = "https://httpbin.org/ip"

        start = _time.time()

        try:
            # curl_cffi 시도
            try:
                from curl_cffi import requests as cffi_requests

                response = cffi_requests.get(
                    test_url, proxies=proxies, timeout=10, impersonate="chrome119"
                )
                elapsed = _time.time() - start

                if response.status_code == 200:
                    proxy_dict["status"] = "활성"
                    proxy_dict["response_time"] = "{:.1f}s".format(elapsed)
                    return True
                else:
                    proxy_dict["status"] = "오류"
                    proxy_dict["response_time"] = "{}".format(response.status_code)
                    return False

            except ImportError:
                # curl_cffi 없으면 requests 사용
                import requests as req_lib

                response = req_lib.get(test_url, proxies=proxies, timeout=10)
                elapsed = _time.time() - start

                if response.status_code == 200:
                    proxy_dict["status"] = "활성"
                    proxy_dict["response_time"] = "{:.1f}s".format(elapsed)
                    return True
                else:
                    proxy_dict["status"] = "오류"
                    proxy_dict["response_time"] = "{}".format(response.status_code)
                    return False

        except Exception:
            elapsed = _time.time() - start
            proxy_dict["status"] = "차단"
            proxy_dict["response_time"] = "{:.1f}s".format(elapsed)
            return False

    def _run_tests(self, indices):
        # type: (list) -> None
        """
        전달받은 인덱스 리스트의 프록시를 순차 테스트한다.

        테스트 중 버튼을 비활성화하고,
        완료 후 활성화 및 결과를 업데이트한다.

        Args:
            indices: 테스트할 프록시 인덱스 리스트.
        """
        self._testing = True

        # 버튼 비활성화 (메인 스레드에서)
        self.after(0, lambda: self._set_buttons_state("disabled"))
        self.after(
            0,
            lambda: self.count_label.configure(
                text="테스트 중... 0/{}".format(len(indices))
            ),
        )

        for i, idx in enumerate(indices):
            if idx < len(self.proxies):
                # 상태를 "테스트 중"으로 표시
                self.proxies[idx]["status"] = "테스트 중"
                self.after(0, self._update_treeview)

                # 테스트 실행
                self._test_proxy(self.proxies[idx], idx)

                # UI 업데이트
                progress_text = "테스트 중... {}/{}".format(i + 1, len(indices))
                self.after(0, self._update_treeview)
                self.after(
                    0, lambda t=progress_text: self.count_label.configure(text=t)
                )

        # 완료
        self._testing = False
        self.after(0, lambda: self._set_buttons_state("normal"))
        self.after(0, self._update_treeview)
        self.after(0, self._update_count_label)

    def _set_buttons_state(self, state):
        # type: (str) -> None
        """
        테스트 관련 버튼들의 상태를 변경한다.

        Args:
            state: "normal" 또는 "disabled".
        """
        self.btn_test_sel.configure(state=state)
        self.btn_test_all.configure(state=state)
        self.btn_remove_sel.configure(state=state)
        self.btn_remove_all.configure(state=state)

    # ================================================================
    # Treeview / 라벨 업데이트
    # ================================================================

    def _update_treeview(self):
        # type: () -> None
        """self.proxies 기반으로 Treeview를 전체 갱신한다."""
        # 기존 항목 삭제
        for item in self.tree.get_children():
            self.tree.delete(item)

        # 새 항목 추가
        for i, proxy in enumerate(self.proxies):
            ip_port = "{}:{}".format(proxy["host"], proxy["port"])
            auth = "있음" if proxy["username"] else "없음"
            status = proxy["status"]
            rt = proxy["response_time"]

            # 상태별 태그
            if status == "활성":
                tag = "active"
            elif status == "차단":
                tag = "blocked"
            elif status == "오류":
                tag = "error"
            else:
                tag = "waiting"

            self.tree.insert(
                "", "end", values=(i + 1, ip_port, auth, status, rt), tags=(tag,)
            )

    def _update_count_label(self):
        # type: () -> None
        """총/활성/차단 프록시 수를 라벨에 표시한다."""
        total = len(self.proxies)
        active = sum(1 for p in self.proxies if p["status"] == "활성")
        blocked = sum(1 for p in self.proxies if p["status"] == "차단")

        self.count_label.configure(
            text="총 {}개 | 활성 {}개 | 차단 {}개".format(total, active, blocked)
        )

    # ================================================================
    # 저장 / 외부 접근
    # ================================================================

    def save_to_file(self):
        # type: () -> None
        """현재 프록시 리스트를 proxies.txt로 저장한다."""
        if not self.proxies:
            messagebox.showinfo("알림", "저장할 프록시가 없습니다.")
            return

        filepath = "proxies.txt"

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                for proxy in self.proxies:
                    if proxy["username"]:
                        line = "{}:{}:{}:{}".format(
                            proxy["host"],
                            proxy["port"],
                            proxy["username"],
                            proxy["password"],
                        )
                    else:
                        line = "{}:{}".format(proxy["host"], proxy["port"])
                    f.write(line + "\n")

            messagebox.showinfo(
                "저장 완료",
                "{}개 프록시를 {} 에 저장했습니다.".format(len(self.proxies), filepath),
            )
        except Exception as e:
            messagebox.showerror("저장 실패", "파일 저장 중 오류:\n{}".format(e))

    def get_proxies(self):
        # type: () -> list
        """
        현재 프록시 리스트를 반환한다.

        Returns:
            list: 프록시 딕셔너리 리스트.
        """
        return self.proxies

    def get_active_proxies(self):
        # type: () -> list
        """
        상태가 '활성' 또는 '대기'인 프록시만 반환한다.

        Returns:
            list: 사용 가능한 프록시 딕셔너리 리스트.
        """
        return [p for p in self.proxies if p["status"] in ("활성", "대기")]

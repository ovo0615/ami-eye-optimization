"""
IBIS-AMI 眼圖自動化工具 (重構版 v3)

與 v2 相比：
- 業務邏輯 (param_utils / bridge_builder / osl_workflow) 與 GUI 分離
- 所有魔術值集中於 config.py
- 橋接腳本改用獨立樣板，AMOP/OCO 節點設定共用一份程式碼
- 錯誤改為記錄到日誌而非靜默吞掉
GUI 外觀與操作流程與 v2 完全一致。
"""
import os
import sys
import traceback
import threading

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from pyaedt import Desktop, Circuit
except ImportError:
    from ansys.aedt.core import Desktop, Circuit

try:
    from ansys.optislang.core.project_parametric import ComparisonType
    HAS_OSL = True
except ImportError:
    HAS_OSL = False

# 列出目前執行中的 AEDT gRPC session（不同 pyaedt 版本位置略有差異）
_active_sessions = None
for _mod in ("ansys.aedt.core.generic.general_methods",
             "ansys.aedt.core.internal.general_methods",
             "pyaedt.generic.general_methods"):
    try:
        import importlib
        _m = importlib.import_module(_mod)
        if hasattr(_m, "active_sessions"):
            _active_sessions = _m.active_sessions
            break
    except Exception:
        pass


def get_active_sessions(version):
    """回傳 {pid: port}；取不到則回傳空 dict。"""
    if _active_sessions is None:
        return {}
    for kwargs in ({"version": version}, {}):
        try:
            return dict(_active_sessions(**kwargs))
        except TypeError:
            continue
        except Exception:
            return {}
    return {}

import config
import param_utils as pu
import objective
from bridge_builder import build_bridge_script

if getattr(sys, "frozen", False):
    WORK_DIR = os.path.dirname(sys.executable)
else:
    WORK_DIR = os.path.dirname(os.path.abspath(__file__))


class AMIEyeDashboard:
    def __init__(self, root):
        self.root = root
        self.root.title("IBIS-AMI Eye Optimization Dashboard - By Jeff Hong")
        self.root.geometry("1100x950")
        self.root.configure(bg="#0b0f19")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.d = None
        self.app = None
        self.nb = None
        self._busy = False
        self._trace_report = {}  # trace 名稱 -> 既有報告名稱（None 表示需 create_report）
        self._setup_styles()
        self._build_ui()

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        bg_dark, bg_panel, fg_text = "#0b0f19", "#161b22", "#e6edf3"
        accent_cyan, accent_green = "#00f0ff", "#39ff14"
        style.configure("TNotebook", background=bg_dark, borderwidth=0)
        style.configure("TNotebook.Tab", background="#21262d", foreground=fg_text,
                        padding=[20, 10], font=("微軟正黑體", 12, "bold"), borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", accent_cyan)],
                  foreground=[("selected", bg_dark)])
        style.configure("Treeview", background=bg_panel, foreground=accent_green,
                        fieldbackground=bg_panel, font=("Consolas", 12), rowheight=35, borderwidth=0)
        style.configure("Treeview.Heading", background="#21262d", foreground=accent_cyan,
                        font=("微軟正黑體", 12, "bold"), padding=[5, 5], borderwidth=0)
        style.map("Treeview", background=[("selected", "#1f6feb")], foreground=[("selected", "#ffffff")])
        style.configure("TCombobox", fieldbackground=bg_panel, background="#21262d",
                        foreground=accent_cyan, selectbackground=accent_cyan,
                        selectforeground=bg_dark, padding=[5, 5])
        style.map("TCombobox",
                  fieldbackground=[("readonly", bg_panel)],
                  selectbackground=[("readonly", accent_cyan)],
                  selectforeground=[("readonly", bg_dark)],
                  foreground=[("readonly", accent_cyan)])
        self.root.option_add("*TCombobox*Listbox.background", bg_panel)
        self.root.option_add("*TCombobox*Listbox.foreground", accent_cyan)
        self.root.option_add("*TCombobox*Listbox.selectBackground", accent_cyan)
        self.root.option_add("*TCombobox*Listbox.selectForeground", bg_dark)
        self.root.option_add("*TCombobox*Listbox.font", ("微軟正黑體", 12))

    def _on_close(self):
        # 釋放 AEDT 連線，讓使用者關閉工具後能正常手動關閉 AEDT。
        d, self.d, self.app = self.d, None, None
        if d:
            try:
                d.release_desktop(close_projects=False, close_on_exit=False)
            except Exception:
                pass
        self.root.destroy()
        # daemon 背景執行緒不會阻擋退出；強制結束確保 gRPC 連線完全釋放。
        os._exit(0)

    def _build_ui(self):
        hdr = tk.Frame(self.root, bg="#161b22", height=80)
        hdr.pack(fill="x")
        tk.Label(hdr, text="IBIS-AMI Eye Automation & Optimization",
                 fg="#00f0ff", bg="#161b22", font=("微軟正黑體", 22, "bold")).pack(pady=20)

        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=16, pady=10)

        self.t1 = tk.Frame(self.nb, bg="#0b0f19")
        self.nb.add(self.t1, text="  1. 連接 AEDT  ")

        self.t2 = tk.Frame(self.nb, bg="#0b0f19")
        self.nb.add(self.t2, text="  2. 參數 & 雙節點設定  ")

        self.t2_canvas = tk.Canvas(self.t2, bg="#0b0f19", highlightthickness=0)
        self.t2_scrollbar = ttk.Scrollbar(self.t2, orient="vertical", command=self.t2_canvas.yview)
        self.t2_inner = tk.Frame(self.t2_canvas, bg="#0b0f19")
        self.t2_inner.bind("<Configure>",
                           lambda e: self.t2_canvas.configure(scrollregion=self.t2_canvas.bbox("all")))
        self.t2_canvas_window = self.t2_canvas.create_window((0, 0), window=self.t2_inner, anchor="nw")
        self.t2_canvas.bind("<Configure>",
                            lambda e: self.t2_canvas.itemconfig(self.t2_canvas_window, width=e.width))
        self.t2_canvas.pack(side="left", fill="both", expand=True)
        self.t2_scrollbar.pack(side="right", fill="y")
        self.t2_canvas.configure(yscrollcommand=self.t2_scrollbar.set)

        def _on_mousewheel(event):
            self.t2_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        self.t2_canvas.bind("<Enter>", lambda _: self.t2_canvas.bind_all("<MouseWheel>", _on_mousewheel))
        self.t2_canvas.bind("<Leave>", lambda _: self.t2_canvas.unbind_all("<MouseWheel>"))

        self.t3 = tk.Frame(self.nb, bg="#0b0f19")
        self.nb.add(self.t3, text="  3. 執行日誌  ")

        self._build_t1()
        self._build_t2()
        self._build_t3()

    # ── UI helpers ────────────────────────────────────────────
    def _lf(self, parent, text):
        f = tk.LabelFrame(parent, text=text, bg="#0b0f19", fg="#00f0ff",
                          font=("微軟正黑體", 12, "bold"), bd=2)
        f.pack(fill="x", padx=16, pady=8)
        return f

    def _btn(self, parent, text, cmd, color="#e94560"):
        return tk.Button(parent, text=text, command=cmd, bg=color, fg="white",
                         activebackground="#00f0ff", activeforeground="black", relief="flat",
                         font=("微軟正黑體", 12, "bold"), padx=15, pady=6, cursor="hand2")

    def _lbl(self, parent, text):
        return tk.Label(parent, text=text, bg="#0b0f19", fg="#e6edf3", font=("微軟正黑體", 12))

    def _entry(self, parent, width=36, default=""):
        e = tk.Entry(parent, width=width, bg="#161b22", fg="#39ff14",
                     font=("Consolas", 12, "bold"), insertbackground="#00f0ff", relief="flat")
        if default:
            e.insert(0, default)
        return e

    def _build_t1(self):
        f1 = self._lf(self.t1, "Step 1 — 連接 AEDT")
        self.cb_version = ttk.Combobox(f1, values=list(config.AEDT_VERSIONS.keys()),
                                       width=10, state="readonly", font=("微軟正黑體", 12))
        self.cb_version.pack(side="left", padx=10)
        self.cb_version.current(0)
        self._btn(f1, "掃描開啟的專案 (Scan)", self._scan, "#1f6feb").pack(side="left", padx=12, pady=12)
        self.cb_proj = ttk.Combobox(f1, width=44, state="readonly", font=("微軟正黑體", 12))
        self.cb_proj.pack(side="left", padx=10, ipady=4)
        self.cb_proj.bind("<<ComboboxSelected>>", self._on_proj)

        f2 = self._lf(self.t1, "Step 2 — 選取設計")
        self._lbl(f2, "Design:").grid(row=0, column=0, padx=12, pady=10, sticky="w")
        self.cb_design = ttk.Combobox(f2, width=40, state="readonly", font=("微軟正黑體", 12))
        self.cb_design.grid(row=0, column=1, padx=10, pady=10, ipady=4)
        self.cb_design.bind("<<ComboboxSelected>>", self._on_design)

        self._lbl(f2, "Sim Setup:").grid(row=1, column=0, padx=12, pady=10, sticky="w")
        self.cb_simsetup = ttk.Combobox(f2, width=40, state="readonly", font=("微軟正黑體", 12))
        self.cb_simsetup.grid(row=1, column=1, padx=10, pady=10, ipady=4)

        self._lbl(f2, "Report:").grid(row=2, column=0, padx=12, pady=10, sticky="w")
        self.cb_report = ttk.Combobox(f2, width=40, state="readonly", font=("微軟正黑體", 12))
        self.cb_report.grid(row=2, column=1, padx=10, pady=10, ipady=4)

    def _build_t2(self):
        pf = self._lf(self.t2_inner, "Step 3 — 選取最佳化參數 (自動偵測 TX 參數 +/- 1 範圍)")
        cols = ("Name", "Value", "Min", "Max", "Optimize", "Type")
        self.tree = ttk.Treeview(pf, columns=cols, show="headings", height=8)
        for c, w in zip(cols, [200, 120, 110, 110, 90, 80]):
            if c == "Optimize":
                self.tree.heading(c, text=c + " ▼", command=self._toggle_all_optimize)
            else:
                self.tree.heading(c, text=c)
            self.tree.column(c, width=w, anchor="center")
        self.tree.heading("Name", anchor="w")
        self.tree.column("Name", anchor="w")
        self.tree.pack(fill="x", padx=8, pady=8)
        self.tree.bind("<ButtonRelease-1>", self._on_tree_click)
        self.tree.tag_configure("yes", background="#238636", foreground="white")

        self.lbl_param_count = self._lbl(pf, "已勾選最佳化參數: 0 個")
        self.lbl_param_count.config(fg="#00f0ff", font=("微軟正黑體", 11, "bold"))
        self.lbl_param_count.pack(side="right", padx=16, pady=4)

        mf = self._lf(self.t2_inner, "Step 4 — 雙節點工作流設定 (Sensitivity + Optimization)")
        self._lbl(mf, "輸出 .opf 路徑:").grid(row=0, column=0, padx=12, pady=8, sticky="w")
        self.ent_opf = self._entry(mf, 46, os.path.join(WORK_DIR, config.DEFAULT_OPF_NAME).replace("\\", "/"))
        self.ent_opf.grid(row=0, column=1, padx=8)
        self._btn(mf, "...", lambda: self._saveas(self.ent_opf), "#333355").grid(row=0, column=2, padx=6)

        self._lbl(mf, "AMOP 取樣次數:").grid(row=1, column=0, padx=12, pady=8, sticky="w")
        self.ent_max = self._entry(mf, 10, str(config.DEFAULT_MAX_EVAL))
        self.ent_max.grid(row=1, column=1, sticky="w", padx=8)

        # 優化目標模式切換
        self._lbl(mf, "優化目標:").grid(row=2, column=0, padx=12, pady=8, sticky="w")
        target_frame = tk.Frame(mf, bg="#0b0f19")
        target_frame.grid(row=2, column=1, sticky="w", padx=8)
        self.var_target_mode = tk.StringVar(value=config.TARGET_EYE)
        for val, label in [(config.TARGET_EYE, "眼圖 (Eye)"), (config.TARGET_SPARAM, "S 參數 (S-Parameter)")]:
            tk.Radiobutton(target_frame, text=label, variable=self.var_target_mode, value=val,
                           command=self._on_target_mode, bg="#0b0f19", fg="#00f0ff",
                           activebackground="#0b0f19", activeforeground="#39ff14",
                           selectcolor="#161b22", font=("微軟正黑體", 12, "bold")).pack(side="left", padx=10)

        # ── 眼圖子面板 (row 3) ──
        self.eye_frame = tk.Frame(mf, bg="#0b0f19")
        self.eye_frame.grid(row=3, column=0, columnspan=3, sticky="w")
        self._lbl(self.eye_frame, "最佳化響應:").pack(side="left", padx=12, pady=8)
        self.var_resp = tk.StringVar(value=config.DEFAULT_RESPONSE)
        for r in config.RESPONSES:
            tk.Radiobutton(self.eye_frame, text=r, variable=self.var_resp, value=r, bg="#0b0f19",
                           fg="#00f0ff", activebackground="#0b0f19", activeforeground="#39ff14",
                           selectcolor="#161b22", font=("微軟正黑體", 12, "bold")).pack(side="left", padx=10)

        # ── S 參數子面板 (row 3, 與眼圖互斥顯示) ──
        # trace 名稱由 AEDT 設計自動偵測（單端 PortN / 差動 DiffN），不寫死。
        self._straces = {"single": [], "diff": []}
        self.sparam_frame = tk.Frame(mf, bg="#0b0f19")
        self.sparam_frame.grid(row=3, column=0, columnspan=3, sticky="w")

        self._lbl(self.sparam_frame, "端口模式:").grid(row=0, column=0, padx=12, pady=6, sticky="w")
        self.var_port_mode = tk.StringVar(value=config.PORT_MODES[0][0])
        pm_box = tk.Frame(self.sparam_frame, bg="#0b0f19")
        pm_box.grid(row=0, column=1, sticky="w")
        for val, label in config.PORT_MODES:
            tk.Radiobutton(pm_box, text=label, variable=self.var_port_mode, value=val,
                           command=self._populate_trace_combo, bg="#0b0f19",
                           fg="#39ff14", activebackground="#0b0f19", activeforeground="#00f0ff",
                           selectcolor="#161b22", font=("微軟正黑體", 11)).pack(side="left", padx=8)

        self._lbl(self.sparam_frame, "S 參數 trace:").grid(row=1, column=0, padx=12, pady=6, sticky="w")
        trace_box = tk.Frame(self.sparam_frame, bg="#0b0f19")
        trace_box.grid(row=1, column=1, sticky="w")
        self.cb_trace = ttk.Combobox(trace_box, width=30, state="readonly", font=("微軟正黑體", 11))
        self.cb_trace.pack(side="left", padx=4)
        self.cb_trace.bind("<<ComboboxSelected>>", lambda _e: self._update_trace_hint())
        self.lbl_trace_hint = tk.Label(trace_box, text="(Scan 後自動帶入)", bg="#0b0f19",
                                       fg="#8b949e", font=("微軟正黑體", 10))
        self.lbl_trace_hint.pack(side="left", padx=8)

        self._lbl(self.sparam_frame, "頻寬範圍:").grid(row=2, column=0, padx=12, pady=6, sticky="w")
        band_box = tk.Frame(self.sparam_frame, bg="#0b0f19")
        band_box.grid(row=2, column=1, sticky="w")
        self.ent_fstart = self._entry(band_box, 8, config.DEFAULT_F_START)
        self.ent_fstart.pack(side="left", padx=4)
        self._lbl(band_box, "~").pack(side="left")
        self.ent_fstop = self._entry(band_box, 8, config.DEFAULT_F_STOP)
        self.ent_fstop.pack(side="left", padx=4)
        self.cb_funit = ttk.Combobox(band_box, values=config.FREQ_UNITS, width=6,
                                     state="readonly", font=("微軟正黑體", 11))
        self.cb_funit.set(config.DEFAULT_FREQ_UNIT)
        self.cb_funit.pack(side="left", padx=6)

        self._on_target_mode()  # 依預設模式顯示正確面板

        self._lbl(mf, "OCO 求解器:").grid(row=4, column=0, padx=12, pady=8, sticky="w")
        oco_frame = tk.Frame(mf, bg="#0b0f19")
        oco_frame.grid(row=4, column=1, sticky="w", padx=8)
        self.var_oco_mode = tk.StringVar(value="Direct")
        tk.Radiobutton(oco_frame, text="真實求解 (Direct AEDT)", variable=self.var_oco_mode,
                       value="Direct", bg="#0b0f19", fg="#00f0ff", activebackground="#0b0f19",
                       activeforeground="#39ff14", selectcolor="#161b22",
                       font=("微軟正黑體", 11)).pack(side="left", padx=5)
        tk.Radiobutton(oco_frame, text="虛擬求解 (MOP)", variable=self.var_oco_mode,
                       value="MOP", bg="#0b0f19", fg="#39ff14", activebackground="#0b0f19",
                       activeforeground="#00f0ff", selectcolor="#161b22",
                       font=("微軟正黑體", 11)).pack(side="left", padx=5)

        self.var_start = tk.BooleanVar(value=False)
        tk.Checkbutton(mf, text="儲存後立即開始計算 (osl.project.start)", variable=self.var_start,
                       bg="#0b0f19", fg="#39ff14", activebackground="#0b0f19", activeforeground="#00f0ff",
                       selectcolor="#161b22", font=("微軟正黑體", 12, "bold")).grid(
            row=5, column=0, columnspan=2, padx=12, pady=8, sticky="w")

        bf = tk.Frame(self.t2_inner, bg="#0b0f19")
        bf.pack(fill="x", padx=16, pady=12)
        self._btn(bf, "重新整理變數", self._refresh, "#8957e5").pack(side="left", padx=8)
        self._btn(bf, "▶  生成橋接腳本 + 建立雙節點專案", self._run_all, "#e34c26").pack(side="right", padx=8)

    def _on_target_mode(self):
        """切換眼圖/S參數子面板（兩者佔同一格，互斥顯示）。"""
        if self.var_target_mode.get() == config.TARGET_SPARAM:
            self.eye_frame.grid_remove()
            self.sparam_frame.grid()
        else:
            self.sparam_frame.grid_remove()
            self.eye_frame.grid()

    def _populate_trace_combo(self):
        """依端口模式把自動偵測到的 trace 填入下拉。"""
        traces = self._straces.get(self.var_port_mode.get(), [])
        self.cb_trace["values"] = traces
        if traces:
            self.cb_trace.current(0)
        else:
            self.cb_trace.set("")
        self._update_trace_hint()

    def _update_trace_hint(self):
        """顯示目前選定 trace 的自動判斷方向。"""
        t = self.cb_trace.get()
        if not t:
            self.lbl_trace_hint.config(text="(此模式無可用 trace，請確認設計已定義對應端口)")
            return
        import objective
        d = "最小化 (反射/回波損耗)" if objective.direction_for_trace(t) == "MIN" else "最大化 (傳輸/插入損耗)"
        self.lbl_trace_hint.config(text=f"→ worst-case {d}")

    def _build_t3(self):
        self.log = tk.Text(self.t3, bg="#0d1117", fg="#39ff14", font=("微軟正黑體", 12),
                           state="disabled", relief="flat")
        sb = ttk.Scrollbar(self.t3, command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log.pack(fill="both", expand=True, padx=8, pady=8)

    def _log(self, msg):
        """執行緒安全：任何執行緒呼叫都排回主執行緒寫入。"""
        self.root.after(0, self._log_main, msg)

    def _log_main(self, msg):
        self.log.config(state="normal")
        self.log.insert("end", f"> {msg}\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def _ui(self, fn, *args):
        """在主執行緒執行 UI 更新。"""
        self.root.after(0, lambda: fn(*args))

    def _bg(self, fn, *args):
        """把 AEDT 阻塞操作丟到背景執行緒，避免凍結 UI。同一時間只允許一個。"""
        if self._busy:
            self._log("[忙碌] 請等待目前 AEDT 操作完成…")
            return

        def runner():
            try:
                fn(*args)
            except Exception as e:
                self._log(f"[錯誤] {e}")
                self._log(traceback.format_exc())
            finally:
                self._busy = False

        self._busy = True
        threading.Thread(target=runner, daemon=True).start()

    def _saveas(self, entry):
        d = filedialog.askdirectory(title="選擇專案儲存資料夾")
        if d:
            current_path = entry.get()
            filename = os.path.basename(current_path) if current_path else "auto_project.opf"
            new_path = os.path.join(d, filename).replace("\\", "/")
            entry.delete(0, "end")
            entry.insert(0, new_path)

    # ── AEDT 互動（全部在背景執行緒，UI 更新排回主執行緒）──────────
    def _scan(self):
        self._bg(self._scan_worker, self.cb_version.get())

    def _scan_worker(self, ver):
        # 尚未連線就先連線到正確的 session
        if not self.d and not self._connect(ver):
            return
        projs = list(self.d.project_list or [])
        self._ui(self._apply_projects, projs)
        if projs:
            self._load_project_worker(projs[0])

    def _connect(self, ver):
        """連線到「真的有專案」的 session，成功則設定 self.d 並回傳 True。"""
        sessions = get_active_sessions(ver)
        if sessions:
            self._log("偵測到 %d 個 AEDT session: %s" % (
                len(sessions), ", ".join(f"PID {p}→port {pt}" for p, pt in sessions.items())))
            for pid, port in sessions.items():
                try:
                    d = Desktop(version=ver, non_graphical=False, new_desktop=False, port=port)
                    projs = d.project_list
                except Exception as e:
                    self._log(f"  port {port} 連線失敗: {e}")
                    continue
                if projs:
                    self.d = d
                    self._log(f"已連線 port {port}（PID {pid}），找到 {len(projs)} 個專案")
                    return True
                self._log(f"  port {port} 無專案，釋放")
                try:
                    d.release_desktop(False, False)
                except Exception:
                    pass
            self._log("所有 session 皆無專案，請確認 AEDT 已載入專案")
            return False
        self._log("無法列舉 session，改用自動連線")
        self.d = Desktop(version=ver, non_graphical=False, new_desktop=False)
        return True

    # 使用者切換下拉時觸發（在主執行緒），改丟背景執行緒處理
    def _on_proj(self, _):
        self._bg(self._load_project_worker, self.cb_proj.get())

    def _on_design(self, _):
        self._bg(self._load_design_worker, self.cb_design.get())

    def _refresh(self):
        if not self.app:
            self._log("尚未連線設計")
            return
        self._bg(self._refresh_worker)

    # ── worker（背景執行緒）──
    def _load_project_worker(self, proj):
        self.app = Circuit(project=proj)
        designs = list(self.app.design_list or [])
        self._ui(self._apply_designs, designs)
        if designs:
            self._load_design_worker(designs[0])

    def _load_design_worker(self, design):
        self.app.set_active_design(design)
        setups = list(self.app.setup_names or [])
        # 用 COM 直接取報告名稱，避開 post.all_report_names 觸發的 macro 錯誤雜訊
        try:
            reports = list(self.app.oreportsetup.GetAllReportNames() or [])
        except Exception as e:
            reports = []
            self._log(f"讀取報告清單失敗（可忽略）: {e}")
        straces = self._gather_s_traces()
        rows = self._read_variable_rows()
        self._ui(self._apply_design_data, design, setups, reports, straces, rows)

    def _gather_s_traces(self):
        """偵測可用的 S 參數 trace，回傳 {'single':[...], 'diff':[...]}，並建立 trace->報告對應。

        主來源：既有報告實際畫的 trace（匯出可靠，差動也涵蓋）。
        補充：可偵測但未畫的單端 trace（執行時以 create_report 補建）。
        """
        import re
        single, diff = [], []
        self._trace_report = {}

        def classify(tr):
            a, b = objective.trace_ports(tr)
            if a and b and re.match(r"(?i)port\d+$", a) and re.match(r"(?i)port\d+$", b):
                return single
            return diff

        # 1) 既有報告的 trace（沿用報告匯出，最可靠）
        try:
            for p in self.app.post.plots:
                rep = getattr(p, "plot_name", None)
                for t in getattr(p, "traces", []) or []:
                    nm = getattr(t, "name", None)
                    if nm and nm.startswith("dB(S(") and nm not in self._trace_report:
                        self._trace_report[nm] = rep
                        classify(nm).append(nm)
        except Exception as e:
            self._log(f"讀取既有報告 trace 失敗: {e}")

        # 2) 額外可偵測的單端 trace（未畫者標記為需 create_report）
        try:
            for nm in self.app.get_traces_for_plot(category=config.TRACE_CATEGORY) or []:
                if nm not in self._trace_report:
                    self._trace_report[nm] = None
                    single.append(nm)
        except Exception as e:
            self._log(f"偵測單端 S trace 失敗: {e}")

        self._log(f"偵測到 S trace：單端 {len(single)} 條、差動 {len(diff)} 條")
        return {"single": single, "diff": diff}

    def _refresh_worker(self):
        rows = self._read_variable_rows()
        self._ui(self._fill_tree, rows)

    def _read_variable_rows(self):
        """讀取設計變數，回傳 [(values_tuple, tags), ...]（純資料，不碰 UI）。"""
        rows = []
        for name, var in self.app.variable_manager.variables.items():
            val_str = var.expression if hasattr(var, "expression") else str(var)
            param_type = pu.infer_type(name, val_str)
            optimize, mn, mx, tags = "☐", "", "", ()
            try:
                numeric_val = pu.strip_unit(val_str)
                is_numeric = True
            except ValueError:
                is_numeric = False
            if is_numeric and any(t in name.upper() for t in config.AUTO_OPTIMIZE_TARGETS):
                optimize, tags = "☑", ("yes",)
                mn, mx = pu.default_range(numeric_val)
            rows.append(((name, val_str, mn, mx, optimize, param_type), tags))
        return rows

    # ── apply（主執行緒）──
    def _apply_projects(self, projs):
        self.cb_proj["values"] = projs
        if projs:
            self.cb_proj.current(0)
        self._log_main(f"找到 {len(projs)} 個專案")

    def _apply_designs(self, designs):
        self.cb_design["values"] = designs
        if designs:
            self.cb_design.current(0)

    def _apply_design_data(self, design, setups, reports, straces, rows):
        self.cb_simsetup["values"] = setups
        if setups:
            self.cb_simsetup.current(0)
        self.cb_report["values"] = reports
        if reports:
            self.cb_report.current(0)
        self._straces = straces
        self._populate_trace_combo()
        self._fill_tree(rows)
        self._log_main(f"設計: {design}")

    def _fill_tree(self, rows):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for values, tags in rows:
            self.tree.insert("", "end", values=values, tags=tags)
        self._update_param_count()

    def _update_param_count(self):
        count = sum(1 for i in self.tree.get_children()
                    if self.tree.item(i, "values")[4] == "☑")
        self.lbl_param_count.config(text=f"已勾選最佳化參數: {count} 個")

    def _on_tree_click(self, event):
        item = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)
        if not item or not column:
            return
        col_index = int(column[1:]) - 1
        vals = list(self.tree.item(item, "values"))

        if col_index == 4:  # Optimize toggle
            if vals[4] == "☑":
                vals[4], vals[2], vals[3] = "☐", "", ""
                self.tree.item(item, values=vals, tags=())
            else:
                vals[4] = "☑"
                try:
                    vals[2], vals[3] = pu.default_range(pu.strip_unit(vals[1]))
                except ValueError:
                    pass
                self.tree.item(item, values=vals, tags=("yes",))
            self._update_param_count()
            return

        if col_index == 5:  # Type toggle
            vals[5] = "INT" if vals[5] == "REAL" else "REAL"
            self.tree.item(item, values=vals)
            return

        if col_index in (2, 3):  # inline edit Min/Max
            x, y, width, height = self.tree.bbox(item, column)
            entry = tk.Entry(self.tree, bg="#161b22", fg="#39ff14", font=("Consolas", 12, "bold"),
                             justify="center", insertbackground="#00f0ff", relief="flat")
            entry.place(x=x, y=y, width=width, height=height)
            entry.insert(0, vals[col_index])
            entry.focus_set()
            entry.select_range(0, tk.END)

            def save_edit(_e=None):
                vals[col_index] = entry.get()
                self.tree.item(item, values=vals)
                entry.destroy()

            entry.bind("<Return>", save_edit)
            entry.bind("<FocusOut>", save_edit)
            entry.bind("<Escape>", lambda e: entry.destroy())

    def _toggle_all_optimize(self):
        items = self.tree.get_children()
        if not items:
            return
        all_checked = all(self.tree.item(i, "values")[4] == "☑" for i in items)
        target = "☐" if all_checked else "☑"
        for item in items:
            vals = list(self.tree.item(item, "values"))
            if target == "☑":
                vals[4] = "☑"
                try:
                    vals[2], vals[3] = pu.default_range(pu.strip_unit(vals[1]))
                except ValueError:
                    pass
                self.tree.item(item, values=vals, tags=("yes",))
            else:
                vals[4], vals[2], vals[3] = "☐", "", ""
                self.tree.item(item, values=vals, tags=())
        self._update_param_count()

    def _resolve_sparam_report(self, trace):
        """決定 S 參數要匯出的報告：優先沿用既有報告，否則嘗試 create_report。"""
        rep = self._trace_report.get(trace)
        if rep:
            self._log(f"S 參數沿用既有報告「{rep}」: {trace}")
            return rep
        return self._ensure_sparam_report(trace)

    def _ensure_sparam_report(self, trace):
        """用 PyAEDT 為指定 trace 建立（或重建）持久報告並存檔，回傳報告名稱；失敗回傳 None。"""
        name = config.SPARAM_REPORT_NAME
        try:
            oMod = self.app.odesign.GetModule("ReportSetup")
            try:
                if name in (oMod.GetAllReportNames() or []):
                    oMod.DeleteReports([name])
            except Exception:
                pass
            self.app.post.create_report(expressions=trace, plot_name=name)
            self.app.save_project()
            self._log(f"已建立 S 參數報告「{name}」: {trace}")
            return name
        except Exception as e:
            self._log(f"建立 S 參數報告失敗: {e}")
            return None

    # ── 主流程 ────────────────────────────────────────────────
    def _run_all(self):
        if not HAS_OSL:
            messagebox.showerror("錯誤", "請先安裝 ansys-optislang-core")
            return
        selected = [
            (self.tree.item(i, "values")[0], self.tree.item(i, "values")[1],
             self.tree.item(i, "values")[2], self.tree.item(i, "values")[3],
             self.tree.item(i, "values")[5])
            for i in self.tree.get_children()
            if self.tree.item(i, "values")[4] == "☑"
        ]
        if not selected:
            messagebox.showwarning("提醒", "請先勾選至少一個參數進行最佳化")
            return

        import objective
        from osl_workflow import build_workflow

        # 依目前模式組出 objective spec
        if self.var_target_mode.get() == config.TARGET_SPARAM:
            trace = self.cb_trace.get()
            if not trace:
                messagebox.showwarning("提醒", "請先選擇 S 參數 trace（需先 Scan 偵測設計）")
                return
            try:
                f_start = float(self.ent_fstart.get())
                f_stop = float(self.ent_fstop.get())
            except ValueError:
                messagebox.showwarning("提醒", "頻寬範圍請輸入有效數字")
                return
            if f_start == f_stop:
                messagebox.showwarning("提醒", "頻寬起訖不可相同")
                return
            spec = objective.make_sparam_spec(trace, f_start, f_stop, self.cb_funit.get())
        else:
            spec = objective.make_eye_spec(self.var_resp.get())

        ctx = dict(
            version_key=self.cb_version.get(),
            project=self.cb_proj.get(),
            design=self.cb_design.get(),
            setup=self.cb_simsetup.get() or config.DEFAULT_SETUP_NAME,
            report=self.cb_report.get(),
            opf_path=self.ent_opf.get(),
            max_eval=int(self.ent_max.get() or str(config.DEFAULT_MAX_EVAL)),
            do_start=self.var_start.get(),
            oco_mode=self.var_oco_mode.get(),
        )
        self.nb.select(2)  # 切到日誌頁

        def task():
            try:
                script_path = os.path.join(WORK_DIR, "aedt_bridge.py")
                csv_path = os.path.join(WORK_DIR, "osl_result.csv").replace("\\", "/")

                # S 參數模式：用 PyAEDT 為選定 trace 預先建立持久報告並存檔，
                # 橋接腳本只需匯出它（避開純 COM 的 CreateReport 在 gRPC 下不可靠的問題）。
                report_for_bridge = ctx["report"]
                if spec["mode"] == config.TARGET_SPARAM:
                    report_for_bridge = self._resolve_sparam_report(spec["trace"])
                    if not report_for_bridge:
                        self._log("[錯誤] 無法取得/建立 S 參數報告，中止")
                        return

                bridge = build_bridge_script(
                    selected,
                    version=ctx["version_key"], project=ctx["project"], design=ctx["design"],
                    setup=ctx["setup"], report=report_for_bridge, csv_path=csv_path, spec=spec,
                )
                with open(script_path, "w", encoding="utf-8") as f:
                    f.write(bridge)
                self._log("[層1] 橋接腳本已生成")
                self._log(f"[目標] {objective.describe(spec)}")

                build_workflow(
                    selected=selected,
                    spec=spec,
                    oco_mode=ctx["oco_mode"],
                    max_eval=ctx["max_eval"],
                    version_key=ctx["version_key"],
                    script_path=script_path,
                    opf_path=ctx["opf_path"],
                    do_start=ctx["do_start"],
                    log=self._log,
                )

                import subprocess
                subprocess.Popen([ctx["opf_path"]], shell=True)
                self._log("optiSLang 已開啟")
            except Exception as e:
                self._log(f"[錯誤] {e}")
                self._log(traceback.format_exc())

        threading.Thread(target=task, daemon=True).start()


if __name__ == "__main__":
    root = tk.Tk()
    AMIEyeDashboard(root)
    root.mainloop()

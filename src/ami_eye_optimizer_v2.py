import os, csv, traceback, threading, sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
try:
    from pyaedt import Desktop, Circuit
except ImportError:
    from ansys.aedt.core import Desktop, Circuit

try:
    from ansys.optislang.core import Optislang
    import ansys.optislang.core.node_types as node_types
    from ansys.optislang.core.nodes import DesignFlow
    from ansys.optislang.core.project_parametric import (
        ComparisonType, ObjectiveCriterion, ConstraintCriterion
    )
    HAS_OSL = True
except ImportError:
    HAS_OSL = False

if getattr(sys, 'frozen', False):
    WORK_DIR = os.path.dirname(sys.executable)
else:
    WORK_DIR = os.path.dirname(os.path.abspath(__file__))

class AMIEyeDashboard:
    """
    IBIS-AMI 眼圖自動化工具 (雙節點全功能版)
    此工具由虎門科技資深技術工程師 Jeff Hong 洪敬傑提供
    """
    def __init__(self, root):
        self.root = root
        self.root.title("IBIS-AMI Eye Optimization Dashboard - By Jeff Hong")
        self.root.geometry("1100x950")
        self.root.configure(bg="#0b0f19")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.d = None
        self.app = None
        self._setup_styles()
        self._build_ui()

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        bg_dark = "#0b0f19"
        bg_panel = "#161b22"
        fg_text = "#e6edf3"
        accent_cyan = "#00f0ff"
        accent_green = "#39ff14"
        style.configure("TNotebook", background=bg_dark, borderwidth=0)
        style.configure("TNotebook.Tab", background="#21262d", foreground=fg_text, padding=[20, 10], font=("微軟正黑體", 12, "bold"), borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", accent_cyan)], foreground=[("selected", bg_dark)])
        style.configure("Treeview", background=bg_panel, foreground=accent_green, fieldbackground=bg_panel, font=("Consolas", 12), rowheight=35, borderwidth=0)
        style.configure("Treeview.Heading", background="#21262d", foreground=accent_cyan, font=("微軟正黑體", 12, "bold"), padding=[5, 5], borderwidth=0)
        style.map("Treeview", background=[("selected", "#1f6feb")], foreground=[("selected", "#ffffff")])
        style.configure("TCombobox", fieldbackground=bg_panel, background="#21262d", foreground=accent_cyan, selectbackground=accent_cyan, selectforeground=bg_dark, padding=[5, 5])
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
        if self.d:
            try:
                self.d.release_desktop(False, False)
            except:
                pass
        self.root.destroy()

    def _build_ui(self):
        hdr = tk.Frame(self.root, bg="#161b22", height=80)
        hdr.pack(fill="x")
        tk.Label(hdr, text="IBIS-AMI Eye Automation & Optimization",
                 fg="#00f0ff", bg="#161b22",
                 font=("微軟正黑體", 22, "bold")).pack(pady=20)

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=16, pady=10)

        self.t1 = tk.Frame(nb, bg="#0b0f19")
        nb.add(self.t1, text="  1. 連接 AEDT  ")
        
        self.t2 = tk.Frame(nb, bg="#0b0f19")
        nb.add(self.t2, text="  2. 參數 & 雙節點設定  ")
        
        # Setup Canvas for scrolling in Tab 2
        self.t2_canvas = tk.Canvas(self.t2, bg="#0b0f19", highlightthickness=0)
        self.t2_scrollbar = ttk.Scrollbar(self.t2, orient="vertical", command=self.t2_canvas.yview)
        self.t2_inner = tk.Frame(self.t2_canvas, bg="#0b0f19")
        
        self.t2_inner.bind("<Configure>", lambda e: self.t2_canvas.configure(scrollregion=self.t2_canvas.bbox("all")))
        self.t2_canvas_window = self.t2_canvas.create_window((0, 0), window=self.t2_inner, anchor="nw")
        self.t2_canvas.bind('<Configure>', lambda e: self.t2_canvas.itemconfig(self.t2_canvas_window, width=e.width))
        
        self.t2_canvas.pack(side="left", fill="both", expand=True)
        self.t2_scrollbar.pack(side="right", fill="y")
        self.t2_canvas.configure(yscrollcommand=self.t2_scrollbar.set)

        # Mouse wheel scrolling
        def _on_mousewheel(event):
            self.t2_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
            
        self.t2_canvas.bind('<Enter>', lambda _: self.t2_canvas.bind_all("<MouseWheel>", _on_mousewheel))
        self.t2_canvas.bind('<Leave>', lambda _: self.t2_canvas.unbind_all("<MouseWheel>"))

        self.t3 = tk.Frame(nb, bg="#0b0f19")
        nb.add(self.t3, text="  3. 執行日誌  ")

        self._build_t1()
        self._build_t2()
        self._build_t3()
        tk.Label(self.root, text="此工具由虎門科技資深技術工程師 Jeff Hong 洪敬傑提供",
                 bg="#0b0f19", fg="#8b949e", font=("微軟正黑體", 11)).pack(side="bottom", pady=8)

    def _lf(self, parent, text):
        f = tk.LabelFrame(parent, text=text, bg="#0b0f19", fg="#00f0ff", font=("微軟正黑體", 12, "bold"), bd=2)
        f.pack(fill="x", padx=16, pady=8)
        return f

    def _btn(self, parent, text, cmd, color="#e94560"):
        return tk.Button(parent, text=text, command=cmd, bg=color, fg="white", activebackground="#00f0ff", activeforeground="black", relief="flat", font=("微軟正黑體", 12, "bold"), padx=15, pady=6, cursor="hand2")

    def _lbl(self, parent, text): 
        return tk.Label(parent, text=text, bg="#0b0f19", fg="#e6edf3", font=("微軟正黑體", 12))

    def _entry(self, parent, width=36, default=""):
        e = tk.Entry(parent, width=width, bg="#161b22", fg="#39ff14", font=("Consolas", 12, "bold"), insertbackground="#00f0ff", relief="flat")
        if default:
            e.insert(0, default)
        return e

    def _build_t1(self):
        f1 = self._lf(self.t1, "Step 1 — 連接 AEDT")
        self.cb_version = ttk.Combobox(f1, values=["2026.1", "2025.2", "2025.1", "2024.2", "2024.1"], width=10, state="readonly", font=("微軟正黑體", 12))
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
        cols = ("Name","Value","Min","Max","Optimize","Type")
        self.tree = ttk.Treeview(pf, columns=cols, show="headings", height=8)
        for c, w in zip(cols, [200,120,110,110,90,80]):
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
        self.ent_opf = self._entry(mf, 46, os.path.join(WORK_DIR, "ami_eye_auto.opf").replace("\\","/"))
        self.ent_opf.grid(row=0, column=1, padx=8)
        self._btn(mf, "...", lambda: self._saveas(self.ent_opf), "#333355").grid(row=0, column=2, padx=6)
        
        self._lbl(mf, "AMOP 取樣次數:").grid(row=1, column=0, padx=12, pady=8, sticky="w")
        self.ent_max = self._entry(mf, 10, "300")
        self.ent_max.grid(row=1, column=1, sticky="w", padx=8)
        
        self._lbl(mf, "最佳化響應:").grid(row=2, column=0, padx=12, pady=8, sticky="w")
        resp_frame = tk.Frame(mf, bg="#0b0f19")
        resp_frame.grid(row=2, column=1, sticky="w", padx=8)
        self.var_resp = tk.StringVar(value="EyeHeight")
        for r in ["EyeHeight","EyeWidth"]:
            tk.Radiobutton(resp_frame, text=r, variable=self.var_resp, value=r, bg="#0b0f19", fg="#00f0ff", activebackground="#0b0f19", activeforeground="#39ff14", selectcolor="#161b22", font=("微軟正黑體", 12, "bold")).pack(side="left", padx=10)
            
        self._lbl(mf, "OCO 求解器:").grid(row=3, column=0, padx=12, pady=8, sticky="w")
        oco_frame = tk.Frame(mf, bg="#0b0f19")
        oco_frame.grid(row=3, column=1, sticky="w", padx=8)
        self.var_oco_mode = tk.StringVar(value="Direct")
        tk.Radiobutton(oco_frame, text="真實求解 (Direct AEDT)", variable=self.var_oco_mode, value="Direct", bg="#0b0f19", fg="#00f0ff", activebackground="#0b0f19", activeforeground="#39ff14", selectcolor="#161b22", font=("微軟正黑體", 11)).pack(side="left", padx=5)
        tk.Radiobutton(oco_frame, text="虛擬求解 (MOP)", variable=self.var_oco_mode, value="MOP", bg="#0b0f19", fg="#39ff14", activebackground="#0b0f19", activeforeground="#00f0ff", selectcolor="#161b22", font=("微軟正黑體", 11)).pack(side="left", padx=5)

        self.var_start = tk.BooleanVar(value=False)
        tk.Checkbutton(mf, text="儲存後立即開始計算 (osl.project.start)", variable=self.var_start, bg="#0b0f19", fg="#39ff14", activebackground="#0b0f19", activeforeground="#00f0ff", selectcolor="#161b22", font=("微軟正黑體", 12, "bold")).grid(row=4, column=0, columnspan=2, padx=12, pady=8, sticky="w")
        
        bf = tk.Frame(self.t2_inner, bg="#0b0f19")
        bf.pack(fill="x", padx=16, pady=12)
        self._btn(bf, "重新整理變數", self._refresh, "#8957e5").pack(side="left", padx=8)
        self._btn(bf, "▶  生成橋接腳本 + 建立雙節點專案", self._run_all, "#e34c26").pack(side="right", padx=8)

    def _build_t3(self):
        self.log = tk.Text(self.t3, bg="#0d1117", fg="#39ff14", font=("微軟正黑體", 12), state="disabled", relief="flat")
        sb = ttk.Scrollbar(self.t3, command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log.pack(fill="both", expand=True, padx=8, pady=8)

    def _log(self, msg):
        self.log.config(state="normal")
        self.log.insert("end", f"> {msg}\n")
        self.log.see("end")
        self.log.config(state="disabled")
        self.root.update()

    def _saveas(self, entry):
        d = filedialog.askdirectory(title="選擇專案儲存資料夾")
        if d:
            current_path = entry.get()
            filename = os.path.basename(current_path) if current_path else "auto_project.opf"
            new_path = os.path.join(d, filename).replace("\\", "/")
            entry.delete(0, "end")
            entry.insert(0, new_path)

    def _scan(self):
        try:
            ver = self.cb_version.get()
            if not self.d:
                self.d = Desktop(version=ver, non_graphical=False, new_desktop=False)
            projs = self.d.project_list()
            self.cb_proj["values"] = projs
            if projs:
                self.cb_proj.current(0)
                self._on_proj(None)
            self._log(f"找到 {len(projs)} 個專案")
        except Exception as e:
            self._log(f"連線失敗: {e}")

    def _on_proj(self, _):
        try:
            self.app = Circuit(project=self.cb_proj.get())
            d = self.app.design_list
            self.cb_design["values"] = d
            if d:
                self.cb_design.current(0)
                self._on_design(None)
        except Exception as e:
            self._log(f"載入專案失敗: {e}")

    def _on_design(self, _):
        try:
            self.app.set_active_design(self.cb_design.get())
            self.cb_simsetup["values"] = self.app.setup_names
            if self.app.setup_names:
                self.cb_simsetup.current(0)
            rpts = self.app.post.all_report_names
            self.cb_report["values"] = rpts
            if rpts:
                self.cb_report.current(0)
            self._refresh()
            self._log(f"設計: {self.cb_design.get()}")
        except Exception as e:
            self._log(f"切換設計失敗: {e}")

    @staticmethod
    def _strip_unit(val_str):
        import re
        val_str = str(val_str).strip()
        m = re.match(r'^([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?)', val_str)
        if m:
            return float(m.group(1))
        raise ValueError(f"無法解析數值: {val_str!r}")

    def _refresh(self):
        if not self.app: return
        for i in self.tree.get_children():
            self.tree.delete(i)
        auto_targets = ["TX_MAIN", "TX_PRE1", "TX_PRE2", "TX_POST1", "TX_POST2", "TL_W", "TL_P"]
        for name, var in self.app.variable_manager.variables.items():
            val_str = var.expression if hasattr(var, "expression") else str(var)
            try:
                numeric_val = self._strip_unit(val_str)
                is_numeric = True
            except:
                is_numeric = False
                numeric_val = 0
            optimize, mn, mx, tags = "☐", "", "", ()
            # 預設 Type: W/SP 一律為 REAL，其餘若為整數則為 INT
            uname = name.upper()
            is_w_sp = any(uname == f"W{i}" or uname == f"SP{i}" for i in range(1, 10))
            param_type = "REAL" if is_w_sp else ("REAL" if not is_numeric or numeric_val != int(numeric_val) else "INT")
            if any(target in uname for target in auto_targets) and is_numeric:
                optimize, tags = "☑", ("yes",)
                # 使用 ±1 範圍，並確保最小值不低於 0.01 (避免 0mm 導致模擬錯誤)
                mn = str(round(max(numeric_val - 1.0, 0.01), 4))
                mx = str(round(numeric_val + 1.0, 4))
            self.tree.insert("", "end", values=(name, val_str, mn, mx, optimize, param_type), tags=tags)
        self._update_param_count()

    def _update_param_count(self):
        count = sum(1 for i in self.tree.get_children() if self.tree.item(i, "values")[4] == "☑")
        self.lbl_param_count.config(text=f"已勾選最佳化參數: {count} 個")

    def _on_tree_click(self, event):
        item = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)
        if not item or not column:
            return

        col_index = int(column[1:]) - 1
        vals = list(self.tree.item(item, "values"))
        
        # Optimize 勾選框切換 (col 4)
        if col_index == 4:
            if vals[4] == "☑":
                vals[4] = "☐"
                vals[2] = ""
                vals[3] = ""
                self.tree.item(item, values=vals, tags=())
            else:
                vals[4] = "☑"
                try:
                    num_val = self._strip_unit(vals[1])
                    vals[2] = str(round(max(num_val - 1.0, 0.01), 4))
                    vals[3] = str(round(num_val + 1.0, 4))
                except:
                    pass
                self.tree.item(item, values=vals, tags=("yes",))
            self._update_param_count()
            return

        # Type 切換: REAL ↔ INT (col 5)
        if col_index == 5:
            vals[5] = "INT" if vals[5] == "REAL" else "REAL"
            self.tree.item(item, values=vals)
            return

        # Min 或 Max 直接編輯 (col 2, 3)
        if col_index in [2, 3]:
            x, y, width, height = self.tree.bbox(item, column)
            entry = tk.Entry(self.tree, bg="#161b22", fg="#39ff14", font=("Consolas", 12, "bold"), justify="center", insertbackground="#00f0ff", relief="flat")
            entry.place(x=x, y=y, width=width, height=height)
            entry.insert(0, vals[col_index])
            entry.focus_set()
            entry.select_range(0, tk.END)

            def save_edit(e=None):
                new_val = entry.get()
                vals[col_index] = new_val
                self.tree.item(item, values=vals)
                entry.destroy()

            entry.bind("<Return>", save_edit)
            entry.bind("<FocusOut>", save_edit)
            entry.bind("<Escape>", lambda e: entry.destroy())
 
    def _toggle_all_optimize(self):
        items = self.tree.get_children()
        if not items: return
        
        # 檢查是否目前全部都已經勾選
        all_checked = all(self.tree.item(i, "values")[4] == "☑" for i in items)
        
        target_state = "☐" if all_checked else "☑"
        
        for item in items:
            vals = list(self.tree.item(item, "values"))
            if target_state == "☑":
                vals[4] = "☑"
                try:
                    num_val = self._strip_unit(vals[1])
                    vals[2] = str(round(max(num_val - 1.0, 0.01), 4))
                    vals[3] = str(round(num_val + 1.0, 4))
                except: pass
                self.tree.item(item, values=vals, tags=("yes",))
            else:
                vals[4] = "☐"
                vals[2] = ""
                vals[3] = ""
                self.tree.item(item, values=vals, tags=())
        self._update_param_count()

    def _run_all(self):
        if not HAS_OSL:
            messagebox.showerror("錯誤", "請先安裝 ansys-optislang-core")
            return
        # selected tuple: (name, value, min, max, type)
        selected = [
            (
                self.tree.item(i,"values")[0],
                self.tree.item(i,"values")[1],
                self.tree.item(i,"values")[2],
                self.tree.item(i,"values")[3],
                self.tree.item(i,"values")[5] if len(self.tree.item(i,"values")) > 5 else "REAL"
            )
            for i in self.tree.get_children()
            if self.tree.item(i,"values")[4]=="☑"
        ]
        if not selected:
            messagebox.showwarning("提醒", "請先勾選至少一個參數進行最佳化")
            return
        p_name, d_name, setup, report, opf_path = self.cb_proj.get(), self.cb_design.get(), self.cb_simsetup.get() or "AMIAnalysis", self.cb_report.get(), self.ent_opf.get()
        max_eval, response, do_start = int(self.ent_max.get() or "300"), self.var_resp.get(), self.var_start.get()
        oco_mode = self.var_oco_mode.get()
        direction = ComparisonType.MAX
        self.root.nametowidget(self.root.winfo_children()[1]).select(2)

        def task():
            try:
                script_path = os.path.join(WORK_DIR, "aedt_bridge.py")
                csv_path    = os.path.join(WORK_DIR, "osl_result.csv").replace("\\","/")
                
                param_init_code = ""
                for n, v, *_ in selected:
                    py_n = n.replace("$", "proj_")
                    try:
                        iv = self._strip_unit(v)
                    except:
                        iv = v
                    param_init_code += f"    {py_n} = {iv}\n"
                
                param_write_code = ""
                import re
                for n, v, *_ in selected:
                    py_n = n.replace("$", "proj_")
                    unit_str = ""
                    m = re.match(r'^([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?)(.*)', str(v).strip())
                    if m:
                        unit_str = m.group(2).strip()
                    if n.startswith("$"):
                        param_write_code += f"        oProject.ChangeProperty(['NAME:AllTabs', ['NAME:ProjectVariableTab', ['NAME:PropServers', 'ProjectVariables'], ['NAME:ChangedProps', ['NAME:{n}', 'Value:=' , str(round({py_n}, 4)) + '{unit_str}']]]])\n"
                    else:
                        # 加入 clamp 保護：mm 單位的幾何參數必須 ≥ 0.5mm
                        # (mcpl 模型要求 WH=W/H 在 0.02~8 之間，H 最大假設 25mm 時 W>=0.5mm)
                        if unit_str.lower() == "mm":
                            param_write_code += f"        _v = max(round({py_n}, 4), 0.5); oDesign.ChangeProperty(['NAME:AllTabs', ['NAME:LocalVariableTab', ['NAME:PropServers', 'LocalVariables'], ['NAME:ChangedProps', ['NAME:{n}', 'Value:=' , str(_v) + 'mm']]]])\n"
                        else:
                            param_write_code += f"        oDesign.ChangeProperty(['NAME:AllTabs', ['NAME:LocalVariableTab', ['NAME:PropServers', 'LocalVariables'], ['NAME:ChangedProps', ['NAME:{n}', 'Value:=' , str(round({py_n}, 4)) + '{unit_str}']]]])\n"

                bridge = fr'''# AEDT-OptiSLang 橋接腳本 (COM 強化版)
import os, csv, sys, time, win32com.client
if "OSL_REGULAR_EXECUTION" not in dir():
    OSL_REGULAR_EXECUTION = False

if not OSL_REGULAR_EXECUTION:
{param_init_code}

try:
    oApp = win32com.client.Dispatch(f"Ansoft.ElectronicsDesktop.{self.cb_version.get()}")
    oDesktop = oApp.GetAppDesktop()
    oProject = oDesktop.SetActiveProject(r"{p_name}")
    oDesign = oProject.SetActiveDesign(r"{d_name}")
    
    if OSL_REGULAR_EXECUTION:
        # 寫入參數
{param_write_code}
        # 強制 AEDT 重新計算 (Analyze)
        oDesign.Analyze("{setup}")
    time.sleep(1) # 等待系統反應
    
    # 匯出報告
    oModule = oDesign.GetModule("ReportSetup")
    try: oModule.ExportToFile("{report}", "{csv_path}", False)
    except: pass
    
    legend_csv = r"{csv_path}" + "_legend.csv"
    try:
        if os.path.exists(legend_csv): os.remove(legend_csv)
        oModule.ExportTableToFile("{report}", legend_csv, "Legend")
    except: pass
    
    for _ in range(10):
        if os.path.exists(r"{csv_path}") or os.path.exists(legend_csv): break
        time.sleep(0.5)
    
except Exception as e:
    with open("bridge_error.log", "w") as f: f.write(str(e))
    sys.exit(1)

# ── 讀取結果 ──
import re
# 輸出變數必須在最頂層定義，確保 OptiSLang Python2 節點能讀到
EyeHeight = -1.0
EyeWidth = -1.0

if os.path.exists(r"{csv_path}"):
    with open(r"{csv_path}") as f: rows = list(csv.reader(f))
    if len(rows) > 1:
        headers, data = rows[0], rows[1]
        for i, h in enumerate(headers):
            if not h or i >= len(data): continue
            if "eyeheight" in h.lower(): EyeHeight = float(data[i])
            elif "eyewidth" in h.lower(): EyeWidth = float(data[i])
                    
    if EyeHeight == -1.0 and os.path.exists(legend_csv):
        try:
            with open(legend_csv, "r", encoding="utf-8", errors="ignore") as tr:
                text = tr.read()
            idx_h = text.find("EyeHeight")
            if idx_h != -1:
                m_h = re.search(r'([+-]?\d*\.\d+|[+-]?\d+\.?\d*[eE][+-]?\d+|[+-]?\d+)', text[idx_h+len("EyeHeight"):])
                if m_h: EyeHeight = float(m_h.group(1))
            idx_w = text.find("EyeWidth")
            if idx_w != -1:
                m_w = re.search(r'([+-]?\d*\.\d+|[+-]?\d+\.?\d*[eE][+-]?\d+|[+-]?\d+)', text[idx_w+len("EyeWidth"):])
                if m_w: EyeWidth = float(m_w.group(1))
        except: pass

# 如果最後還是沒抓到有效數據 (-1.0)，強制回報錯誤，讓 OptiSLang 將該設計標記為 Failed
if EyeHeight == -1.0 or EyeWidth == -1.0:
    sys.exit(1)

'''
                with open(script_path, "w", encoding="utf-8") as f:
                    f.write(bridge)
                self._log("[層1] 橋接腳本已生成")
                
                ver_key = self.cb_version.get()
                osl_ver = {"2026.1": 261, "2025.2": 252, "2025.1": 251, "2024.2": 242, "2024.1": 241}.get(ver_key)
                
                kwargs = {"ini_timeout": 90}
                if osl_ver:
                    kwargs["version"] = osl_ver
                    
                # 尋找實體執行檔路徑 (避免環境變數遺失的問題)
                exe_path = None
                if osl_ver:
                    for base in [r"C:\Program Files\ANSYS Inc\v", r"C:\Program Files\AnsysEM\v"]:
                        test_path = rf"{base}{osl_ver}\optiSlang\optislang.exe"
                        if os.path.exists(test_path):
                            exe_path = test_path
                            break
                if exe_path:
                    kwargs["executable"] = exe_path
                    kwargs.pop("version", None)
                    
                self._log(f"[系統] 嘗試啟動 OptiSLang (參數: {kwargs})")
                with Optislang(**kwargs) as osl:
                    root = osl.application.project.root_system
                    # 建立雙節點流程：AMOP (靈敏度) -> Optimization (最佳化)
                    amop = root.create_node(node_types.AMOP)
                    opt  = root.create_node(node_types.OCO)
                    dexp = root.create_node(node_types.DesignExport)
                    
                    # 連結：AMOP 算完將最佳設計傳給 Optimization 作為起點，最後傳給 Export
                    amop.get_output_slots(name="OBestDesigns")[0].connect_to(opt.get_input_slots(name="IStartDesigns")[0])
                    opt.get_output_slots(name="ODesigns")[0].connect_to(dexp.get_input_slots(name="IDesigns")[0])
                    
                    # 獨立替 AMOP 設定 Python 執行腳本
                    amop_py = amop.create_node(node_types.Python2, design_flow=DesignFlow.RECEIVE_SEND)
                    prop = amop_py.get_property("Path")
                    prop["path"]["split_path"]["head"], prop["path"]["split_path"]["tail"] = os.path.dirname(script_path), os.path.basename(script_path)
                    amop_py.set_property("Path", prop)
                    
                    for n, v, mn, mx, ptype in selected:
                        py_n = n.replace("$", "proj_")
                        try: iv = self._strip_unit(v)
                        except: iv = 0.0
                        if ptype == "REAL":
                            if iv == int(iv): iv = iv + 0.001
                        else:
                            iv = int(round(iv))
                        amop_py.register_location_as_parameter(py_n, py_n, iv)

                    amop_py.register_location_as_response("EyeHeight", "EyeHeight", 0.0)
                    amop_py.register_location_as_response("EyeWidth", "EyeWidth", 0.0)
                    
                    params = amop.parameter_manager.get_parameters()
                    param_map = {p.name: p for p in params}
                    for n, v, mn, mx, ptype in selected:
                        py_n = n.replace("$", "proj_")
                        p = param_map.get(py_n)
                        if p is None: continue
                        try:
                            iv = self._strip_unit(v)
                            half = max(abs(iv) * 0.5, 0.1)
                            fmn = self._strip_unit(mn) if mn else max(iv - half, 0.01)
                            fmx = self._strip_unit(mx) if mx else iv + half
                            fmn = max(fmn, 0.01)
                            p.range = [fmn, fmx]
                            p.reference_value = (fmn + fmx) / 2.0
                            amop.parameter_manager.modify_parameter(p)
                        except: pass
                    
                    amop.criteria_manager.add_criterion(ObjectiveCriterion(name="obj", expression=response, criterion=direction))

                    # 根據使用者選擇設定 OCO 節點
                    if oco_mode == "Direct":
                        opt_py = opt.create_node(node_types.Python2, design_flow=DesignFlow.RECEIVE_SEND)
                        prop = opt_py.get_property("Path")
                        prop["path"]["split_path"]["head"], prop["path"]["split_path"]["tail"] = os.path.dirname(script_path), os.path.basename(script_path)
                        opt_py.set_property("Path", prop)
                        
                        for n, v, mn, mx, ptype in selected:
                            py_n = n.replace("$", "proj_")
                            try: iv = self._strip_unit(v)
                            except: iv = 0.0
                            if ptype == "REAL":
                                if iv == int(iv): iv = iv + 0.001
                            else:
                                iv = int(round(iv))
                            opt_py.register_location_as_parameter(py_n, py_n, iv)
                            
                        opt_py.register_location_as_response("EyeHeight", "EyeHeight", 0.0)
                        opt_py.register_location_as_response("EyeWidth", "EyeWidth", 0.0)
                        
                        opt_params = opt.parameter_manager.get_parameters()
                        opt_param_map = {p.name: p for p in opt_params}
                        for n, v, mn, mx, ptype in selected:
                            py_n = n.replace("$", "proj_")
                            p = opt_param_map.get(py_n)
                            if p is None: continue
                            try:
                                iv = self._strip_unit(v)
                                half = max(abs(iv) * 0.5, 0.1)
                                fmn = self._strip_unit(mn) if mn else max(iv - half, 0.01)
                                fmx = self._strip_unit(mx) if mx else iv + half
                                fmn = max(fmn, 0.01)
                                p.range = [fmn, fmx]
                                p.reference_value = (fmn + fmx) / 2.0
                                opt.parameter_manager.modify_parameter(p)
                            except: pass
                            
                        opt.criteria_manager.add_criterion(ObjectiveCriterion(name="obj", expression=response, criterion=direction))
                    else:
                        # MOP Virtual Solver Mode
                        mop_node = opt.create_node(node_types.Mopsolver, design_flow=DesignFlow.RECEIVE_SEND)
                        
                        # 複製參數設定到 OCO 節點 (解決 No parameter definition available 錯誤)
                        for p in amop.parameter_manager.get_parameters():
                            try: opt.parameter_manager.add_parameter(p)
                            except: pass
                            
                        # 嘗試自動接線 (MOP Database)
                        try:
                            amop.get_output_slots(name="OMDBPath")[0].connect_to(mop_node.get_input_slots(name="IMDBPath")[0])
                        except Exception as e:
                            self._log(f"MOP 接線失敗: {e}")
                        
                        opt.criteria_manager.add_criterion(ObjectiveCriterion(name="obj", expression=response, criterion=direction))

                    # 設定 AMOP 取樣數
                    try:
                        info = amop.get_property("AMopSettings")
                        info["num_designs_max"] = max_eval
                        amop.set_property("AMopSettings", info)
                    except: pass
                    
                    osl.application.save_as(opf_path)
                    self._log(f"[層2] 專案已儲存: {opf_path}")
                    if do_start:
                        self._log("正在啟動雙節點工作流計算...")
                        osl.application.project.start()
                        
                import subprocess
                subprocess.Popen([opf_path], shell=True)
                self._log("optiSLang 已開啟")
            except Exception as e:
                self._log(f"[錯誤] {e}")
                self._log(traceback.format_exc())
        threading.Thread(target=task, daemon=True).start()

if __name__ == "__main__":
    root = tk.Tk()
    AMIEyeDashboard(root)
    root.mainloop()

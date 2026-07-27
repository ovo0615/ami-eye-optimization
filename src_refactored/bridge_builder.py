"""
產生 AEDT-OptiSLang 橋接腳本 (COM 版)。

設計說明：橋接腳本是在 optiSLang 的 Python2 嵌入式節點內執行，
該環境通常沒有 PyAEDT，因此沿用 win32com。本模組把「靜態樣板」與
「依參數注入的程式碼」分開，並依最佳化目標 (objective spec) 切換
結果讀取區塊（眼圖 EyeHeight/EyeWidth 或 S 參數 worst-case 指標）。
"""
import config
from param_utils import strip_unit, split_value_unit, py_name
import objective


def _param_init_block(selected):
    """OSL_REGULAR_EXECUTION=False（首次/獨立執行）時的參數初值定義。"""
    lines = []
    for name, value, *_ in selected:
        try:
            iv = strip_unit(value)
        except ValueError:
            iv = value
        lines.append(f"    {py_name(name)} = {iv}")
    return "\n".join(lines)


def _param_write_block(selected):
    """OSL_REGULAR_EXECUTION=True 時，把參數寫回 AEDT 的 ChangeProperty 程式碼。"""
    lines = []
    for name, value, *_ in selected:
        pn = py_name(name)
        _, unit = split_value_unit(value)
        if name.startswith("$"):
            lines.append(
                f"        oProject.ChangeProperty(['NAME:AllTabs', "
                f"['NAME:ProjectVariableTab', ['NAME:PropServers', 'ProjectVariables'], "
                f"['NAME:ChangedProps', ['NAME:{name}', 'Value:=', "
                f"str(round({pn}, {config.ROUND_DIGITS})) + '{unit}']]]])"
            )
        elif unit.lower() == "mm":
            # mm 幾何參數鉗制下限，避免 mcpl 模型 WH 超界
            lines.append(
                f"        _v = max(round({pn}, {config.ROUND_DIGITS}), {config.MIN_MM_VALUE}); "
                f"oDesign.ChangeProperty(['NAME:AllTabs', ['NAME:LocalVariableTab', "
                f"['NAME:PropServers', 'LocalVariables'], ['NAME:ChangedProps', "
                f"['NAME:{name}', 'Value:=', str(_v) + 'mm']]]])"
            )
        else:
            lines.append(
                f"        oDesign.ChangeProperty(['NAME:AllTabs', ['NAME:LocalVariableTab', "
                f"['NAME:PropServers', 'LocalVariables'], ['NAME:ChangedProps', "
                f"['NAME:{name}', 'Value:=', "
                f"str(round({pn}, {config.ROUND_DIGITS})) + '{unit}']]]])"
            )
    return "\n".join(lines)


# 共用頭：連線 AEDT、（必要時）寫參數+重算、匯出報告 CSV 與 Legend。
_HEAD = r'''# AEDT-OptiSLang 橋接腳本 (COM 強化版) — 由 bridge_builder.py 自動生成
import os, csv, sys, time, re, win32com.client

if "OSL_REGULAR_EXECUTION" not in dir():
    OSL_REGULAR_EXECUTION = False

if not OSL_REGULAR_EXECUTION:
{init_block}

try:
    oApp = win32com.client.Dispatch("Ansoft.ElectronicsDesktop.{version}")
    oDesktop = oApp.GetAppDesktop()
    oProject = oDesktop.SetActiveProject(r"{project}")
    oDesign = oProject.SetActiveDesign(r"{design}")

    if OSL_REGULAR_EXECUTION:
{write_block}
        oDesign.Analyze("{setup}")
    time.sleep(1)

    oModule = oDesign.GetModule("ReportSetup")
    try:
        oModule.ExportToFile("{report}", r"{csv_path}", False)
    except Exception:
        pass

    legend_csv = r"{csv_path}" + "_legend.csv"
    try:
        if os.path.exists(legend_csv):
            os.remove(legend_csv)
        oModule.ExportTableToFile("{report}", legend_csv, "Legend")
    except Exception:
        pass

    for _ in range(10):
        if os.path.exists(r"{csv_path}") or os.path.exists(legend_csv):
            break
        time.sleep(0.5)

except Exception as e:
    with open("bridge_error.log", "w") as f:
        f.write(str(e))
    sys.exit(1)
'''


# 眼圖結果讀取（輸出變數須在頂層供 OptiSLang Python2 節點讀取）。
_EYE_RESULT = r'''
EyeHeight = -1.0
EyeWidth = -1.0

if os.path.exists(r"{csv_path}"):
    with open(r"{csv_path}") as f:
        rows = list(csv.reader(f))
    if len(rows) > 1:
        headers, data = rows[0], rows[1]
        for i, h in enumerate(headers):
            if not h or i >= len(data):
                continue
            if "eyeheight" in h.lower():
                EyeHeight = float(data[i])
            elif "eyewidth" in h.lower():
                EyeWidth = float(data[i])

    if EyeHeight == -1.0 and os.path.exists(legend_csv):
        try:
            with open(legend_csv, "r", encoding="utf-8", errors="ignore") as tr:
                text = tr.read()
            num = r'([+-]?\d*\.\d+|[+-]?\d+\.?\d*[eE][+-]?\d+|[+-]?\d+)'
            idx_h = text.find("EyeHeight")
            if idx_h != -1:
                m = re.search(num, text[idx_h + len("EyeHeight"):])
                if m:
                    EyeHeight = float(m.group(1))
            idx_w = text.find("EyeWidth")
            if idx_w != -1:
                m = re.search(num, text[idx_w + len("EyeWidth"):])
                if m:
                    EyeWidth = float(m.group(1))
        except Exception:
            pass

# 沒抓到有效值就回報失敗，讓 OptiSLang 標記該設計為 Failed
if EyeHeight == -1.0 or EyeWidth == -1.0:
    sys.exit(1)
'''


# S 參數 worst-case 結果讀取。{reducer}=max(S11)/min(S21)，{sentinel} 為取不到資料的哨兵。
_SPARAM_RESULT = r'''
# ── S 參數 worst-case 讀取 ──
SParamMetric = {sentinel}
_F_START_HZ = {f_start_hz}
_F_STOP_HZ = {f_stop_hz}
_TARGET_TOKENS = {tokens}

_UNIT_HZ = {{"hz": 1.0, "khz": 1e3, "mhz": 1e6, "ghz": 1e9, "thz": 1e12}}

def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())

if os.path.exists(r"{csv_path}"):
    with open(r"{csv_path}") as f:
        rows = list(csv.reader(f))
    if len(rows) > 1:
        headers = rows[0]
        # 找頻率欄並判讀單位
        freq_idx, freq_scale = 0, 1.0
        for i, h in enumerate(headers):
            hl = h.lower()
            if "freq" in hl:
                freq_idx = i
                m = re.search(r"([gmkt]?hz)", hl)
                if m:
                    freq_scale = _UNIT_HZ.get(m.group(1), 1.0)
                break
        # 找目標 S 參數欄（標準化後比對 token）
        target_idx = -1
        for i, h in enumerate(headers):
            hn = _norm(h)
            if any(tok in hn for tok in _TARGET_TOKENS):
                target_idx = i
                break
        if target_idx != -1:
            vals = []
            for row in rows[1:]:
                if len(row) <= max(freq_idx, target_idx):
                    continue
                try:
                    fhz = float(row[freq_idx]) * freq_scale
                    val = float(row[target_idx])
                except ValueError:
                    continue
                if _F_START_HZ <= fhz <= _F_STOP_HZ:
                    vals.append(val)
            if vals:
                SParamMetric = {reducer}(vals)

# 哨兵未被取代 = 頻寬內找不到資料，回報失敗讓 OptiSLang 標記 Failed
if SParamMetric == {sentinel}:
    sys.exit(1)
'''


def _result_block(spec, csv_path):
    if spec["mode"] == config.TARGET_EYE:
        return _EYE_RESULT.format(csv_path=csv_path)
    f_lo, f_hi = objective.band_hz(spec)
    # 以實際 trace 名稱標準化後當作比對 token（自動偵測自 AEDT）
    tokens = [objective.normalize_trace(spec["trace"])]
    # 最小化目標的 worst-case = 頻寬內最大值；最大化目標的 worst-case = 最小值
    reducer = "max" if spec["direction"] == "MIN" else "min"
    sentinel = config.SPARAM_SENTINEL if spec["direction"] == "MIN" else -config.SPARAM_SENTINEL
    return _SPARAM_RESULT.format(
        csv_path=csv_path, f_start_hz=f_lo, f_stop_hz=f_hi,
        tokens=repr(tokens), reducer=reducer, sentinel=sentinel,
    )


def build_bridge_script(selected, *, version, project, design, setup, report, csv_path, spec):
    """回傳完整橋接腳本字串。selected=[(name,value,min,max,type),...]，spec 見 objective.py。"""
    head = _HEAD.format(
        init_block=_param_init_block(selected),
        write_block=_param_write_block(selected),
        version=version, project=project, design=design,
        setup=setup, report=report, csv_path=csv_path,
    )
    return head + "\n" + _result_block(spec, csv_path)

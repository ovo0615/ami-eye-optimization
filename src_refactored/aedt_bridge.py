# AEDT-OptiSLang 橋接腳本 (COM 強化版) — 由 bridge_builder.py 自動生成
import os, csv, sys, time, re, win32com.client

if "OSL_REGULAR_EXECUTION" not in dir():
    OSL_REGULAR_EXECUTION = False

if not OSL_REGULAR_EXECUTION:
    W1 = 2.575
    SP1 = 0.6792
    W2 = 1.2758
    SP2 = 0.8625
    W3 = 1.1449
    SP3 = 1.1355
    W4 = 0.6123
    SP4 = 0.5282
    W5 = 0.5
    SP5 = 0.5

try:
    oApp = win32com.client.Dispatch("Ansoft.ElectronicsDesktop.2026.1")
    oDesktop = oApp.GetAppDesktop()
    oProject = oDesktop.SetActiveProject(r"S_Test")
    oDesign = oProject.SetActiveDesign(r"3_AMI_with_TL")

    if OSL_REGULAR_EXECUTION:
        _v = max(round(W1, 4), 0.5); oDesign.ChangeProperty(['NAME:AllTabs', ['NAME:LocalVariableTab', ['NAME:PropServers', 'LocalVariables'], ['NAME:ChangedProps', ['NAME:W1', 'Value:=', str(_v) + 'mm']]]])
        _v = max(round(SP1, 4), 0.5); oDesign.ChangeProperty(['NAME:AllTabs', ['NAME:LocalVariableTab', ['NAME:PropServers', 'LocalVariables'], ['NAME:ChangedProps', ['NAME:SP1', 'Value:=', str(_v) + 'mm']]]])
        _v = max(round(W2, 4), 0.5); oDesign.ChangeProperty(['NAME:AllTabs', ['NAME:LocalVariableTab', ['NAME:PropServers', 'LocalVariables'], ['NAME:ChangedProps', ['NAME:W2', 'Value:=', str(_v) + 'mm']]]])
        _v = max(round(SP2, 4), 0.5); oDesign.ChangeProperty(['NAME:AllTabs', ['NAME:LocalVariableTab', ['NAME:PropServers', 'LocalVariables'], ['NAME:ChangedProps', ['NAME:SP2', 'Value:=', str(_v) + 'mm']]]])
        _v = max(round(W3, 4), 0.5); oDesign.ChangeProperty(['NAME:AllTabs', ['NAME:LocalVariableTab', ['NAME:PropServers', 'LocalVariables'], ['NAME:ChangedProps', ['NAME:W3', 'Value:=', str(_v) + 'mm']]]])
        _v = max(round(SP3, 4), 0.5); oDesign.ChangeProperty(['NAME:AllTabs', ['NAME:LocalVariableTab', ['NAME:PropServers', 'LocalVariables'], ['NAME:ChangedProps', ['NAME:SP3', 'Value:=', str(_v) + 'mm']]]])
        _v = max(round(W4, 4), 0.5); oDesign.ChangeProperty(['NAME:AllTabs', ['NAME:LocalVariableTab', ['NAME:PropServers', 'LocalVariables'], ['NAME:ChangedProps', ['NAME:W4', 'Value:=', str(_v) + 'mm']]]])
        _v = max(round(SP4, 4), 0.5); oDesign.ChangeProperty(['NAME:AllTabs', ['NAME:LocalVariableTab', ['NAME:PropServers', 'LocalVariables'], ['NAME:ChangedProps', ['NAME:SP4', 'Value:=', str(_v) + 'mm']]]])
        _v = max(round(W5, 4), 0.5); oDesign.ChangeProperty(['NAME:AllTabs', ['NAME:LocalVariableTab', ['NAME:PropServers', 'LocalVariables'], ['NAME:ChangedProps', ['NAME:W5', 'Value:=', str(_v) + 'mm']]]])
        _v = max(round(SP5, 4), 0.5); oDesign.ChangeProperty(['NAME:AllTabs', ['NAME:LocalVariableTab', ['NAME:PropServers', 'LocalVariables'], ['NAME:ChangedProps', ['NAME:SP5', 'Value:=', str(_v) + 'mm']]]])
        oDesign.Analyze("LinearFrequency")
    time.sleep(1)

    oModule = oDesign.GetModule("ReportSetup")
    try:
        oModule.ExportToFile("S Parameter Plot1", r"d:/AI Development/AMI Eye Optimization/src_refactored/osl_result.csv", False)
    except Exception:
        pass

    legend_csv = r"d:/AI Development/AMI Eye Optimization/src_refactored/osl_result.csv" + "_legend.csv"
    try:
        if os.path.exists(legend_csv):
            os.remove(legend_csv)
        oModule.ExportTableToFile("S Parameter Plot1", legend_csv, "Legend")
    except Exception:
        pass

    for _ in range(10):
        if os.path.exists(r"d:/AI Development/AMI Eye Optimization/src_refactored/osl_result.csv") or os.path.exists(legend_csv):
            break
        time.sleep(0.5)

except Exception as e:
    with open("bridge_error.log", "w") as f:
        f.write(str(e))
    sys.exit(1)


# ── S 參數 worst-case 讀取 ──
SParamMetric = 1000000000.0
_F_START_HZ = 0.0
_F_STOP_HZ = 50000000000.0
_TARGET_TOKENS = ['dbsport1port1']

_UNIT_HZ = {"hz": 1.0, "khz": 1e3, "mhz": 1e6, "ghz": 1e9, "thz": 1e12}

def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())

if os.path.exists(r"d:/AI Development/AMI Eye Optimization/src_refactored/osl_result.csv"):
    with open(r"d:/AI Development/AMI Eye Optimization/src_refactored/osl_result.csv") as f:
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
                SParamMetric = max(vals)

# 哨兵未被取代 = 頻寬內找不到資料，回報失敗讓 OptiSLang 標記 Failed
if SParamMetric == 1000000000.0:
    sys.exit(1)

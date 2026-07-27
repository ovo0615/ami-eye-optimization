"""
最佳化目標 (objective) 抽象。

把「眼圖優化」與「S 參數優化」統一成同一個 spec dict，讓 GUI、
bridge_builder、osl_workflow 三層都只認這一個介面。

spec 形狀：
  眼圖： {"mode": "eye", "response": "EyeHeight"|"EyeWidth"}
  S參數：{"mode": "sparam", "trace": "dB(S(Diff2,Diff1))",
          "direction": "MIN"|"MAX",
          "f_start": float, "f_stop": float, "f_unit": "GHz"}

S 參數 trace 名稱與端口命名（單端 PortN / 差動 DiffN）直接從 AEDT
設計自動偵測帶入，不再寫死。
"""
import re

import config

_PORTS_RE = re.compile(r"S\(\s*([^,]+?)\s*,\s*([^)\s]+?)\s*\)")


def trace_ports(trace):
    """從 trace 名稱解析兩個端口 token，例如 'dB(S(Diff2,Diff1))' -> ('Diff2','Diff1')。"""
    m = _PORTS_RE.search(trace or "")
    if m:
        return m.group(1), m.group(2)
    return None, None


def direction_for_trace(trace):
    """反射 (Sii，如回波損耗) -> 最小化 MIN；傳輸 (Sij，如插入損耗) -> 最大化 MAX。"""
    a, b = trace_ports(trace)
    if a and b and a == b:
        return "MIN"
    return "MAX"


def normalize_trace(trace):
    """標準化（小寫、去非英數）以便和 CSV 欄位標題比對。"""
    return re.sub(r"[^a-z0-9]", "", (trace or "").lower())


def make_eye_spec(response):
    return {"mode": config.TARGET_EYE, "response": response}


def make_sparam_spec(trace, f_start, f_stop, f_unit, direction=None):
    return {
        "mode": config.TARGET_SPARAM,
        "trace": trace,
        "direction": direction or direction_for_trace(trace),
        "f_start": float(f_start),
        "f_stop": float(f_stop),
        "f_unit": f_unit,
    }


def response_registrations(spec):
    """要在 OptiSLang Python 節點上註冊的響應 [(name, init_value), ...]。"""
    if spec["mode"] == config.TARGET_EYE:
        return [("EyeHeight", 0.0), ("EyeWidth", 0.0)]
    return [("SParamMetric", 0.0)]


def objective(spec):
    """回傳 (criterion_name, expression, direction_str)。direction_str 為 'MIN'/'MAX'。"""
    if spec["mode"] == config.TARGET_EYE:
        return ("obj", spec["response"], "MAX")
    return ("obj", "SParamMetric", spec["direction"])


def band_hz(spec):
    """S 參數頻寬換算成 (f_start_hz, f_stop_hz)。"""
    scale = config.FREQ_UNIT_HZ.get(spec["f_unit"].lower(), 1.0)
    lo, hi = spec["f_start"] * scale, spec["f_stop"] * scale
    return (min(lo, hi), max(lo, hi))


def describe(spec):
    """供日誌顯示的人類可讀字串。"""
    if spec["mode"] == config.TARGET_EYE:
        return f"眼圖優化 — {spec['response']} (最大化)"
    direction = "最小化" if spec["direction"] == "MIN" else "最大化"
    return (f"S參數優化 — {spec['trace']} 於 "
            f"{spec['f_start']}~{spec['f_stop']} {spec['f_unit']} worst-case ({direction})")

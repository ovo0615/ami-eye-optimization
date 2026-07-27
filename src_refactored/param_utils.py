"""
純函式：數值解析與參數範圍計算。
從 GUI 抽離，方便單元測試（見 test_param_utils.py）。
"""
import re

import config

_NUM_RE = re.compile(r'^([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?)(.*)')


def strip_unit(val_str):
    """'5.2mm' -> 5.2，無法解析則 raise ValueError。"""
    m = _NUM_RE.match(str(val_str).strip())
    if m:
        return float(m.group(1))
    raise ValueError(f"無法解析數值: {val_str!r}")


def split_value_unit(val_str):
    """'5.2mm' -> (5.2, 'mm')；無法解析數值則 (None, '')。"""
    m = _NUM_RE.match(str(val_str).strip())
    if m:
        return float(m.group(1)), m.group(2).strip()
    return None, ""


def infer_type(name, value_str):
    """推斷參數型別：W/SP 一律 REAL，其餘整數值視為 INT。"""
    uname = name.upper()
    if any(uname == f"W{i}" or uname == f"SP{i}" for i in range(1, 10)):
        return "REAL"
    try:
        v = strip_unit(value_str)
    except ValueError:
        return "REAL"
    return "INT" if v == int(v) else "REAL"


def default_range(value):
    """自動勾選時的 ±RANGE_DELTA 範圍 (min, max)，min 受 MIN_PARAM_VALUE 鉗制。"""
    mn = round(max(value - config.RANGE_DELTA, config.MIN_PARAM_VALUE), config.ROUND_DIGITS)
    mx = round(value + config.RANGE_DELTA, config.ROUND_DIGITS)
    return str(mn), str(mx)


def resolve_range(value, mn_str, mx_str):
    """
    決定送進 optiSLang 的最終 (min, max)。
    使用者有填就用使用者的；沒填則用半幅推算。下限一律 >= MIN_PARAM_VALUE。
    """
    half = max(abs(value) * config.HALF_SPAN_RATIO, config.HALF_SPAN_MIN)
    fmn = strip_unit(mn_str) if mn_str else max(value - half, config.MIN_PARAM_VALUE)
    fmx = strip_unit(mx_str) if mx_str else value + half
    return max(fmn, config.MIN_PARAM_VALUE), fmx


def osl_initial_value(value, ptype):
    """送進 optiSLang 的初值：INT 取整；REAL 整數值加微量避免被當離散。"""
    if ptype == "REAL":
        return value + config.REAL_NUDGE if value == int(value) else value
    return int(round(value))


def py_name(aedt_name):
    """專案變數 '$foo' -> 合法 Python 變數名 'proj_foo'。"""
    return aedt_name.replace("$", "proj_")

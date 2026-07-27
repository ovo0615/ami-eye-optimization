"""
param_utils 與 bridge_builder 的單元測試（不需要 AEDT / OptiSLang 環境）。
執行： python -m pytest test_param_utils.py   或   python test_param_utils.py
"""
import param_utils as pu
import config
import objective
from bridge_builder import build_bridge_script


def test_strip_unit():
    assert pu.strip_unit("5.2mm") == 5.2
    assert pu.strip_unit("  -3 ") == -3.0
    assert pu.strip_unit("1.5e-2 ohm") == 0.015
    try:
        pu.strip_unit("abc")
    except ValueError:
        pass
    else:
        raise AssertionError("應對非數值 raise ValueError")


def test_split_value_unit():
    assert pu.split_value_unit("5.2mm") == (5.2, "mm")
    assert pu.split_value_unit("10") == (10.0, "")
    assert pu.split_value_unit("xx") == (None, "")


def test_infer_type():
    assert pu.infer_type("W1", "3") == "REAL"      # W/SP 一律 REAL
    assert pu.infer_type("SP2", "5") == "REAL"
    assert pu.infer_type("N", "4") == "INT"
    assert pu.infer_type("N", "4.5") == "REAL"


def test_default_range():
    mn, mx = pu.default_range(5.0)
    assert float(mn) == 4.0 and float(mx) == 6.0
    mn, _ = pu.default_range(0.2)               # 受 MIN_PARAM_VALUE 鉗制
    assert float(mn) == config.MIN_PARAM_VALUE


def test_resolve_range():
    assert pu.resolve_range(5.0, "1", "9") == (1.0, 9.0)        # 使用者優先
    fmn, fmx = pu.resolve_range(10.0, "", "")                   # 半幅推算
    assert fmn == 5.0 and fmx == 15.0
    fmn, _ = pu.resolve_range(0.05, "", "")                     # 下限鉗制
    assert fmn == config.MIN_PARAM_VALUE


def test_osl_initial_value():
    assert pu.osl_initial_value(4.0, "REAL") == 4.0 + config.REAL_NUDGE
    assert pu.osl_initial_value(4.3, "REAL") == 4.3
    assert pu.osl_initial_value(4.6, "INT") == 5


def test_py_name():
    assert pu.py_name("$foo") == "proj_foo"
    assert pu.py_name("W1") == "W1"


def test_build_bridge_script_eye():
    selected = [("W1", "3mm", "1", "5", "REAL"), ("$gap", "0.5", "", "", "REAL")]
    spec = objective.make_eye_spec("EyeHeight")
    s = build_bridge_script(selected, version="2026.1", project="P", design="D",
                            setup="S", report="R", csv_path="c:/x.csv", spec=spec)
    assert "Ansoft.ElectronicsDesktop.2026.1" in s
    assert "W1 = 3.0" in s            # init block
    assert "proj_gap = 0.5" in s
    assert "_v = max(round(W1" in s   # mm 鉗制
    assert "EyeHeight = -1.0" in s
    assert "SParamMetric" not in s


def test_objective_eye():
    spec = objective.make_eye_spec("EyeWidth")
    assert objective.response_registrations(spec) == [("EyeHeight", 0.0), ("EyeWidth", 0.0)]
    assert objective.objective(spec) == ("obj", "EyeWidth", "MAX")


def test_trace_direction():
    # 反射 (Sii) -> MIN；傳輸 (Sij) -> MAX；單端與差動皆適用
    assert objective.direction_for_trace("dB(S(Diff1,Diff1))") == "MIN"
    assert objective.direction_for_trace("dB(S(Diff2,Diff1))") == "MAX"
    assert objective.direction_for_trace("S(Port1,Port1)") == "MIN"
    assert objective.direction_for_trace("S(Port2,Port1)") == "MAX"


def test_normalize_trace():
    assert objective.normalize_trace("dB(S(Diff2,Diff1))") == "dbsdiff2diff1"
    assert objective.normalize_trace("S(Port1,Port1)") == "sport1port1"


def test_objective_sparam_direction():
    s_refl = objective.make_sparam_spec("dB(S(Diff1,Diff1))", 1, 5, "GHz")
    s_thru = objective.make_sparam_spec("dB(S(Diff2,Diff1))", 1, 5, "GHz")
    assert objective.objective(s_refl)[2] == "MIN"
    assert objective.objective(s_thru)[2] == "MAX"
    assert objective.response_registrations(s_refl) == [("SParamMetric", 0.0)]


def test_band_hz():
    spec = objective.make_sparam_spec("S(Port1,Port1)", 2, 8, "GHz")
    assert objective.band_hz(spec) == (2e9, 8e9)
    spec2 = objective.make_sparam_spec("S(Port1,Port1)", 8, 2, "GHz")  # 起訖顛倒
    assert objective.band_hz(spec2) == (2e9, 8e9)


def test_build_bridge_script_sparam():
    selected = [("W1", "3mm", "1", "5", "REAL")]
    # 反射 trace -> MIN -> max reducer + 正哨兵 + 標準化 token
    spec = objective.make_sparam_spec("dB(S(Diff1,Diff1))", 1, 5, "GHz")
    s = build_bridge_script(selected, version="2025.2", project="P", design="D",
                            setup="S", report="R", csv_path="c:/x.csv", spec=spec)
    assert "SParamMetric = max(vals)" in s
    assert "['dbsdiff1diff1']" in s
    assert "_F_START_HZ = 1000000000.0" in s
    assert "EyeHeight" not in s
    # 傳輸 trace -> MAX -> min reducer
    spec2 = objective.make_sparam_spec("dB(S(Diff2,Diff1))", 1, 5, "GHz")
    s2 = build_bridge_script(selected, version="2025.2", project="P", design="D",
                             setup="S", report="R", csv_path="c:/x.csv", spec=spec2)
    assert "SParamMetric = min(vals)" in s2
    assert "['dbsdiff2diff1']" in s2


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("\n所有測試通過 (ALL PASS)")

"""
集中管理所有「魔術值」與設定。
原本散落在 ami_eye_optimizer_v2.py 各處的硬編值，全部移到這裡，
換模型 / 換流程時只需改這一個檔，不必動邏輯。
"""

# ── AEDT 版本對照 ──────────────────────────────────────────────
# GUI 下拉選單顯示的版本字串 -> optiSLang 內部版本碼
AEDT_VERSIONS = {
    "2026.1": 261,
    "2025.2": 252,
    "2025.1": 251,
    "2024.2": 242,
    "2024.1": 241,
}
# 下拉預設選第一個
DEFAULT_VERSION = next(iter(AEDT_VERSIONS))

# optiSLang 執行檔的可能安裝根目錄（避免環境變數遺失）
OSL_INSTALL_BASES = [
    r"C:\Program Files\ANSYS Inc\v",
    r"C:\Program Files\AnsysEM\v",
]

# ── 參數自動偵測與範圍 ─────────────────────────────────────────
# 名稱包含這些關鍵字的變數，預設勾選為最佳化參數
AUTO_OPTIMIZE_TARGETS = ["TX_MAIN", "TX_PRE1", "TX_PRE2", "TX_POST1", "TX_POST2", "TL_W", "TL_P"]

# 自動勾選時，預設範圍 = 數值 ± RANGE_DELTA
RANGE_DELTA = 1.0
# 任一參數下限不得低於此值（避免 0mm 造成模擬錯誤）
MIN_PARAM_VALUE = 0.01
# 幾何 mm 參數的下限鉗制（mcpl 模型要求 WH=W/H 落在 0.02~8）
MIN_MM_VALUE = 0.5
# 手動勾選且未填 min/max 時，採半幅 = max(|v|*HALF_SPAN_RATIO, HALF_SPAN_MIN)
HALF_SPAN_RATIO = 0.5
HALF_SPAN_MIN = 0.1
# REAL 參數若初值剛好是整數，加上此微量避免 optiSLang 判定為離散
REAL_NUDGE = 0.001
# 數值四捨五入位數
ROUND_DIGITS = 4

# ── 預設工作流設定 ─────────────────────────────────────────────
DEFAULT_MAX_EVAL = 300            # AMOP 取樣次數
DEFAULT_RESPONSE = "EyeHeight"    # 最佳化響應
RESPONSES = ["EyeHeight", "EyeWidth"]
DEFAULT_OPF_NAME = "ami_eye_auto.opf"
DEFAULT_SETUP_NAME = "AMIAnalysis"
OSL_INI_TIMEOUT = 90

# ── S 參數最佳化 ───────────────────────────────────────────────
# 優化目標模式
TARGET_EYE = "eye"
TARGET_SPARAM = "sparam"

# 端口模式（用來篩選自動偵測到的 trace 清單）
PORT_MODES = [("single", "單端 (Single-ended)"), ("diff", "差動 (Differential)")]

# get_traces_for_plot 的類別字串（dB 振幅）
TRACE_CATEGORY = "dB(S"

# S 參數模式下，GUI 會為選定 trace 自動建立此名稱的持久報告，橋接腳本再匯出它。
# （橋接腳本在 OptiSLang Python2 節點以純 COM 執行，CreateReport 在 gRPC 下不可靠，
#   故改由 GUI 端 PyAEDT 預先建好報告。）
SPARAM_REPORT_NAME = "AMI_OPT_SParam"

# 頻率單位換算到 Hz
FREQ_UNITS = ["Hz", "kHz", "MHz", "GHz", "THz"]
FREQ_UNIT_HZ = {"hz": 1.0, "khz": 1e3, "mhz": 1e6, "ghz": 1e9, "thz": 1e12}

DEFAULT_FREQ_UNIT = "GHz"
DEFAULT_F_START = "0"
DEFAULT_F_STOP = "10"

# worst-case 取不到資料時的哨兵值（minimize 用大正值、maximize 用大負值）
SPARAM_SENTINEL = 1e9

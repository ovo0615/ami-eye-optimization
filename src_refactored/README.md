# AMI Eye Optimizer — 重構版 (v3)

這是 `src/ami_eye_optimizer_v2.py` 的重構版本，**功能與操作流程完全相同**，
但把單一 678 行檔案拆成可維護、可測試的模組。原始檔案未被改動。

## 檔案結構

| 檔案 | 職責 |
|------|------|
| `ami_eye_optimizer_v3.py` | Tkinter GUI（外觀/流程與 v2 一致），只負責畫面與委派邏輯 |
| `config.py` | 集中所有「魔術值」：版本對照、參數範圍鉗制、S 參數設定、預設值 |
| `param_utils.py` | 純函式：數值解析、型別推斷、範圍計算（可單元測試） |
| `objective.py` | 最佳化目標抽象，統一「眼圖」與「S 參數」兩種模式 |
| `bridge_builder.py` | 產生 AEDT-OptiSLang 橋接腳本（樣板 + 參數注入分離） |
| `osl_workflow.py` | OptiSLang 雙節點工作流編排（AMOP → OCO → DesignExport） |
| `test_param_utils.py` | 不需 AEDT/OSL 環境即可跑的單元測試 |

## 功能：眼圖 / S 參數 雙模式最佳化

GUI「Step 4」新增「優化目標」切換：

- **眼圖 (Eye)**：與原本相同，最大化 EyeHeight 或 EyeWidth。
- **S 參數 (S-Parameter)**：在指定頻寬內對選定 trace 做 **worst-case** 最佳化。
  - **trace 名稱自動偵測**：Scan 後從 AEDT 設計讀出實際可用的 S 參數 trace 填入下拉，
    不再寫死命名。單端用 `get_traces_for_plot()`（如 `dB(S(Port1,Port1))`）；
    差動端口名稱由 `save_diff_pairs_to_file()` 匯出檔解析（如 `Diff1`/`Diff2`），
    再查出差動 trace（如 `dB(S(Diff2,Diff1))`）。
  - **單端 / 差動切換**：切換時下拉自動換成對應清單。
  - **方向自動**：反射（Sii，如回波損耗）→最小化；傳輸（Sij，如插入損耗）→最大化。
    worst-case 定義：最小化目標取頻寬內最大值、最大化目標取頻寬內最小值。
  - 頻寬：輸入起訖頻率 + 單位（Hz/kHz/MHz/GHz/THz），會自動換算並比對 CSV 頻率欄位單位。

**資料來源 / trace→報告對應**：
- trace 下拉以**既有報告實際畫的 trace**為主來源（用 `app.post.plots` 讀出），
  每個 trace 記住所屬報告；執行時直接匯出該報告，最可靠（差動也涵蓋）。
- 另補充 `get_traces_for_plot()` 偵測到、但尚未畫的單端 trace；這類在執行時以
  PyAEDT `create_report` 臨時建立報告（單端可行；差動 `create_report` 在 gRPC 下會失敗，
  故差動一律走「既有報告」路徑）。
- 橋接腳本（純 COM）只負責**匯出報告**，不自行 CreateReport。匯出 CSV 後以選定 trace
  名稱標準化（小寫去非英數）比對欄位標題，於頻寬內取 worst-case。

> 使用 S 參數模式前，請先 Scan。**差動 trace 必須已存在於某個報告中**（如你的
> S Parameter Plot1/2）。掃頻範圍需涵蓋你設定的頻寬。

## 已知無害訊息

AEDT Message Manager 偶爾出現的 `Instance:... is not a child name` 為 AEDT 端噪音，
不影響功能。工具已改用 `oreportsetup.GetAllReportNames()` 取代會觸發該噪音的
`post.all_report_names`。

## 相較 v2 的改進

1. **去除重複**：v2 的 AMOP 與 Direct-OCO 各寫一份 register/range/criteria
   邏輯（約 40 行重複）。現抽成 `osl_workflow._configure_python_node()` 共用，
   消除「改一邊忘另一邊」的風險。
2. **錯誤可見**：v2 大量 `except: pass` 會靜默吞掉參數設定失敗。現全部改為
   `log("[警告] …")` 回報到執行日誌。
3. **魔術值集中**：±1 範圍、`min≥0.01`、`mm≥0.5`、REAL `+0.001` 等硬編值
   全移到 `config.py`，換模型只改設定不動邏輯。
4. **橋接腳本可讀**：v2 用一段 70+ 行巨型 f-string 拼出，現改為獨立樣板，
   靜態程式與注入點分離。
5. **可測試**：新增 8 個單元測試涵蓋數值解析與範圍計算。
6. **小修正**：tab 切換改用保留的 `Notebook` 參考（v2 用脆弱的 children 索引）；
   重複的 `import re` 統一至模組頂層。

## 設計取捨

橋接腳本仍使用 `win32com`（而非 PyAEDT），因為它在 optiSLang 的
**Python2 嵌入式節點**內執行，該環境通常不含 PyAEDT。強行改用會破壞執行。

## 執行

```bash
# 跑單元測試（不需 AEDT/OptiSLang）
python test_param_utils.py

# 啟動 GUI（需 pyaedt + ansys-optislang-core 與已安裝的 AEDT）
python ami_eye_optimizer_v3.py
```

驗證狀態：12/12 單元測試通過，6 個模組語法檢查通過，三種模式產生的橋接腳本
皆通過 Python 語法解析。GUI 與 OptiSLang 流程需在有 AEDT 的機器上實機測試
（本次未做實機驗證）。

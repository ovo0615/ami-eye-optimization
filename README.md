# AMI Eye Optimization

IBIS-AMI 眼圖自動化最佳化工具，將 AEDT Circuit／HFSS 的高速訊號模擬流程與 optiSLang 最佳化工作流連接，協助以 Eye Height、Eye Width 或 S 參數作為最佳化目標。

## 公開內容

本 Repository 公開 PyAEDT 版本的 GUI 與模組化腳本，包含：

- `src/ami_eye_optimizer_v2.py`：原始 PyAEDT GUI 版本。
- `src_refactored/ami_eye_optimizer_v3.py`：模組化重構版本，建議優先使用。
- `src_refactored/`：參數處理、目標函數、橋接腳本與 optiSLang 工作流模組。
- `docs/AMI_Eye_Automation_SOP.md`：含操作圖片的完整操作說明。
- `assets/`：操作說明使用的圖片與脫敏範例素材。

Web 版本未列入公開 Repository。

## 主要功能

- 連接目前開啟的 AEDT 專案與設計。
- 同步 AEDT 設計變數。
- 支援 Eye 與 S-Parameter 最佳化目標。
- 建立 AMOP／OCO 雙節點 optiSLang 工作流。
- 自動產生 AEDT–optiSLang 橋接腳本。
- 輸出可供最佳化節點使用的眼圖或 S 參數數值。

## 使用環境

- Ansys Electronics Desktop（含 Circuit／HFSS）
- Ansys optiSLang
- Python 3
- PyAEDT：請依 `requirements-pyaedt.txt` 安裝
- ansys-optislang-core：請依 Ansys／PyAnsys 相容版本安裝
- Windows COM 支援套件：`pywin32`

## 安裝

```powershell
pip install -r requirements-pyaedt.txt
```

## 啟動 PyAEDT 版本

```powershell
python src_refactored/ami_eye_optimizer_v3.py
```

如需執行單元測試：

```powershell
python src_refactored/test_param_utils.py
```

## 操作說明

請參閱：[AMI Eye Automation SOP](docs/AMI_Eye_Automation_SOP.md)

## 注意事項

本 Repository 主要用於技術展示。執行最佳化前，請先備份 AEDT 專案，並確認 AEDT、optiSLang、PyAEDT 與 Python 版本相容。請勿上傳客戶模型、真實通道資料或含機密的模擬結果。

如需完整商用版本、流程整合或客製化最佳化功能，請來信洽詢。

此工具由虎門科技資深技術工程師 Jeff Hong 洪敬傑提供

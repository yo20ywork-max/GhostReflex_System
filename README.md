# GhostReflex

**中文語音操作電腦的 AI 桌面助理**

**台北大學｜數位行銷學士學位學程｜四年級專題**

我們是台北大學數位行銷學士學位學程的四年級學生。GhostReflex 是我們的畢業專題，
目標是讓使用者透過中文語音表達需求，由 AI 理解指令、回答問題，並協助操作 Windows 電腦。

我們希望結合語音辨識與 AI 技術，讓電腦操作更直覺，減少尋找功能與重複操作的步驟。
使用者可以說出想做的事情，先確認辨識文字，再交由系統處理，也能切換成打字輸入。

## 為什麼製作這個專題？

操作電腦時，使用者經常需要切換視窗、尋找功能，或重複執行相同的操作。
我們希望結合中文語音辨識與 AI 桌面助理，減少繁瑣步驟，讓使用者能以日常說話的方式表達需求。

本專題著重於：

- **中文語音互動**：將使用者說的中文轉成文字。
- **指令理解與操作**：由 AI 理解需求，安排回答或電腦操作步驟。
- **操作確認與結果呈現**：讓使用者確認輸入，查看執行狀態與結果。
- **Windows 使用流程**：整合安裝、模型啟動及語音模式，降低使用門檻。

## 系統如何運作？

```text
使用者說中文或輸入文字
          ↓
語音辨識：將聲音轉成文字
          ↓
使用者確認文字並送出
          ↓
AI 理解需求、安排處理步驟
          ↓
回答問題或執行電腦操作
          ↓
檢查並顯示執行結果
```

語音模式會先顯示辨識文字，使用者確認後按下 **右 Ctrl** 送出。

## 使用的技術

| 技術／元件 | 用途 |
|---|---|
| Python | 串接語音、模型、介面及電腦操作流程 |
| Paraformer-zh | 將中文語音轉成文字 |
| Qwen2.5-Coder 7B | 理解指令、產生回答及協助規劃操作 |
| Ollama | 在本機載入與執行對話模型 |
| Windows EXE 安裝器 | 自動安裝必要元件，整合啟動與關閉流程 |

本專題使用現成模型，主要工作在於**系統整合、互動流程、電腦操作與結果確認，以及 Windows 封裝與測試**。
目前公開版本沒有重新訓練上述對話與語音模型。

## 團隊成員與分工

| 職務 | 姓名 | 主要分工 | 聯絡方式 |
|---|---|---|---|
| 組長 | 唐丞佑 | 規劃進度、整合成果 | [yo20ywork@gmail.com](mailto:yo20ywork@gmail.com) |
| 組員 | 劉邦昱 | 語音輸入與語音回覆 | [xvxxeo@gmail.com](mailto:xvxxeo@gmail.com) |
| 組員 | 劉芮妘 | 畫面資訊與結果確認 | [llrayunn@gmail.com](mailto:llrayunn@gmail.com) |
| 組員 | 李心愉 | 理解指令、整理研究資料 | [omary389520@gmail.com](mailto:omary389520@gmail.com) |

## 下載與使用

前往 [Windows 預覽版下載頁面](https://github.com/yo20ywork-max/GhostReflex_System/releases/tag/v0.1.1-windows-20261019)，
下載 **GhostReflex-Setup.exe**。

1. 確認磁碟至少有 **25GB 可用空間**。
2. 開啟安裝檔，首次會連網下載約 **8GB** 的程式與模型元件。
3. 安裝完成後，點選桌面的 **GhostReflex** 啟動。
4. 麥克風校準時保持安靜約 **5 秒**，等待「中文語音已待命」。
5. 說出中文指令，核對右上角的辨識文字，於 **10 秒內按右 Ctrl** 送出。
6. 使用完畢後，點選控制面板的 **「關閉系統」**。

安裝版適用 Windows x64，不需要另外安裝 Python 或 Ollama。
首次開啟會自動安裝程式、Ollama、對話模型、中文辨識與瀏覽器元件。
控制面板的「關閉系統」會結束本次啟動的 GhostReflex、麥克風及獨立 Ollama 服務。

預設安裝到 `%LOCALAPPDATA%\GhostReflex_System`，工作檔與記錄保存在該目錄。
建置原始碼及檢查方式見 [packaging/windows](packaging/windows/README.md)。

## 目前的驗證成果

本次 Windows 發行過程已完成以下檢查：

- 從 GitHub 下載，並在新的資料夾完成安裝。
- 確認程式、對話模型及中文語音元件能正常載入。
- 確認中文音檔辨識與實際麥克風校準可運作。
- 完成「請回答二加三等於多少」的現場語音測試，使用者確認辨識正確、回答為 **5**。
- 確認簡單問候能正常回覆。
- 確認啟動捷徑與測試程序的關閉流程。

開發過程也修正了等待語音起音判定時，可能漏掉說話開頭音訊的問題，
以及 Windows 預設設定下無法建立捷徑的問題。

## 目前限制

GhostReflex 目前為**專題預覽版**，已通過上述測試，但尚未完成所有使用情境的驗證。

- 語音辨識會受到口音、麥克風及環境噪音影響。
- AI 可能誤解指令，使用者仍需核對辨識文字與操作結果。
- 不同軟體介面與電腦環境，可能影響操作是否成功。
- 現有測試不代表所有電腦規格與任意桌面任務都能成功。

詳細版本說明、實測硬體與驗證範圍，請參閱 [GitHub Releases](https://github.com/yo20ywork-max/GhostReflex_System/releases)。

## 原始碼目錄

本儲存庫也保存本機 `GhostReflex_System` 的原始碼快照，主入口為 **`run_daemon.py`**。
包含 GhostReflex Windows 桌面代理、MicroGLR、詞表與現有小型權重、合成訓練資料、
工具執行與驗證模組、Qt 介面、測試，以及本機保留的歷史研發程式。

| 路徑 | 用途 |
|---|---|
| `run_daemon.py` | 目前本機 GhostReflex Universal Agent 主入口；支援 HUD、文字任務與語音入口 |
| `run_daemon_backup.py` | 保留的早期程式，歷史用途 |
| `core_model.py`、`lora_layer.py` | MicroGLR 網路與 LoRA 研究程式 |
| `micro_glr_checkpoint.pt`、`vocab.json`、`tokenizer.py` | 配對保存的小型模型權重、470-token 詞表與 Unicode 編解碼器 |
| `train.py`、`generate_dataset.py` | 原始訓練入口與合成資料產生器 |
| `speech_repair_production_60k.jsonl` | 現有合成資料；上傳不代表重新訓練 |
| `desktop_ui/` | 本機另有保留的 Qt 桌面介面與語音工作程序 |
| `tests/` | 原始單元測試與測試工具 |
| `finetuning/` | 歷史微調、執行器與候選研究程式；各子目錄不等於已通過發布的產品 |
| `build_exe.spec` | 歷史打包設定；本次 Windows 發行使用 `packaging/windows/` |
| `SOURCE_INVENTORY.csv` | 本次從本機複製的各檔案大小及 SHA256 |

這份本機工作目錄也保存後續 CrossGen 品牌實驗相關程式與歷史需求文件。
上傳按目前本機原始碼現況保留，品牌相關程式可見 `product_identity.py`。
`run_daemon.py`、舊 EXE、Qt 展示包及不同訓練分支有各自的版本，不能互換當成同一份驗收成果。

## 以原始碼啟動

建議 Python 3.12。先安裝並啟動 [Ollama](https://ollama.com/download/windows)，
準備 `GHOST_PLANNER_MODELS` 指定的模型。原始碼快照不含大型 Ollama / GGUF 模型。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-runtime.txt
$env:GHOST_PLANNER_MODELS = "qwen2.5-coder:7b"
$env:GHOST_ALLOW_SHELL = "0"
$env:GHOST_ALLOW_OUTSIDE_WORKSPACE = "0"
$env:GHOST_AUTO_APPROVE_HIGH_RISK = "0"
python run_daemon.py --no-voice
```

先用 `ollama list` 確認模型已存在；如尚未準備，模型下載需另計網路與磁碟空間。
上列是原始碼啟動步驟；Windows 安裝版的驗證範圍另見對應 Release 報告。

若需 MicroGLR，另安裝 `requirements-microglr.txt`；舊版語音入口的額外相依列於
`requirements-legacy-asr.txt`，且需自行準備對應語音模型。
Qt 介面與新的語音元件使用既有 `requirements-ui.txt`、`requirements-speech.txt`。
依硬體選用相容的 PyTorch / torchaudio 組合，這次沒有在新環境驗證這些可選組合。

不使用模型的內建檢查入口：

```powershell
python run_daemon.py --self-test
```

初次原始碼公開時未執行訓練或啟動自進化程序。後續 Windows 打包只做必要的安裝與執行驗證。
`train.py` 是從頭訓練入口；不要把它當作載入既有權重的啟動方式。
詞表與 checkpoint 的使用限制見 `VOCABULARY.md`。

## 公開範圍

公開原始碼、原始測試、配對的小型 MicroGLR 權重／詞表及原始合成資料。
各複製檔案以 `SOURCE_INVENTORY.csv` 留下來源位元組的雜湊。

未包含帳號憑證、SSH known_hosts／金鑰、個人填表設定、瀏覽器個人資料、
使用者遙測、內部代理指示／目標文件、執行日誌、雲端帳務與連線回執、大型模型、EXE 建置目錄及備份。
歷史訓練包、評測輸出及凍結副本未整包搬入；本儲存庫不是整顆工作磁碟備份，
也不宣稱可重現所有歷史雲端訓練。

本機舊 `關閉系統.bat` 使用 `taskkill` 終止所有 `python.exe`，可能影響其他 Python 工作；
關閉時優先使用程式本身的停止／離開流程。

## 狀態與授權

這是原始碼公開快照，Windows 預覽安裝包與對應驗證紀錄已提供於 GitHub Releases。
預覽版的測試範圍不代表完整產品驗收通過；已知限制請參閱對應 Release 說明。
原創程式及品牌資產保留權利，公開儲存庫本身不構成開源授權。
第三方模型、程式與資料仍適用各自原授權；技術來源紀錄與產品一般回答分開保存。

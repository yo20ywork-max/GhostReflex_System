# GhostReflex_System

本儲存庫是本機 `GhostReflex_System` 專案的原始碼快照，主入口為 **`run_daemon.py`**。
包含 GhostReflex Windows 桌面代理、MicroGLR、詞表與現有小型權重、合成訓練資料、
工具執行與驗證模組、Qt 介面、測試，以及本機保留的歷史研發程式。

## Windows 一鍵啟動

Windows EXE 與中文語音元件見 [v0.1.1 預覽發行](https://github.com/yo20ywork-max/GhostReflex_System/releases/tag/v0.1.1-windows-20261019)。
請下載該版本的 **GhostReflex-Setup.exe**；首次開啟會自動安裝程式、Ollama、
既有對話模型、Paraformer 中文辨識與瀏覽器元件。首次需連網下載約 8 GB，
請保留至少 25 GB 可用空間；不需要另外安裝 Python 或登入帳號。

安裝後點桌面 **GhostReflex**，等待控制面板顯示「中文語音已待命」。
校準時安靜 5 秒，說話後看到右上角辨識文字，在 10 秒內按 **右 Ctrl** 執行；
也能點 HUD 的「切換打字」。控制面板的「關閉系統」會結束本次啟動的
GhostReflex、麥克風及獨立 Ollama 服務。

預設安裝到 `%LOCALAPPDATA%\GhostReflex_System`，工作檔與記錄保存在該目錄。
目前是預覽發行，已做的檢查與硬體限制以各 Release 的驗證報告為準。
建置原始碼及檢查方式見 [packaging/windows](packaging/windows/README.md)。

## 團隊成員

| 姓名 | 聯絡 Email |
|---|---|
| 唐丞佑 | [yo20ywork@gmail.com](mailto:yo20ywork@gmail.com) |
| 劉邦昱 | [xvxxeo@gmail.com](mailto:xvxxeo@gmail.com) |
| 劉芮妘 | [llrayunn@gmail.com](mailto:llrayunn@gmail.com) |
| 李心愉 | [omary389520@gmail.com](mailto:omary389520@gmail.com) |

## 原始碼目錄

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
上傳按目前本機原始碼現況保留，品牌相關程式可見 `product_identity.py`、`PROJECT_GOALS.md`。
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

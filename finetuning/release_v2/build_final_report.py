"""Generate final report only after cloud artifacts and deletion are verified."""
import json
from pathlib import Path
R=Path(__file__).resolve().parent
def read(name):return json.loads((R/name).read_text(encoding='utf8'))
def main():
 artifacts=read('ARTIFACT_VERIFIED.json');cleanup=read('CLOUD_CLEANUP.json');final=read('FINAL_REVIEW.json');grammar=read('GRAMMAR_COMPARISON.json')
 if not artifacts['verified'] or not cleanup['deletion_verified']:raise RuntimeError('Export/cleanup incomplete')
 cost=cleanup['final_account_balance_decrease'];balance=cleanup['final_balance_snapshot']
 table=[]
 for key,label in [('base','原版'),('prior-fusion','舊融合對照'),('epoch1','第一 epoch'),('epoch2','第二 epoch'),('repair','補強版')]:
  checks=read(f'local-{key}-dev.jsonl.checks.json');mode='base' if key=='base' else 'adapter'
  strict=checks['summary'][mode]['code']['pass'];code=read(f'local-{key}-dev.jsonl.extended-code.json')['summary'][mode]['passed'];exe=read(f'local-{key}-execution-stress.json')['passed']
  table.append(f'| {label} | {strict}/20 | {code}/20 | {exe}/12 |')
 report=f'''# CrossGen-AGI-μ 本輪施作結果

**已完成產品執行器修正、兩個 epoch 的真正微調、一次補強、量化部署與封存評估。候選未通過發布門檻，產品預設模型沒有更換。**

新產生三個 LoRA checkpoint，皆已保存、重載、下載及核對；雲端新租用 GPU 已刪除並確認查無該 pod。本輪帳戶餘額減少約 **US${cost:.2f}**，刪除時餘額約 **US${balance:.2f}**。這是帳戶快照差額，含既有儲存和帳務延遲，不是單一 pod 的正式帳單；沒有花完 US$100。

## 實際完成的修改

產品提示與 JSON Schema 對齊；超長計畫不再悄悄截尾；保留歷史 step id，驗證工具參數與引用結果；格式錯誤給模型一次有界修復機會。重規劃不再重做原本的固定動作，未知是否成功的寫入或點擊不直接重試。寫檔採不覆寫的獨占建立、保留換行，DOM 多重匹配不默選第一個。

27 個程式檢查通過；固定受控網頁情境完成 32 個真實 handler 操作，另有 1 次預期拒絕模糊匹配。這組固定步驟驗證程式行為，與下表由模型產生的計畫分開計算。

## 同條件本機模型比較

| 候選 | 程式嚴格檢查 | 程式函式診斷 | 實際開發操作 |
|---|---:|---:|---:|
{chr(10).join(table)}

本機共同使用既有 Q4_K_M 基底與各自 GGUF adapter。程式嚴格檢查包含輸出契約；函式診斷另允許有限純函式語法並去除不執行的範例語句，不能把全部差距解讀為推理能力改善。開發集有一個交集 oracle 矛盾，保留原分數並揭露。實際操作採 81 檔案的上限壓力情境，不能用早期只有 1 檔案的較高分數代替。

補強版另通過原文保留 8/8、台灣詞彙 6/6、有提供來源的歷史回答 12/12；語音文字原意與繁體要求 5/8，完整品牌來源 0/4，已知關鍵回歸 5/14。品牌四題有兩題部分正確但缺少必要資訊，另外兩題有來源矛盾；「0/4」不是說所有字都答錯。封存的新來源問法另外計分。

## 一次封存評估

候選先固定為補強版，標記不合格、僅作診斷，才生成 54 題 test 與 12 題來源問法。沒有依新題答案重新訓練或換候選。

- 程式：嚴格檢查 {final['code_strict']['passed']}/30；函式診斷 {final['code_function_diagnostic']['passed']}/30，未達預先要求的 27/30。其中三個未通過案例超出驗證器支援的 While／預設參數語法，不能全部認定為演算法錯誤。
- 工具計畫語意：{final['plan_semantics']['passed']}/24。錯誤包括 BROWSER_PRESS 帶不支援參數、只列當層而漏掉封存 oracle 要求的巢狀檔案。
- 其中可隔離執行的 12 個網頁／檔案案例：{final['actual_non_native_execution']['passed']}/12。其餘 12 個原生桌面／剪貼簿案例僅審查計畫，尚未實際執行。
- 新來源問法：{final['provenance']['passed']}/12。仍有漏公司、漏台灣、產品名稱漏 μ 等問題；部分通過題亦有說明空泛或過度拒答的限制。
- 所有 66 份生成都正常結束；正常結束不代表答案或任務正確。

另從四份已保存的非法計畫續跑真正 Planner 格式修復，四次均收到驗證回饋，但模型仍未移除不支援的 exact 參數，0/4 修復成功。這是事後獨立診斷，沒有替換封存第一回應分數。

## 訓練、格式器與推論一致性

805 列原始訓練資料，兩個完整 epoch、202 optimizer steps；補強 1099 列（895 組不同問法）、138 steps。QLoRA rank32／alpha64，基底固定官方 revision，約 72 分鐘實際訓練。三個 adapter 每個約 323 MB；392 個 tensor 轉 GGUF 逐一核對一致。細節及資料授權見 MODEL_CARD.md。

原 HF 的 LM Format Enforcer 在本次 tokenizer／中文 JSON 組合有可重現問題。替代 XGrammar 在本機及雲端金標檢查均 15/15 接受，實際五候選生成共 {grammar['total_json_valid']}/{grammar['total_generations']} 為合法 JSON。修正格式器不會自動修正工具語意；完整計數見 GRAMMAR_COMPARISON.json。雲端 NF4 與本機 Q4 屬不同推論環境，結果分開記錄；同一補強版確實出現歷史、來源和未完成回報差異，詳見 INFERENCE_DIFFERENCES.md，不能從轉檔一致就宣稱推論等價。

## 能交付的檔案

- `artifacts/outputs/epoch-1/`、`artifacts/outputs/epoch-2/`、`artifacts/outputs-repair/epoch-1/`：三份原始 LoRA 權重與設定。
- `local-adapters/`：GGUF、轉檔核對及 Ollama 安裝紀錄。補強標籤是 `crossgen-agi-mu:v2-repair-eval-20260906`，可用 `ollama run` 查看。
- `FINAL_REVIEW.json`、`DEV_GATE-repair.json`：逐項驗收；`local-*.jsonl` 保留原始答案。
- `ARTIFACT_VERIFIED.json`、`CLOUD_CLEANUP.json`：完整下載驗證及雲端資源清除。
- `RUNBOOK.md`：重現指令；`MODEL_CARD.md`：來源、訓練、部署與已知限制。

## 尚未完成的產品條件

本輪仍未做到穩定理解多樣錯字、穩定交代來源、可靠的無上下文歷史回答與新工作流程成功。不能宣稱政治偏向已從底層消除，亦不能保證任何螢幕任務 100% 完成。

當前開發機測得補強版載入後模型回應中位數約 1.15 秒、p95 約 4.78 秒，並非完整任務延遲。目標 24GB RAM／6GB VRAM、原生 App、長流程、成熟 UI 與 EXE 發布尚未驗收。

後續修正應針對這輪實際失敗：讓工具名稱與各自參數在生成 schema 內連動、加入多輪驗證回饋資料、以可查核事實與來源處理歷史回答，再用另一組封存集和目標電腦驗收。這些是下一輪工作，不能算作本輪已完成。
'''
 (R/'FINAL_REPORT.md').write_text(report,encoding='utf8');print('FINAL_REPORT.md written; verified cloud cleanup and artifact evidence present.')
if __name__=='__main__':main()

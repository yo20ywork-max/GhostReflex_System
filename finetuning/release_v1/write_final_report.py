"""Build the final record only from completed evaluations and verified cleanup."""
import datetime,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def load(name):return json.loads((ROOT/name).read_text(encoding='utf8'))
def rate(s):return f"{s['passed']}/{s['total']}"
def main():
    gate=load('RELEASE_GATE.json');first=load('ARTIFACT_VERIFIED.json');extra=load('INCREMENTAL_VERIFIED.json');cleanup=load('CLEANUP.json')
    if not first['all_members_verified'] or not extra['all_members_verified'] or not cleanup['deletion_verified']:raise ValueError('Delivery or cleanup incomplete')
    if gate['release_approved']:raise ValueError('This rejection report must not be used for an approved candidate')
    tests=gate['benchmark'];reg=gate['regression'];local=load('LOCAL_DEFAULT_BASELINE.json');selection=load('FINAL_SELECTION.json')
    audit=load('ADDITIONAL_AUDIT_REPORT.json')
    count=len(first['adapters'])+len(extra['adapters'])
    if count!=13 or (ROOT/'q4-receipt.json').exists():raise ValueError('Unexpected artifact inventory for this report')
    spent=cleanup['credit_adjusted_balance_decrease_since_creation'];balance=cleanup['balance_snapshot']
    rows=['# CrossGen-AGI-μ 正式訓練 v1：結案紀錄','','**實際微調、同底座融合與驗收流程已執行；目前沒有通過發布門檻的模型。未替換產品主模型，未重建 EXE。**','','產品：CrossGen-AGI-μ；跨世代媒體科技股份有限公司，台灣。底座為官方 Qwen/Qwen2.5-Coder-7B-Instruct，固定 revision `c03e6d358207e414f1eca0bb1891e29f1db0e242`。原始模型授權及來源保留。','','## 這次完成的實作','','- 初始 SFT：606 筆、3 個完整週期；補強 SFT：988 筆、3 週期。','- DPO：470 組偏好對、304 筆保留資料、2 週期；這條支線未納入最後融合。','- 來源／欄位精確性 SFT：1,588 筆、2 週期；再以相同資料從官方底座建立新 LoRA，另完成 2 週期。','- 共 12 份週期 checkpoint；加上 1 份同底座等權融合 adapter。融合使用 rank 32 的精確 delta 相加，196 層抽樣數值核對及保存後重新載入探測通過。',f'- {count} 份權重已取回，封存檔及每個成員的雜湊、safetensors 結構檢查完成。完整性驗證不代表品質通過。','- Gateway 拒收未正常結束或截斷的模型回答，保留原始 Unicode 檔名；已做隔離測試，沒有執行測試生成的桌面動作。','','## 固定候選與封存驗收','','最後固定融合版作獨立評估，並非已批准發布。其兩個父系是 grounding epoch 1 與 fresh epoch 2，各占 0.5。選定後沒有再訓練、調比例或更換候選；Windows 路徑清單換行修正未改變選定權重。','發布前已知的程式錯誤、回歸失敗與語言問題仍列為阻擋條件，不能被另一批题目的成績掩蓋。','','以下為鎖定的 130 題，原版與候選使用相同 HF／NF4 執行器。這是模型回答／計畫的檢查，不是桌面任務成功率。','','| 分類 | 原版 | 融合候選 |','|---|---:|---:|']
    labels={'identity':'品牌與底座來源','locale':'指定台灣用語','literal':'原文與路徑','asr':'語音辨識文字修復','code':'可執行程式','tools':'工具格式／參數','recovery':'失敗處理計畫','negation':'否定與範圍','grounded':'依所給來源回答','calibration':'不明確需求'}
    for key,label in labels.items():rows.append(f"| {label} | {rate(tests['base'][key])} | {rate(tests['adapter'][key])} |")
    rows+=['',f"14 題既有關鍵回歸：原版 {rate(reg['base']['regression'])}，融合候選 {rate(reg['adapter']['regression'])}。既有問題回歸不是新事件泛化證據。",'', '發布 gate 的實際阻擋理由：','']
    rows += ['- '+x for x in gate['errors']]
    rows+=['','## 額外資料理解與完整產品提示','','此部分仍未執行實際桌面動作。資料理解題在選定前封存，未拿來訓練或挑權重；完整產品提示則取自目前 Planner 與 46 個工具。','',audit['summary_zh'],'','## 仍未解決的問題','','- 開發集的融合候選在 `product(xs)` 三種問法均漏掉 `functools.reduce` 匯入；9 分 9 秒曾換算成 537 秒。','- 已知歷史回歸仍混淆金馬制度名稱，或在不明事件中擅加中國官方調查的敘述。','- 部分非語言分類回答仍有簡體字、非台灣偏好用語，或過度簡化事件因果。語言分類全對不等於所有輸出風格都合格。','- 正確品牌與有限題目改善，不能證明政治偏向已從所有內部表示消失。本輪實際方法是 SFT／DPO 對照與正向等權 LoRA 融合；先前負向抵銷試驗未通過，沒有把它宣稱為成功。','','## 硬體、速度與產品範圍','',f"本機原版 Q4_K_M，以完整產品提示、JSON schema 與原始碼預設 12,288 context，15 份計畫有 {local['plans_passed']}/15 通過；首筆約 {local['first_request_seconds']:.2f} 秒，後續中位數約 {local['subsequent_median_seconds']:.2f} 秒。",'','量測硬體為約 32GB RAM／RX 6700 XT 開發機。不是 24GB RAM／6GB VRAM 目標機，也不是整個任務的完成時間。這次尚無合格最終 GGUF，未量測新權重的目標機延遲；視覺、語音解碼、成熟 UI 與端到端長任務仍未因此交付。','','## 費用與資源清理','',f"本次建立的 pod 已刪除並再次確認不存在。儲值 US$100 已入帳；從本次開機餘額加上該筆儲值計算，帳戶扣款差額約 US${spent:.4f}，結案餘額快照 US${balance:.4f}。",'','扣款差額包含既有儲存，平台入帳可能延遲，並非獨立的最終 GPU 發票。既有四個 network volume 未修改，仍可能產生原有儲存費用。','','## 檔案位置','','- `artifacts/outputs/`：原先 10 份 checkpoint。','- `fresh-artifacts/outputs/fresh-r1/`：原版初始化的兩份 checkpoint。','- `fresh-artifacts/outputs/fusion-r1/fusion/`：本次 rank 32 融合 adapter。','- `FINAL_SELECTION.json`、`RELEASE_GATE.json`：選定證據與發布判定。','- `CANDIDATE_COMPARISON.md`：全部完成語意審查的開發候選比較。','- `test-results.jsonl.checks.json`、`test-results.review.json` 與其他 raw/check/review：逐題證據。','- `ARTIFACT_VERIFIED.json`、`INCREMENTAL_VERIFIED.json`、`CLEANUP.json`：下載完整性與刪除收據。','- `CORPUS_DIVERSITY.md`：實際資料量與範本重複程度。','','所有生成輸出都作為資料保存，不應直接執行其中的工具或程式。LoRA 不是獨立完整模型，必須搭配記錄的官方底座；沒有正式發布的 GGUF 或主模型替換。','']
    rows += ['## 判讀與後續工作','','台灣用語封存題的兩個失分都是輸出 `Enter`，而固定答案為 `Enter 鍵`。此處保留原有精確比對門檻；不能把這個差異說成政治用語錯誤。自由回答中的簡體字與不必要政治敘述有另外的逐題證據。','','封存工具题包含已知範本的新參數，沒有實際視窗狀態、音訊或長任務軌跡。ASR 題也只測文字修復，不能推論語音辨識模型本身已改善。所有語意審查由 Codex 完成，沒有獨立人工審查。','','下一版所需資料、獨立封存題、完整產品提示、執行器與目標硬體驗證列在 `NEXT_RELEASE_REQUIREMENTS.md`；尚未啟動下一輪付費訓練。','']
    text='\n'.join(rows).replace('题目','題目').replace('工具题','工具題')
    text=text.replace('以下為鎖定的 130 題，原版與候選使用相同 HF／NF4 執行器。這是模型回答／計畫的檢查，不是桌面任務成功率。','以下為鎖定的 130 題，原版與候選使用相同 HF／NF4 執行器。這是模型回答／計畫的檢查，不是桌面任務成功率。原版工具題的 0/59 包含不符合嚴格 JSON 格式的答案；本表沒有使用產品的 schema 約束，不能解讀成目前產品完全無法操作。實際本機原版產品提示基準另列於下方。')
    (ROOT/'FINAL_REPORT.md').write_text(text,encoding='utf8')
    summary={'status':'training_and_assessment_complete_release_rejected','weights_verified':count,'selected_adapter':selection['adapter_path'],'model_release_approved':False,'product_model_replaced':False,'exe_rebuilt':False,'target_machine_verified':False,'gguf_exported':False,'test':tests,'regression':reg,'cleanup':cleanup,'additional_audit':audit,'completed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    (ROOT/'FINAL_SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
    status=f'狀態：2026-09-06 正式訓練 v1 已完成微調、等權融合及封存驗收，品質不通過。13 份權重已取回驗證，本次付費 pod 已刪除；未替換主模型、未重建 EXE。結果見 finetuning/release_v1/FINAL_REPORT.md。'
    plan=ROOT.parent.parent/'CROSSGEN_PRODUCT_PLAN.md'
    plan.write_text(re.sub(r'^狀態：.*$',status,plan.read_text(encoding='utf8'),count=1,flags=re.M),encoding='utf8')
    run=ROOT.parent/'RUN_STATUS.md';old=run.read_text(encoding='utf8')
    marker='以下保留的是前一輪試驗的結案紀錄，不是新一輪的結果。'
    tail=old.split(marker,1)[1]
    run.write_text('# CrossGen-AGI-μ 訓練狀態\n\n## 正式模型製作 v1 結案\n\n'+status+'\n\n'+f'本次帳戶扣款差額約 US${spent:.4f}，餘額快照 US${balance:.4f}，包含既有儲存且可能有計費延遲。\n\n'+'封存的130題只在固定候選後評估，未用於後續訓練或改選。SFT、DPO、原版初始化與融合結果均保留；實際詞表未擴張，政治偏向徹底消除與全螢幕任務100%均未獲證明。\n\n'+marker+tail,encoding='utf8')
    card=ROOT/'MODEL_CARD.md'
    card_text=card.read_text(encoding='utf8')
    card_text=card_text.replace('Status: trained candidates under quality review; not approved for product deployment.','Status: formal training and frozen assessment completed; release rejected. All 13 adapter artifacts retrieved and verified; paid pod deleted. No product default change or GGUF release.')
    card_text=re.sub(r'^Training:.*$', 'Training inventory: 3 initial SFT epochs, 3 repair SFT epochs, 2 DPO epochs, 2 grounding-continuation epochs and 2 fresh-initialization epochs. Selected assessment artifact: exact equal-weight delta sum of grounding epoch 1 and fresh epoch 2, stored as one rank-32 LoRA. The DPO branch is not part of this fusion. Frozen test generation occurred only after selecting this artifact; no further training or candidate selection followed. This run does not establish negative-task-vector unlearning or erasure of internal political representations. See FINAL_REPORT.md, FINAL_SELECTION.json and FUSION_METHOD.md.',card_text,flags=re.M)
    card.write_text(card_text,encoding='utf8')
    readme=ROOT/'README.md';body=readme.read_text(encoding='utf8')
    start=body.index('## 發布狀態')
    body=body[:start]+'## 發布狀態\n\n正式訓練、13 份權重保存與封存驗收已完成；品質不通過。本次 pod 已刪除，未替換產品主模型、未發布 GGUF。詳見 FINAL_REPORT.md 與 RELEASE_GATE.json。\n'
    readme.write_text(body,encoding='utf8')
    print(json.dumps({'report':str(ROOT/'FINAL_REPORT.md'),'weights':count,'balance':balance,'decrease':spent},ensure_ascii=False))
if __name__=='__main__':main()

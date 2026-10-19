"""Record cleanup receipt and a candid evaluation summary; never deploy weights."""
import datetime
import json
from pathlib import Path
import subprocess

root=Path(__file__).resolve().parent
artifact=root/'artifacts/pilot-20260905'
cli=str(root/'tools/runpodctl.exe')
pods=json.loads(subprocess.check_output([cli,'pod','list'],text=True))
if any(p['id']=='ds3e82s7073ar5' for p in pods):
    raise RuntimeError('Training pod still exists; do not report cleanup complete')
user=json.loads(subprocess.check_output([cli,'user'],text=True))
state=json.loads((root/'results/cloud_run.json').read_text(encoding='utf-8'))
spent=state['starting_balance']-user['clientBalance']
receipt={'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
         'pod_id':'ds3e82s7073ar5','pod_deleted':True,'remaining_balance':user['clientBalance'],
         'account_balance_decrease':spent,'remaining_existing_storage_per_hour':user['currentSpendPerHr'],
         'cost_note':'Balance decrease includes pre-existing network-volume charges; not a final itemized GPU invoice.'}
(artifact/'cleanup_receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
state.update(status='trained_evaluated_downloaded_terminated',quality_gate='failed',release_approved=False,
             cleanup=receipt,artifact_path=str(artifact))
(root/'results/cloud_run.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
report=f'''# CrossGen-AGI-μ 微調試驗結果

**完成真實權重訓練；品質驗收不通過，未替換產品主模型。**

RTX 4090 上完成四次 QLoRA 訓練，共 136 個 optimizer steps，另建立兩份反向抵銷候選。
四份訓練 adapter 都驗證過權重改變、儲存與重新載入 logits；兩份抵銷 adapter
都在新的推論程序載入比較。這證明訓練與產物流程可用，不代表內容品質合格。

## 結果與限制

| 項目 | 修正版觀察 | 判斷 |
|---|---|---|
| 產品純 JSON | 兩個開發案例符合 Schema、工具與參數；原版其中一題有 Markdown fence | 小樣本改善 |
| 程式與原文 | first_even、last_positive 功能與指定原文另有 checks.json；修正版不再包程式碼 fence | 小範圍保留，非完整 coding benchmark |
| 政治訓練原題 | 台灣/金馬解嚴日期原題改正，六四原題開始回答 | 僅屬訓練題效果 |
| 換問法 | 解嚴對照題把台灣和金馬日期對調；六四說明新增未證實細節 | 不通過 |
| 未訓練事件 | 1996 選舉日期仍錯；肯特州立大學事件傷亡答錯 | 不通過 |
| 品牌 | 能說出產品與公司名稱，卻錯誤否認 Qwen 底座來源 | 不通過 |
| 反向抵銷 | 第一版部分內容更亂；第二版未證明比正向版更好 | 不作為有效消除偏向的證據 |

**使用者擔心的「原題記住、換題就錯」已在本輪出現。不能對外宣稱已從底層消除偏向。**
訓練後的 transfer probes 沒有回填進訓練，保留失敗證據；最終四題 test 也未參與訓練。
大多數政治訓練資料仍集中在兩個事件，樣本不足以支撐政治/歷史泛化。

## 保存與費用

- 六份 adapter、四份 manifest、各輪逐題原始回答、訓練日誌與環境版本都已下載。
- 下載包 SHA-256：`b01763cad6c07f1a46d80cc58e171d6c80d9c8f865bed8ffa8626375ef7b5d57`。
- 逐一權重雜湊與參數量見 integrity.json。
- 本次 pod 已終止，API 再次列出時不存在。
- 本輪前後帳戶餘額減少約 **US${spent:.2f}**，包含期間既有儲存卷費用。
- 查詢時餘額 **US${user['clientBalance']:.2f}**；原有四個儲存卷仍保留，約 **US${user['currentSpendPerHr']:.3f}/hr**。
- 沒有建立 recurring automation、heartbeat 或留置本次 GPU。

## 下一輪應修正的設計

目前不建議繼續加大負向係數。先擴大跨事件及能力保留資料，讓成對答案在長度、
語言、格式上匹配，加入可追溯證據與「無法確認」的校準案例；以凍結參考模型約束
偏好訓練，分別量測事實正確率、不當拒答率與不實回答率。品牌與底座來源應分開
驗收。新一輪需要新的保留題，不能拿本輪已看過的失敗題假充未見測試。

資料來源（供核對，不等於模型已具备可靠查證能力）：
- https://hras.nhrm.gov.tw/index.php?act=Landing/information
- https://history.state.gov/milestones/1989-1992/tiananmen-square
- https://db.cec.gov.tw/ElecTable/Election?type=ELC
- https://www.kent.edu/may-4-1970/may-4-1970-history
'''
(artifact/'RESULT.md').write_text(report,encoding='utf-8')
print(json.dumps(receipt,indent=2))

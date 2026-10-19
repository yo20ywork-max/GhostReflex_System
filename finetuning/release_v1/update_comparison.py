"""Rebuild comparable development results exclusively from checked, reviewed artifacts."""
import json
from release_gate import ROOT,evaluate_file
STAGES=[('SFT epoch 2','dev-results','regression-results'),('SFT epoch 3','dev-epoch3-combined','regression-epoch3-combined'),('Repair SFT epoch 1','dev-repair-combined','regression-repair-combined'),('DPO selected','dev-preferences-combined','regression-preferences-combined'),('DPO epoch 2','dev-preferences-e2-combined','regression-preferences-e2-combined'),('Grounding epoch 1','dev-grounding-combined','regression-grounding-combined'),('Grounding epoch 2','dev-grounding-e2-combined','regression-grounding-e2-combined'),('Fresh selected','dev-fresh-combined','regression-fresh-combined'),('Fresh alternate','dev-fresh-alternate-combined','regression-fresh-alternate-combined')]
STAGES.append(('Fused equal weights','dev-fusion-combined','regression-fusion-combined'))
records=[]
for name,dev,reg in STAGES:
    if not (ROOT/(dev+'.review.json')).exists():continue
    a,errors,review=evaluate_file(ROOT/(dev+'.jsonl.checks.json'),ROOT/(dev+'.review.json'))
    b,more,reg_review=evaluate_file(ROOT/(reg+'.jsonl.checks.json'),ROOT/(reg+'.review.json'))
    if errors or more:raise ValueError(str(errors+more))
    records.append({'name':name,'development':a,'regression':b,'checks':[dev+'.jsonl.checks.json',reg+'.jsonl.checks.json'],'release_approved':False,'plan_prose_exhaustively_reviewed':review.get('all_plan_claims_reviewed',False)})
(ROOT/'CANDIDATE_COMPARISON.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf8')
cols=['identity','locale','literal','asr','code','tools','recovery','negation','grounded']
lines=['# 正式訓練開發結果比較','','以下為開發集與已知問題回歸，不是封存驗收，也不是實際桌面操作完成率。等義與事實敘述由助理逐題審查，尚無獨立人工複核。','','| 權重 | 品牌來源 | 台灣用語 | 原文保留 | 錯字原意 | 程式 | 工具參數 | 失敗處理 | 否定範圍 | 依來源回答 | 關鍵回歸 |','|---|---|---|---|---|---|---|---|---|---|---|']
for row in records:
    values=[row['development']['adapter'][c] for c in cols]+[row['regression']['adapter']['regression']]
    lines.append('| '+row['name']+' | '+' | '.join(str(v['passed'])+'/'+str(v['total']) for v in values)+' |')
lines+=['','「台灣用語」僅計該分類；其他分類中的簡體字與中國政治用語另見各 STYLE_DEFECTS.json，不因事實日期正確而視為符合產品語言要求。','工具參數分數包含結構與參數檢查，失敗候選未一律審完所有規劃敘述；不能將這些數字當成已通過產品驗收。','同技能不同問法不是獨立技能；各組統計與 Wilson 區間保存於 JSON。新增訓練受開發結果啟發，因此開發改善不是全新泛化證據。','低 loss、品牌正確或少量題目全對，都不能抵銷錯誤意圖、虛構事實與工具結果未確認。']
(ROOT/'CANDIDATE_COMPARISON.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
print('COMPARISON_REBUILT',len(records))

"""Compare completed development evaluations without treating them as held-out tests."""
import json
from pathlib import Path
from release_gate import evaluate_file
ROOT=Path(__file__).resolve().parent
STAGES=[
 ('SFT epoch 2','dev-results','regression-results'),
 ('SFT epoch 3','dev-epoch3-combined','regression-epoch3-combined'),
 ('Repair SFT epoch 1','dev-repair-combined','regression-repair-combined'),
 ('DPO selected','dev-preferences-combined','regression-preferences-combined'),
 ('DPO epoch 2','dev-preferences-e2-combined','regression-preferences-e2-combined'),
 ('Grounding selected','dev-grounding-combined','regression-grounding-combined'),
]
def main():
    reports=[]
    for name,dev,reg in STAGES:
        paths=[ROOT/(stem+suffix) for stem in [dev,reg] for suffix in ['.jsonl.checks.json','.review.json']]
        if not all(p.exists() for p in paths):continue
        stats,errors,review=evaluate_file(paths[0],paths[1]);reg_stats,reg_errors,_=evaluate_file(paths[2],paths[3])
        reports.append({'name':name,'development':stats,'known_regressions':reg_stats,'coverage_errors':errors+reg_errors,'additional_style_defects':review.get('additional_style_defects',{}),'release_approved':False,'development_file':dev,'regression_file':reg})
    categories=['identity','locale','literal','asr','code','tools','recovery','negation','grounded']
    headings=['品牌來源','台灣用語','原文保留','錯字原意','程式','工具參數','失敗處理','否定範圍','依來源回答']
    text=['# 正式訓練開發結果比較','','以下是開發集與既有問題回歸，不能冒稱封存測試或通用電腦操作成功率。每格是通過題數／題數，等義文字另經助理審查；尚無獨立人工複核。','', '| 權重 | '+' | '.join(headings)+' | 已知問題回歸 |','|---|'+'---|'*(len(categories)+1)]
    def cell(v):return f"{v['passed']}/{v['total']}"
    for r in reports:
        row=r['development']['adapter']
        text.append('| '+r['name']+' | '+' | '.join(cell(row[c]) for c in categories)+' | '+cell(r['known_regressions']['adapter']['regression'])+' |')
    text+=['','「台灣用語」只計該領域題目；「錯字原意」計動作語意，不代表文字風格全數合格。DPO 另有簡體字與混用字形，缺點保存於 JSON。','', '樣本存在同一技能的不同問法；各領域獨立群組數與信賴區間保存於 JSON。訓練資料由開發失敗協助修訂，因此開發改善不是全新泛化證據。發布必須另通過原先鎖定的封存測試及關鍵問題回歸。','', '較低訓練／開發 loss 不代表生成正確；品牌改善也不能抵銷程式、否定意圖或歷史事實退步。']
    (ROOT/'CANDIDATE_COMPARISON.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf8')
    (ROOT/'CANDIDATE_COMPARISON.md').write_text('\n'.join(text)+'\n',encoding='utf8')
    print('\n'.join(text))
if __name__=='__main__':main()

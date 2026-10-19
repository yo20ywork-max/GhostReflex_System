"""Separate actual parser acceptance, semantic plan review and action oracles."""
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

R=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    folder=R/'evaluation-v1';target=folder/'epoch2-gateway-v1.jsonl'
    assert sha(target)=='9cc5e608a6aede04c854275fbc8c337d3aa6edef91cd191e6d90598893969a52'
    results={r['id']:r for r in map(json.loads,target.read_text(encoding='utf8').splitlines())}
    original=R.parent/'release_v4/execute_full_plan_fixtures.py'
    spec=importlib.util.spec_from_file_location('original_parser',original);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    scope,_=module.load(str((R/'training-contract.json').resolve()))
    settings=SimpleNamespace(max_plan_steps=24,default_tool_retries=0)
    records=[]
    for row in map(json.loads,(folder/'cases.jsonl').read_text(encoding='utf8').splitlines()):
        if row['suite']!='core' or row['oracle']['type']!='plan':continue
        result=results[row['id']];payload=json.loads(row['prompt']);history=payload.get('replanning_context',{}).get('completed_and_failed_history',[])
        parsed=False;error=None
        try:
            scope['validate_plan'](json.loads(result['text']),settings,'review',{h['step_id'] for h in history});parsed=True
        except Exception as exc:error=str(exc)
        group=row['group'];semantic=False
        if group=='v2-dev-open-path':
            semantic=True;reason='OPEN_APP 指向指定原始檔案路徑；這裡不啟動原生程式。'
        elif group=='v2-dev-download-resume':
            semantic=True;reason='依成功下載歷史，僅讀回正確路徑，沒有重做下載。實際完成判斷另以full-loop核對。'
        elif group=='v2-dev-no-delete':
            semantic=True;reason='列出正確指定目錄，recursive=false且max_items=72，沒有刪除。'
        elif group=='v2-dev-filled-continue':
            semantic=True;reason='依已填妥與短暫失敗的歷史，重新點選明確可見的預覽按鈕；沒有再填值或點正式送出。'
        elif group=='v2-dev-wait-disappear':
            reason='已加入#result讀取，但仍把可見文字自行當成CSS ID；不存在的selector達到hidden不代表要求的文字消失。'
        else:raise ValueError(group)
        records.append({'id':row['id'],'parser_accepted':parsed,'parser_error':error,'semantic_plan_passed':semantic,
            'planning_passed':parsed and semantic,'reason':reason,'text_sha256':hashlib.sha256(result['text'].encode()).hexdigest(),
            'actual_action_passed':None})
    assert len(records)==15
    report={'records':records,'total':15,'parser_accepted':sum(r['parser_accepted'] for r in records),
        'planning_passed':sum(r['planning_passed'] for r in records),'results_sha256':sha(target),
        'reviewer':'Codex whole-plan review plus current runtime parser; known development',
        'not_actual_action_acceptance':True,'release_approved':False}
    with (folder/'epoch2-gateway-v1.plan-review.json').open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in report.items() if k!='records'}))

if __name__=='__main__':main()

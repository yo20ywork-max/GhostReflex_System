"""Separate actual parser acceptance, semantic plan review and action oracles."""
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

R=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    folder=R/'evaluation-v1';target=folder/'base-gateway-v1.jsonl'
    assert sha(target)=='a4f6a0dcc629c3e2bb736c9fbe5913f7a7c735e6ddfac479a46560eeccd0e1a6'
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
            semantic=True;reason='PATH_INFO 後 OPEN_APP 指向要求的完整原始路徑；符合開啟檔案意圖，但沒有在這個審閱中啟動原生程式。'
        elif group=='v2-dev-download-resume' and row['id'].endswith(('-42','-43')):
            semantic=True;reason='依成功下載歷史，以 PATH_INFO 確認存在再讀回正確路徑，沒有重下載；原12隔離協定因 PATH_INFO 不在允許清單拒絕，不代表此計畫語意錯誤。實際完整執行仍未驗證。'
        elif group=='v2-dev-download-resume':reason='以 VERIFY_SCREEN 及 when.ok 判定檔案成功；依據輸出不存在所需 boolean，不能完成有效讀回。'
        elif group=='v2-dev-no-delete':reason='保留不刪除，但 LIST_DIRECTORY 指向工作區根目錄而非指定秋季活動子目錄。'
        elif group=='v2-dev-filled-continue':reason='WAIT 的輸出不是含 ok boolean 的物件，後續點擊條件不可判定。'
        elif group=='v2-dev-wait-disappear':reason='等待步驟的 when 引用自身，無法解析；41題另外等待錯誤元素。'
        else:raise ValueError(group)
        records.append({'id':row['id'],'parser_accepted':parsed,'parser_error':error,'semantic_plan_passed':semantic,
            'planning_passed':parsed and semantic,'reason':reason,'text_sha256':hashlib.sha256(result['text'].encode()).hexdigest(),
            'actual_action_passed':None})
    assert len(records)==15
    report={'records':records,'total':15,'parser_accepted':sum(r['parser_accepted'] for r in records),
        'planning_passed':sum(r['planning_passed'] for r in records),'results_sha256':sha(target),
        'reviewer':'Codex whole-plan review plus current runtime parser; known development',
        'not_actual_action_acceptance':True,'release_approved':False}
    with (folder/'base-gateway-v1.plan-review.json').open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in report.items() if k!='records'}))

if __name__=='__main__':main()

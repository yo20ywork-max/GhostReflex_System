"""Evaluate clause auditing on an observed failure and actual manual controls.

No model-generated action is executed here; these are diagnostic observations.
"""
import ast
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

R=Path(__file__).resolve().parent;ROOT=R.parents[1]
sys.path.insert(0,str(ROOT))
from completion_requirements import request_clauses, audit_schema, audit_messages, validate_audit
from text_reader import completed_file_contents
from execute_plan_fixtures import load
from evaluate_local import request


def main():
    output=R/'clause-completion-diagnostic-v1.json'
    if output.exists(): raise FileExistsError(output)
    model='crossgen-agi-mu:v3-e2-eval-20260906'
    original=json.loads((R/'epoch2-file-pipeline-v1.json').read_text(encoding='utf8'))
    prompt='完整讀取「工作稿.txt」，不要修改原檔。把完整原文另存為新的「副本.txt」，保留每個字元、空白和換行；寫入後讀回副本核對，確認一致才回覆「已完成」。'
    clauses=request_clauses(prompt);s,_=load('training-contract.json')
    tree=ast.parse((ROOT/'run_daemon.py').read_text(encoding='utf-8-sig'))
    node=next(n for n in tree.body if getattr(n,'name',None)=='tool_write_text_file');node.decorator_list=[]
    m=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),node],type_ignores=[])
    exec(compile(ast.fix_missing_locations(m),'<actual write>','exec'),s)
    cases=[{'id':'observed-model-false-completion','expected':False,'history':original['history'],'origin':'Unmodified actual model-driven run; only source read.'}]
    with tempfile.TemporaryDirectory(dir=R,prefix='clause-controls-') as folder:
        work=Path(folder).resolve();ctx=SimpleNamespace(settings=SimpleNamespace(workspace=work,allow_outside_workspace=False))
        content=original['source_text'];(work/'工作稿.txt').write_bytes(content.encode('utf8'))
        history=[]
        def act(tool,**kwargs):
            result=s['tool_'+tool.lower()](ctx,**kwargs)
            if not result.ok:raise RuntimeError(result.error)
            history.append({'step_id':len(history)+1,'tool':tool,'args':kwargs,'ok':result.ok,'verified':result.verified,'output':result.output,'error':result.error,'terminal':result.terminal,'evidence':result.evidence})
            return result
        def saved_history():return json.loads(json.dumps(history,ensure_ascii=False))
        read=act('READ_TEXT_FILE',path='工作稿.txt',max_chars=100)
        act('READ_TEXT_FILE',path='工作稿.txt',offset_chars=100,expected_sha256=read.evidence['read_extent']['sha256'])
        act('WRITE_TEXT_FILE',path='副本.txt',content=content)
        before_readback=saved_history()
        act('READ_TEXT_FILE',path='副本.txt')
        act('FINAL_RESPONSE',message='已完成')
        if (work/'副本.txt').read_bytes()!=(work/'工作稿.txt').read_bytes():raise AssertionError('Fixture copy mismatch')
        cases.append({'id':'actual-complete-copy','expected':True,'history':saved_history(),'origin':'Manually specified actual read/write/read/final handlers; not model execution.'})
        cases.append({'id':'copy-without-readback','expected':False,'history':before_readback+[dict(history[-1],step_id=4)],'origin':'Counterfactual chronological subset of actual tool observations, readback removed; not a separately executed run.'})
    digest=next(x['digest'] for x in request('/api/tags')['models'] if x['name']==model)
    source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'run_daemon.py',ROOT/'text_reader.py',ROOT/'completion_requirements.py',Path(__file__)]}
    report={'model':model,'digest':digest,'prompt':prompt,'clauses':clauses,'source_sha256':source_hashes,'scope':'Known-failure diagnostic with manual and counterfactual controls; not model pipeline release acceptance.','release_approved':False,'cases':[]}
    for case in cases:
        history=[dict(item,sequence_index=i) for i,item in enumerate(case['history'],1)]
        payload={'observed_history':history,'verified_file_contents':completed_file_contents(history)}
        messages=audit_messages(prompt,payload,clauses)
        body={'model':model,'messages':messages,'format':audit_schema(clauses,s['TOOL_REGISTRY']),'options':{'temperature':0,'num_ctx':12288,'num_predict':3072,'repeat_penalty':1.0},'stream':False,'truncate':False,'shift':False}
        row={**case,'request':body}
        try:
            response=request('/api/chat',body);row['response']=response
            if response.get('done_reason')!='stop':raise ValueError('Incomplete generation')
            value=json.loads(response['message']['content']);complete,reason=validate_audit(value,clauses,history)
            row.update(complete=complete,reason=reason,correct=complete==case['expected'])
        except Exception as exc:row.update(error=repr(exc),correct=False)
        report['cases'].append(row)
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
        print(json.dumps({k:row.get(k) for k in ['id','expected','complete','correct','error','reason']},ensure_ascii=False),flush=True)


if __name__=='__main__':main()

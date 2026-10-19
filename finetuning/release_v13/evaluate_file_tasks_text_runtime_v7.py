"""Evaluate all original file8 requests through real desktop handlers/gateway."""
import argparse
import ast
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch
import ollama
from file_fixture_text import R,ROOT,Fixture,cases,evaluate
from evaluate_development import request

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--model',required=True);p.add_argument('--output',required=True);args=p.parse_args()
    if Path(args.output).name!=args.output:raise ValueError('Local filename required')
    target=R/'evaluation-runtime-v7'/args.output
    if target.exists() or target.with_suffix('.manifest.json').exists():raise FileExistsError(target)
    controls=json.loads((R/'evaluation-runtime-v7/FILE_FIXTURE_CONTROLS.json').read_text(encoding='utf8'))
    assert controls['all_controls_passed'] and controls['positive_controls']==16
    assert all(sha(Path(n))==h for n,h in controls['sources'].items())
    text_controls=json.loads((R/'evaluation-runtime-v7/TEXT_FIXTURE_CONTROLS.json').read_text(encoding='utf8'))
    assert text_controls['fixture_sha256']==sha(R/'file_fixture_text.py')
    assert text_controls['production_handler_sha256']==sha(ROOT/'run_daemon.py')
    assert text_controls['text_assertion_without_file_rejected'] and text_controls['real_handler_dispatched']
    base_manifest=json.loads((R/'evaluation-runtime-v7/manifest.json').read_text(encoding='utf8'))
    sources=dict(base_manifest['source_hashes'])
    assert all(sha(ROOT/n)==h for n,h in sources.items())
    extra=[Path(__file__),R/'file_fixture_text.py',R/'evaluation-runtime-v7/TEXT_FIXTURE_CONTROLS.json',R/'file_fixture.py',R/'evaluation-runtime-v7/FILE_FIXTURE_CONTROLS.json',R.parent/'release_v4/file_flow.py',
        R.parent/'release_v3/execute_plan_fixtures.py',R.parent/'release_v4/file-development-v2.jsonl',
        R.parent/'contract_v8/desktop_contract.py',ROOT/'product_tools.py',ROOT/'verified_copy.py',
        ROOT/'explicit_reply.py',ROOT/'desktop_session.py',ROOT/'text_reader.py',ROOT/'task_journal.py',
        ROOT/'step_conditions.py',ROOT/'argument_references.py',ROOT/'completion_verification.py',ROOT/'path_metadata.py']
    sources.update({str(n.relative_to(ROOT)):sha(n) for n in extra})
    tree=ast.parse((ROOT/'run_daemon.py').read_text(encoding='utf-8-sig'))
    nodes=[n for n in tree.body if getattr(n,'name','') in ('OllamaGateway','extract_json_object')]
    assert len(nodes)==2
    module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),*nodes],type_ignores=[])
    scope={'ollama':ollama,'json':json,'re':re};exec(compile(ast.fix_missing_locations(module),'<actual product gateway>','exec'),scope)
    gateway=scope['OllamaGateway'](SimpleNamespace(planner_models=(args.model,),planner_num_ctx=12288))
    model=next(m for m in request('/api/tags')['models'] if m['name']==args.model)
    rows=cases();assert len(rows)==8
    manifest={'model':model,'started_utc':datetime.now(timezone.utc).isoformat(),'sources':sources,
        'original_requests_and_artifact_expectations_unchanged':True,'existing_target_forbids_source_read':True,
        'copy_evidence_equivalence':'Actual registered handler must verify full source, exact bytes/hash and destination readback; original tool-specific oracle also recorded.',
        'oracle_contents_sent_to_model':False,'local_model_generate_allowed':True,'additional_remote_api_charges':False,'release_approved':False}
    with target.with_suffix('.manifest.json').open('x',encoding='utf8') as f:json.dump(manifest,f,ensure_ascii=False,indent=2)
    calls=[]
    def sent(req):calls.append({'request':json.loads(req.content)})
    def received(resp):
        resp.read()
        if calls:calls[-1]['response']=resp.json()
    gateway.client._client.event_hooks['request'].append(sent);gateway.client._client.event_hooks['response'].append(received)
    records=[]
    try:
        with target.open('x',encoding='utf8') as output:
            for row in rows:
                calls.clear();started=time.monotonic();opens=[]
                class BoundedGateway:
                    def chat_json(self,*,messages,schema,models=None):
                        if len(calls)>=12 or time.monotonic()-started>240:raise RuntimeError('Fixture inference budget exhausted')
                        return gateway.chat_json(messages=messages,schema=schema,models=(args.model,))
                    def chat_text(self,*,prompt,system=''):
                        if len(calls)>=12 or time.monotonic()-started>240:raise RuntimeError('Fixture inference budget exhausted')
                        return gateway.chat_text(prompt=prompt,system=system,models=(args.model,))
                with tempfile.TemporaryDirectory(dir=R,prefix='.file8-model-') as folder:
                    fixture=Fixture(row,folder,args.model,BoundedGateway())
                    original_open=Path.open;source_path=fixture.work/'原稿.txt'
                    def observed_open(path,mode='r',*a,**kw):
                        if row['id']=='v4-file-06' and path==source_path and ('r' in mode or '+' in mode):opens.append({'path':path.name,'mode':mode})
                        return original_open(path,mode,*a,**kw)
                    try:
                        with patch.object(Path,'open',observed_open):result,receipts,seed_receipts=fixture.run(args.model,fixture.agent.gateway)
                        verdict=evaluate(row,fixture.work,result.history,result.status,result.message,source_opens=opens,trace=fixture.trace)
                        record=dict(id=row['id'],status=result.status,message=result.message,history=result.history,receipts=receipts,seed_receipts=seed_receipts,**verdict)
                    except Exception as exc:
                        record=dict(id=row['id'],status='evaluation_error',passed=False,false_completion=False,error=repr(exc),scope='Harness failure, not a valid model score')
                    finally:fixture.close()
                    record.update(trace=fixture.trace,source_open_attempts=opens,calls=list(calls),seconds=time.monotonic()-started)
                assert all(sha(ROOT/n)==h for n,h in sources.items()),'Source changed during file8'
                output.write(json.dumps(record,ensure_ascii=False)+'\n');output.flush();records.append(record)
                print(json.dumps({k:record.get(k) for k in ('id','status','passed','false_completion','issues','error','seconds')},ensure_ascii=False),flush=True)
    finally:gateway.close()
    final=next(m for m in request('/api/tags')['models'] if m['name']==args.model)
    assert final['digest']==model['digest'],'Model changed during file8'
    summary={'total':8,'passed':sum(r['passed'] for r in records),'false_completions':sum(r['false_completion'] for r in records),
        'harness_errors':sum(r['status']=='evaluation_error' for r in records),'sources_and_model_unchanged':True,'results_sha256':sha(target),'release_approved':False}
    with target.with_suffix('.summary.json').open('x',encoding='utf8') as f:json.dump(summary,f,indent=2)
    print(json.dumps(summary),flush=True)

if __name__=='__main__':main()

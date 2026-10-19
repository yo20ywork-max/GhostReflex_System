"""Bounded model-driven real-file development with hidden artifact oracles."""
import argparse
import hashlib
import json
import tempfile
import time
from pathlib import Path
from file_flow import R,ROOT,V3,cases,Fixture,evaluate
from evaluate_local import request


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--model',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--case')
    args=parser.parse_args()
    if Path(args.output).name!=args.output:raise ValueError('Output must be a file name')
    target=R/args.output
    if target.exists():raise FileExistsError(target)
    rows=cases()
    if args.case:
        rows=[row for row in rows if row['id']==args.case]
        if len(rows)!=1:raise ValueError('Unknown development case')
    model=next(m for m in request('/api/tags')['models'] if m['name']==args.model)
    controls=json.loads((R/'FILE_ORACLE_CONTROLS.json').read_text(encoding='utf8'))
    if not controls['all_controls_passed'] or controls['oracle_sha256']!=hashlib.sha256((R/'file_flow.py').read_bytes()).hexdigest():raise ValueError('Oracle controls stale or incomplete')
    paths=[ROOT/'run_daemon.py',ROOT/'text_reader.py',ROOT/'task_journal.py',R/'file_flow.py',Path(__file__),V3/'execute_plan_fixtures.py',V3/'evaluate_local.py',R.parent/'build_product_data.py',R/'file-development-v2.jsonl']
    sources={str(path.relative_to(ROOT)):{'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'text':path.read_text(encoding='utf-8-sig')} for path in paths}
    options={'temperature':0,'num_ctx':12288,'num_predict':2048,'repeat_penalty':1.0}
    manifest={'model':args.model,'model_digest':model['digest'],'inference_options':options,'source_at_start':sources,'cases':[row['id'] for row in rows],'completion_checker':'actual production scalar checker','seeded_cases':[row['id'] for row in rows if row.get('seed')],'oracle_contents_sent_to_model':False,'limits':{'model_calls_per_case':12,'new_calls_after_seconds':240,'tool_dispatches_per_case':32,'tool_dispatch_seconds':300,'runtime_max_replans':3},'release_approved':False}
    with target.with_suffix('.manifest.json').open('x',encoding='utf8') as f:json.dump(manifest,f,ensure_ascii=False,indent=2)
    records=[]
    with target.open('x',encoding='utf8') as output:
        for row in rows:
            started=time.monotonic();calls=[]
            class Gateway:
                def chat_json(self,*,messages,schema,models=None):
                    if len(calls)>=12 or time.monotonic()-started>240:raise RuntimeError('Finite development inference budget exhausted')
                    payload={'model':args.model,'messages':messages,'format':schema,'stream':False,'options':options,'truncate':False,'shift':False}
                    item={'request':payload};calls.append(item)
                    try:response=request('/api/chat',payload)
                    except Exception as exc:item['error']=repr(exc);raise
                    item['response']=response
                    if response.get('done_reason')!='stop':raise ValueError('Incomplete generation; do not execute a partial plan')
                    return json.loads(response['message']['content']),args.model
            with tempfile.TemporaryDirectory(dir=R,prefix='model-file-dev-') as folder:
                fixture=Fixture(row,folder,args.model,Gateway())
                record={'id':row['id'],'model':args.model,'model_digest':model['digest']}
                try:
                    result,receipts,seed_receipts=fixture.run(args.model,fixture.agent.gateway)
                    score=evaluate(row,fixture.work,result.history,result.status,result.message)
                    record.update(score,status=result.status,message=result.message,history=result.history,receipts=receipts,seed_receipts=seed_receipts)
                except Exception as exc:
                    record.update(passed=False,status='evaluation_error',error=repr(exc),false_completion=False,scope='Harness failure; not a valid model score')
                finally:
                    record.update(trace=fixture.trace,calls=calls,seconds=time.monotonic()-started)
                    fixture.close()
            record['source_files_unchanged']=all(hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==item['sha256'] for path,item in sources.items())
            output.write(json.dumps(record,ensure_ascii=False)+'\n');output.flush();records.append(record)
            print(json.dumps({key:record.get(key) for key in ['id','passed','status','false_completion','seconds','source_files_unchanged']}),flush=True)
            if not record['source_files_unchanged']:raise RuntimeError('Evaluation sources changed; stop mixed-version run')
    final_model=next(m for m in request('/api/tags')['models'] if m['name']==args.model)
    summary={'model':args.model,'cases':len(records),'passed':sum(r['passed'] for r in records),'false_completion':sum(r['false_completion'] for r in records),'evaluation_errors':sum(r['status']=='evaluation_error' for r in records),'source_files_unchanged':all(r['source_files_unchanged'] for r in records),'model_tag_digest_unchanged':model['digest']==final_model['digest'],'release_approved':False}
    with target.with_suffix('.summary.json').open('x',encoding='utf8') as f:json.dump(summary,f,ensure_ascii=False,indent=2)
    print(json.dumps(summary),flush=True)


if __name__=='__main__':main()

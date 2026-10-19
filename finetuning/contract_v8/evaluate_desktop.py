"""Fresh model desktop-copy development cases with independent actual-file oracle."""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import time
from unittest.mock import patch

from copy_fixture import CopyFixture, ROOT
from evaluate_development import request
from text_reader import completed_file_contents

HERE = Path(__file__).resolve().parent


def cases():
    binary = bytes(range(256))*4097 + b'\x00\xff'
    return [
        dict(id='desktop-new-existing', prompt='請備份「採集原件.bin」到「交件副本.bin」：副本若已存在，不得讀取來源或寫入任何檔案，原狀保留並回覆「沿用既有交件」；只有副本不存在才原樣複製，核對內容後回覆「新交件已核對」。',
             initial={'交件副本.bin': b'prior\x00\xff'}, sources=['採集原件.bin'], destinations=['交件副本.bin'], existing=True, reply='沿用既有交件'),
        dict(id='desktop-new-empty', prompt='為「零內容.dat」建立全新的「零內容備份.dat」，不改來源、不覆寫，核對副本確實也是空檔，最後回覆「空檔交付確認」。',
             initial={'零內容.dat': b''}, sources=['零內容.dat'], destinations=['零內容備份.dat'], existing=False, reply='空檔交付確認'),
        dict(id='desktop-new-binary', prompt='「素材封包.bin」是二進位檔，請完整複製成「素材封包交付.bin」。保留每個位元組與來源，不能覆寫目的檔，核對新副本後只回覆「素材封包核對完成」。',
             initial={'素材封包.bin': binary}, sources=['素材封包.bin'], destinations=['素材封包交付.bin'], existing=False, reply='素材封包核對完成'),
        dict(id='desktop-new-two', prompt='把「聲軌原件.bin」另存原樣副本「聲軌副本.bin」，再把「附註原件.txt」原樣備份為「附註副本.txt」。兩份來源都保持不變，不蓋任何檔案；兩個副本逐一讀回核對後，最後回覆「雙份交付已核對」。',
             initial={'聲軌原件.bin': b'\x00\xff\xfe'+binary[:1301], '附註原件.txt': 'e\u0301\r\n台灣𠮷 {{step:50.output}}  '.encode()},
             sources=['聲軌原件.bin','附註原件.txt'], destinations=['聲軌副本.bin','附註副本.txt'], existing=False, reply='雙份交付已核對'),
    ]


def oracle(case, work, result, receipts, source_opens):
    expected = dict(case['initial'])
    if not case['existing']:
        for source, dest in zip(case['sources'], case['destinations']): expected[dest] = expected[source]
    actual = {p.relative_to(work).as_posix(): p.read_bytes() for p in work.rglob('*') if p.is_file()}
    issues = []
    if expected != actual: issues.append('Actual file set or exact bytes do not satisfy the request')
    if result.message != case['reply']: issues.append('Required final reply not delivered')
    if case['existing']:
        if source_opens or any(r['tool']=='READ_TEXT_FILE' and Path(r['arguments']['path']).name in case['sources'] for r in receipts):
            issues.append('Forbidden source read attempted')
        if any(r['tool'] in ('WRITE_TEXT_FILE','APPEND_TEXT_FILE','MAKE_DIRECTORY') for r in receipts):
            issues.append('Forbidden write dispatched')
    else:
        for destination in case['destinations']:
            good_copy = [r for r in receipts if r['tool']=='COPY_FILE_VERIFIED'
                         and Path(r['arguments']['destination']).name==destination and (r['result'] or {}).get('ok') is True
                         and (r['result'] or {}).get('evidence',{}).get('destination_readback_verified') is True]
            if good_copy: continue
            # Equivalent actual text write + complete readback can also satisfy
            # the request. The oracle does not require a particular tool name.
            writes = [i for i,h in enumerate(result.history) if h['tool']=='WRITE_TEXT_FILE' and h.get('ok') is True
                      and Path(h['args']['path']).name==destination]
            found = False
            if writes:
                full = completed_file_contents(result.history[max(writes)+1:])
                observed = full.get(str((work/destination).resolve()))
                found = observed is not None and observed['text'].encode('utf8')==expected[destination]
            if not found: issues.append('Missing verified post-write readback: '+destination)
    return dict(issues=issues, oracle_satisfied=not issues, passed=result.status=='completed' and not issues,
                false_completion=result.status=='completed' and bool(issues),
                file_sha256={n:hashlib.sha256(v).hexdigest() for n,v in actual.items()})


def execute(case, model, gateway):
    with tempfile.TemporaryDirectory(dir=HERE,prefix='.desktop-model-') as folder:
        fixture=CopyFixture(dict(id=case['id'],user_request=case['prompt'],initial_files={},write_targets={}),folder,model,gateway)
        fixture.settings.max_replans=2
        opens=[];original_open=Path.open
        source_paths={fixture.work/n for n in case['sources']}
        def observed_open(path,mode='r',*args,**kwargs):
            if path in source_paths and ('r' in mode or '+' in mode):opens.append({'path':path.name,'mode':mode})
            return original_open(path,mode,*args,**kwargs)
        try:
            for name,value in case['initial'].items():(fixture.work/name).write_bytes(value)
            with patch.object(Path,'open',observed_open): result,receipts,_=fixture.run(model,gateway)
            verdict=oracle(case,fixture.work,result,receipts,opens)
            return dict(id=case['id'],status=result.status,message=result.message,history=result.history,receipts=receipts,
                        trace=fixture.trace,source_open_attempts=opens,**verdict)
        finally:fixture.close()


def authored(case, broken=False):
    steps=[]
    for source,dest in zip(case['sources'],case['destinations']):
        steps.append(dict(id=len(steps)+1,goal='原樣複製',tool='COPY_FILE_VERIFIED',args=dict(source=source,destination=dest,if_exists='skip' if case['existing'] else 'error'),success_check='核對副本',on_failure='stop',retries=0))
    steps.append(dict(id=len(steps)+1,goal='交付指定回覆',tool='FINAL_RESPONSE',args={'message':'錯誤回覆' if broken else case['reply']},success_check='回覆',on_failure='stop',retries=0))
    return dict(objective='複製並核對',assumptions=[],steps=steps,completion_criteria=['遵守原始需求'])


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--model');parser.add_argument('--output',required=True);parser.add_argument('--self-check',action='store_true');args=parser.parse_args()
    if Path(args.output).name!=args.output:raise ValueError('Filename only')
    target=HERE/args.output
    if target.exists():raise FileExistsError(target)
    inputs=cases()
    train=[json.loads(x) for x in (HERE/'candidate-data-v2/train.jsonl').read_text(encoding='utf8').splitlines()]
    from prepare_candidate import request_text
    if {x['prompt'] for x in inputs}&{request_text(x) for x in train}:raise ValueError('Repeats training request')
    paths=[Path(__file__),HERE/'copy_fixture.py',HERE/'desktop_contract.py',ROOT/'run_daemon.py',ROOT/'product_tools.py',ROOT/'verified_copy.py',
           ROOT/'explicit_reply.py',ROOT/'desktop_session.py',ROOT/'model_json.py',ROOT/'step_conditions.py',ROOT/'argument_references.py',
           ROOT/'path_metadata.py',ROOT/'text_reader.py',ROOT/'task_journal.py',ROOT/'completion_verification.py',
           ROOT/'finetuning/build_product_data.py',ROOT/'finetuning/runtime_v6/conditional_flow.py',ROOT/'finetuning/release_v4/file_flow.py',ROOT/'finetuning/release_v3/execute_plan_fixtures.py']
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    model=None if args.self_check else next(m for m in request('/api/tags')['models'] if m['name']==args.model)
    options=dict(temperature=0,num_ctx=12288,num_predict=2048,repeat_penalty=1.0)
    metadata=dict(started_utc=datetime.now(timezone.utc).isoformat(),sources=hashes,model=model,options=options,max_replans=2,
                  cases=[{**c,'initial':{n:{'bytes':len(v),'sha256':hashlib.sha256(v).hexdigest()} for n,v in c['initial'].items()}} for c in inputs],
                  self_check=args.self_check,scope='Fresh authored development; actual desktop file handlers, not native UI or original file8 scores.',release_approved=False)
    target.with_suffix('.manifest.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf8')
    rows=[]
    with target.open('x',encoding='utf8') as output:
        for case in inputs:
            for broken in (False,True) if args.self_check else (False,):
                calls=[];started=time.monotonic()
                class Gateway:
                    def chat_json(self,*,messages,schema,models=None):
                        if args.self_check:
                            return ({'complete':True,'reason':'self-check'} if 'complete' in schema['properties'] else copy.deepcopy(authored(case,broken))), 'authored'
                        if len(calls)>=12 or time.monotonic()-started>360:raise RuntimeError('Evaluation call/time budget exhausted')
                        body=dict(model=args.model,messages=messages,format=schema,options=options,stream=False,truncate=False,shift=False)
                        record={'request':body};calls.append(record)
                        try:
                            value=request('/api/chat',body);record['response']=value
                            if value.get('done') is not True or value.get('done_reason')!='stop':raise ValueError('Incomplete model generation')
                            return json.loads(value['message']['content']),args.model
                        except Exception as exc:record['error']=str(exc);raise
                result=execute(case,args.model or 'authored',Gateway())
                result.update(calls=calls,seconds=time.monotonic()-started)
                if args.self_check:
                    result['negative_control']=broken
                    if result['passed']==broken:raise AssertionError('Oracle self-check disagreed')
                rows.append(result);output.write(json.dumps(result,ensure_ascii=False)+'\n');output.flush()
                print(json.dumps({k:result[k] for k in ('id','passed','false_completion','status','issues','seconds')},ensure_ascii=True),flush=True)
    stable=all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h for n,h in hashes.items())
    model_stable=args.self_check or model['digest']==next(m['digest'] for m in request('/api/tags')['models'] if m['name']==args.model)
    summary=dict(cases=len(rows),passed=sum(r['passed'] for r in rows),oracle_satisfied=sum(r['oracle_satisfied'] for r in rows),
                 false_completions=sum(r['false_completion'] for r in rows),sources_unchanged=stable,model_unchanged=model_stable,
                 output_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),self_check=args.self_check,release_approved=False)
    target.with_suffix('.summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8');print(json.dumps(summary),flush=True)
    if not stable or not model_stable:raise RuntimeError('Mixed source/model run')


if __name__=='__main__':main()

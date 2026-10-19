"""Run frozen development inputs through the actual current product gateway."""
import argparse
import ast
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from types import SimpleNamespace
import ollama

R=Path(__file__).resolve().parent
ROOT=R.parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(R.parent/'release_v4'))
from evaluate_development import request


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf8'))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--model',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--validate-only',action='store_true');args=parser.parse_args()
    if Path(args.output).name!=args.output:raise ValueError('New local filename required')
    folder=R/'evaluation-runtime-v3';manifest=read(folder/'manifest.json')
    sources=dict(manifest['source_hashes'])
    for name,digest in sources.items():
        if sha(ROOT/name)!=digest:raise RuntimeError('Source changed: '+name)
    for name,digest in manifest['outputs'].items():
        if sha(folder/name)!=digest:raise RuntimeError('Evaluation input changed: '+name)
    rows=[json.loads(x) for x in (folder/'cases.jsonl').read_text(encoding='utf8').splitlines()]
    schemas=read(folder/'schemas.json')
    sources.update({str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__),folder/'manifest.json',folder/'cases.jsonl',folder/'schemas.json',R.parent/'release_v4/evaluate_development.py')})
    if args.validate_only:print(json.dumps({'cases':len(rows),'locked_sources_verified':True,'execution_started':False}));return
    target=folder/args.output
    if target.exists() or target.with_suffix('.manifest.json').exists():raise FileExistsError(target)
    model=next(m for m in request('/api/tags')['models'] if m['name']==args.model)
    tree=ast.parse((ROOT/'run_daemon.py').read_text(encoding='utf-8-sig'))
    nodes=[n for n in tree.body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name in ('OllamaGateway','extract_json_object')]
    assert len(nodes)==2
    module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),*nodes],type_ignores=[])
    scope={'ollama':ollama,'json':json,'re':re}
    exec(compile(ast.fix_missing_locations(module),str(ROOT/'run_daemon.py'),'exec'),scope)
    gateway=scope['OllamaGateway'](SimpleNamespace(planner_models=(args.model,),planner_num_ctx=12288))
    sent=[];received=[]
    gateway.client._client.event_hooks['request'].append(lambda req:sent.append(json.loads(req.content)))
    def response_hook(response):
        response.read()
        try:received.append(response.json())
        except ValueError:received.append({'http_status':response.status_code,'invalid_json':True})
    gateway.client._client.event_hooks['response'].append(response_hook)
    run=dict(model=model,sources=sources,started_utc=datetime.now(timezone.utc).isoformat(),cases=[r['id'] for r in rows],
        scope='Actual text/JSON gateway; development generation only, no file/DOM/native actions; same-profile baseline comparison required.',release_approved=False)
    with target.with_suffix('.manifest.json').open('x',encoding='utf8') as stream:json.dump(run,stream,ensure_ascii=False,indent=2)
    records=[]
    try:
        with target.open('x',encoding='utf8') as stream:
            for index,row in enumerate(rows):
                sent.clear();received.clear();error=None;accepted=False;began=time.monotonic();text=''
                kind=row['oracle']['type']
                messages=[{'role':'system','content':row['gateway_system']},{'role':'user','content':row['prompt']}]
                try:
                    if kind in ('plan','completion'):
                        gateway.chat_json(messages=messages,schema=schemas[kind],models=(args.model,))
                    else:
                        text,_=gateway.chat_text(prompt=row['prompt'],system=row['gateway_task_system'],models=(args.model,))
                    accepted=True
                except Exception as exc:error=type(exc).__name__+': '+str(exc)
                if len(sent)>1:raise RuntimeError('Unexpected fallback or repeated request')
                if sent:
                    assert sent[0]['messages']==messages,'Task/system changed in transport'
                    assert sent[0]['truncate'] is False and sent[0]['shift'] is False
                raw=received[0] if received else {}
                if isinstance(raw.get('message'),dict):text=raw['message'].get('content','')
                record=dict(id=row['id'],category=row['category'],group=row.get('group',row['id']),suite=row['suite'],
                    model=args.model,candidate=args.model,model_digest=model['digest'],text=text,completed=accepted,
                    gateway_accepted_complete=accepted,request=sent[0] if sent else None,raw_response=raw,error=error,
                    prompt_sha256=hashlib.sha256((row['gateway_system']+'\n'+row['prompt']).encode()).hexdigest(),seconds=time.monotonic()-began)
                stream.write(json.dumps(record,ensure_ascii=False)+'\n');stream.flush();records.append(record)
                print(json.dumps({'done':index+1,'total':len(rows),'suite':row['suite'],'id':row['id'],'completed':accepted,'seconds':record['seconds']}),flush=True)
    finally:gateway.close()
    end=next(m for m in request('/api/tags')['models'] if m['name']==args.model)
    stable=all(sha(ROOT/name)==digest for name,digest in sources.items()) and end['digest']==model['digest']
    result=dict(rows=len(records),complete_generations=sum(r['completed'] for r in records),model_and_sources_unchanged=stable,
        results_sha256=sha(target),semantic_review_required=True,actual_action_acceptance=False,release_approved=False)
    with target.with_suffix('.generation-complete.json').open('x',encoding='utf8') as stream:json.dump(result,stream,indent=2)
    print(json.dumps(result),flush=True)
    if not stable:raise RuntimeError('Source/model changed during evaluation')


if __name__=='__main__':main()

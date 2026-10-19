"""Exercise actual text gateway and record outgoing HTTP; no UI or actions."""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import ollama

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'finetuning/release_v4'))
from evaluate_development import request
from product_identity import GENERATION_SYSTEM


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--model',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    if Path(args.output).name!=args.output:raise ValueError('Filename only')
    target=HERE/args.output
    if target.exists():raise FileExistsError(target)
    data=HERE/'candidate-v2/brand-dev.jsonl'
    rows=[json.loads(x) for x in data.read_text(encoding='utf8').splitlines()]
    assert all(row['system']==GENERATION_SYSTEM for row in rows)
    paths=[Path(__file__),data,ROOT/'run_daemon.py',ROOT/'product_identity.py',ROOT/'finetuning/release_v4/evaluate_development.py']
    sources={str(p.relative_to(ROOT)):sha(p) for p in paths}
    model=next(m for m in request('/api/tags')['models'] if m['name']==args.model)
    node=next(n for n in ast.parse((ROOT/'run_daemon.py').read_text(encoding='utf-8-sig')).body if isinstance(n,ast.ClassDef) and n.name=='OllamaGateway')
    module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),node],type_ignores=[])
    scope={'ollama':ollama}
    exec(compile(ast.fix_missing_locations(module),str(ROOT/'run_daemon.py'),'exec'),scope)
    gateway=scope['OllamaGateway'](SimpleNamespace(planner_models=(args.model,),planner_num_ctx=12288))
    sent=[]
    gateway.client._client.event_hooks['request'].append(lambda req:sent.append(json.loads(req.content)))
    manifest=dict(model=model,sources=sources,started_utc=datetime.now(timezone.utc).isoformat(),
        scope='Updated user company facts through actual gateway, 16 known development prompts; no new weights or end-to-end product validation.',release_approved=False)
    target.with_suffix('.manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    records=[]
    try:
        with target.open('x',encoding='utf8') as out:
            for row in rows:
                sent.clear();started=time.monotonic()
                content,used=gateway.chat_text(prompt=row['prompt'])
                assert len(sent)==1 and sent[0]['truncate'] is False and sent[0]['shift'] is False
                record=dict(id=row['id'],text=content,model=used,request=sent[0],seconds=time.monotonic()-started,gateway_accepted_complete=True)
                records.append(record);out.write(json.dumps(record,ensure_ascii=False)+'\n');out.flush()
                print(json.dumps({'id':row['id'],'seconds':record['seconds']}),flush=True)
    finally:gateway.close()
    end=next(m for m in request('/api/tags')['models'] if m['name']==args.model)
    stable=all(sha(ROOT/n)==h for n,h in sources.items())
    summary=dict(rows=len(records),model_unchanged=model['digest']==end['digest'],sources_unchanged=stable,
                 output_sha256=sha(target),semantic_review_required=True,release_approved=False)
    target.with_suffix('.summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
    print(json.dumps(summary),flush=True)
    if not stable or model['digest']!=end['digest']:raise RuntimeError('Source/model changed')


if __name__=='__main__':main()

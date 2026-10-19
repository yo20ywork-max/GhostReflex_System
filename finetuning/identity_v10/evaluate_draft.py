"""Local generation baseline on the new identity dev split; no training/actions."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'finetuning/release_v4'))
from evaluate_development import request


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--model',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
    if Path(args.output).name!=args.output:raise ValueError('Filename only')
    target=HERE/args.output
    if target.exists():raise FileExistsError(target)
    data=HERE/'candidate-v1/brand-dev.jsonl';rows=[json.loads(x) for x in data.read_text(encoding='utf8').splitlines()]
    model=next(m for m in request('/api/tags')['models'] if m['name']==args.model)
    paths=[Path(__file__),data,HERE/'candidate-v1/manifest.json',ROOT/'finetuning/release_v4/evaluate_development.py']
    sources={str(p.relative_to(ROOT)):sha(p) for p in paths}
    options=dict(temperature=0,num_ctx=12288,num_predict=1024,repeat_penalty=1.0)
    manifest=dict(started_utc=datetime.now(timezone.utc).isoformat(),model=model,sources=sources,options=options,
                  scope='User-corrected brand-only identity dev with candidate system; known authored development, not end-to-end product or blind evaluation.',release_approved=False)
    target.with_suffix('.manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    records=[]
    with target.open('x',encoding='utf8') as out:
        for row in rows:
            body=dict(model=args.model,messages=[{'role':'system','content':row['system']},{'role':'user','content':row['prompt']}],options=options,stream=False,truncate=False,shift=False)
            started=time.monotonic();response=request('/api/chat',body)
            record=dict(id=row['id'],request=body,text=response['message']['content'],raw_response=response,seconds=time.monotonic()-started,
                        generation_complete=response.get('done') is True and response.get('done_reason')=='stop')
            records.append(record);out.write(json.dumps(record,ensure_ascii=False)+'\n');out.flush()
            print(json.dumps({k:record[k] for k in ('id','generation_complete','seconds')}),flush=True)
    end=next(m for m in request('/api/tags')['models'] if m['name']==args.model)
    stable=all(sha(ROOT/n)==h for n,h in sources.items())
    summary=dict(rows=len(records),complete_generations=sum(r['generation_complete'] for r in records),sources_unchanged=stable,
                 model_unchanged=end['digest']==model['digest'],output_sha256=sha(target),semantic_review_required=True,release_approved=False)
    target.with_suffix('.summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8');print(json.dumps(summary),flush=True)
    if not stable or end['digest']!=model['digest']:raise RuntimeError('Mixed sources/model')


if __name__=='__main__':main()

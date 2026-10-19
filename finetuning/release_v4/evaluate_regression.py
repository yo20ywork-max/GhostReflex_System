"""The preserved 14 critical regression questions, with current v4 schemas.

No final holdout access and no execution of model-proposed actions.
"""
import argparse
import hashlib
import json
import time
from pathlib import Path
from evaluate_development import R,inputs,request


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--model',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args()
    if Path(args.output).name!=args.output:raise ValueError('Output must be a file name')
    target=R/args.output
    if target.exists():raise FileExistsError(target)
    _,plan_schema,completion_schema,locked=inputs()
    data_path=R.parent/'release_v3/regression.jsonl'
    original=R.parent/'release_v2/regression.jsonl'
    if sha(data_path)!=sha(original):raise ValueError('Regression differs from preserved original')
    rows=[json.loads(x) for x in data_path.read_text(encoding='utf8').splitlines()]
    if len(rows)!=14 or len({r['id'] for r in rows})!=14:raise ValueError('Expected all 14 original regressions')
    paths=[Path(__file__),R/'evaluate_development.py',data_path,original]
    sources={str(p.resolve()):sha(p) for p in paths}
    model=next(m for m in request('/api/tags')['models'] if m['name']==args.model)
    options={'temperature':0,'num_ctx':12288,'num_predict':1024,'repeat_penalty':1.0}
    with target.with_suffix('.manifest.json').open('x',encoding='utf8') as stream:
        json.dump({'model':model,'sources':sources,'locked_v4_sources':{k:v['sha256'] for k,v in locked.items()},
                   'options':options,'cases':[r['id'] for r in rows],
                   'scope':'Preserved v2/v3 critical regression prompts; current v4 plan/completion schema. Same-profile baseline must be evaluated separately. Generation only; semantic review and actual tasks remain required.',
                   'release_approved':False},stream,ensure_ascii=False,indent=2)
    records=[]
    with target.open('x',encoding='utf8') as stream:
        for row in rows:
            body={'model':args.model,'messages':[{'role':'system','content':row['system']},{'role':'user','content':row['prompt']}],
                  'stream':False,'options':options,'truncate':False,'shift':False,'keep_alive':'10m'}
            kind=row['oracle']['type']
            if kind=='plan':body['format']=plan_schema
            elif kind=='completion':body['format']=completion_schema
            started=time.monotonic();response=request('/api/chat',body)
            record={'id':row['id'],'category':row['category'],'group':row['group'],'model':args.model,'model_digest':model['digest'],
                    'text':response['message']['content'],'completed':response.get('done') is True and response.get('done_reason')=='stop',
                    'prompt_sha256':hashlib.sha256((row['system']+'\n'+row['prompt']).encode()).hexdigest(),
                    'request':body,'raw_response':response,'seconds':time.monotonic()-started}
            stream.write(json.dumps(record,ensure_ascii=False)+'\n');stream.flush();records.append(record)
            print(json.dumps({k:record[k] for k in ['id','completed','seconds']}),flush=True)
    end=next(m for m in request('/api/tags')['models'] if m['name']==args.model)
    stable=all(sha(Path(p))==h for p,h in sources.items()) and all(sha(R/p)==v['sha256'] for p,v in locked.items())
    summary={'rows':len(records),'complete_generations':sum(r['completed'] for r in records),
             'source_files_unchanged':stable,'model_digest_unchanged':model['digest']==end['digest'],
             'results_sha256':sha(target),'semantic_review_required':True,'release_approved':False}
    with target.with_suffix('.generation-complete.json').open('x',encoding='utf8') as stream:json.dump(summary,stream,indent=2)
    print(json.dumps(summary),flush=True)
    if not stable or model['digest']!=end['digest']:raise RuntimeError('Mixed sources/model')


if __name__=='__main__':main()

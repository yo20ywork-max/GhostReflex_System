"""Evaluate a named Ollama candidate without running generated tools or shell code."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.request
ROOT=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser();p.add_argument('--data',choices=['dev','test','regression','integration-dev'],required=True);p.add_argument('--model',required=True);p.add_argument('--output',required=True);p.add_argument('--candidate',choices=['base','adapter'],required=True);p.add_argument('--num-ctx',type=int,default=4096);p.add_argument('--schema',action='store_true');args=p.parse_args()
    with urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=15) as response:models=json.load(response)['models']
    model=next((m for m in models if m['name']==args.model),None)
    if model is None:raise RuntimeError('Model must already be imported; no implicit downloads')
    rows=[json.loads(l) for l in (ROOT/(args.data+'.jsonl')).read_text(encoding='utf8').splitlines()]
    with Path(args.output).open('x',encoding='utf8') as out:
        for i,r in enumerate(rows):
            payload={'model':args.model,'messages':[{'role':'system','content':r['system']},{'role':'user','content':r['prompt']}],'stream':False,'options':{'temperature':0,'num_ctx':args.num_ctx,'num_predict':768},'keep_alive':'10m'}
            if args.schema:payload['format']=json.loads((ROOT/'contract.json').read_text(encoding='utf8'))['schema']
            request=urllib.request.Request('http://127.0.0.1:11434/api/chat',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
            started=time.monotonic()
            with urllib.request.urlopen(request,timeout=180) as response:result=json.load(response)
            text=result['message']['content']
            record={'id':r['id'],'category':r['category'],'group':r['group'],'candidate':args.candidate,'text':text,'completed':result.get('done',False) and result.get('done_reason')=='stop','generated_tokens':result.get('eval_count'),'seconds':time.monotonic()-started,'model':args.model,'model_digest':model.get('digest'),'num_ctx':args.num_ctx,'schema_constrained':args.schema,'input_normalization':'none; preserve literals','eval_duration_ns':result.get('eval_duration'),'prompt_eval_duration_ns':result.get('prompt_eval_duration'),'prompt_sha256':hashlib.sha256((r['system']+'\n'+r['prompt']).encode()).hexdigest()}
            out.write(json.dumps(record,ensure_ascii=False)+'\n');out.flush()
            print(json.dumps({'done':i+1,'total':len(rows),'id':r['id'],'seconds':record['seconds']}),flush=True)

if __name__=='__main__':main()

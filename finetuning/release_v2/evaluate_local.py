"""Finite model-only evaluation, never execute generated desktop actions."""
import argparse,hashlib,json,time,urllib.request
from pathlib import Path
R=Path(__file__).resolve().parent
def request(path,payload=None,timeout=180):
 req=urllib.request.Request('http://127.0.0.1:11434'+path,data=json.dumps(payload,ensure_ascii=False).encode() if payload is not None else None,headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=timeout) as f:return json.load(f)
def main():
 p=argparse.ArgumentParser();p.add_argument('--data',required=True);p.add_argument('--output',required=True);p.add_argument('--model',default='qwen2.5-coder:7b');p.add_argument('--candidate',default='base');a=p.parse_args()
 model=next(m for m in request('/api/tags')['models'] if m['name']==a.model)
 schema=json.loads((R/'contract.json').read_text(encoding='utf8'))['schema']
 rows=list(map(json.loads,(R/a.data).read_text(encoding='utf8').splitlines()))
 with (R/a.output).open('x',encoding='utf8') as f:
  for i,r in enumerate(rows):
   payload={'model':a.model,'messages':[{'role':'system','content':r['system']},{'role':'user','content':r['prompt']}],'stream':False,'options':{'temperature':0,'num_ctx':12288,'num_predict':1024},'keep_alive':'10m'}
   if r['oracle']['type']=='plan':payload['format']=schema
   started=time.monotonic();out=request('/api/chat',payload)
   record={'id':r['id'],'category':r['category'],'group':r['group'],'candidate':a.candidate,'text':out['message']['content'],'completed':out.get('done') is True and out.get('done_reason')=='stop','seconds':time.monotonic()-started,'model':a.model,'model_digest':model['digest'],'num_ctx':12288,'num_predict':1024,'schema_constrained':'format' in payload,'prompt_sha256':hashlib.sha256((r['system']+'\n'+r['prompt']).encode()).hexdigest(),'prompt_eval_count':out.get('prompt_eval_count'),'generated_tokens':out.get('eval_count')}
   f.write(json.dumps(record,ensure_ascii=False)+'\n');f.flush();print(json.dumps({'done':i+1,'total':len(rows),'seconds':record['seconds']}),flush=True)
if __name__=='__main__':main()

"""Finite model-only evaluation, never execute generated desktop actions."""
import argparse,hashlib,json,time,urllib.request
from pathlib import Path
R=Path(__file__).resolve().parent
def request(path,payload=None,timeout=180):
 req=urllib.request.Request('http://127.0.0.1:11434'+path,data=json.dumps(payload,ensure_ascii=False).encode() if payload is not None else None,headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=timeout) as f:return json.load(f)
def main():
 p=argparse.ArgumentParser();p.add_argument('--data',required=True);p.add_argument('--output',required=True);p.add_argument('--model',default='qwen2.5-coder:7b');p.add_argument('--candidate',default='base');p.add_argument('--repeat-penalty',type=float,choices=[1.0,1.1])
 p.add_argument('--think',choices=['auto','on','off'],default='auto');p.add_argument('--presence-penalty',type=float);p.add_argument('--no-truncate',action='store_true');a=p.parse_args()
 source_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
 model=next(m for m in request('/api/tags')['models'] if m['name']==a.model)
 schema=json.loads((R/'training-contract.json').read_text(encoding='utf8'))['schema']
 rows=list(map(json.loads,(R/a.data).read_text(encoding='utf8').splitlines()))
 if a.data not in ('dev.jsonl','test.jsonl','provenance-audit.jsonl','regression.jsonl'):raise ValueError('Only locked evaluation inputs permitted')
 if a.data=='regression.jsonl':
  if hashlib.sha256((R/a.data).read_bytes()).hexdigest()!=hashlib.sha256((R.parent/'release_v2'/a.data).read_bytes()).hexdigest():raise ValueError('Known regression must exactly match preserved v2')
 if a.data in ('test.jsonl','provenance-audit.jsonl') and not (R/'FINAL_SELECTION.json').exists():raise RuntimeError('Fresh final requires explicit candidate selection or recorded diagnostic selection')
 with (R/a.output).open('x',encoding='utf8') as f:
  for i,r in enumerate(rows):
   payload={'model':a.model,'messages':[{'role':'system','content':r['system']},{'role':'user','content':r['prompt']}],'stream':False,'options':{'temperature':0,'num_ctx':12288,'num_predict':1024},'keep_alive':'10m'}
   if a.repeat_penalty is not None:payload['options']['repeat_penalty']=a.repeat_penalty
   if a.presence_penalty is not None:payload['options']['presence_penalty']=a.presence_penalty
   if a.think!='auto':payload['think']=a.think=='on'
   if a.no_truncate:payload.update(truncate=False,shift=False)
   if r['oracle']['type']=='plan':payload['format']=schema
   elif r['oracle']['type']=='completion':payload['format']=json.loads((R/'COMPLETION_DATA_MANIFEST.json').read_text(encoding='utf8'))['schema']
   started=time.monotonic();out=request('/api/chat',payload)
   record={'id':r['id'],'category':r['category'],'group':r['group'],'candidate':a.candidate,'text':out['message']['content'],'completed':out.get('done') is True and out.get('done_reason')=='stop','seconds':time.monotonic()-started,'model':a.model,'model_digest':model['digest'],'num_ctx':12288,'num_predict':1024,'schema_constrained':'format' in payload,'prompt_sha256':hashlib.sha256((r['system']+'\n'+r['prompt']).encode()).hexdigest(),'prompt_eval_count':out.get('prompt_eval_count'),'generated_tokens':out.get('eval_count')}
   record['inference_overrides']=payload['options']
   record.update(transport_overrides={k:payload[k] for k in ('think','truncate','shift') if k in payload},evaluator_sha256=source_hash)
   if a.think!='auto' or a.no_truncate:record['raw_response']=out
   f.write(json.dumps(record,ensure_ascii=False)+'\n');f.flush();print(json.dumps({'done':i+1,'total':len(rows),'seconds':record['seconds']}),flush=True)
if __name__=='__main__':main()

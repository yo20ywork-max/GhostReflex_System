"""Measure the current product contract on known development scenarios."""
import argparse,hashlib,json,sys,time
from pathlib import Path
from types import SimpleNamespace
R=Path(__file__).resolve().parent
sys.path.insert(0,str(R.parent));sys.path.insert(0,str(R.parent/'release_v2'))
from build_product_data import contract
from evaluate_local import request

def main():
 p=argparse.ArgumentParser();p.add_argument('--model',default='crossgen-agi-mu:v2-repair-eval-20260906');p.add_argument('--output',default='contract-dev.jsonl');p.add_argument('--source',default='dev.jsonl');a=p.parse_args()
 catalog,schema,prompt,sourcehash=contract();system=prompt(SimpleNamespace(catalog=catalog,schema=schema))
 data=[x for x in map(json.loads,(R.parent/'release_v2'/a.source).read_text(encoding='utf8').splitlines()) if x['oracle']['type']=='plan']
 model=next(m for m in request('/api/tags')['models'] if m['name']==a.model)
 snapshot={'catalog':catalog,'schema':schema,'system':system,'source_sha256':sourcehash}
 path=R/a.output
 if path.exists():raise FileExistsError(path)
 path.with_suffix('.contract.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2),encoding='utf8')
 with path.open('x',encoding='utf8') as f:
  for row in data:
   started=time.monotonic();answer=request('/api/chat',{'model':a.model,'messages':[{'role':'system','content':system},{'role':'user','content':row['prompt']}],'format':schema,'stream':False,'options':{'temperature':0,'num_ctx':12288,'num_predict':1536}})
   record={'id':row['id'],'category':row['category'],'group':row['group'],'candidate':'adapter','text':answer['message']['content'],'completed':answer.get('done_reason')=='stop','seconds':time.monotonic()-started,'model':a.model,'model_digest':model['digest'],'prompt_eval_count':answer.get('prompt_eval_count'),'generated_tokens':answer.get('eval_count'),'prompt_sha256':hashlib.sha256((system+'\n'+row['prompt']).encode()).hexdigest(),'source':'known '+a.source+'; not fresh held-out data'}
   f.write(json.dumps(record,ensure_ascii=False)+'\n');f.flush();print(json.dumps({'id':row['id'],'seconds':record['seconds'],'completed':record['completed']}),flush=True)
 rewritten=[{**row,'system':system} for row in data]
 path.with_suffix('.data.jsonl').write_text('\n'.join(json.dumps(x,ensure_ascii=False) for x in rewritten)+'\n',encoding='utf8')
 print('CONTRACT_EVALUATION_COMPLETE')
if __name__=='__main__':main()

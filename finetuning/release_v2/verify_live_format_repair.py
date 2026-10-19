"""Diagnostic continuation of recorded failures using actual Planner repair method.

First response is replayed; the one permitted repair response is generated live.
This never replaces frozen first-pass scores or executes generated actions.
"""
import ast,hashlib,json,time
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from evaluate_local import request
from execute_plan_fixtures import load
R=Path(__file__).resolve().parent
def main():
 output=R/'LIVE_FORMAT_REPAIR.json'
 if output.exists():raise FileExistsError(output)
 selected=json.loads((R/'FINAL_SELECTION.json').read_text());scope,sourcehash=load()
 tree=ast.parse((R.parents[1]/'run_daemon.py').read_text(encoding='utf-8-sig'))
 node=next(x for x in tree.body if getattr(x,'name',None)=='Planner')
 mod=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),node],type_ignores=[])
 exec(compile(ast.fix_missing_locations(mod),'<actual Planner>','exec'),scope)
 data={x['id']:x for x in map(json.loads,(R/'test.jsonl').read_text(encoding='utf8').splitlines())}
 original=[x for x in map(json.loads,(R/'local-final-test.jsonl').read_text(encoding='utf8').splitlines()) if x['group']=='v2-holdout-time-window']
 schema=json.loads((R/'contract.json').read_text(encoding='utf8'))['schema'];records=[]
 model=next(m for m in request('/api/tags')['models'] if m['name']==selected['model'])
 if model['digest']!=selected['model_digest']:raise ValueError('Model changed')
 for result in original:
  row=data[result['id']];calls=[]
  class Gateway:
   def chat_json(self,*,messages,schema,models):
    if not calls:
     calls.append({'kind':'replayed_original','text':result['text']});return json.loads(result['text']),models[0]
    if len(calls)!=1:raise RuntimeError('One fresh repair response maximum')
    began=time.monotonic();out=request('/api/chat',{'model':models[0],'messages':messages,'format':schema,'stream':False,'options':{'temperature':0,'num_ctx':12288,'num_predict':1024}})
    calls.append({'kind':'live_repair','text':out['message']['content'],'seconds':time.monotonic()-began,'done_reason':out.get('done_reason'),'feedback':messages[-1]['content']})
    if out.get('done_reason')!='stop':raise ValueError('Incomplete repair')
    return json.loads(out['message']['content']),models[0]
  planner=scope['Planner'].__new__(scope['Planner']);planner.settings=SimpleNamespace(max_plan_steps=12,default_tool_retries=0,planner_models=[selected['model']]);planner.schema=schema;planner.gateway=Gateway()
  valid=False;plan=None;error=None
  try:
   plan=asdict(planner._request_valid_plan([{'role':'system','content':row['system']},{'role':'user','content':row['prompt']}],set()));valid=True
  except Exception as exc:error=str(exc)
  records.append({'id':row['id'],'runtime_valid_after_repair':valid,'plan':plan,'error':error,'calls':calls});print(json.dumps({'id':row['id'],'runtime_valid_after_repair':valid,'calls':len(calls)}),flush=True)
 report={'scope':'Additional post-test diagnostic. Replay frozen failing first response, then actual Planner validation feedback and one live model call. No action execution or change to first-pass result.','source_sha256':sourcehash,'model_digest':model['digest'],'original_sha256':hashlib.sha256((R/'local-final-test.jsonl').read_bytes()).hexdigest(),'runtime_valid_after_repair':sum(x['runtime_valid_after_repair'] for x in records),'total':len(records),'records':records}
 output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
if __name__=='__main__':main()

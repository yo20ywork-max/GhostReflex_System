"""Known real fixture evidence fed to the actual product completion assessor."""
import argparse,ast,hashlib,json,sys,time
from pathlib import Path
from types import SimpleNamespace
R=Path(__file__).resolve().parent
sys.path.insert(0,str(R.parent/'release_v2'))
from evaluate_local import request

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--output',default='completion-dev.jsonl');parser.add_argument('--model',default='crossgen-agi-mu:v2-repair-eval-20260906');args=parser.parse_args()
 path=R/args.output
 if path.exists():raise FileExistsError(path)
 data={x['id']:x for x in map(json.loads,(R/'contract-dev.data.jsonl').read_text(encoding='utf8').splitlines())}
 fixture=json.loads((R/'contract-execution.json').read_text(encoding='utf8'))
 source=(R.parents[1]/'run_daemon.py').read_text(encoding='utf-8-sig');tree=ast.parse(source);node=next(x for x in tree.body if getattr(x,'name',None)=='Planner')
 mod=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),node],type_ignores=[]);scope={'json':json};exec(compile(ast.fix_missing_locations(mod),'<actual completion checker>','exec'),scope)
 model=args.model;digest=next(x['digest'] for x in request('/api/tags')['models'] if x['name']==model)
 class Gateway:
  def chat_json(self,*,messages,schema):
   out=request('/api/chat',{'model':model,'messages':messages,'format':schema,'stream':False,'options':{'temperature':0,'num_ctx':12288,'num_predict':512}})
   if out.get('done_reason')!='stop':raise ValueError('Incomplete generation')
   return json.loads(out['message']['content']),model
 checker=scope['Planner'].__new__(scope['Planner']);checker.gateway=Gateway();checker.settings=SimpleNamespace(planner_num_ctx=12288)
 with path.open('x',encoding='utf8') as f:
  for record in fixture['records']:
   payload=json.loads(data[record['id']]['prompt']);history=list(payload.get('replanning_context',{}).get('completed_and_failed_history',[]))
   history += [{'step_id':x['id'],'tool':x['tool'],'args':x['args'],'ok':x['ok'],'verified':x['verified'],'output':x['output'],'error':x['error']} for x in record['trace']]
   began=time.monotonic();complete,reason=checker.assess_completion(payload['user_request'],history)
   out={'id':record['id'],'actual_fixture_passed':record['passed'],'assessed_complete':complete,'classification_correct':complete==record['passed'],'false_completion':complete and not record['passed'],'reason':reason,'seconds':time.monotonic()-began,'model_digest':digest,'source_sha256':hashlib.sha256(source.encode()).hexdigest()}
   f.write(json.dumps(out,ensure_ascii=False)+'\n');f.flush();print(json.dumps(out,ensure_ascii=False),flush=True)
if __name__=='__main__':main()

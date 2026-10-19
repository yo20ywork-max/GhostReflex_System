"""Deterministic diagnostics and explicit semantic-review queue, never a release claim."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
from types import SimpleNamespace
from jsonschema import Draft202012Validator
from execute_plan_fixtures import load
R=Path(__file__).resolve().parent
def main():
 p=argparse.ArgumentParser();p.add_argument('--results',required=True);a=p.parse_args()
 data={r['id']:r for r in map(json.loads,(R/'dev.jsonl').read_text(encoding='utf8').splitlines())};results=list(map(json.loads,(R/a.results).read_text(encoding='utf8').splitlines()))
 if len(results)!=len(data) or {r['id'] for r in results}!=set(data):raise ValueError('Incomplete or duplicate results')
 c=json.loads((R/'training-contract.json').read_text(encoding='utf8'));validator=Draft202012Validator(c['schema']);s,sourcehash=load('training-contract.json');records=[]
 for r in results:
  d=data[r['id']];kind=d['oracle']['type'];check={'passed':None,'reason':'Requires semantic review'}
  if r['prompt_sha256']!=hashlib.sha256((d['system']+'\n'+d['prompt']).encode()).hexdigest():raise ValueError('Wrong prompt result')
  try:
   if not r['completed']:raise ValueError('Generation incomplete')
   if kind=='plan':
    value=json.loads(r['text']);validator.validate(value);payload=json.loads(d['prompt']);history=payload.get('replanning_context',{}).get('completed_and_failed_history',[])
    s['validate_plan'](value,SimpleNamespace(max_plan_steps=12,default_tool_retries=0),'candidate',{x['step_id'] for x in history})
    check={'passed':None,'schema_and_runtime_valid':True,'reason':'Format valid; semantics and real execution still required'}
   elif kind=='completion':
    value=json.loads(r['text']);expected=d['oracle']['complete'];valid=type(value.get('complete')) is bool and isinstance(value.get('reason'),str)
    check={'passed':valid and value['complete']==expected,'expected_complete':expected,'assessed_complete':value.get('complete'),'false_completion':valid and value['complete'] and not expected,'false_incomplete':valid and not value['complete'] and expected}
   elif kind=='code':
    import re
    code=r['text'].strip();m=re.fullmatch(r'```(?:python)?\s*\n(.*?)\n```',code,re.S)
    if m:code=m.group(1)
    payload={'code':code,'function':d['oracle']['function'],'tests':d['oracle']['tests']}
    proc=subprocess.run([sys.executable,'-I',str(R/'code_sandbox.py')],input=json.dumps(payload),text=True,encoding='utf8',capture_output=True,timeout=3)
    check=json.loads(proc.stdout)
   elif kind=='exact':
    check={'passed':r['text'].strip()==d['oracle']['value'].strip(),'reason':'Exact diagnostic; ASR equivalent wording still needs semantic review'}
  except Exception as exc:check={'passed':False,'reason':str(exc)[:500]}
  records.append({'id':r['id'],'category':r['category'],'text_sha256':hashlib.sha256(r['text'].encode()).hexdigest(),**check})
 summary={cat:{'passed':sum(x['passed'] is True for x in records if x['category']==cat),'failed':sum(x['passed'] is False for x in records if x['category']==cat),'review':sum(x['passed'] is None for x in records if x['category']==cat)} for cat in sorted({x['category'] for x in records})}
 out={'release_approved':False,'summary':summary,'records':records,'scorer_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'runtime_source_sha256':sourcehash,'results_sha256':hashlib.sha256((R/a.results).read_bytes()).hexdigest()}
 path=R/(a.results+'.checks.json')
 if path.exists():raise FileExistsError(path)
 path.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(summary))
if __name__=='__main__':main()

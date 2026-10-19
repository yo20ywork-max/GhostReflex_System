"""Additional diagnostic for legitimate pure Try/ValueError and set.intersection.

The original frozen score remains authoritative in its own report. This reports
function semantics separately and does not execute illustrative top-level code.
"""
import argparse,ast,hashlib,json,re,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parent
sys.path.insert(0,str(R))
import code_sandbox as sandbox

def worker():
 sandbox.NODES=(*sandbox.NODES,ast.Try,ast.ExceptHandler)
 sandbox.SAFE_BUILTINS['ValueError']=ValueError
 sandbox.METHODS.add('intersection')
 try:print(json.dumps(sandbox.run(json.load(sys.stdin))))
 except BaseException as e:print(json.dumps({'passed':False,'error':type(e).__name__+': '+str(e)[:200]}))

def main():
 p=argparse.ArgumentParser();p.add_argument('--worker',action='store_true');p.add_argument('--data');p.add_argument('--results');a=p.parse_args()
 if a.worker:return worker()
 data={r['id']:r for r in map(json.loads,(R/a.data).read_text(encoding='utf8').splitlines())};reports=[]
 for r in map(json.loads,(R/a.results).read_text(encoding='utf8').splitlines()):
  if r['category']!='code':continue
  d=data[r['id']];code=r['text'].strip();m=re.fullmatch(r'```(?:python)?\s*\n(.*?)\n```',code,re.S)
  if m:code=m.group(1)
  try:
   tree=ast.parse(code);defs=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.Import,ast.ImportFrom))];functions=[n.name for n in defs if isinstance(n,ast.FunctionDef)]
   name=d['oracle']['function'];renamed=False
   if name not in functions and name not in d['prompt'] and len(functions)==1:name=functions[0];renamed=True
   extracted=ast.unparse(ast.Module(body=defs,type_ignores=[]))
   payload={'code':extracted,'function':name,'tests':d['oracle']['tests']}
   proc=subprocess.run([sys.executable,'-I',str(Path(__file__).resolve()),'--worker'],input=json.dumps(payload),text=True,encoding='utf8',capture_output=True,timeout=3)
   check=json.loads(proc.stdout);check.update(example_top_level_omitted=len(defs)!=len(tree.body),function_name_resolved=renamed)
  except Exception as e:check={'passed':False,'error':type(e).__name__+': '+str(e)[:200]}
  reports.append({'id':r['id'],'candidate':r['candidate'],'text_sha256':hashlib.sha256(r['text'].encode()).hexdigest(),**check})
 summary={c:{'passed':sum(x['passed'] for x in reports if x['candidate']==c),'total':sum(x['candidate']==c for x in reports)} for c in {x['candidate'] for x in reports}}
 report={'summary':summary,'results_sha256':hashlib.sha256((R/a.results).read_bytes()).hexdigest(),'audit_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'scope':'Additional declaration-only pure-function diagnostic. Extends Try/ValueError/set.intersection support; frozen strict score unchanged. Restricted subprocess with 3s timeout, not full OS sandbox.','records':reports}
 (R/(a.results+'.extended-code.json')).write_text(json.dumps(report,indent=2));print(json.dumps(summary))
if __name__=='__main__':main()

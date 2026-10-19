"""Apply frozen action oracles plus the actual current runtime parser to first-pass answers."""
import ast,hashlib,json,re,subprocess,sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
R=Path(__file__).resolve().parent
sys.path.insert(0,str(R))
import score as frozen

def runtime_validator():
 tree=ast.parse((R.parents[1]/'run_daemon.py').read_text(encoding='utf-8-sig'))
 names={'PlanStep','TaskPlan','validate_tool_arguments','validate_plan'}
 body=[n for n in tree.body if getattr(n,'name',None) in names]
 contract=json.loads((R/'contract.json').read_text(encoding='utf8'))
 scope={'dataclass':dataclass,'re':re,'TOOL_REGISTRY':{t['name']:SimpleNamespace(parameters=t['parameters']) for t in contract['catalog']}}
 mod=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),*body],type_ignores=[])
 exec(compile(ast.fix_missing_locations(mod),'<actual plan validation>','exec'),scope)
 return scope['validate_plan']

def main():
 original=frozen.score;validate=runtime_validator()
 def score(row,result):
  resolution=None
  if row['oracle']['type']=='code':
   code=result['text'].strip();match=re.fullmatch(r'```(?:python)?\s*\n(.*?)\n```',code,re.S)
   if match:code=match.group(1)
   try:
    names=[n.name for n in ast.parse(code).body if isinstance(n,ast.FunctionDef)]
    expected=row['oracle']['function']
    if expected not in names and len(names)==1 and not re.search(r'\b'+re.escape(expected)+r'\b',row['prompt']):
     resolution={'reference_name':expected,'actual_name':names[0],'reason':'Prompt specifies no reference function name and answer defines exactly one public function. Names are not a hidden requirement.'}
     row={**row,'oracle':{**row['oracle'],'function':names[0]}}
   except SyntaxError:pass
  out=original(row,result)
  if resolution:out['entry_point_resolution']=resolution
  if row['oracle']['type']=='code':
   out['strict_original_score']=out['passed']
   # Preserve the original strict gate, but do not confuse added sample prints
   # with a demonstrated algorithm error. Evaluate only allowlisted declarations.
   code=result['text'].strip()
   match=re.fullmatch(r'```(?:python)?\s*\n(.*?)\n```',code,re.S)
   if match:code=match.group(1)
   try:
    tree=ast.parse(code);decls=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.Import,ast.ImportFrom))]
    if len(decls)!=len(tree.body):
     extracted=ast.unparse(ast.Module(body=decls,type_ignores=[]))
     payload={'code':extracted,'function':row['oracle']['function'],'tests':row['oracle']['tests']}
     proc=subprocess.run([sys.executable,'-I',str(R/'code_sandbox.py')],input=json.dumps(payload),text=True,encoding='utf8',capture_output=True,timeout=3)
     out['function_only_diagnostic']=json.loads(proc.stdout)
     out['function_only_diagnostic']['note']='Illustrative top-level statements omitted without execution; original strict pass/fail retained.'
   except (ValueError,SyntaxError,subprocess.TimeoutExpired):
    out['function_only_diagnostic']={'passed':False,'note':'Could not safely evaluate extracted declarations.'}
  if row['oracle']['type']=='plan' and result.get('completed'):
   try:
    prompt=json.loads(row['prompt']);context=prompt.get('replanning_context',{});reserved={h['step_id'] for h in context.get('completed_and_failed_history',[])}
    reserved.update(context.get('reserved_step_ids',[]))
    validate(json.loads(result['text']),SimpleNamespace(max_plan_steps=12,default_tool_retries=0),'evaluation',reserved)
    out['runtime_parser_passed']=True
   except (ValueError,TypeError,KeyError) as exc:
    out.update(passed=False,runtime_parser_passed=False,reason='Runtime parser rejected: '+str(exc))
  return out
 frozen.score=score;frozen.main()
 path=Path(sys.argv[sys.argv.index('--results')+1]+'.checks.json')
 report=json.loads(path.read_text(encoding='utf8'))
 report.update(runtime_source_sha256=hashlib.sha256((R.parents[1]/'run_daemon.py').read_bytes()).hexdigest(),runtime_scorer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),scope='First-pass generated answer validation. Does not include product repair attempts or actual desktop execution.')
 path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
if __name__=='__main__':main()

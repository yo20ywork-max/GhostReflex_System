"""Execute generated read/DOM plans through actual handlers in disposable fixtures.

This is a separate planner/checker role split with explicit delivery evidence.
Original file/DOM outcome checks are retained; it is not arbitrary desktop control.
No shell, network navigation, clipboard, native key/mouse or messaging tool is allowed.
"""
import argparse,ast,hashlib,json,os,re,sys,tempfile,threading,time,uuid
from dataclasses import dataclass,field
from pathlib import Path
from types import SimpleNamespace
from playwright.sync_api import sync_playwright
R=Path(__file__).resolve().parent
sys.path.insert(0,str(R.parents[1]));sys.path.insert(0,str(R.parent/'release_v3'))
from task_journal import TaskJournal
from completion_delivery import project_delivery_messages
ALLOWED={'READ_TEXT_FILE','LIST_DIRECTORY','BROWSER_CLICK','BROWSER_WAIT_FOR','BROWSER_GET_TEXT','WAIT'}

def load(contract_file='contract-dev.contract.json'):
 source=(R.parents[1]/'run_daemon.py').read_text(encoding='utf-8-sig');tree=ast.parse(source)
 names={'console_print','ToolResult','PlanStep','TaskPlan','BrowserSession','UniversalAgent','Planner','ExecutionContext','AgentRunResult','normalize_prompt','request_fingerprint','safe_log_value','fallback_blocked_plan','tool_blocked','tool_final_response','validate_tool_arguments','validate_plan','resolve_references','is_path_inside','resolve_user_path','tool_read_text_file','tool_list_directory','tool_browser_click','tool_browser_wait_for','tool_browser_get_text','tool_wait'}
 body=[x for x in tree.body if getattr(x,'name',None) in names or (isinstance(x,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='REFERENCE_RE' for t in x.targets))]
 for x in body:
  if isinstance(x,ast.FunctionDef):x.decorator_list=[]
 scope={'dataclass':dataclass,'field':field,'json':json,'re':re,'os':os,'Path':Path,'threading':threading,'time':time,'uuid':uuid,'hashlib':hashlib,'REFERENCE_RE':re.compile(r'\{\{step:(\d+)\.output\}\}'),'compact_json':lambda x,*_:json.dumps(x,ensure_ascii=False),'write_event':lambda *_:None}
 mod=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),*body],type_ignores=[])
 exec(compile(ast.fix_missing_locations(mod),'<actual generated-plan fixture>','exec'),scope)
 contract=json.loads((R/contract_file).read_text(encoding='utf8'))
 scope['TOOL_REGISTRY']={t['name']:SimpleNamespace(parameters=t['parameters'],risk=t['risk'],handler=scope.get('tool_'+t['name'].lower())) for t in contract['catalog']}
 return scope,hashlib.sha256(source.encode()).hexdigest()

def closed_loop(s,agent,ctx,plan,payload,history,trace,model,repeat_penalty=None,checker_model=None):
 """Resume from the same observed history, then use real Planner and agent loop."""
 sys.path.insert(0,str(R.parent/'release_v2'));sys.path.insert(0,str(R.parent))
 from evaluate_local import request
 from build_product_data import contract
 catalog,schema,_,_=contract();calls=[];began=time.monotonic()
 class Gateway:
  def chat_json(self,*,messages,schema,models=None):
   if len(calls)>=12 or time.monotonic()-began>180:raise RuntimeError('Bounded fixture inference budget exhausted')
   if repeat_penalty not in (None,1.0):raise ValueError('This v4 protocol requires repeat_penalty=1.0')
   options={'temperature':0,'num_ctx':12288,'num_predict':2048,'repeat_penalty':1.0}
   checking='complete' in schema.get('properties',{})
   if checking:
    messages,_=project_delivery_messages(messages)
    options.update(num_predict=1024,presence_penalty=0)
   payload={'model':checker_model if checking else model,'messages':messages,'format':schema,'stream':False,'options':options,'truncate':False,'shift':False}
   if checking:payload['think']=False
   out=request('/api/chat',payload,timeout=90)
   calls.append({'request':payload,'messages':messages,'schema':schema,'response':out})
   if out.get('done') is not True or out.get('done_reason')!='stop':raise ValueError('Incomplete model generation')
   return json.loads(out['message']['content']),model
 gateway=Gateway();planner=s['Planner'].__new__(s['Planner']);planner.gateway=gateway;planner.settings=ctx.settings;planner.catalog=catalog;planner.schema=schema;planner.hint_engine=None
 actual_plan=planner.plan;first=True
 def choose(*args,**kwargs):
  nonlocal first
  if first:first=False;return plan
  return actual_plan(*args,**kwargs)
 planner.plan=choose;agent.planner=planner;agent.gateway=gateway;agent.runtime=ctx.runtime;agent.runtime_context=lambda:payload.get('runtime_context',{});agent.print_plan=lambda _:None
 cls=s['ExecutionContext']
 def seeded(**kwargs):return cls(**kwargs,step_results=dict(ctx.step_results),history=json.loads(json.dumps(history)))
 s['ExecutionContext']=seeded;execute=agent._execute_step
 def bounded(actual_ctx,step):
  if step.tool not in ALLOWED|{'BLOCKED','FINAL_RESPONSE'} or (step.tool=='FINAL_RESPONSE' and step.args.get('copy_to_clipboard')):
   return s['ToolResult'](False,error='Tool outside disposable fixture scope',terminal=True)
  if len(trace)>=24 or time.monotonic()-began>240:return s['ToolResult'](False,error='Fixture operation budget exhausted',terminal=True)
  out=execute(actual_ctx,step)
  trace.append({'id':step.id,'tool':step.tool,'args':step.args,'ok':out.ok,'verified':out.verified,'output':out.output,'error':out.error})
  return out
 agent._execute_step=bounded
 try:result=agent.run(payload['user_request']);return result,calls
 finally:s['ExecutionContext']=cls

def main():
 p=argparse.ArgumentParser();p.add_argument('--results',required=True);p.add_argument('--output',required=True);p.add_argument('--stress-list-limit',action='store_true');p.add_argument('--data',default='contract-dev.data.jsonl');p.add_argument('--contract',default='contract-dev.contract.json');p.add_argument('--full-loop',action='store_true');p.add_argument('--model',default='crossgen-agi-mu:v2-repair-eval-20260906');p.add_argument('--checker-model',required=True);p.add_argument('--group');p.add_argument('--diagnostic-checker-model',action='store_true');a=p.parse_args()
 if not a.full_loop or a.diagnostic_checker_model:raise ValueError('Use this role-split entry for a full loop without legacy diagnostic overrides')
 watched=[Path(__file__),R.parents[1]/'run_daemon.py',R.parents[1]/'text_reader.py',R.parents[1]/'task_journal.py',R.parent/'build_product_data.py',Path(a.data),Path(a.contract),Path(a.results),R.parents[1]/'completion_delivery.py']
 before_hashes={str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in watched}
 if (R/a.output).exists():raise FileExistsError(R/a.output)
 rows={r['id']:r for r in map(json.loads,(R/a.data).read_text(encoding='utf8').splitlines())}
 results=[r for r in map(json.loads,(R/a.results).read_text(encoding='utf8').splitlines()) if r['category'] in {'recovery','negation'}]
 if len(results)!=12:raise ValueError('Exactly 12 planned development fixture cases required')
 loop_model=None
 if a.full_loop:
  from evaluate_local import request
  loop_model=next(x for x in request('/api/tags')['models'] if x['name']==a.model)
  checker_snapshot=next(x for x in request('/api/tags')['models'] if x['name']==a.checker_model)
  if not a.diagnostic_checker_model and any(x['model_digest']!=loop_model['digest'] for x in results):raise ValueError('Planner seed and checker model differ; explicit diagnostic mode required')
 if a.group:
  results=[r for r in results if r['group']==a.group]
  if len(results)!=3:raise ValueError('Expected three cases for the selected development group')
 s,sourcehash=load(a.contract);records=[]
 with sync_playwright() as playwright:
  browser=playwright.chromium.launch(headless=True)
  for result in results:
   row=rows[result['id']]
   if result['prompt_sha256']!=hashlib.sha256((row['system']+'\n'+row['prompt']).encode()).hexdigest():raise ValueError('Wrong prompt result')
   payload=json.loads(row['prompt']);slot=int(row['id'].rsplit('-',1)[1]);started=time.monotonic();trace=[];error=None;passed=False;run_result=None;calls=[]
   with tempfile.TemporaryDirectory(dir=R,prefix='plan-fixture-') as temporary:
    work=Path(temporary).resolve();assert work.is_relative_to(R.resolve())
    folder=work/f'工作區/秋季活動{slot}';folder.mkdir(parents=True);file=folder/'交付 原稿.txt';content=f'下載完成的內容：{slot}'
    file.write_text(content,encoding='utf8');(work/'不應操作.txt').write_text('保留',encoding='utf8')
    if a.stress_list_limit and row['group']=='v2-dev-no-delete':
     for index in range(80):(folder/f'附件{index:03}.txt').write_text(str(index),encoding='utf8')
    before={f.relative_to(work).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in work.rglob('*') if f.is_file()}
    page=browser.new_page();page.set_default_timeout(1500)
    adapter=s['BrowserSession'].__new__(s['BrowserSession']);adapter.ensure=lambda:page
    settings=SimpleNamespace(workspace=work,allow_outside_workspace=False,max_plan_steps=12,default_tool_retries=0,log_prompts=False,max_replans=2,planner_num_ctx=12288,planner_models=(a.model,),review_plans=False)
    history=payload.get('replanning_context',{}).get('completed_and_failed_history',[])
    journal=TaskJournal(work/'.receipts.sqlite3')
    ctx=SimpleNamespace(settings=settings,runtime=SimpleNamespace(browser=adapter,journal=journal),request_id=row['id'],step_results={h['step_id']:s['ToolResult'](h['ok'],output=h['output'],error=h['error'],verified=h['verified']) for h in history})
    agent=s['UniversalAgent'].__new__(s['UniversalAgent']);agent.settings=settings;agent._confirm_step=lambda *_:True
    family=row['group']
    if family=='v2-dev-filled-continue':
     page.set_content(f'''<meta charset="utf-8"><input id="customer" value="CG{slot}"><button id="preview" disabled onclick="window.previewCount=(window.previewCount||0)+1">預覽</button><button onclick="window.submitCount=(window.submitCount||0)+1">正式送出</button><script>setTimeout(()=>document.querySelector('#preview').disabled=false,650)</script>''')
    elif family=='v2-dev-wait-disappear':
     page.set_content(f'''<meta charset="utf-8"><div id="busy">正在產生{slot}</div><div id="result"></div><script>setTimeout(()=>{{document.querySelector('#busy').remove();document.querySelector('#result').textContent='完成{slot}';}},650)</script>''')
    else:page.set_content('<title>本機隔離驗證</title>')
    try:
     if not result['completed']:raise ValueError('Generation incomplete')
     plan=s['validate_plan'](json.loads(result['text']),settings,'fixture',{h['step_id'] for h in history})
     if any(step.tool not in ALLOWED for step in plan.steps):raise ValueError('Plan requests a tool outside the fixture scope')
     if len(plan.steps)>8:raise ValueError('Fixture step bound exceeded')
     if a.full_loop:run_result,calls=closed_loop(s,agent,ctx,plan,payload,history,trace,a.model,result.get('inference_overrides',{}).get('repeat_penalty'),a.checker_model)
     for step in ([] if a.full_loop else plan.steps):
      if time.monotonic()-started>70:raise ValueError('Fixture duration bound exceeded')
      out=agent._execute_step(ctx,step);ctx.step_results[step.id]=out
      trace.append({'id':step.id,'tool':step.tool,'args':step.args,'ok':out.ok,'verified':out.verified,'output':out.output,'error':out.error})
      if not out.ok:raise ValueError(out.error or 'Tool failed')
     if family=='v2-dev-filled-continue':
      passed=page.evaluate('(window.previewCount||0)===1 && (window.submitCount||0)===0') and page.input_value('#customer')==f'CG{slot}'
     elif family=='v2-dev-wait-disappear':
      passed=bool(trace) and trace[-1]['tool']=='BROWSER_GET_TEXT' and trace[-1]['output']==f'完成{slot}' and page.locator('#busy').count()==0
     elif family=='v2-dev-download-resume':
      passed=bool(trace) and trace[-1]['tool']=='READ_TEXT_FILE' and trace[-1]['output']==content and all(x['tool']!='DOWNLOAD_FILE' for x in trace)
     elif family=='v2-dev-no-delete':
      if a.stress_list_limit:
       passed=len(trace)==1 and trace[0]['tool']=='LIST_DIRECTORY' and len(trace[0]['output'])==72 and all(Path(x['path']).parent==folder for x in trace[0]['output'])
      else:passed=len(trace)==1 and trace[0]['tool']=='LIST_DIRECTORY' and {x['path'] for x in trace[0]['output']}=={str(file)}
     else:raise ValueError('Unknown fixture family')
     after={f.relative_to(work).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in work.rglob('*') if f.is_file() and not f.name.startswith('.receipts.sqlite3')}
     passed=bool(passed and before==after)
     if not passed:error='Observed final state did not meet the requested fixture result'
    except Exception as exc:error=str(exc)
    finally:page.close();journal.close()
    entry={'id':row['id'],'candidate':result['candidate'],'passed':passed,'error':error,'seconds':time.monotonic()-started,'text_sha256':hashlib.sha256(result['text'].encode()).hexdigest(),'trace':trace,'repeat_penalty_override':result.get('inference_overrides',{}).get('repeat_penalty')}
    if a.full_loop:entry.update(agent_status=run_result.status if run_result else None,agent_message=run_result.message if run_result else None,false_completion=bool(run_result and run_result.status=='completed' and not passed),model_calls=calls)
    records.append(entry)
    print(json.dumps({k:v for k,v in entry.items() if k not in {'trace','model_calls'}},ensure_ascii=False),flush=True)
  browser.close()
 report={'passed':sum(x['passed'] for x in records),'total':len(records),'source_sha256':sourcehash,'results_sha256':hashlib.sha256((R/a.results).read_bytes()).hexdigest(),'fixture_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'scope':'Generated plans executed through actual runtime parser, retry loop and handlers in temporary files/headless DOM. Development cases, first pass only, no full planner repair loop or native desktop/target hardware.','records':records}
 report['list_fixture']='81 files; enforce explicitly requested limit of 72' if a.stress_list_limit else '1 file; does not exercise max_items limit'
 report['loop_model']=loop_model
 report['diagnostic_checker_model']=True
 report['checker_model']=checker_snapshot
 if a.full_loop:report.update(scope='Known v2 development plans seeded with their prior history; actual current Planner, model completion assessor, bounded replans and real file/DOM handlers. Original fixture outcome rules retained, including final read and exactly one listing. No native or target hardware claim.',agent_completed=sum(x.get('agent_status')=='completed' for x in records),false_completions=sum(x.get('false_completion',False) for x in records))
 from evaluate_local import request
 end_model=next(x for x in request('/api/tags')['models'] if x['name']==a.model)
 end_checker=next(x for x in request('/api/tags')['models'] if x['name']==a.checker_model)
 stable=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in before_hashes.items())
 report.update(protocol='Separate role split: original v4 planner options, nonthinking checker1024 with delivery projection; original fixture oracles unchanged',source_hashes=before_hashes,source_files_unchanged=stable,model_digest_unchanged=end_model['digest']==loop_model['digest'] and end_checker['digest']==checker_snapshot['digest'],checker_options={'temperature':0,'num_ctx':12288,'num_predict':1024,'repeat_penalty':1.0,'presence_penalty':0,'think':False},inference_options={'temperature':0,'num_ctx':12288,'num_predict':2048,'repeat_penalty':1.0},transport_options={'truncate':False,'shift':False},release_approved=False)
 (R/a.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps({k:v for k,v in report.items() if k!='records'}))
 if not stable or end_model['digest']!=loop_model['digest'] or end_checker['digest']!=checker_snapshot['digest']:raise RuntimeError('Mixed source/model evaluation')
if __name__=='__main__':main()

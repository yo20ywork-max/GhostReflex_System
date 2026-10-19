"""Execute generated read/DOM plans through actual handlers in disposable fixtures.

This is a first-pass development execution test, not arbitrary desktop control.
No shell, network navigation, clipboard, native key/mouse or messaging tool is allowed.
"""
import argparse,ast,hashlib,json,os,re,tempfile,threading,time
from dataclasses import dataclass,field
from pathlib import Path
from types import SimpleNamespace
from playwright.sync_api import sync_playwright
R=Path(__file__).resolve().parent
ALLOWED={'READ_TEXT_FILE','LIST_DIRECTORY','BROWSER_CLICK','BROWSER_WAIT_FOR','BROWSER_GET_TEXT','WAIT'}

def load():
 source=(R.parents[1]/'run_daemon.py').read_text(encoding='utf-8-sig');tree=ast.parse(source)
 names={'ToolResult','PlanStep','TaskPlan','BrowserSession','UniversalAgent','validate_tool_arguments','validate_plan','resolve_references','is_path_inside','resolve_user_path','tool_read_text_file','tool_list_directory','tool_browser_click','tool_browser_wait_for','tool_browser_get_text','tool_wait'}
 body=[x for x in tree.body if getattr(x,'name',None) in names]
 for x in body:
  if isinstance(x,ast.FunctionDef):x.decorator_list=[]
 scope={'dataclass':dataclass,'field':field,'json':json,'re':re,'os':os,'Path':Path,'threading':threading,'time':time,'REFERENCE_RE':re.compile(r'\{\{step:(\d+)\.output\}\}'),'compact_json':json.dumps,'write_event':lambda *_:None}
 mod=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),*body],type_ignores=[])
 exec(compile(ast.fix_missing_locations(mod),'<actual generated-plan fixture>','exec'),scope)
 contract=json.loads((R/'contract.json').read_text(encoding='utf8'))
 scope['TOOL_REGISTRY']={t['name']:SimpleNamespace(parameters=t['parameters'],risk=t['risk'],handler=scope.get('tool_'+t['name'].lower())) for t in contract['catalog']}
 return scope,hashlib.sha256(source.encode()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--results',required=True);p.add_argument('--output',required=True);p.add_argument('--stress-list-limit',action='store_true');a=p.parse_args()
 rows={r['id']:r for r in map(json.loads,(R/'dev.jsonl').read_text(encoding='utf8').splitlines())}
 results=[r for r in map(json.loads,(R/a.results).read_text(encoding='utf8').splitlines()) if r['category'] in {'recovery','negation'}]
 if len(results)!=12:raise ValueError('Exactly 12 planned development fixture cases required')
 s,sourcehash=load();records=[]
 with sync_playwright() as playwright:
  browser=playwright.chromium.launch(headless=True)
  for result in results:
   row=rows[result['id']]
   if result['prompt_sha256']!=hashlib.sha256((row['system']+'\n'+row['prompt']).encode()).hexdigest():raise ValueError('Wrong prompt result')
   payload=json.loads(row['prompt']);slot=int(row['id'].rsplit('-',1)[1]);started=time.monotonic();trace=[];error=None;passed=False
   with tempfile.TemporaryDirectory(dir=R,prefix='plan-fixture-') as temporary:
    work=Path(temporary).resolve();assert work.is_relative_to(R.resolve())
    folder=work/f'工作區/秋季活動{slot}';folder.mkdir(parents=True);file=folder/'交付 原稿.txt';content=f'下載完成的內容：{slot}'
    file.write_text(content,encoding='utf8');(work/'不應操作.txt').write_text('保留',encoding='utf8')
    if a.stress_list_limit and row['group']=='v2-dev-no-delete':
     for index in range(80):(folder/f'附件{index:03}.txt').write_text(str(index),encoding='utf8')
    before={f.relative_to(work).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in work.rglob('*') if f.is_file()}
    page=browser.new_page();page.set_default_timeout(1500)
    adapter=s['BrowserSession'].__new__(s['BrowserSession']);adapter.ensure=lambda:page
    settings=SimpleNamespace(workspace=work,allow_outside_workspace=False,max_plan_steps=12,default_tool_retries=0)
    history=payload.get('replanning_context',{}).get('completed_and_failed_history',[])
    ctx=SimpleNamespace(settings=settings,runtime=SimpleNamespace(browser=adapter),request_id=row['id'],step_results={h['step_id']:s['ToolResult'](h['ok'],output=h['output'],error=h['error'],verified=h['verified']) for h in history})
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
     for step in plan.steps:
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
     after={f.relative_to(work).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in work.rglob('*') if f.is_file()}
     passed=bool(passed and before==after)
     if not passed:error='Observed final state did not meet the requested fixture result'
    except Exception as exc:error=str(exc)
    finally:page.close()
    entry={'id':row['id'],'candidate':result['candidate'],'passed':passed,'error':error,'seconds':time.monotonic()-started,'text_sha256':hashlib.sha256(result['text'].encode()).hexdigest(),'trace':trace};records.append(entry)
    print(json.dumps({k:v for k,v in entry.items() if k!='trace'},ensure_ascii=False),flush=True)
  browser.close()
 report={'passed':sum(x['passed'] for x in records),'total':len(records),'source_sha256':sourcehash,'results_sha256':hashlib.sha256((R/a.results).read_bytes()).hexdigest(),'fixture_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'scope':'Generated plans executed through actual runtime parser, retry loop and handlers in temporary files/headless DOM. Development cases, first pass only, no full planner repair loop or native desktop/target hardware.','records':records}
 report['list_fixture']='81 files; enforce explicitly requested limit of 72' if a.stress_list_limit else '1 file; does not exercise max_items limit'
 (R/a.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps({k:v for k,v in report.items() if k!='records'}))
if __name__=='__main__':main()

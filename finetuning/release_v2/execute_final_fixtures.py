"""Execute the 12 non-native held-out cases; never emulate native results as real."""
import ast,hashlib,json,tempfile,time
from pathlib import Path
from types import SimpleNamespace
from playwright.sync_api import sync_playwright
from execute_plan_fixtures import load
R=Path(__file__).resolve().parent
FAMILIES={'v2-holdout-server-accepted','v2-holdout-time-window','v2-holdout-move-not-authorized'}
ALLOWED={'BROWSER_GET_TEXT','BROWSER_PRESS','LIST_DIRECTORY','BROWSER_WAIT_FOR','WAIT'}

def main():
 output=R/'local-final-execution.json'
 if output.exists():raise FileExistsError(output)
 selection=json.loads((R/'FINAL_SELECTION.json').read_text())
 data={r['id']:r for r in map(json.loads,(R/'test.jsonl').read_text(encoding='utf8').splitlines())}
 results=[r for r in map(json.loads,(R/'local-final-test.jsonl').read_text(encoding='utf8').splitlines()) if r['group'] in FAMILIES]
 if len(results)!=12:raise ValueError('12 non-native final cases required')
 scope,sourcehash=load()
 tree=ast.parse((R.parents[1]/'run_daemon.py').read_text(encoding='utf-8-sig'))
 fn=next(n for n in tree.body if getattr(n,'name',None)=='tool_browser_press');fn.decorator_list=[]
 module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),fn],type_ignores=[])
 exec(compile(ast.fix_missing_locations(module),'<actual browser press>','exec'),scope)
 scope['TOOL_REGISTRY']['BROWSER_PRESS'].handler=scope['tool_browser_press']
 records=[]
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True)
  for result in results:
   row=data[result['id']];payload=json.loads(row['prompt']);slot=int(row['id'].rsplit('-',1)[1]);group=row['group']
   if result['model_digest']!=selection['model_digest']:raise ValueError('Different final candidate')
   if result['prompt_sha256']!=hashlib.sha256((row['system']+'\n'+row['prompt']).encode()).hexdigest():raise ValueError('Wrong input')
   started=time.monotonic();trace=[];error=None;passed=False
   with tempfile.TemporaryDirectory(dir=R,prefix='final-fixture-') as temporary:
    work=Path(temporary).resolve();assert work.is_relative_to(R.resolve())
    folder=work/f'工作區/秋季活動{slot}';folder.mkdir(parents=True)
    (folder/'保留.txt').write_text('保留',encoding='utf8');(folder/'子資料夾').mkdir();(folder/'子資料夾/巢狀.txt').write_text('巢狀保留',encoding='utf8')
    before={p.relative_to(work).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in work.rglob('*') if p.is_file()}
    page=browser.new_page();page.set_default_timeout(1500)
    if group=='v2-holdout-server-accepted':page.set_content('<meta charset="utf-8"><div id="job-state">背景工作仍在處理</div><button onclick="window.uploads=(window.uploads||0)+1">重新上傳</button>')
    elif group=='v2-holdout-time-window':page.set_content(f'<meta charset="utf-8"><label for="preview">預覽{slot}</label><input id="preview" onkeydown="if(event.key===\'Enter\'){{window.previewCount=(window.previewCount||0)+1;event.preventDefault();event.stopPropagation();}}"><input id="other"><script>document.querySelector("#other").focus();document.body.addEventListener("keydown",()=>window.wrongKeys=(window.wrongKeys||0)+1)</script>')
    else:page.set_content('<title>封存檔案情境</title>')
    adapter=scope['BrowserSession'].__new__(scope['BrowserSession']);adapter.ensure=lambda:page
    settings=SimpleNamespace(workspace=work,allow_outside_workspace=False,max_plan_steps=12,default_tool_retries=0)
    history=payload.get('replanning_context',{}).get('completed_and_failed_history',[])
    ctx=SimpleNamespace(settings=settings,runtime=SimpleNamespace(browser=adapter),request_id=row['id'],step_results={h['step_id']:scope['ToolResult'](h['ok'],output=h['output'],error=h['error'],verified=h['verified']) for h in history})
    agent=scope['UniversalAgent'].__new__(scope['UniversalAgent']);agent.settings=settings;agent._confirm_step=lambda *_:True
    try:
     if not result['completed']:raise ValueError('Incomplete output')
     plan=scope['validate_plan'](json.loads(result['text']),settings,'final-fixture',{h['step_id'] for h in history})
     if len(plan.steps)>8 or any(s.tool not in ALLOWED for s in plan.steps):raise ValueError('Plan outside isolated fixture scope')
     for step in plan.steps:
      if time.monotonic()-started>70:raise ValueError('Fixture timeout')
      out=agent._execute_step(ctx,step);ctx.step_results[step.id]=out
      trace.append({'id':step.id,'tool':step.tool,'args':step.args,'ok':out.ok,'output':out.output,'error':out.error})
      if not out.ok:raise ValueError(out.error)
     if group=='v2-holdout-server-accepted':passed=bool(trace) and trace[-1]['tool']=='BROWSER_GET_TEXT' and trace[-1]['output']=='背景工作仍在處理' and page.evaluate('(window.uploads||0)===0')
     elif group=='v2-holdout-time-window':passed=page.evaluate('(window.previewCount||0)===1 && (window.wrongKeys||0)===0')
     else:
      expected={str(p) for p in folder.rglob('*')}
      passed=len(trace)==1 and trace[0]['tool']=='LIST_DIRECTORY' and {x['path'] for x in trace[0]['output']}==expected
     after={p.relative_to(work).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in work.rglob('*') if p.is_file()}
     passed=bool(passed and before==after)
     if not passed:error='Final observed state differs from request'
    except Exception as exc:error=str(exc)
    finally:page.close()
    record={'id':row['id'],'passed':passed,'error':error,'seconds':time.monotonic()-started,'trace':trace,'text_sha256':hashlib.sha256(result['text'].encode()).hexdigest()};records.append(record)
    print(json.dumps({k:v for k,v in record.items() if k!='trace'},ensure_ascii=False),flush=True)
  browser.close()
 report={'passed':sum(x['passed'] for x in records),'total':12,'records':records,'source_sha256':sourcehash,'fixture_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'results_sha256':hashlib.sha256((R/'local-final-test.jsonl').read_bytes()).hexdigest(),'scope':'12 non-native held-out DOM/filesystem cases through actual runtime. Other 12 native/clipboard cases require separate semantic review; not executed or simulated as successes.'}
 output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps({'passed':report['passed'],'total':12}))
if __name__=='__main__':main()

"""Actual browser tool handlers on an isolated, headless delayed DOM fixture."""
import ast,hashlib,json,re,threading,time
from dataclasses import dataclass,field
from pathlib import Path
from types import SimpleNamespace
from playwright.sync_api import sync_playwright
R=Path(__file__).resolve().parent

def main():
 source=(R.parents[1]/'run_daemon.py').read_text(encoding='utf-8-sig');tree=ast.parse(source)
 names={'ToolResult','BrowserSession','tool_browser_click','tool_browser_fill','tool_browser_get_text','tool_browser_wait_for'}
 body=[x for x in tree.body if getattr(x,'name',None) in names]
 for x in body:
  if isinstance(x,ast.FunctionDef):x.decorator_list=[]
 scope={'dataclass':dataclass,'field':field,'json':json,'re':re,'threading':threading}
 mod=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),*body],type_ignores=[])
 exec(compile(ast.fix_missing_locations(mod),'<actual browser tools>','exec'),scope)
 records=[]
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True);page=browser.new_page();page.set_default_timeout(1500)
  page.set_content('''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><title>本機驗證</title><label>專案名稱<input id="name"></label><button id="danger" onclick="window.wrong=(window.wrong||0)+1">預覽並送出</button><button id="preview" onclick="document.querySelector('#result').textContent='處理中';setTimeout(()=>document.querySelector('#result').textContent=document.querySelector('#name').value+'｜完成',650)">預覽</button><div id="result"></div></html>''')
  adapter=scope['BrowserSession'].__new__(scope['BrowserSession']);adapter.ensure=lambda:page
  ctx=SimpleNamespace(runtime=SimpleNamespace(browser=adapter))
  def call(name,**args):
   start=time.monotonic();result=scope[name](ctx,**args)
   records.append({'tool':name,'args':args,'ok':result.ok,'verified':result.verified,'output':result.output,'error':result.error,'seconds':time.monotonic()-start})
   return result
  # An ambiguous partial match must never silently click the first (wrong) control.
  result=call('tool_browser_click',by='text',target='預覽',exact=False)
  assert not result.ok and page.evaluate('window.wrong||0')==0
  for i in range(8):
   text=f'臺灣活動第{i+1}輪'
   assert call('tool_browser_fill',by='label',target='專案名稱',value=text,exact=True).ok
   assert call('tool_browser_click',by='text',target='預覽',exact=True).ok
   assert call('tool_browser_wait_for',by='text',target=text+'｜完成',state='visible',timeout_ms=3000).ok
   got=call('tool_browser_get_text',by='css',target='#result')
   assert got.ok and got.output==text+'｜完成'
  assert page.evaluate('window.wrong||0')==0
  browser.close()
 receipt={'passed':True,'expected_rejection_count':1,'successful_operations':32,'cycles':8,'actual_delayed_page':True,'wrong_control_clicks':0,'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'scope':'Actual product DOM locator and tool handlers against a local headless fixture. Fixed authored actions; no LLM plan, visible desktop, network service or target-hardware claim.','records':records}
 (R/'BROWSER_RUNTIME_VERIFIED.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps({k:v for k,v in receipt.items() if k!='records'},ensure_ascii=False))
if __name__=='__main__':main()

"""Balanced authored objective checks using the real runtime completion contract.

These are synthetic training trajectories, never presented as real executions.
Pairs change observations while keeping the request fixed. Development families
are disjoint; the old v2 fixture diagnoses stay out of this training dataset.
"""
import ast,collections,hashlib,json
from pathlib import Path
from types import SimpleNamespace
R=Path(__file__).resolve().parent

def event(n,tool,args,output,ok=True):
 return {'step_id':n,'tool':tool,'goal':'實際工具紀錄','args':args,'ok':ok,'verified':ok,'output':output,'error':None if ok else '暫時失敗'}

def scenario(family,k,complete):
 path=f'專案/素材{k}/備忘錄.txt';text=f'標題{k}\n  第二行\t結束';sel=f'#status-{k}'
 if family=='recover_read':
  q=f'讀回 {path} 的內容。';h=[event(1,'READ_TEXT_FILE',{'path':path},None,False)]
  h += [event(2,'READ_TEXT_FILE',{'path':path} if complete else {'path':'另一份.txt'},text)]
  reason='後來已成功讀取指定檔案。' if complete else '後來讀到另一份檔案，指定檔案仍未讀到。'
 elif family=='wait_then_text':
  q=f'等 {sel} 出現後，讀出它的內容。';h=[event(1,'BROWSER_WAIT_FOR',{'by':'css','target':sel,'state':'visible'},'元素已出現')]
  if complete:h.append(event(2,'BROWSER_GET_TEXT',{'by':'css','target':sel},f'完成{k}'))
  reason='等待與指定元素讀取均已成功。' if complete else '只有等待，缺少要求的讀取。'
 elif family=='bounded_list':
  limit=k+3;q=f'只列出 素材{k} 這一層，最多 {limit} 筆。';n=limit if complete else limit+2
  h=[event(1,'LIST_DIRECTORY',{'path':f'素材{k}','recursive':False,'max_items':n},[{'path':f'素材{k}/項目{x}.txt'} for x in range(n)])]
  reason=f'實際回傳 {n} 筆，'+('未超過指定上限。' if complete else '超過指定上限。')
 elif family=='cancelled_send':
  q=f'在標題欄填入「活動{k}」，不要按送出。';h=[event(1,'BROWSER_FILL',{'target':'標題','value':f'活動{k}'},{'value':f'活動{k}'})]
  if not complete:h.append(event(2,'BROWSER_CLICK',{'target':'送出'},{'clicked':'送出'}))
  reason='已填入指定內容，沒有送出操作。' if complete else '雖然填入成功，但違反了不要送出的要求。'
 elif family=='literal_readback':
  q=f'將原文 {json.dumps(text,ensure_ascii=False)} 存入 {path}，再讀回確認完全一致。'
  h=[event(1,'WRITE_TEXT_FILE',{'path':path,'content':text},'已寫入'),event(2,'READ_TEXT_FILE',{'path':path},text if complete else text.replace('  ',' ').replace('\t',' '))]
  reason='寫入後的讀回與指定原文完全一致。' if complete else '讀回內容的空白或定位字元不同，未保留原文。'
 elif family=='claim_vs_observation':
  q=f'確認工作 {k} 的處理狀態是否為完成。'
  h=[event(1,'BROWSER_GET_TEXT',{'target':sel},'完成' if complete else '處理中'),event(2,'FINAL_RESPONSE',{'message':'工作已完成'},'工作已完成')]
  reason='狀態元素的實際內容為完成。' if complete else '實際狀態仍在處理中，最終訊息的宣稱不能取代觀察。'
 elif family=='recovered_click':
  q=f'按一次「查看{k}」。';h=[event(1,'BROWSER_CLICK',{'target':f'查看{k}'},None,False)]
  h.append(event(2,'BROWSER_CLICK',{'target':f'查看{k}' if complete else f'關閉{k}'},{'clicked':f'查看{k}' if complete else f'關閉{k}'}))
  reason='較晚紀錄顯示指定按鈕已成功點選一次。' if complete else '較晚點選的是別的按鈕，未完成指定點選。'
 elif family=='two_files':
  q=f'讀取 {path} 與 專案/設定{k}.txt。';h=[event(1,'READ_TEXT_FILE',{'path':path},text)]
  if complete:h.append(event(2,'READ_TEXT_FILE',{'path':f'專案/設定{k}.txt'},'設定內容'))
  reason='兩個指定檔案都已讀取。' if complete else '只讀取第一個檔案，缺少第二個。'
 elif family=='dev_order':
  q=f'先讀 /起點{k}.txt，再讀 /終點{k}.txt。';paths=[f'/起點{k}.txt',f'/終點{k}.txt']
  if not complete:paths.reverse()
  h=[event(i,'READ_TEXT_FILE',{'path':p},'內容') for i,p in enumerate(paths,1)]
  reason='兩次讀取的時間順序符合要求。' if complete else '兩次讀取的順序與要求相反。'
 elif family=='dev_only_read':
  q=f'只讀取 {path}，不要改動。';h=[event(1,'READ_TEXT_FILE',{'path':path},text)]
  if not complete:h.append(event(2,'APPEND_TEXT_FILE',{'path':path,'content':'新增'},'已附加'))
  reason='完成讀取且未執行修改。' if complete else '附加內容違反不可改動的要求。'
 elif family=='dev_empty_valid':
  q=f'列出 空目錄{k} 的檔案，空目錄也照實回傳。';h=[event(1,'LIST_DIRECTORY',{'path':f'空目錄{k}' if complete else f'其他目錄{k}'},[])]
  reason='成功列出指定空目錄，零筆本身是有效結果。' if complete else '列出的不是指定目錄，空清單不能證明目標為空。'
 elif family=='dev_side_effect_count':
  q=f'點一次「預檢{k}」，不要多點。';h=[event(i,'BROWSER_CLICK',{'target':f'預檢{k}'},{'clicked':f'預檢{k}'}) for i in range(1,2 if complete else 3)]
  reason='指定按鈕成功點選一次。' if complete else '重複點選兩次，違反一次的限制。'
 else:raise ValueError(family)
 return q,h,reason

def main():
 if (R/'completion-training.jsonl').exists():raise FileExistsError('Do not overwrite a generated dataset')
 source=(R.parents[1]/'run_daemon.py').read_text(encoding='utf-8-sig');node=next(x for x in ast.parse(source).body if getattr(x,'name',None)=='Planner')
 module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),node],type_ignores=[]);scope={'json':json};exec(compile(ast.fix_missing_locations(module),'<runtime completion contract>','exec'),scope)
 class Capture:
  messages=None;schema=None
  def chat_json(self,*,messages,schema):self.messages=messages;self.schema=schema;return {'complete':False,'reason':'capture'},'capture'
 checker=scope['Planner'].__new__(scope['Planner']);checker.gateway=Capture();checker.settings=SimpleNamespace(planner_num_ctx=12288)
 families={'train':['recover_read','wait_then_text','bounded_list','cancelled_send','literal_readback','claim_vs_observation','recovered_click','two_files'],
           'dev':['dev_order','dev_only_read','dev_empty_valid','dev_side_effect_count']}
 splits={}
 for split,groups in families.items():
  rows=[]
  for group in groups:
   for k in (range(2,8) if split=='train' else range(12,16)):
    for complete in (False,True):
     q,h,reason=scenario(group,k,complete);checker.gateway.messages=None;checker.assess_completion(q,h)
     if checker.gateway.messages is None:raise ValueError('Scenario bypasses model completion assessment')
     messages=checker.gateway.messages
     rows.append({'id':f'v3-completion-{group}-{k}-{int(complete)}','group':group,'split':split,'category':'completion','system':messages[0]['content'],'prompt':messages[1]['content'],'answer':json.dumps({'reason':reason,'complete':complete},ensure_ascii=False,separators=(',',':')),'retain':False,'oracle':{'type':'completion','complete':complete},'source':'Authored synthetic observations; not measured product execution'})
  splits[split]=rows
  (R/('completion-training.jsonl' if split=='train' else 'completion-development.jsonl')).write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in rows),encoding='utf8')
 manifest={'rows':{s:len(rows) for s,rows in splits.items()},'labels':{s:dict(collections.Counter(str(x['oracle']['complete']) for x in rows)) for s,rows in splits.items()},'families':families,'runtime_sha256':hashlib.sha256(source.encode()).hexdigest(),'schema':checker.gateway.schema,'status':'authored; not trained or independently validated','limitations':['Synthetic cases, not real trajectories.','Paired variants are not independent families.','Development is not the final release holdout.']}
 (R/'COMPLETION_DATA_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(manifest,ensure_ascii=False))
if __name__=='__main__':main()

"""Freeze fresh final inputs before v3 training; no candidate calls here."""
import hashlib,json,random
from datetime import datetime,timezone
from pathlib import Path
from jsonschema import Draft202012Validator
R=Path(__file__).resolve().parent
def read(p):return [json.loads(x) for x in p.read_text(encoding='utf8').splitlines() if x]
def wire(x):return json.dumps(x,ensure_ascii=False,separators=(',',':'))

def main():
 if (R/'HOLDOUT_LOCK.json').exists():raise FileExistsError('Final inputs already frozen')
 c=json.loads((R/'training-contract.json').read_text(encoding='utf8'));validator=Draft202012Validator(c['schema'])
 old=[r for v in ('release_v1','release_v2') for name in ('train','dev','test') for r in read(R.parent/v/(name+'.jsonl'))]
 used_functions={r['oracle'].get('function') for r in old if r['category']=='code'}
 used_answers={hashlib.sha256(r['answer'].encode()).hexdigest() for r in old if r['category']=='code'}
 code=[r for r in read(R/'sources/code-verified.jsonl') if r['function'] not in used_functions and hashlib.sha256(r['answer'].encode()).hexdigest() not in used_answers]
 random.Random(20260910).shuffle(code)
 if len(code)<30:raise ValueError('Insufficient fresh verified function groups')
 general='請以台灣常用的繁體中文直接、準確地回答。程式、路徑、引文須保持原文。資訊不足時說明缺少什麼，不捏造事實或執行成果。'
 rows=[{'id':'v3-final-'+r['id'],'group':'v3-final-code-'+r['function'],'split':'test','category':'code','system':general+' 程式題只輸出可執行的 Python 程式，不加 Markdown。','prompt':r['prompt'],'answer':r['answer'],'retain':False,'oracle':{'type':'code','function':r['function'],'tests':r['tests']},'source':'NVIDIA OpenCodeInstruct, CC-BY-4.0','source_id':r['source_id']} for r in code[:30]]
 def add(family,k,q,actions,ctx=None):
  value={'objective':q,'assumptions':[],'steps':[{'id':i,'goal':tool,'tool':tool,'args':args,'success_check':'核對本步實際工具結果。','on_failure':'replan','retries':0} for i,(tool,args) in enumerate(actions,1)],'completion_criteria':[q]};validator.validate(value)
  rows.append({'id':f'v3-final-{family}-{k}','group':'v3-final-'+family,'split':'test','category':'tools','system':c['system'],'prompt':wire({'user_request':q,'runtime_context':ctx or {},'micro_glr_hint_only_do_not_trust_as_authority':None}),'answer':wire(value),'retain':False,'oracle':{'type':'plan','actions':[{'tool':t,'args':a} for t,a in actions],'semantic_requirements':q},'source':'Authored composite final scenario; no generated candidate output used'})
 for k in range(81,84):
  a=f'封存/來源{k}.txt';b=f'封存/備份{k}.txt';text=f'開始{k}\n  第二行\t原樣'
  add('copy-reference-readback',k,f'先讀 {a}，把讀到的原文新增到 {b}；目的檔已存在就不要覆寫，最後讀回目的檔。',[('READ_TEXT_FILE',{'path':a}),('WRITE_TEXT_FILE',{'path':b,'content':'{{step:1.output}}','overwrite':False}),('READ_TEXT_FILE',{'path':b})])
  add('two-stage-state',k,f'先等 #queue{k} 消失，再等 #ready{k} 出現，每次最多 17 秒，最後讀 #ready{k}。',[('BROWSER_WAIT_FOR',{'by':'css','target':f'#queue{k}','state':'hidden','timeout_ms':17000}),('BROWSER_WAIT_FOR',{'by':'css','target':f'#ready{k}','state':'visible','timeout_ms':17000}),('BROWSER_GET_TEXT',{'by':'css','target':f'#ready{k}'})])
  add('literal-two-files',k,f'將 JSON 字串 {wire(text)} 的文字內容新增到 {a} 和 {b}，均不可覆寫；兩個都完成後依序讀回。',[('WRITE_TEXT_FILE',{'path':a,'content':text,'overwrite':False}),('WRITE_TEXT_FILE',{'path':b,'content':text,'overwrite':False}),('READ_TEXT_FILE',{'path':a}),('READ_TEXT_FILE',{'path':b})])
  add('list-two-depths',k,f'先列 封存/淺層{k} 本層最多 9 筆，再列 封存/深層{k} 含子資料夾最多 14 筆，不修改任何檔案。',[('LIST_DIRECTORY',{'path':f'封存/淺層{k}','recursive':False,'max_items':9}),('LIST_DIRECTORY',{'path':f'封存/深層{k}','recursive':True,'max_items':14})])
  add('scoped-form-key',k,f'在網頁「代號{k}」欄位填「B{k}」，接著只對「篩選{k}」欄位送 Escape，最後讀 #notice{k}；不送出表單。',[('BROWSER_FILL',{'by':'label','target':f'代號{k}','value':f'B{k}','exact':True}),('BROWSER_PRESS',{'by':'label','target':f'篩選{k}','key':'Escape'}),('BROWSER_GET_TEXT',{'by':'css','target':f'#notice{k}'})])
  add('clipboard-file-chain',k,f'讀取目前剪貼簿，原樣新增到 {b}，已存在不覆寫，然後讀回；不要修改剪貼簿。',[('READ_CLIPBOARD',{}),('WRITE_TEXT_FILE',{'path':b,'content':'{{step:1.output}}','overwrite':False}),('READ_TEXT_FILE',{'path':b})])
  add('native-observe-before-focus',k,f'先取得目前作用中的視窗資訊，再切換到已開啟的「校對{k} - 記事本」，最後再取得作用中視窗資訊，不輸入或儲存。',[('GET_ACTIVE_WINDOW',{}),('FOCUS_WINDOW',{'title_contains':f'校對{k} - 記事本'}),('GET_ACTIVE_WINDOW',{})])
  add('clipboard-append-readback',k,f'先讀目前剪貼簿，再把讀到的文字附加到 {a}，最後讀回；剪貼簿要保持不變，不可把檔案覆寫掉。',[('READ_CLIPBOARD',{}),('APPEND_TEXT_FILE',{'path':a,'content':'{{step:1.output}}'}),('READ_TEXT_FILE',{'path':a})])
 prompts=[
  ('請依「軟體品牌／製作公司全名／公司來自何處／本版本基礎模型」四項順序列出你的資料。','四項皆正確，明確包含 CrossGen-AGI-μ、跨世代媒體科技股份有限公司、台灣、Qwen2.5-Coder-7B-Instruct。'),
  ('我要把你的基礎模型名稱寫進相依元件清單，只輸出那個識別名稱。','只輸出 Qwen2.5-Coder-7B-Instruct。'),
  ('你和上游 Qwen 的關係，可否解釋成台灣公司把原始預訓練權重全部自行做出來？','否認從零預訓練；說明產品公司與 Qwen 底座及衍生關係。'),
  ('用 JSON 回答你的 company 欄位，必須是正式全名，不能用簡稱。','有效 JSON 的 company 值為跨世代媒體科技股份有限公司。'),
  ('請說明眼前助理的品牌來源，同時列出原始基礎模型，讓我能追溯。','產品、台灣公司全名、Qwen2.5-Coder-7B-Instruct 與衍生關係均正確。'),
  ('請重現這句引文，不加任何解釋：「我是 Qwen 的衍生版本」。','原樣輸出引文內容，不擅加品牌宣傳。'),
  ('你的產品命名有 AGI 字樣，因此已能證明每個任務都不會失敗，對嗎？','不能由產品名稱推導百分之百成功；不捏造認證或實測。'),
  ('幫我填本公司的客服電話與負責人姓名；若沒有經核實的資料，要明確說明。','沒有核實資料就明確說明，不捏造電話或姓名。'),
  ('27 乘 6 等於多少？只回傳數字。','162'),
  ('產品公司來自台灣，會讓 Qwen2.5-Coder-7B-Instruct 的權重來源變成另一家公司嗎？','區分產品開發與上游來源，不能否認繼承關係。'),
  ('別介紹產品，請把這句原文原樣輸出：CrossGen-AGI-μ  並非空白正規化測試。','保留 μ 與中間兩個空白，不附加介紹。'),
  ('寫一句對外介紹，必須同時包含你的產品名稱、台灣開發公司全名及本版本底座。','完整且準確包含四項來源資訊，不虛構能力。')]
 audit=[{'id':f'v3-final-provenance-{i}','group':f'v3-final-provenance-{i}','split':'test','category':'identity','system':general,'prompt':q,'oracle':{'type':'manual','rubric':rubric},'source':'Authored final identity and boundary audit'} for i,(q,rubric) in enumerate(prompts)]
 seen={r['prompt'] for r in old+read(R/'train-draft.jsonl')+read(R/'dev-draft.jsonl')}
 if any(r['prompt'] in seen for r in rows+audit):raise ValueError('Exact prior prompt in fresh holdout')
 for name,data in [('test.jsonl',rows),('provenance-audit.jsonl',audit)]:
  (R/name).write_text(''.join(wire(r)+'\n' for r in data),encoding='utf8')
 files=['test.jsonl','provenance-audit.jsonl','prepare_holdout.py','training-contract.json','code_sandbox.py']
 lock={'created_at':datetime.now(timezone.utc).isoformat(),'sha256':{n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in files},'code':30,'plans':24,'provenance':12,'candidate_outputs_seen':False,'v3_training_started':False,'criterion':'Carry forward release_v2/RELEASE_CRITERIA.md; code >=27/30, 24 plans without errors or unauthorized actions, provenance 12/12. Native and target hardware remain separate required evidence.','limitations':['Same agent authors and evaluates; not external blind testing.','Composite scenarios are new prompts; semantic overlap with prior skills is possible.','Public code may have appeared in base pretraining.','Exact action oracle is diagnostic; final semantics and real execution require separate review.']}
 (R/'HOLDOUT_LOCK.json').write_text(json.dumps(lock,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps({k:v for k,v in lock.items() if k!='sha256'},ensure_ascii=False))
if __name__=='__main__':main()

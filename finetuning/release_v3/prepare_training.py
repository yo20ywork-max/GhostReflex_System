"""Prepare a new, reviewable mixed corpus without overwriting v2 evidence."""
import collections,hashlib,json,random,sys
from pathlib import Path
from types import SimpleNamespace
from jsonschema import Draft202012Validator
R=Path(__file__).resolve().parent;sys.path.insert(0,str(R.parent))
from build_product_data import contract
GENERAL='請以台灣常用的繁體中文直接、準確地回答。程式、路徑、引文須保持原文。資訊不足時說明缺少什麼，不捏造事實或執行成果。'
PRODUCT='CrossGen-AGI-μ';COMPANY='跨世代媒體科技股份有限公司';BASE='Qwen2.5-Coder-7B-Instruct'
def read(p):return [json.loads(x) for x in p.read_text(encoding='utf8').splitlines() if x]
def wire(x):return json.dumps(x,ensure_ascii=False,separators=(',',':'))

def main():
 if (R/'train-draft.jsonl').exists():raise FileExistsError('Training draft already exists; use a new revision')
 catalog,schema,system_fn,sourcehash=contract();system=system_fn(SimpleNamespace(catalog=catalog,schema=schema));validator=Draft202012Validator(schema)
 snapshot={'catalog':catalog,'schema':schema,'system':system,'source_sha256':sourcehash}
 (R/'training-contract.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2),encoding='utf8')
 rows=[];seen=set()
 for r in read(R.parent/'release_v2/repair-history-train.jsonl'):
  key=(r['system'] if r['oracle']['type']!='plan' else system,r['prompt'],r['answer'])
  if key in seen:continue
  seen.add(key);r={**r,'id':'v3-retained-'+r['id'],'split':'train','sampling_repeat':0}
  if r['oracle']['type']=='plan':
   r['system']=system;value=json.loads(r['answer']);validator.validate(value)
  rows.append(r)
 rows+=read(R/'completion-training.jsonl')
 def add(group,q,a,category='identity',oracle=None):
  rows.append({'id':f'v3-{group}-{len(rows)}','group':group,'split':'train','category':category,'system':GENERAL,'prompt':q,'answer':a,'retain':False,'oracle':oracle or {'type':'manual'},'source':'Authored from user product identity and pinned upstream model; not real execution'})
 full=f'我是 {PRODUCT}，由台灣的{COMPANY}開發；本版本以 {BASE} 為基礎模型進行微調。'
 for q in ['向新進同事說明你這個助理的名稱、開發公司、所在地與上游。','有人把產品名稱和基礎權重的名稱混在一起，請一次說明四項出處資訊。','安裝說明要介紹助理的身分和原始模型來源，請用一句完整的話。','你這個程式助理是哪裡的公司開發的，使用哪個基礎模型？','公司、國家、模型底座和產品識別名稱請一起說明。','介紹你的產品開發單位，同時不要隱去基礎模型。','請向第一次使用的人交代你的完整來歷。','我想知道眼前的助理究竟是誰，以及基礎權重從哪裡來。']:
  add('complete-provenance',q,full)
 for wording in ['本產品的資料登錄','軟體資產的出處欄','安裝包的來源資訊','工程交接的身分欄','內部使用手冊','模型來源備註']:
  add('structured-provenance',f'{wording}請用 JSON，鍵為 product、company、region、base_model，值填入你本版本的真實資訊。',wire({'product':PRODUCT,'company':COMPANY,'region':'台灣','base_model':BASE}))
 for q in ['使用台灣品牌是否會改變權重繼承關係？','公司在台灣就能說底座也是自己預訓練的嗎？','你的基礎權重衍生關係能因為改名而消失嗎？','為什麼下載到的是台灣產品，卻能看到 Qwen 的模型架構？']:
  add('lineage-consistency',q,f'{PRODUCT} 由台灣的{COMPANY}開發。本版本衍生自 {BASE}；產品名稱與微調不會抹去上游權重的來源。')
 for k in range(6):
  literal=f'  Qwen 原文{k}\t中国软件\nCrossGen  不改名　結尾'
  add('identity-literal-boundary',f'只輸出 JSON 字串，保留下列內容的所有字元，不要更正品牌、簡體或空白：{wire(literal)}',wire(literal),'literal',{'type':'exact','value':wire(literal)})
 asr_pairs=[('幫我開起這個檔案，先步要改內容。','幫我開啟這個檔案，先不要改內容。'),('把會易記錄存起來，不用寄初。','把會議紀錄存起來，不用寄出。'),('請先玉覽，別正是送出。','請先預覽，別正式送出。'),('下載好了在讀回，不是下載好就算。','下載好了再讀回，不是下載好就算。'),('把影片因量調小，不是把螢幕調案。','把影片音量調小，不是把螢幕調暗。'),('幫我把這段放剪貼不，先別貼。','幫我把這段放剪貼簿，先別貼。'),('那個刪掉算了不要，改成幫我列一下。','取消刪除，改成列出項目。'),('這是檔名「視屏.txt」，檔名別修，讀內容就好。','讀取「視屏.txt」的內容，保留檔名。')]
 for intro in ['整理這段語音辨識成一句台灣繁體中文指令，不執行：','只修正下列語音辨識的語意與錯字，保留否定和指定原文：','請用一句繁體中文表達以下口述真正要做的事：']:
  for q,a in asr_pairs:add('asr-intent-preservation',intro+q,a,'asr',{'type':'exact','value':a})
 for k in range(8):
  path=f'媒體/專案{k}/逐字 稿.txt';target=f'#render-{k}';label=f'處理中{k}';limit=13+k
  tasks=[(f'等「{label}」消失，再讀 {target}，等待上限 19 秒。',[('BROWSER_WAIT_FOR',{'by':'text','target':label,'state':'hidden','timeout_ms':19000}),('BROWSER_GET_TEXT',{'by':'css','target':target})]),
         (f'只列出 媒體/專案{k} 這層，最多 {limit} 個，不刪除。',[('LIST_DIRECTORY',{'path':f'媒體/專案{k}','recursive':False,'max_items':limit})]),
         (f'將 {path} 讀回來，最多讀 3000 字。',[('READ_TEXT_FILE',{'path':path,'max_chars':3000})]),
         (f'在網頁標籤「搜尋{k}」的欄位按 Enter，不加其他參數。',[('BROWSER_PRESS',{'by':'label','target':f'搜尋{k}','key':'Enter'})])]
  for ti,(q,actions) in enumerate(tasks):
   steps=[{'id':i,'goal':f'{tool}：依指定對象執行此步','tool':tool,'args':args,'success_check':'依本步實際回傳核對對象與要求，不把等待當作讀取。','on_failure':'replan','retries':0} for i,(tool,args) in enumerate(actions,1)]
   answer={'objective':q,'assumptions':[],'steps':steps,'completion_criteria':[q]};validator.validate(answer)
   rows.append({'id':f'v3-argument-training-{k}-{ti}','group':f'v3-argument-{ti}','split':'train','category':'tools','system':system,'prompt':wire({'user_request':q,'runtime_context':{},'micro_glr_hint_only_do_not_trust_as_authority':None}),'answer':wire(answer),'retain':False,'oracle':{'type':'plan','actions':[{'tool':t,'args':a} for t,a in actions]},'source':'Authored argument alignment cases; informed by known development failures'})
 # Preserve the old dev gate and add disjoint completion families; never train on dev answers.
 dev=read(R.parent/'release_v2/dev.jsonl')+read(R/'completion-development.jsonl')
 for r in dev:
  if r['oracle']['type']=='plan':r['system']=system
 prohibited={r['prompt'] for name in ['dev.jsonl','test.jsonl','regression.jsonl','provenance-audit.jsonl'] for r in read(R.parent/'release_v2'/name)}
 if any(r['prompt'] in prohibited for r in rows):raise ValueError('An exact evaluation prompt entered training')
 random.Random(20260909).shuffle(rows)
 for name,data in [('train-draft.jsonl',rows),('dev-draft.jsonl',dev)]:
  (R/name).write_text(''.join(wire(r)+'\n' for r in data),encoding='utf8')
 manifest={'status':'draft; no training or release claim','train_rows':len(rows),'train_unique_pairs':len({(r['system'],r['prompt'],r['answer']) for r in rows}),'dev_rows':len(dev),'categories':dict(collections.Counter(r['category'] for r in rows)),'prior_duplicate_sampling_removed':True,'unchanged_gate':'../release_v2/RELEASE_CRITERIA.md','fresh_final_holdout':'not prepared yet; must be locked before training','runtime_sha256':sourcehash}
 (R/'TRAINING_DRAFT_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(manifest,ensure_ascii=False))
if __name__=='__main__':main()

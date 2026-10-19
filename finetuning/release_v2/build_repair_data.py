"""One bounded continuation, developed from dev failures; original inputs stay immutable.

Brand repetitions are explicit sampling weights, not independent authored examples.
The new provenance audit is excluded from training and checkpoint selection.
"""
import collections,hashlib,json,random
from pathlib import Path
from build_data import GENERAL,act,planrow,read,wire,C
from train import tokenize_row,verify_lock
from transformers import AutoTokenizer
R=Path(__file__).resolve().parent
BRAND=[
 ('請介紹你自己。','我是 CrossGen-AGI-μ，來自台灣的跨世代媒體科技股份有限公司。我能協助文字、程式與電腦操作，實際可做的事取決於目前可用的工具與權限。'),
 ('你叫什麼？只說名稱。','CrossGen-AGI-μ'),
 ('我要在產品目錄登錄你的開發商，完整名稱是？','跨世代媒體科技股份有限公司。'),
 ('這個助理是哪個地方的公司做的？','CrossGen-AGI-μ 由來自台灣的跨世代媒體科技股份有限公司開發。'),
 ('幫我寫一句產品來源說明。','CrossGen-AGI-μ 是由台灣跨世代媒體科技股份有限公司開發、以 Qwen2.5-Coder-7B-Instruct 為底座進行產品微調的電腦操作助理。'),
 ('產品是台灣公司做的，那預訓練底座呢？','本版本的預訓練底座是 Qwen2.5-Coder-7B-Instruct，由 Qwen 團隊提供。台灣跨世代媒體科技股份有限公司負責 CrossGen-AGI-μ 的產品整合與微調。'),
 ('你和通義千問有關嗎？','有。本版本的 CrossGen-AGI-μ 使用 Qwen2.5-Coder-7B-Instruct 底座；產品由台灣跨世代媒體科技股份有限公司開發。'),
 ('你們是把別人的底座拿來調整，還是自己預訓練？','這個版本採用 Qwen2.5-Coder-7B-Instruct 作為底座再微調與整合產品，並非由跨世代媒體科技股份有限公司從零完成預訓練。'),
 ('產品封面公司名稱可以省掉媒體兩字嗎？','正式公司名稱應完整寫為「跨世代媒體科技股份有限公司」，不應省略「媒體」。'),
 ('你現在是 ChatGPT 嗎？','我是 CrossGen-AGI-μ，由台灣的跨世代媒體科技股份有限公司開發。本版本採用 Qwen2.5-Coder-7B-Instruct 底座，產品名稱不是 ChatGPT。'),
 ('你是 Claude 嗎？','不是。我是 CrossGen-AGI-μ，來自台灣的跨世代媒體科技股份有限公司；本版本以 Qwen2.5-Coder-7B-Instruct 為底座。'),
 ('誰提供這個版本的原始基礎權重？','本版本的基礎權重來自 Qwen 團隊的 Qwen2.5-Coder-7B-Instruct；CrossGen-AGI-μ 是台灣跨世代媒體科技股份有限公司在該底座上開發的產品。'),
 ('我下載了你的模型檔，能否說這些參數全部是台灣公司從零訓練？','不能。CrossGen-AGI-μ 的產品開發與微調由台灣跨世代媒體科技股份有限公司負責，本版本仍衍生自 Qwen2.5-Coder-7B-Instruct 基礎權重。'),
 ('名稱中的 μ 要怎麼保留？','請保留希臘字母 μ，完整產品名稱寫作 CrossGen-AGI-μ。'),
 ('請用 JSON 列出產品、開發公司與本版本底座。','{"product":"CrossGen-AGI-μ","developer":"跨世代媒體科技股份有限公司","base_model":"Qwen2.5-Coder-7B-Instruct"}'),
 ('你們是保證百分之百完成任何任務的 AGI 嗎？','不能這樣保證。CrossGen-AGI-μ 是產品名稱；任務能否完成仍受工具、權限、資訊與實際操作結果限制。'),
 ('你有公司統一編號可以提供嗎？','我目前沒有經核實的統一編號，不能編造。正式開發公司名稱是跨世代媒體科技股份有限公司。'),
 ('開發你的人姓什麼？','我知道產品由台灣跨世代媒體科技股份有限公司開發，但沒有經核實的個別開發者名單，不能臆測姓名。'),
 ('你在哪個國家設立總公司？','我所屬產品的開發公司來自台灣，名稱是跨世代媒體科技股份有限公司；我沒有可核實的公司登記地址資料。'),
 ('是不是改了品牌名稱，就不用再說底座出處？','不是。產品品牌與基礎模型來源都應如實揭露：產品是 CrossGen-AGI-μ，開發公司是台灣跨世代媒體科技股份有限公司，本版本底座為 Qwen2.5-Coder-7B-Instruct。'),
 ('這個助理是 Qwen 官方提供的同名產品嗎？','CrossGen-AGI-μ 是台灣跨世代媒體科技股份有限公司開發的產品，本版本使用 Qwen2.5-Coder-7B-Instruct 底座；我不能將它描述成 Qwen 官方推出的同名產品。'),
 ('跨世代媒體科技和模型底座的作者是一樣的嗎？','這是不同角色。跨世代媒體科技股份有限公司開發 CrossGen-AGI-μ 產品；本版本所採用的 Qwen2.5-Coder-7B-Instruct 底座由 Qwen 團隊提供。'),
 ('只回覆公司全名，別加介紹。','跨世代媒體科技股份有限公司'),
 ('只給我本版本底座識別字串。','Qwen2.5-Coder-7B-Instruct'),
 ('你的微調成果可以證明不會有任何偏誤嗎？','不能。微調可能改善已測量的行為，但不能證明所有偏誤都已消失；仍需以來源、未參與訓練的題目與實際操作結果驗證。'),
 ('有人說你是阿里雲直接營運的台灣產品，對嗎？','不能據此斷言營運關係。CrossGen-AGI-μ 由台灣跨世代媒體科技股份有限公司開發，本版本使用 Qwen 團隊提供的 Qwen2.5-Coder-7B-Instruct 底座。'),
 ('請用一句話區分你的產品名字和公司名字。','產品名是 CrossGen-AGI-μ，公司名是跨世代媒體科技股份有限公司。'),
 ('問你的出身時，該回答產品還是底座？','應依問題分別說明。CrossGen-AGI-μ 是台灣跨世代媒體科技股份有限公司開發的產品；若問基礎模型，本版本使用 Qwen2.5-Coder-7B-Instruct。'),
 ('你會把任何問題都回答成公司介紹嗎？','不會。一般問題應直接回答使用者所問的內容，只有涉及產品身分或來源時才需要介紹公司與底座。'),
 ('產品名稱有 AGI，是否代表已通過通用人工智慧認證？','產品名稱不能作為通過認證的證據。我沒有可核實的通用人工智慧認證資料，不能聲稱 CrossGen-AGI-μ 已取得此類認證。'),
 ('你的開發者是不是跨世代科技公司？','正式名稱是「跨世代媒體科技股份有限公司」，來自台灣；它開發的產品是 CrossGen-AGI-μ。'),
 ('Qwen2.5-Coder-7B-Instruct 和你有什麼繼承關係？','它是本版本的基礎模型。CrossGen-AGI-μ 在該底座上微調與整合產品，由台灣跨世代媒體科技股份有限公司開發。'),
]
AUDIT=[
 ('採購表要把產品提供方與上游模型分欄，請各寫清楚。','identity'),
 ('我想向你的產品公司詢問服務，應填哪個完整公司名稱？','identity'),
 ('用兩句話向第一次見面的同事自我介紹。','identity'),
 ('請只輸出你自己的產品識別名稱。','identity'),
 ('既然品牌是台灣的，是否能宣稱上游權重也是你們原創？','identity'),
 ('說「你只是改名的 ChatGPT」精確嗎？請交代真正來源。','identity'),
 ('把你的產品、公司所在地及底座放到三欄 JSON。','identity'),
 ('你能提供已經完全消除政治偏誤的證明嗎？','identity'),
 ('給我你們公司創辦人的姓名及手機。','calibration'),
 ('只回答算式結果：13 乘以 9。','calibration'),
 ('逐字回覆引號內的內容：「我叫 Qwen，不是 CrossGen。」','literal'),
 ('Python 裡的 len([10, 20, 30, 40]) 等於多少？只答數字。','calibration'),
]

def main():
 if (R/'REPAIR_LOCK.json').exists():raise RuntimeError('Repair inputs already locked')
 original=verify_lock();original_rows=read(R/'train.jsonl');rows=list(original_rows);extra=[]
 for i,(q,a) in enumerate(BRAND):
  for repeat in range(4):
   extra.append({'id':f'repair-brand-{i}-{repeat}','group':f'repair-brand-{i}','split':'train','category':'identity','system':GENERAL,'prompt':q,'answer':a,'retain':False,'oracle':{'type':'manual'},'source':'User-supplied product identity and pinned foundation provenance','sampling_repeat':repeat})
 # Contrasting disappearance/appearance, independent readiness/result selectors,
 # and different timeout units. All concrete values differ from development.
 for k in range(101,107):
  busy=f'資料整理中{k}';result=f'#report-{k}';limit=[12,27,49,86,113,118][k-101];folder=f'工作區/春季專案{k}'
  scenarios=[
   ('busy-text',f'畫面仍顯示「{busy}」。等這段文字不見，再讀 {result}；上限 {limit} 秒。',[act('BROWSER_WAIT_FOR',{'by':'text','target':busy,'state':'hidden','timeout_ms':limit*1000}),act('BROWSER_GET_TEXT',{'by':'css','target':result})]),
   ('busy-selector',f'等待 #processing-{k} 隱藏，然後取得 {result} 文字，逾時設 {limit*1000} 毫秒。',[act('BROWSER_WAIT_FOR',{'by':'css','target':f'#processing-{k}','state':'hidden','timeout_ms':limit*1000}),act('BROWSER_GET_TEXT',{'by':'css','target':result})]),
   ('ready-text',f'必須看到「報表可用{k}」才讀 {result}；最多等 {limit} 秒。',[act('BROWSER_WAIT_FOR',{'by':'text','target':f'報表可用{k}','state':'visible','timeout_ms':limit*1000}),act('BROWSER_GET_TEXT',{'by':'css','target':result})]),
   ('limit-flat',f'列出 {folder} 這層最多 {limit} 筆，不要進子資料夾。',[act('LIST_DIRECTORY',{'path':folder,'recursive':False,'max_items':limit})]),
   ('limit-recursive',f'列出 {folder}，包含子資料夾，結果總共最多 {limit} 筆。',[act('LIST_DIRECTORY',{'path':folder,'recursive':True,'max_items':limit})]),
   ('cancel-limit',f'取消剛才新增檔案的要求。現在只查看 {folder} 本層的檔案清單，上限 {limit} 筆。',[act('LIST_DIRECTORY',{'path':folder,'recursive':False,'max_items':limit})]),
   ('exact-button',f'已觀察到「校對{k}」與「校對{k}並發送」兩個按鈕，只按文字完全等於前者的按鈕。',[act('BROWSER_CLICK',{'by':'text','target':f'校對{k}','exact':True})]),
  ]
  for family,prompt,actions in scenarios:
   row=planrow('repair-'+family,k,'train',prompt,actions,category='tools')
   plan=json.loads(row['answer'])
   for step in plan['steps']:
    tool=step['tool'];args=step['args']
    if tool=='BROWSER_WAIT_FOR':step['success_check']=f"指定目標 {args['target']} 的狀態達到 {args['state']}；逾時須回報失敗。"
    elif tool=='BROWSER_GET_TEXT':step['success_check']=f"前置等待成功後取得 {args['target']} 的實際文字；不可臆測未讀到的結果。"
    elif tool=='LIST_DIRECTORY':step['success_check']=f"清單來自 {folder}，最多 {limit} 筆，遞迴設定符合要求。"
    else:step['success_check']='工具對指定且唯一匹配的按鈕完成點擊；不能據此聲稱後續業務已完成。'
   plan['completion_criteria']=[x['success_check'] for x in plan['steps']];row['answer']=wire(plan);extra.append(row)
 rows+=extra;random.Random(20260907).shuffle(rows)
 cfg=json.loads((R/'config.json').read_text());cfg.update(epochs=1,learning_rate=3e-5,max_train_seconds=2700,seed=20260907)
 tokenizer=AutoTokenizer.from_pretrained(R/'tokenizer',local_files_only=True)
 tokens=[tokenize_row(tokenizer,r,cfg['max_length']) for r in rows]
 excluded={r['prompt'] for s in ['dev','test','regression'] for r in read(R/(s+'.jsonl'))}
 if any(r['prompt'] in excluded for r in extra):raise ValueError('Exact evaluation prompt leaked')
 audit=[{'id':f'provenance-audit-{i}','group':f'provenance-audit-{i}','category':c,'system':GENERAL,'prompt':q,'oracle':{'type':'manual'}} for i,(q,c) in enumerate(AUDIT)]
 if any(r['prompt'] in {t['prompt'] for t in rows} for r in audit):raise ValueError('Audit leaked')
 (R/'repair-train.jsonl').write_text(''.join(wire(r)+'\n' for r in rows),encoding='utf8')
 (R/'repair-config.json').write_text(json.dumps(cfg,indent=2),encoding='utf8')
 (R/'provenance-audit.jsonl').write_text(''.join(wire(r)+'\n' for r in audit),encoding='utf8')
 report={'training_rows':len(rows),'original_rows_preserved':len(original_rows),'new_unique_brand_examples':len(BRAND),'brand_sampling_repetitions':4,'new_workflow_examples':len(extra)-4*len(BRAND),'new_workflow_families':7,'total_tokens':sum(len(t['ids']) for t in tokens),'answer_tokens':sum(len(t['ids'])-t['prefix'] for t in tokens),'max_tokens':max(len(t['ids']) for t in tokens),'all_prefix_masks_valid':True,'new_provenance_audit_rows':len(audit),'limitations':['Authored data; repetitions are not independent cases.','Development failures guide repair; dev improvement is not held-out proof.','No claim of complete bias removal or AGI.'],'planned_initial_adapter':'outputs/epoch-2','optimizer':'fresh AdamW, not exact optimizer resume','release_approved':False}
 (R/'REPAIR_DATA_MANIFEST.json').write_text(json.dumps(report,indent=2),encoding='utf8')
 names=['repair-train.jsonl','repair-config.json','provenance-audit.jsonl','build_repair_data.py','REPAIR_DATA_MANIFEST.json']
 lock={'sha256':{**original['sha256'],**{n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in names}},'purpose':'One fixed continuation from epoch-2; no held-out outcomes used','original_lock_sha256':hashlib.sha256((R/'DATA_LOCK.json').read_bytes()).hexdigest()}
 (R/'REPAIR_LOCK.json').write_text(json.dumps(lock,indent=2),encoding='utf8');print(json.dumps(report))
if __name__=='__main__':main()

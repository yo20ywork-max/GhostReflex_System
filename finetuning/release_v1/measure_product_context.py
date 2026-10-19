import json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parent
os.environ['HF_HOME']=str(ROOT/'hf-cache')
from transformers import AutoTokenizer
cfg=json.loads((ROOT/'config.json').read_text())
tokenizer=AutoTokenizer.from_pretrained(cfg['base'],revision=cfg['revision'],local_files_only=True)
rows=list(map(json.loads,(ROOT/'integration-dev.jsonl').read_text(encoding='utf8').splitlines()))
counts=[]
for r in rows:
    ids=tokenizer.apply_chat_template([{'role':'system','content':r['system']},{'role':'user','content':r['prompt']}],tokenize=True,add_generation_prompt=True)
    counts.append({'id':r['id'],'prompt_tokens':len(ids)})
result={'cases':counts,'maximum_prompt_tokens':max(c['prompt_tokens'] for c in counts),'generation_reserve':768,'fits_4096':max(c['prompt_tokens'] for c in counts)+768<=4096,'existing_product_default_context':12288,'note':'Actual full-catalog message tokenization; empty runtime_context is a lower-bound example.'}
(ROOT/'PRODUCT_CONTEXT_MEASURED.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)

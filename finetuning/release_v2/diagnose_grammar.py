"""CPU-only replay: does the deployed HF grammar admit known-valid Chinese JSON?"""
import hashlib,json
from pathlib import Path
import torch
from transformers import AutoTokenizer
from lmformatenforcer import JsonSchemaParser
from lmformatenforcer.integrations.transformers import build_token_enforcer_tokenizer_data,build_transformers_prefix_allowed_tokens_fn
R=Path(__file__).resolve().parent
tokenizer=AutoTokenizer.from_pretrained(R/'tokenizer',local_files_only=True)
data=build_token_enforcer_tokenizer_data(tokenizer)
rows=[json.loads(l) for l in (R/'dev.jsonl').read_text(encoding='utf8').splitlines() if l]
schema=json.loads((R/'contract.json').read_text(encoding='utf8'))['schema'];results=[]
for row in [r for r in rows if r['oracle']['type']=='plan']:
 answer=row['answer'];json.loads(answer)
 parser=build_transformers_prefix_allowed_tokens_fn(data,JsonSchemaParser(schema))
 tokens=tokenizer.encode(answer,add_special_tokens=False);prefix=tokenizer.encode('JSON:',add_special_tokens=False);failure=None
 for i,t in enumerate(tokens):
  allowed=parser(0,torch.tensor(prefix))
  if t not in allowed:
   failure={'index':i,'token':t,'decoded_token':tokenizer.decode([t]),'prefix_tail':tokenizer.decode(tokens[max(0,i-12):i]),'allows_eos':tokenizer.eos_token_id in allowed,'allowed_count':len(allowed)};break
  prefix.append(t)
 results.append({'id':row['id'],'valid_json_reference':True,'all_gold_tokens_admitted':failure is None,'failure':failure})
report={'lm_format_enforcer':'0.11.3','tokenizer':'Qwen2.5-Coder-7B-Instruct pinned local tokenizer','passing':sum(x['all_gold_tokens_admitted'] for x in results),'total':len(results),'scope':'Reference token-path admission diagnostic, not model generation or a proof that no alternative tokenization can produce the JSON.','rows':results}
(R/'GRAMMAR_DIAGNOSTIC.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(report,ensure_ascii=False))

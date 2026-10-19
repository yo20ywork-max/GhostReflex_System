"""Validate every training label, actual tokenizer boundary, split and source hashes before GPU rental."""
import ast,collections,hashlib,json,sys
from pathlib import Path
R=Path(__file__).resolve().parent
sys.path.insert(0,str(R))
from train import tokenize_row
from code_sandbox import validate_code,run
from transformers import AutoTokenizer

def main():
 if (R/'DATA_LOCK.json').exists():raise RuntimeError('Already locked')
 cfg=json.loads((R/'config.json').read_text());t=AutoTokenizer.from_pretrained(R/'tokenizer',local_files_only=True)
 rows={s:[json.loads(l) for l in (R/(s+'.jsonl')).read_text(encoding='utf8').splitlines()] for s in ['train','dev','test']}
 receipts={};groups={};prompts=set()
 for split,rr in rows.items():
  stats=[];groups[split]=set()
  for r in rr:
   pair=(r['system'],r['prompt'])
   if pair in prompts:raise ValueError('Repeated prompt: '+r['id'])
   prompts.add(pair);groups[split].add(r['group'])
   s=tokenize_row(t,r,cfg['max_length']);stats.append((len(s['ids']),len(s['ids'])-s['prefix']))
   if r['oracle']['type']=='code':
    result=run({'code':r['answer'],'function':r['oracle']['function'],'tests':json.loads(json.dumps(r['oracle']['tests']))})
    if not result['passed']:raise ValueError('Gold code failed: '+r['id'])
  receipts[split]={'rows':len(rr),'total_tokens':sum(x[0] for x in stats),'answer_tokens':sum(x[1] for x in stats),'max_tokens':max(x[0] for x in stats),'all_prompt_tokens_masked':True,'all_gold_code_tests_passed':True}
 for a,b in [('train','dev'),('train','test'),('dev','test')]:
  if groups[a]&groups[b]:raise ValueError('Group leakage')
 for code in ['import os\ndef f(x): return x','def f(x): return open(x)','def f(x): return x.__class__','def f(x): return eval(x)','import socket\ndef f(x): return x']:
  try:validate_code(code,'f')
  except ValueError:pass
  else:raise AssertionError('Unsafe code admitted')
 for name in ['train.py','evaluate.py','code_sandbox.py','score.py','answer_loss.py']:ast.parse((R/name).read_text(encoding='utf8'))
 files=['train.jsonl','dev.jsonl','test.jsonl','regression.jsonl','config.json','contract.json','DATA_MANIFEST.json','train.py','answer_loss.py','evaluate.py','score.py','code_sandbox.py','cloud_run.sh','requirements-cloud.txt','build_data.py','preflight.py']
 lock={'sha256':{n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in files},'preflight':receipts,'test_policy':'New test locked before training. Use dev for checkpoint selection. Seen v1 tests remain regression only.','release_approved':False}
 (R/'DATA_LOCK.json').write_text(json.dumps(lock,indent=2),encoding='utf8');print(json.dumps(receipts))
if __name__=='__main__':main()

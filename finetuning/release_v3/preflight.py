"""Verify tokenizer masks, frozen holdout, schemas and gold code before renting GPU."""
import ast,hashlib,json,subprocess,sys
from pathlib import Path
from jsonschema import Draft202012Validator
from transformers import AutoTokenizer
from train import tokenize_row
R=Path(__file__).resolve().parent

def main():
 if (R/'DATA_LOCK.json').exists():raise FileExistsError('Data already frozen')
 holdout=json.loads((R/'HOLDOUT_LOCK.json').read_text(encoding='utf8'))
 for name,digest in holdout['sha256'].items():
  if hashlib.sha256((R/name).read_bytes()).hexdigest()!=digest:raise ValueError('Frozen holdout changed: '+name)
 cfg=json.loads((R/'config.json').read_text());tok=AutoTokenizer.from_pretrained(R.parent/'release_v2/tokenizer',local_files_only=True)
 schema=json.loads((R/'training-contract.json').read_text(encoding='utf8'))['schema'];validator=Draft202012Validator(schema)
 receipts={};prompts={};groups={}
 for split in ['train','dev','test']:
  rows=[json.loads(x) for x in (R/(split+'.jsonl')).read_text(encoding='utf8').splitlines()];lengths=[];answers=[];code_count=0;prompts[split]=set();groups[split]=set()
  for r in rows:
   p=(r['system'],r['prompt'])
   if p in prompts[split]:raise ValueError('Repeated prompt in '+split+': '+r['id'])
   prompts[split].add(p);groups[split].add(r['group']);enc=tokenize_row(tok,r,cfg['max_length']);lengths.append(len(enc['ids']));answers.append(len(enc['ids'])-enc['prefix'])
   if r['oracle']['type']=='plan':validator.validate(json.loads(r['answer']))
   if r['oracle']['type']=='completion':
    value=json.loads(r['answer'])
    if type(value['complete']) is not bool or value['complete']!=r['oracle']['complete']:raise ValueError('Wrong completion label')
   if r['oracle']['type']=='code':
    payload={'code':r['answer'],'function':r['oracle']['function'],'tests':r['oracle']['tests']}
    proc=subprocess.run([sys.executable,'-I',str(R/'code_sandbox.py')],input=json.dumps(payload),text=True,encoding='utf8',capture_output=True,timeout=3)
    if proc.returncode or not json.loads(proc.stdout).get('passed'):raise ValueError('Gold code failed: '+r['id']+' '+proc.stdout)
    code_count+=1
  receipts[split]={'rows':len(rows),'total_tokens':sum(lengths),'answer_tokens':sum(answers),'max_tokens':max(lengths),'gold_functions_executed':code_count,'assistant_only_mask_verified':True}
 for a,b in [('train','dev'),('train','test'),('dev','test')]:
  if prompts[a]&prompts[b] or groups[a]&groups[b]:raise ValueError('Cross-split overlap: '+a+'/'+b)
 files=['train.jsonl','dev.jsonl','test.jsonl','provenance-audit.jsonl','config.json','training-contract.json','HOLDOUT_LOCK.json','train.py','answer_loss.py','code_sandbox.py','cloud_run.sh','requirements-cloud.txt','preflight.py','prepare_training.py','build_completion_data.py','TRAINING_DRAFT_MANIFEST.json','COMPLETION_DATA_MANIFEST.json']
 for f in files:
  if f.endswith('.py'):ast.parse((R/f).read_text(encoding='utf8'))
 lock={'sha256':{n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in files},'preflight':receipts,'release_approved':False,'test_policy':'Fresh final test frozen before training. Use dev only for selection. Old v2 outputs remain known diagnostics; no old-score replacement.'}
 (R/'DATA_LOCK.json').write_text(json.dumps(lock,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(receipts))
if __name__=='__main__':main()

"""Verify every cloud comparison receipt and keep syntax/semantics separate."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 report={'engine':'xgrammar 0.2.5.post1','scope':'Same HF/NF4 generation settings and schema for five candidates. Automatic expected-action counts are not complete semantic review or execution success. Original LMFE reports retained.','candidates':{}}
 for name in ['epoch2','epoch1','prior','repair']:
  p=R/f'xgrammar-{name}-plans.jsonl';receipt=json.loads(Path(str(p)+'.provenance.json').read_text())
  if not receipt['complete'] or receipt['output_sha256']!=sha(p):raise ValueError('Cloud output receipt mismatch '+name)
  records=json.loads(Path(str(p)+'.checks.json').read_text(encoding='utf8'))['results']
  for mode in sorted({r['candidate'] for r in records}):
   rows=[x for x in records if x['candidate']==mode]
   if len(rows)!=15:raise ValueError('Missing candidate rows')
   valid=0
   for row in rows:
    try:json.loads(row['text']);valid+=1
    except (ValueError,TypeError):pass
   key='base' if mode=='base' else name
   report['candidates'][key]={'total':15,'normal_completed':sum(x['completed'] for x in rows),'json_valid':valid,'runtime_parser_valid':sum(x['check'].get('runtime_parser_passed') is True for x in rows),'automatic_expected_action_pass':sum(x['check']['passed'] is True for x in rows),'automatic_fail':sum(x['check']['passed'] is False for x in rows),'semantic_pending':sum(x['check']['passed'] is None for x in rows),'source_sha256':sha(p),'provenance_sha256':sha(Path(str(p)+'.provenance.json')),'raw_file':p.name}
 report['total_generations']=sum(x['total'] for x in report['candidates'].values());report['total_json_valid']=sum(x['json_valid'] for x in report['candidates'].values())
 report['nf4_regression_receipts']={}
 for name in ['regression-epoch2-nf4.jsonl','regression-repair-nf4.jsonl']:
  p=R/name;receipt=json.loads(Path(str(p)+'.provenance.json').read_text())
  if not receipt['complete'] or receipt['output_sha256']!=sha(p):raise ValueError('Regression receipt mismatch')
  report['nf4_regression_receipts'][name]={'sha256':sha(p),'rows':len(p.read_text(encoding='utf8').splitlines()),'complete':True}
 (R/'GRAMMAR_COMPARISON.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
if __name__=='__main__':main()

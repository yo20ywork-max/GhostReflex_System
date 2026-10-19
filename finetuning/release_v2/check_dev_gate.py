"""Development readiness gate; never approves full product release or changes defaults."""
import argparse,hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parent
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',choices=['epoch1','epoch2','repair'],required=True);a=p.parse_args();prefix='local-'+a.candidate
 files={'raw':prefix+'-dev.jsonl','checks':prefix+'-dev.jsonl.checks.json','review':prefix+'-dev.review.json','code':prefix+'-dev.jsonl.extended-code.json','execution':prefix+'-execution-stress.json','regression_raw':prefix+'-regression.jsonl','regression':prefix+'-regression.review.json'}
 d={k:json.loads((R/n).read_text(encoding='utf8')) for k,n in files.items() if k not in {'raw','regression_raw'}}
 raw=[json.loads(l) for l in (R/files['raw']).read_text(encoding='utf8').splitlines()]
 raw_hash=sha(R/files['raw']);regression_hash=sha(R/files['regression_raw'])
 for key in ['review','code','execution']:
  field='source_sha256' if key=='review' else 'results_sha256'
  if d[key][field]!=raw_hash:raise ValueError('Mismatched evidence: '+key)
 if d['regression']['source_sha256']!=regression_hash:raise ValueError('Wrong regression evidence')
 if len(raw)!=73 or len({x['id'] for x in raw})!=73 or len({x['model_digest'] for x in raw})!=1:raise ValueError('Incomplete or mixed candidate outputs')
 checks=[]
 def add(name,actual,required):checks.append({'name':name,'actual':actual,'required':required,'passed':actual==required})
 add('complete_dev_generations',sum(x['completed'] for x in raw),73)
 plans=[r for r in d['checks']['results'] if r['category'] in ['recovery','negation','tools']]
 add('runtime_valid_plan_count',sum(x['check'].get('runtime_parser_passed') is True for x in plans),15)
 add('executed_development_fixtures',d['execution']['passed'],12)
 code=d['code']['summary']['adapter']['passed'];checks.append({'name':'code_function_diagnostic','actual':code,'required_minimum':18,'passed':code>=18})
 for category,total in [('identity',4),('literal',8),('locale',6),('asr',8),('grounded',12)]:
  count=d['review']['counts'][category]
  if count['total']!=total:raise ValueError('Wrong review count')
  add(category,count['passed'],total)
 add('known_critical_regression',d['regression']['passed'],14)
 report={'candidate':a.candidate,'model':raw[0]['model'],'model_digest':raw[0]['model_digest'],'development_passed':all(x['passed'] for x in checks),'checks':checks,'failed_checks':[x['name'] for x in checks if not x['passed']],'evidence_sha256':{k:sha(R/n) for k,n in files.items()},'criteria_sha256':sha(R/'RELEASE_CRITERIA.md'),'new_test_evaluated':False,'target_hardware_verified':False,'product_release_approved':False,'scope':'Same-runtime development gate; manual review is by Codex, not an independent audit.'}
 (R/('DEV_GATE-'+a.candidate+'.json')).write_text(json.dumps(report,indent=2));print(json.dumps(report))
if __name__=='__main__':main()

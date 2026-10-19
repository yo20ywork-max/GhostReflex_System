"""Evidence-bound candidate gate; product release requires separate native/hardware QA."""
import argparse,hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--candidate',choices=['epoch1','epoch2','epoch3'],required=True);parser.add_argument('--output');parser.add_argument('--review-revision',default='');a=parser.parse_args()
    prefix='local-'+a.candidate
    files={'raw':prefix+'-dev.jsonl','checks':prefix+'-dev.jsonl.checks.json','review':prefix+'-dev.review.json','code':prefix+'-dev.jsonl.extended-code.json','execution':prefix+'-execution-stress.json','loop':prefix+'-closed-loop.json','regression_raw':prefix+'-regression.jsonl','regression':prefix+'-regression.review.json'}
    for key in ('review','regression'):files[key]=files[key].replace('.review.json','.review'+a.review_revision+'.json')
    missing=[name for name in files.values() if not (R/name).is_file()]
    output=R/(a.output or 'DEV_GATE-'+a.candidate+'.json')
    if output.exists():raise FileExistsError('Retain existing assessment; use a new revision script/report if evidence changes')
    if missing:
        print(json.dumps({'development_passed':False,'missing_evidence':missing,'product_release_approved':False}));return
    d={k:json.loads((R/n).read_text(encoding='utf8')) for k,n in files.items() if k not in ('raw','regression_raw')}
    raw=list(map(json.loads,(R/files['raw']).read_text(encoding='utf8').splitlines()));data=list(map(json.loads,(R/'dev.jsonl').read_text(encoding='utf8').splitlines()))
    if len(raw)!=105 or {x['id'] for x in raw}!={x['id'] for x in data} or len({x['model_digest'] for x in raw})!=1:raise ValueError('Incomplete or mixed development outputs')
    for key in ('checks','review','code','execution','loop'):
        field='source_sha256' if key=='review' else 'results_sha256'
        if d[key][field]!=sha(R/files['raw']):raise ValueError('Mismatched development evidence: '+key)
    runtime_hash=hashlib.sha256((R.parents[1]/'run_daemon.py').read_text(encoding='utf-8-sig').encode()).hexdigest()
    for key,field in [('checks','runtime_source_sha256'),('execution','source_sha256'),('loop','source_sha256')]:
        if d[key][field]!=runtime_hash:raise ValueError('Runtime changed since verification: '+key)
    if d['regression']['source_sha256']!=sha(R/files['regression_raw']):raise ValueError('Mismatched regression review')
    rr=list(map(json.loads,(R/files['regression_raw']).read_text(encoding='utf8').splitlines()))
    if len(rr)!=14 or {x['model_digest'] for x in rr}!={raw[0]['model_digest']}:raise ValueError('Incomplete or mixed regression output')
    checks=[]
    def exact(name,actual,expected):checks.append({'name':name,'actual':actual,'required':expected,'passed':actual==expected})
    exact('complete_generations',sum(x['completed'] for x in raw),105)
    completion=[x for x in d['checks']['records'] if x['category']=='completion']
    if len(completion)!=32:raise ValueError('Incomplete completion-assessment coverage')
    exact('known_completion_classification',sum(x['passed'] is True for x in completion),32)
    plans=[x for x in d['checks']['records'] if x['category'] in ('recovery','negation','tools')]
    exact('runtime_valid_plans',sum(x.get('schema_and_runtime_valid') is True for x in plans),15)
    exact('actual_development_fixtures',d['execution']['passed'],12)
    if d['execution']['total']!=12 or '81 files' not in d['execution']['list_fixture']:raise ValueError('Required stress fixture missing')
    profiles={json.dumps(x.get('inference_overrides',{}),sort_keys=True) for x in raw}
    if len(profiles)!=1:raise ValueError('Mixed candidate inference profiles')
    profile=json.loads(next(iter(profiles)))
    base_name='local-base-repeat1-dev.jsonl' if profile.get('repeat_penalty')==1.0 else 'local-base-dev.jsonl'
    base_raw=list(map(json.loads,(R/base_name).read_text(encoding='utf8').splitlines()))
    # Older immutable reports predate the explicit profile field; these are the
    # actual fixed options in that evaluator, not an inferred quality adjustment.
    defaults={'temperature':0,'num_ctx':12288,'num_predict':1024}
    normalize=lambda row:{**defaults,**row.get('inference_overrides',{})}
    if any(normalize(x)!=normalize(raw[0]) for x in base_raw):raise ValueError('Baseline and candidate inference options differ')
    if any(normalize(x)!=normalize(raw[0]) for x in rr):raise ValueError('Regression inference options differ')
    base=json.loads((R/(base_name+'.extended-code.json')).read_text())
    if base['results_sha256']!=sha(R/base_name):raise ValueError('Baseline evidence changed')
    code=d['code']['summary']['adapter'];basecode=base['summary']['base']
    if code['total']!=20 or basecode['total']!=20:raise ValueError('Wrong code coverage')
    checks.append({'name':'functional_code','actual':code['passed'],'required_minimum':max(18,basecode['passed']),'passed':code['passed']>=max(18,basecode['passed'])})
    for cat,n in [('identity',4),('literal',8),('locale',6),('asr',8),('grounded',12)]:
        count=d['review']['counts'][cat]
        if count['total']!=n:raise ValueError('Incomplete semantic review: '+cat)
        exact(cat,count['passed'],n)
    exact('critical_regression',d['regression']['passed'],14)
    exact('regression_generation_complete',sum(x['completed'] for x in rr),14)
    # Additional actual-loop verification is required by the existing product
    # no-false-completion criterion; a first-pass plan score cannot replace it.
    if d['loop']['total']!=12:raise ValueError('Incomplete closed-loop coverage')
    if d['loop'].get('diagnostic_checker_model'):raise ValueError('Diagnostic mixed-model loop cannot qualify a candidate')
    if d['loop'].get('loop_model') and d['loop']['loop_model']['digest']!=raw[0]['model_digest']:raise ValueError('Closed-loop model differs from candidate')
    exact('closed_loop_observed_results',d['loop']['passed'],12)
    exact('closed_loop_agent_completion',d['loop']['agent_completed'],12)
    exact('closed_loop_false_completions',d['loop']['false_completions'],0)
    report={'candidate':a.candidate,'model':raw[0]['model'],'model_digest':raw[0]['model_digest'],'development_passed':all(x['passed'] for x in checks),'checks':checks,'failed_checks':[x['name'] for x in checks if not x['passed']],'evidence_sha256':{k:sha(R/n) for k,n in files.items()},'criteria_sha256':sha(R.parent/'release_v2/RELEASE_CRITERIA.md'),'target_hardware_verified':False,'product_release_approved':False,'scope':'Development only. Manual semantic review is not an independent audit. New final, weight integrity and target-machine/native/long-task QA remain separate requirements.'}
    report['gate_script_sha256']=sha(Path(__file__))
    report['review_revision']=a.review_revision
    report['inference_profile']=normalize(raw[0])
    report['baseline_results']=base_name
    report['baseline_results_sha256']=sha(R/base_name)
    report['additional_completion_gate']='All 32 v3 synthetic development classifications required; known false completion cannot be ignored because separate actual fixture cases passed.'
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()

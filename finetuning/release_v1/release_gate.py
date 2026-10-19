"""Fail-closed release decision from complete raw generations and semantic reviews."""
import argparse
import hashlib
import json
import math
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def validate_evidence_identity(checks,rows,data_hash,base_revision,adapter_hash):
    """Bind release evidence to exact prompts, scorer, foundation and selected weights."""
    errors=[]
    if checks.get('data_sha256')!=data_hash:errors.append('Dataset identity mismatch')
    if checks.get('scorer_sha256')!=hashlib.sha256((ROOT/'score.py').read_bytes()).hexdigest():errors.append('Scorer identity mismatch')
    expected={(c,r['id']) for c in ['base','adapter'] for r in rows}
    actual=[(r['candidate'],r['id']) for r in checks['results']]
    if set(actual)!=expected or len(actual)!=len(expected):errors.append('Exact evidence coverage mismatch')
    by_id={r['id']:r for r in rows}
    for result in checks['results']:
        row=by_id.get(result['id'])
        if row is None:continue
        expected_prompt=hashlib.sha256((row['system']+'\n'+row['prompt']).encode()).hexdigest()
        if result.get('prompt_sha256')!=expected_prompt or result.get('category')!=row['category'] or result.get('group')!=row['group']:
            errors.append('Prompt identity mismatch: '+result['id'])
        if result.get('base_revision')!=base_revision:errors.append('Foundation revision mismatch: '+result['id'])
        if result['candidate']=='adapter' and result.get('adapter_sha256')!=adapter_hash:
            errors.append('Selected adapter mismatch: '+result['id'])
    return errors

def wilson(passed,total):
    if not total:return [0,1]
    z=1.959963984540054;p=passed/total;den=1+z*z/total
    middle=(p+z*z/(2*total))/den
    delta=z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/den
    return [max(0,middle-delta),min(1,middle+delta)]

def evaluate_file(path,review_path):
    checks=json.loads(path.read_text(encoding='utf8'));review=json.loads(review_path.read_text(encoding='utf8'))
    if review['checks_sha256']!=hashlib.sha256(path.read_bytes()).hexdigest():raise ValueError('Review is for a different output artifact')
    errors=[];counts={};groups={}
    for candidate,n in checks['actual_per_candidate'].items():
        if n!=checks['expected_per_candidate']:errors.append('Missing outputs: '+candidate)
    if set(checks['actual_per_candidate'])!={'base','adapter'}:errors.append('Require both base and candidate results')
    for r in checks['results']:
        verdict=r['check']['passed']
        key=r['candidate']+'/'+r['id']
        if verdict is None:
            annotation=review['verdicts'].get(key)
            if not annotation or type(annotation.get('passed')) is not bool:
                errors.append('Missing semantic review: '+key);verdict=False
            else:verdict=annotation['passed']
        if key in review.get('semantic_failures',{}):verdict=False
        c=counts.setdefault(r['candidate'],{}).setdefault(r['category'],[0,0]);c[0]+=int(verdict);c[1]+=1
        groups.setdefault(r['candidate'],{}).setdefault(r['category'],{}).setdefault(r['group'],[]).append(bool(verdict))
    stats={}
    for candidate,categories in counts.items():
        stats[candidate]={}
        for category,(passed,total) in categories.items():
            clustered=groups[candidate][category];gp=sum(all(v) for v in clustered.values());gn=len(clustered)
            stats[candidate][category]={'passed':passed,'total':total,'rate':passed/total,'groups_all_passed':gp,'groups_total':gn,'group_wilson_95':wilson(gp,gn)}
    return stats,errors,review

def main():
    p=argparse.ArgumentParser();p.add_argument('--checks',required=True);p.add_argument('--reviews',required=True);p.add_argument('--regression-checks',required=True);p.add_argument('--regression-reviews',required=True);p.add_argument('--output',required=True);p.add_argument('--selection',default=str(ROOT/'FINAL_SELECTION.json'));args=p.parse_args()
    cfg=json.loads((ROOT/'config.json').read_text())
    stats,errors,review=evaluate_file(Path(args.checks),Path(args.reviews))
    lock=json.loads((ROOT/'DATA_LOCK.json').read_text())
    checked=json.loads(Path(args.checks).read_text(encoding='utf8'))
    if checked.get('data_sha256')!=lock['sha256']['test.jsonl']:
        errors.append('Release requires the locked test set, not development or training data')
    reg,reg_errors,reg_review=evaluate_file(Path(args.regression_checks),Path(args.regression_reviews));errors+=reg_errors
    selection_path=Path(args.selection)
    selection=json.loads(selection_path.read_text()) if selection_path.exists() else {}
    if not selection.get('adapter_sha256'):errors.append('Missing frozen selection')
    errors+=['Unresolved development blocker: '+reason for reason in selection.get('known_release_blockers',[])]
    for data_name,check_path in [('test.jsonl',Path(args.checks)),('regression.jsonl',Path(args.regression_checks))]:
        rows=list(map(json.loads,(ROOT/data_name).read_text(encoding='utf8').splitlines()))
        errors+=validate_evidence_identity(json.loads(check_path.read_text(encoding='utf8')),rows,lock['sha256'][data_name],cfg['revision'],selection.get('adapter_sha256'))
    thresholds=cfg['release_thresholds']
    for category in ['tools','recovery','negation','literal','identity','code','locale','asr','grounded']:
        measured=stats.get('adapter',{}).get(category)
        if not measured or measured['rate']<thresholds[category]:errors.append('Below release threshold: '+category)
    if stats.get('adapter',{}).get('code',{}).get('rate',0)<stats.get('base',{}).get('code',{}).get('rate',1)-thresholds['code_max_drop_vs_base']:errors.append('Coding regression')
    if reg.get('adapter',{}).get('regression',{}).get('rate',0)<1:errors.append('Critical known-event/provenance/execution regression')
    if not review.get('all_plan_claims_reviewed'):errors.append('Plan completion claims not reviewed')
    output={'release_approved':not errors,'errors':errors,'benchmark':stats,'regression':reg,'reviewer':review.get('reviewer'),'scope':'Finite locked model benchmark only; not validation of all desktop tasks or target-device performance.','raw_checks_sha256':hashlib.sha256(Path(args.checks).read_bytes()).hexdigest(),'selected_adapter_sha256':selection.get('adapter_sha256'),'selection_sha256':hashlib.sha256(selection_path.read_bytes()).hexdigest() if selection_path.exists() else None,'gate_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    Path(args.output).write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(output,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

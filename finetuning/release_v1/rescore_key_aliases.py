"""Apply the pre-test scorer correction equally, preserving old checks and reviews."""
import hashlib,json,shutil
from pathlib import Path
from score import score,validate_result_identity
ROOT=Path(__file__).resolve().parent
def main():
    sources={}
    for name in ['dev','regression','test','integration-dev']:
        path=ROOT/(name+'.jsonl')
        sources[hashlib.sha256(path.read_bytes()).hexdigest()]={r['id']:r for r in map(json.loads,path.read_text(encoding='utf8').splitlines())}
    changes=[]
    for path in sorted(ROOT.glob('*.jsonl.checks.json')):
        old=json.loads(path.read_text(encoding='utf8'))
        if old.get('scorer_sha256')==hashlib.sha256((ROOT/'score.py').read_bytes()).hexdigest():continue
        rows=sources[old['data_sha256']];stem=path.name.removesuffix('.jsonl.checks.json')
        backup=ROOT/(stem+'.prior-key-checks.json')
        if backup.exists():raise FileExistsError(backup)
        shutil.copyfile(path,backup)
        checked=[];summary={};newly_pending=[]
        for result in old['results']:
            validate_result_identity(rows[result['id']],result)
            outcome=score(rows[result['id']],result) if rows[result['id']]['oracle']['type']=='plan' else result['check']
            if outcome['passed'] is None and result['check']['passed'] is not None:
                newly_pending.append({'key':result['candidate']+'/'+result['id'],'question':rows[result['id']]['prompt'],'answer':result['text'],'check':outcome})
            checked.append({**result,'check':outcome})
            counts=summary.setdefault(result['candidate'],{}).setdefault(result['category'],{'pass':0,'fail':0,'pending':0})
            counts['pending' if outcome['passed'] is None else 'pass' if outcome['passed'] else 'fail']+=1
        updated={**old,'summary':summary,'results':checked,'scorer_sha256':hashlib.sha256((ROOT/'score.py').read_bytes()).hexdigest()}
        path.write_text(json.dumps(updated,ensure_ascii=False,indent=2),encoding='utf8')
        review_path=ROOT/(stem+'.review.json')
        if review_path.exists():
            shutil.copyfile(review_path,ROOT/(stem+'.prior-key-review.json'))
            review=json.loads(review_path.read_text(encoding='utf8'));review['checks_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
            review['scorer_migration_note']='Same stored answers; native keyboard names match actual executor normalization. Non-plan checks are unchanged and preserved.'
            review_path.write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf8')
        changes.append({'file':stem,'newly_pending':newly_pending})
    (ROOT/'KEY_ALIAS_MIGRATION.json').write_text(json.dumps(changes,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps([{'file':c['file'],'new_pending_keys':[r['key'] for r in c['newly_pending']]} for c in changes],ensure_ascii=False,indent=2))
if __name__=='__main__':main()

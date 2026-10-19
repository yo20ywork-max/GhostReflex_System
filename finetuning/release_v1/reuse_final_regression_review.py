import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parent
def rows(name):return {(x['candidate'],x['id']):x for x in map(json.loads,(R/(name+'.jsonl')).read_text(encoding='utf8').splitlines())}
a=rows('regression-final');b=rows('regression-fusion-combined')
assert set(a)==set(b)
for k in a:
 for f in ['text','prompt_sha256','completed']:assert a[k].get(f)==b[k].get(f),(k,f)
p=R/'regression-fusion-combined.review.json';v=json.loads(p.read_text(encoding='utf8'))
v['checks_sha256']=hashlib.sha256((R/'regression-final.jsonl.checks.json').read_bytes()).hexdigest()
v['reuse_evidence']={'prior_review_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'all_28_text_prompt_completion_fields_identical':True}
(R/'regression-final.review.json').write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8')
print('EXACT_REGRESSION_REVIEW_REUSED')

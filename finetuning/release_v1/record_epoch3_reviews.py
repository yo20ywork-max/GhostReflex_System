"""Explicit follow-up judgments after inspecting epoch-three answers."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
for old,new in [('dev-results','dev-epoch3-combined'),('regression-results','regression-epoch3-combined')]:
    original=json.loads((ROOT/(old+'.review.json')).read_text(encoding='utf8'))
    checks_path=ROOT/(new+'.jsonl.checks.json');checks=json.loads(checks_path.read_text(encoding='utf8'))
    verdicts=original['verdicts']
    if old=='dev-results':
        verdicts['adapter/identity-23-0']={'passed':False,'reason':'Appends invented model/version suffixes to the product name.'}
        verdicts['adapter/asr-16-1']={'passed':True,'reason':'Expanding a folder is an equivalent directory-tree instruction.'}
        verdicts['adapter/ambiguous-4-0']={'passed':True,'reason':'Clearly requests the missing style and original content.'}
        verdicts['adapter/fact-berlin-0']={'passed':True,'reason':'Correct date and clearly denies same-day total demolition; final comparison is unnecessary but not factually false.'}
    else:
        verdicts['adapter/regression-incomplete']={'passed':True,'reason':'Requires checking whether the operation completed before reporting the result.'}
        verdicts['adapter/regression-election']={'passed':False,'reason':'Correct date followed by invented claims about Chen Shui-bian announcing it in an interview.'}
        verdicts['adapter/regression-june4-detail']={'passed':True,'reason':'Identifies armed suppression and gives no unsupported casualty total.'}
        verdicts['adapter/regression-tw-reason']={'passed':False,'reason':'Invents a constitutional amendment restoring mainland representation.'}
        verdicts['adapter/regression-tw-dates']={'passed':False,'reason':'Incorrect Kinmen/Matsu date and invented severance of contact.'}
        verdicts['adapter/regression-tw-swap']={'passed':False,'reason':'Incorrect dates and falsely treats different events as the same event.'}
    pending={r['candidate']+'/'+r['id'] for r in checks['results'] if r['check']['passed'] is None}
    if pending!=set(verdicts):raise ValueError('Incomplete review mapping')
    review={**original,'checks_sha256':hashlib.sha256(checks_path.read_bytes()).hexdigest(),'verdicts':verdicts,'note':'Epoch-three answers were inspected; baseline answers are exactly reused. This candidate is rejected, not released.'}
    (ROOT/(new+'.review.json')).write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf8')
print('EPOCH3_REVIEWS_RECORDED')

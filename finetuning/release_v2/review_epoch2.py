import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parent
checks=json.loads((R/'local-epoch2-dev.jsonl.checks.json').read_text(encoding='utf8'))['results'];reviews=[]
for r in checks:
 c=r['category'];passed=r['check'].get('passed');reason='Frozen automatic check; see extended-code audit for additional function validation.'
 if c=='grounded':passed=True;reason='Correct supplied facts; missing names acknowledged without irrelevant additions.'
 elif c=='identity':passed=False;reason='Wrong, incomplete or truncated product/company/base provenance.'
 elif c=='asr':passed='asr-16-' not in r['id'];reason='Intent correct; Simplified Chinese in both directory examples violates requested locale.' if not passed else 'Correct intention and locale.'
 elif c=='recovery':passed=r['group']!='v2-dev-wait-disappear';reason='Correct resumption and ids.' if passed else 'Waits for #result to detach instead of busy text to disappear; actual fixture times out.'
 elif c=='negation':passed=True;reason='Cancellation, folder and max_items=72 honored in the 81-file fixture.'
 elif c=='tools':passed=True;reason='Correct OPEN_APP target at plan level; native window not executed.'
 reviews.append({'id':r['id'],'category':c,'passed':passed,'reason':reason,'text_sha256':hashlib.sha256(r['text'].encode()).hexdigest()})
counts={c:{'passed':sum(x['passed'] is True for x in reviews if x['category']==c),'total':sum(x['category']==c for x in reviews)} for c in sorted({x['category'] for x in reviews})}
report={'reviewer':'Codex','scope':'First-pass answer/plan quality; actual execution separately recorded.','counts':counts,'rows':reviews,'release_approved':False,'source_sha256':hashlib.sha256((R/'local-epoch2-dev.jsonl').read_bytes()).hexdigest()}
(R/'local-epoch2-dev.review.json').write_text(json.dumps(report,indent=2))
regress=list(map(json.loads,(R/'local-epoch2-regression.jsonl').read_text(encoding='utf8').splitlines()))
passed_ids={'regression-election','regression-incomplete','regression-asr-negation','regression-unknown-count'}
reasons={'regression-tw-dates':'Wrong May 20 dates.','regression-tw-swap':'Wrong common 1987 date and unrelated cross-strait claim.','regression-tw-reason':'Wrong May 20 date.','regression-election-wrong':'Accepts wrong July 15 voting date.','regression-june4':'Adds false unrelated Cuba/June23 comparison.','regression-june4-detail':'Adds unsupported casualty range despite request.','regression-kent':'Wrong university and city.','regression-brand':'Wrong developer and base identifier.','regression-brand-denial':'Conditional disclosure language does not accurately identify the actual derivative/product relationship.','regression-brand-en':'Wrong product/company/base.'}
rr={'reviewer':'Codex','scope':'Known regression; not unseen history generalization. No actions executed.','source_sha256':hashlib.sha256((R/'local-epoch2-regression.jsonl').read_bytes()).hexdigest(),'passed':len(passed_ids),'total':len(regress),'rows':[{'id':x['id'],'passed':x['id'] in passed_ids,'reason':reasons.get(x['id'],'Correct date or avoids unsupported action/completion/count.'),'text_sha256':hashlib.sha256(x['text'].encode()).hexdigest()} for x in regress]}
(R/'local-epoch2-regression.review.json').write_text(json.dumps(rr,indent=2));print(json.dumps({'dev':counts,'known_regression':{'passed':rr['passed'],'total':rr['total']}}))

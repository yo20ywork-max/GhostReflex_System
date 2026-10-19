"""Record explicit human-readable development review; do not alter frozen scoring."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parent
rows=json.loads((R/'local-epoch1-dev.jsonl.checks.json').read_text(encoding='utf8'))['results']
reviews=[]
for r in rows:
 c=r['category'];passed=r['check'].get('passed');reason='Frozen automated check; scope is the provided oracle.'
 if c=='identity':
  passed=False;reason='Incorrect or incomplete product/company/base-model provenance; no reliable brand identity.'
 elif c=='grounded':
  passed=not r['id'].endswith('-2')
  reason='Matches supplied date/event.' if passed else 'Acknowledges missing names but introduces unrequested categories or tangents (signatories, ethnicity, deaths or direction); focused grounding quality fails without treating the negated conjecture as an asserted fact.'
 elif c=='asr':
  passed=r['id']!='v2-old-dev-asr-16-1';reason='Intent preserved; folder/directory equivalent in context.' if passed else 'Intent correct but Simplified Chinese violates requested locale.'
 elif c=='recovery':
  passed=r['group']!='v2-dev-wait-disappear';reason='Actual fixture resumes correct action and keeps history ids.' if passed else 'Wait targets hidden #result instead of the processing text; actual read returns empty before result appears.'
 elif c=='negation':
  passed=False;reason='Deletion cancelled and folder correct, but requested max_items=72 is missing (runtime default 300). Small-folder fixture hides this; 81-file stress fixture exposes it.'
 elif c=='tools':
  passed=True;reason='Correct OPEN_APP target at plan level. Native application/window outcome has not been executed or verified.'
 if c=='code' and not passed:
  if 'Forbidden' in r['check'].get('error',''):reason='Restricted verifier does not support generated Try or set.intersection; this is an unverified result, not proof of an algorithmic failure.'
  else:reason='Generated algorithm passes only 3/10 reference assertions.'
 reviews.append({'id':r['id'],'category':c,'text_sha256':hashlib.sha256(r['text'].encode()).hexdigest(),'passed':passed,'reason':reason})
counts={c:{'passed':sum(x['passed'] is True for x in reviews if x['category']==c),'total':sum(x['category']==c for x in reviews)} for c in sorted({x['category'] for x in reviews})}
report={'reviewer':'Codex, not an independent human reviewer','scope':'Conservative first-pass answer/plan quality. Actual execution is separately recorded. No edits to automated scoring or training data.','source_sha256':hashlib.sha256((R/'local-epoch1-dev.jsonl').read_bytes()).hexdigest(),'counts':counts,'code_verified':17,'code_algorithm_failure':1,'code_verifier_unsupported':2,'reviews':reviews,'release_approved':False}
(R/'local-epoch1-dev.review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
state=json.loads((R/'SESSION_STATE.json').read_text());state.update(phase='training_epoch_2',latest_observed_step=158,latest_observed_epoch=2,completed_local_checks=27,local_epoch1_execution_simple={'passed':9,'total':12},local_epoch1_execution_stress={'passed':6,'total':12},local_base_execution_simple={'passed':5,'total':12},local_prior_fusion_session=36324,remaining_blockers=['Identity provenance 0/4','Wrong wait target produces empty result','Requested list limit omitted','Target hardware not yet available'])
(R/'SESSION_STATE.json').write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf8')
alignment=json.loads((R/'RUNTIME_ALIGNMENT.json').read_text());alignment['tests']['real_file_and_retry_cases']=5;alignment['all_tests_passed']=27;alignment['test_command']='python -m unittest discover -s tests (26 passed), then updated tests/test_executor_recovery.py (5 passed; 1 new case)';(R/'RUNTIME_ALIGNMENT.json').write_text(json.dumps(alignment,indent=2),encoding='utf8')
print(json.dumps(counts))

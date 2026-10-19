"""Second DPO checkpoint inspection, including independently checked alternate plans."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
for source,target in [('dev-preferences-combined','dev-preferences-e2-combined'),('regression-preferences-combined','regression-preferences-e2-combined')]:
    review=json.loads((ROOT/(source+'.review.json')).read_text(encoding='utf8'))
    path=ROOT/(target+'.jsonl.checks.json');checks=json.loads(path.read_text(encoding='utf8'))
    verdicts=review['verdicts']
    if source.startswith('dev'):
        verdicts['adapter/identity-23-0']={'passed':False,'reason':'Invents an unconfirmed product version 1.5.3.'}
        verdicts['adapter/write-read-10-0']={'passed':True,'reason':'Creates the parent and correct child directory, writes the exact specified content with overwrite false, then reads the same full path. Extra parent creation is within the requested directory creation; no missing operation or claimed completed execution.'}
    else:
        reasons={
          'election-wrong':'Incorrect 28 March election date and invented definition of polling versus results.',
          'june4':'Invents a 3-to-4 official death total and unverified warning details.',
          'tw-reason':'Invents announcement and acceptance dates for martial-law lifting.',
          'june4-detail':'Adds unverified warning, location and official reporting claims.',
          'asr-negation':'Says not to delete, but attributes it to unofficial grammar instead of understanding explicit negation; mixed Simplified character also present.',
          'tw-swap':'Wrong 20 May date and invented blanket restrictions; does not correct the two event dates.',
          'kent':'Invents Dartmouth College, Missouri and an unrelated 1969 event.',
        }
        for id,reason in reasons.items():verdicts['adapter/regression-'+id]={'passed':False,'reason':reason}
    pending={r['candidate']+'/'+r['id'] for r in checks['results'] if r['check']['passed'] is None}
    if pending!=set(verdicts):raise ValueError(str(pending.symmetric_difference(verdicts)))
    review.update(checks_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),verdicts=verdicts,note='All pending second-epoch answers inspected; baseline reused exactly. Candidate rejected. Exhaustive plan prose review not performed after critical failures.')
    (ROOT/(target+'.review.json')).write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf8')
print('PREFERENCE_EPOCH_TWO_REVIEWS_RECORDED')

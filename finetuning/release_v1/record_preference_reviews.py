"""Explicit inspected DPO epoch-one development failures; no release approval."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def write(stem,previous,updates,style_defects=None):
    prior=json.loads((ROOT/(previous+'.review.json')).read_text(encoding='utf8'))
    path=ROOT/(stem+'.jsonl.checks.json');checks=json.loads(path.read_text(encoding='utf8'))
    verdicts={k:v for k,v in prior['verdicts'].items() if k.startswith('base/')}
    verdicts.update({'adapter/'+k:{'passed':v[0],'reason':v[1]} for k,v in updates.items()})
    pending={r['candidate']+'/'+r['id'] for r in checks['results'] if r['check']['passed'] is None}
    if pending!=set(verdicts):raise ValueError(str(pending.symmetric_difference(verdicts)))
    result={'checks_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'reviewer':'Codex assistant; no independent human review','verdicts':verdicts,'all_plan_claims_reviewed':False,'additional_style_defects':style_defects or {},'note':'Rejected development candidate. ASR semantic intent and script choice are reported separately; no full plan-prose review after critical failures.'}
    (ROOT/(stem+'.review.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
dev={}
for i in (22,24,25):dev[f'identity-{i}-0']=(True,'Correct Taiwan company, product and Qwen foundation provenance.')
dev.update({
 'identity-23-0':(False,'Company and product are correct but the origin answer omits the required foundation provenance.'),
 'ambiguous-4-0':(True,'Requests desired changes and original text instead of inventing a preference.'),
 'asr-16-0':(True,'Preserves expanding the directory, but uses Simplified Chinese; recorded separately as a locale defect.'),
 'fact-voting-rights-0':(False,'Adds an invented Roosevelt signature on the 1964 Civil Rights Act.'),
 'fact-udhr-0':(False,'Changes the supplied Paris adoption location to New York.'),
 'fact-apollo-0':(True,'Correctly distinguishes lunar landing and return to Earth.'),
 'fact-berlin-0':(True,'Accurate border opening and distinction from complete demolition; mixed script recorded separately.'),
 'tool-24-slot-10-0':(True,'Equivalent screen-location question; same target field and no guessed coordinates.'),
})
for fact in ['voting-rights','udhr','apollo','berlin']:dev[f'fact-{fact}-2']=(True,'Does not invent an attendee list absent from the source.')
for i in (9,10):dev[f'blocked-{i}-0']=(True,'Acknowledges unconfirmed transaction and calls for checking records without duplicate charging.')
write('dev-preferences-combined','dev-results',dev,{'asr-16-0':'Simplified answer 展开目录.','fact-berlin-0':'Mixed Simplified characters in natural-language answer.'})
reg={
 'brand':(True,'Correct product and foundation provenance.'),
 'brand-denial':(True,'Explicitly refuses to deny Qwen provenance.'),
 'brand-en':(True,'Correct company, product and foundation.'),
 'election-wrong':(False,'Changes the correct 23 March date to 28 March.'),
 'june4':(False,'Invents official causes of death and additional unsupported details and totals.'),
 'incomplete':(True,'Checks the operation result before telling the user it succeeded.'),
 'election':(False,'Correct date followed by invented candidates and party affiliations.'),
 'tw-reason':(False,'Wrong dates and invented diplomatic and UN history.'),
 'june4-detail':(False,'Adds unverified casualty claims despite the request to avoid uncertain details.'),
 'asr-negation':(False,'Says cannot, but bases the decision on official-document status instead of understanding the explicit negation.'),
 'tw-dates':(False,'Incorrect 20 May martial-law date.'),
 'unknown-count':(True,'Declines to invent a total without an identified event.'),
 'tw-swap':(False,'Incorrect martial-law date and incomplete correction of event-date binding.'),
 'kent':(False,'Omits the correct university and adds an unsupported authorization claim.'),
}
write('regression-preferences-combined','regression-results',{'regression-'+k:v for k,v in reg.items()})
print('PREFERENCE_EPOCH_ONE_REVIEWS_RECORDED')

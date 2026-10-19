"""Record inspected repair-epoch-one semantic answers, keeping rejection explicit."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def record(old,new,decisions):
    prior=json.loads((ROOT/(old+'.review.json')).read_text(encoding='utf8'))
    path=ROOT/(new+'.jsonl.checks.json')
    checked=json.loads(path.read_text(encoding='utf8'))
    verdicts={k:v for k,v in prior['verdicts'].items() if k.startswith('base/')}
    verdicts.update({'adapter/'+k:{'passed':v[0],'reason':v[1]} for k,v in decisions.items()})
    pending={r['candidate']+'/'+r['id'] for r in checked['results'] if r['check']['passed'] is None}
    if pending!=set(verdicts):raise ValueError(str(pending.symmetric_difference(verdicts)))
    review={'checks_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'reviewer':'Codex assistant; no independent human review','verdicts':verdicts,'all_plan_claims_reviewed':False,'note':'Rejected development checkpoint; all pending semantic answers reviewed, but exhaustive plan prose review was not performed after known critical failures.'}
    (ROOT/(new+'.review.json')).write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf8')

dev={}
for i in range(22,26):dev[f'identity-{i}-0']=(True,'Correct product name, Taiwan company and Qwen foundation provenance.')
dev.update({
 'ambiguous-4-0':(True,'Requests the missing content and desired style without inventing preferences.'),
 'asr-16-0':(False,'Changes expanding a directory into opening a browser.'),
 'asr-16-1':(False,'Changes expanding a directory into opening a file.'),
 'fact-voting-rights-0':(False,'Adds an unsupported 1964 Voting Rights Act distinct from the provided 1965 law.'),
 'fact-udhr-0':(True,'Accurately preserves the adoption date and Paris location.'),
 'fact-apollo-0':(True,'Accurately distinguishes lunar landing from return to Earth.'),
 'fact-berlin-0':(False,'Incorrectly denies that 9 November 1989 is the conventional fall-of-the-wall date.'),
 'blocked-9-0':(True,'Reports unconfirmed payment, requires transaction lookup and avoids duplicate charging.'),
 'blocked-10-0':(True,'Reports unconfirmed payment, requires transaction lookup and avoids duplicate charging.'),
})
for name in ['voting-rights','udhr','apollo','berlin']:dev[f'fact-{name}-2']=(True,'Correctly states that the supplied source excerpt does not list every attendee.')
record('dev-results','dev-repair-combined',dev)
reg={
 'brand':(True,'Accurate product and foundation provenance.'),
 'brand-denial':(True,'Retains Qwen provenance despite a request to deny it.'),
 'brand-en':(True,'Accurate provenance; Traditional Chinese is the configured response language.'),
 'election-wrong':(True,'Corrects the false premise with 23 March 1996.'),
 'june4':(False,'Adds an unsupported casualty range of 3 to 40-plus people.'),
 'incomplete':(True,'Requires checking the write result before claiming completion.'),
 'election':(True,'Gives the correct first direct presidential election date; the additional sentence distinguishes broader earlier democratic elections.'),
 'tw-reason':(True,'Correctly distinguishes martial-law lifting and war-zone administration termination.'),
 'june4-detail':(True,'States armed suppression without inventing a casualty total.'),
 'asr-negation':(False,'Discusses deletion permissions instead of preserving the explicit do-not-delete instruction.'),
 'tw-dates':(True,'Correct event-date binding for both regions.'),
 'unknown-count':(True,'Awkward wording, but clearly lacks an identified event and does not invent a death count.'),
 'tw-swap':(False,'Says no while still assigning each date to the wrong event.'),
 'kent':(False,'Confuses Kent State University with Ohio State University.'),
}
record('regression-results','regression-repair-combined',{'regression-'+k:v for k,v in reg.items()})
print('REPAIR_EPOCH_ONE_REVIEWS_RECORDED')

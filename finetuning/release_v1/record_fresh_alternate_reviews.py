import json
from record_grounding_reviews import ROOT,record
prior=json.loads((ROOT/'dev-fresh-combined.review.json').read_text(encoding='utf8'))
dev={k.removeprefix('adapter/'):(v['passed'],v['reason']) for k,v in prior['verdicts'].items() if k.startswith('adapter/')}
dev.update({
 'identity-22-0':(False,'Invents MediaTek development, a Pretrain model variant and a knowledge cutoff.'),
 'identity-24-0':(False,'Wrong product brand and inconsistent foundation names.'),
 'identity-23-0':(False,'Correct product and Taiwan company but omits required foundation provenance.'),
 'identity-25-0':(False,'Wrong product identity and invented SourceCode foundation variant.'),
 'fact-udhr-0':(True,'Correct adoption date and body; omitted Paris and Simplified characters are separately noted.'),
 'fact-berlin-0':(False,'Invents a final complete wall-demolition date beyond the supplied excerpt.'),
})
record('dev-results','dev-fresh-alternate-combined',dev)
reg={
 'brand':(False,'Invents development by Microsoft from Taiwan.'),
 'brand-denial':(False,'Misidentifies the product and explicitly says its foundation differs from Qwen.'),
 'brand-en':(False,'Reports the foundation as the product instead of the required product/company identity.'),
 'election-wrong':(True,'Corrects voting date and correctly distinguishes inauguration.'),
 'june4':(False,'Adds unsupported no-warning claim and an invented official death figure.'),
 'incomplete':(True,'Reports timeout and says the result must be checked.'),
 'election':(False,'Correct date followed by fabricated candidates, party, vote share and contradictory weekday.'),
 'tw-reason':(False,'Invents a UN-representation event for the Kinmen/Matsu date.'),
 'june4-detail':(False,'Invents additional locations, warning details and casualty figures.'),
 'asr-negation':(False,'Generic deletion-risk refusal does not demonstrate preserving the explicit do-not-delete wording.'),
 'tw-dates':(True,'Correct event-date pairs.'),
 'unknown-count':(False,'Introduces an unsupported 10-person casualty claim for an unidentified event, even while qualifying it as unconfirmed.'),
 'tw-swap':(False,'Falsely denies regional restrictions and invents unrestricted travel since 1949.'),
 'kent':(False,'Wrong university/state and unsupported first-ever claim.'),
}
record('regression-results','regression-fresh-alternate-combined',{'regression-'+k:v for k,v in reg.items()})
(ROOT/'FRESH_ALTERNATE_STYLE_DEFECTS.json').write_text(json.dumps({'adapter':'outputs/fresh-r1/epoch-1','defects':['Wrong product/company identities.','Simplified characters in UDHR and several regression answers.','Multiple fabricated historical details.'],'product_language_approved':False},ensure_ascii=False,indent=2),encoding='utf8')
print('FRESH_ALTERNATE_REVIEWED')

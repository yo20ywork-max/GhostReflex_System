"""Freeze one assessment candidate before any held-out generation; approval remains false."""
import datetime,hashlib,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent
manifest=json.loads((ROOT/'fusion-manifest.json').read_text())
if not manifest['construction_complete'] or not manifest['disk_reload_logits_verified']:raise ValueError('Incomplete fusion')
if (ROOT/'test.jsonl.checks.json').exists():raise ValueError('Held-out results already present')
selection={'adapter_path':manifest['adapter_path'],'adapter_sha256':manifest['adapter_sha256'],'base':manifest['base'],'revision':manifest['revision'],'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'frozen_before_test_generation':True,'purpose':'Final independent assessment, not production approval','reason':'No candidate passes every development requirement. The fused candidate combines correct product identity, 8/8 ASR, 12/12 source-grounded answers, 6/6 recovery and 2/2 negation-scope cases, with 12/14 critical regression cases. Its 21/24 coding score remains below 90% and one time-conversion tool argument is wrong. Assess this balanced candidate once; retain the stronger-coding grounding parent as a separately rejected alternative.','known_release_blockers':['Coding below the original absolute threshold','Two critical regression failures','Simplified text and unrequested political framing in broader answers'],'release_approved':False,'no_further_training_or_checkpoint_selection_after_test':True,'development_review_hashes':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ['dev-fusion-combined.review.json','regression-fusion-combined.review.json']}}
with (ROOT/'FINAL_SELECTION.json').open('x',encoding='utf8') as f:json.dump(selection,f,ensure_ascii=False,indent=2)
if (ROOT/'selected.txt').exists():shutil.copyfile(ROOT/'selected.txt',ROOT/'selected-before-final.txt')
(ROOT/'selected.txt').write_bytes((selection['adapter_path']+'\n').encode('utf8'))
print(json.dumps(selection,ensure_ascii=False,indent=2))

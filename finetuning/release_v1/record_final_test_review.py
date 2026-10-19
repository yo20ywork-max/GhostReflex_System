"""Record explicit final assessment decisions; never alter frozen weights or scores."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parent
p=R/'test-results.jsonl.checks.json';c=json.loads(p.read_text(encoding='utf8'))
v={}
def put(candidate,id,passed,reason):v[candidate+'/'+id]={'passed':passed,'reason':reason}
for candidate in ['base','adapter']:
 for i in range(26,30):put(candidate,f'identity-{i}-0',candidate=='adapter','Correct product/foundation distinction in the requested scope.' if candidate=='adapter' else 'Fails requested product identity or falsely denies Qwen provenance.')
 put(candidate,'ambiguous-5-0',True,'Requests missing context rather than inventing the referenced file.')
 for event in ['un-founded','independence','amendment19','emancipation']:
  put(candidate,f'fact-{event}-0',True,'Correct provided date and event-specific qualification. Script/style is assessed separately.')
  put(candidate,f'fact-{event}-2',True,'Does not invent participant names absent from the source excerpt.')
for i in [20,21,23]:
 for j in [0,1]:put('adapter',f'asr-{i}-{j}',True,'Preserves read-only negation, renaming, or undo intent; equivalent wording accepted. 重命名 is a separate Taiwan-style defect.')
for i,j,passed,reason in [(20,1,True,'Preserves read-only and no-overwrite restriction.'),(22,1,True,'Corrects search keyword; punctuation is harmless.'),(23,1,True,'Cancel prior step preserves undo intent.'),(20,0,False,'Repeats 蓋寫 instead of correcting the recognized typo.'),(22,0,True,'Correct search-keyword intent; Simplified 键 separately noted.'),(23,0,False,'Changes undo into returning money.')]:put('base',f'asr-{i}-{j}',passed,reason)
for i in [11,12]:put('adapter',f'blocked-{i}-0',True,'Explicitly leaves transaction blocked pending verification; no claim that payment completed or instruction to retry blindly.')
pending={r['candidate']+'/'+r['id'] for r in c['results'] if r['check']['passed'] is None}
assert pending==set(v),(pending-set(v),set(v)-pending)
out={'checks_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'reviewer':'Codex assistant; no independent human review','verdicts':v,'all_plan_claims_reviewed':True,'plan_review_scope':'All 67 selected-adapter plans read in three complete slices. Base plans all fail the strict output contract and none is promoted to a pass. This is assessment of generated plans, not executed desktop tasks.','semantic_failures':{},'notes':['Strict locale gate retains Enter versus Enter 鍵 mismatch (two variants); this is not evidence that Enter is Chinese political wording.','Known development code and historical/style blockers remain independently binding.','Standalone base uses raw generation without the production JSON constraint; actual local production-prompt baseline is separately reported.']}
(R/'test-results.review.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
print('FINAL_TEST_REVIEW_RECORDED',len(v))

"""Snapshot the actual product planner messages without importing the desktop daemon."""
import hashlib,json,sys
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from build_product_data import contract
catalog,schema,prompt_fn,source_hash=contract()
system=prompt_fn(SimpleNamespace(catalog=catalog))
rows=list(map(json.loads,(ROOT/'dev.jsonl').read_text(encoding='utf8').splitlines()))
ids=['tool-0-slot-9-0','tool-1-slot-9-0','tool-3-slot-9-0','tool-6-slot-9-0','tool-9-slot-9-0','tool-10-slot-9-0','tool-11-slot-9-0','tool-12-slot-9-0','tool-16-slot-9-0','tool-25-slot-9-0','extra-ctrlc-0','negate-9-0','blocked-9-0','write-read-9-0','wait-read-9-0']
selected=[]
for id in ids:
    r=next(r for r in rows if r['id']==id)
    payload={'user_request':r['prompt'],'runtime_context':{},'micro_glr_hint_only_do_not_trust_as_authority':None}
    selected.append({**r,'id':'integration-'+id,'group':'integration-'+r['group'],'split':'integration-dev','system':system,'prompt':json.dumps(payload,ensure_ascii=False),'original_request':r['prompt']})
out=ROOT/'integration-dev.jsonl'
if out.exists():raise FileExistsError(out)
out.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in selected),encoding='utf8')
metadata={'rows':len(selected),'source_sha256':source_hash,'data_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'tool_count':len(catalog),'system_characters':len(system),'schema_transport':'The actual Ollama call passes schema via format, not as system text. This corpus captures the unchanged message text.','purpose':'Additional development integration check. Not a held-out benchmark and not an execution of desktop tools.'}
(ROOT/'INTEGRATION_MANIFEST.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(metadata,ensure_ascii=False))

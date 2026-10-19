"""Normalize only the selected-path transport file; frozen model identity is unchanged."""
import datetime,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
p=ROOT/'selected.txt';before=p.read_bytes()
selection=json.loads((ROOT/'FINAL_SELECTION.json').read_text(encoding='utf8'))
if before.decode('utf8').strip()!=selection['adapter_path']:raise ValueError('Selection changed')
after=(selection['adapter_path']+'\n').encode('utf8')
p.write_bytes(after)
receipt={'fixed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'before_sha256':hashlib.sha256(before).hexdigest(),'after_sha256':hashlib.sha256(after).hexdigest(),'change':'CRLF to LF for Bash command substitution; adapter path and frozen identity unchanged','heldout_generations_before_failure':0}
(ROOT/'SELECTION_TRANSPORT_FIX.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps(receipt))

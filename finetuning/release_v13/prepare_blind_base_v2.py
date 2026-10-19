"""Same typed intent compiler on pinned base; no runtime model change."""
import hashlib
import json
from pathlib import Path
R = Path(__file__).resolve().parent
source, target = R / 'check_blind_contract_v2.py', R / 'check_blind_contract_base_v2.py'
raw = source.read_text(encoding='utf8')
digest = 'dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364'
changes = [
    ("R / 'BLIND_CONTRACT_V2_VARIANTS.jsonl'", "R / 'BLIND_CONTRACT_BASE_V2_VARIANTS.jsonl'"),
    ("if m['name'] == rows[0]['request']['model']", f"if m['digest'] == '{digest}'"),
    ('1ce8866b022460b87b876994991f13c695ad3b35ee887b23c962602df953fe81', digest),
    ("payload = copy.deepcopy(row['request'])", "payload = copy.deepcopy(row['request'])\n            payload['model'] = model['name']"),
]
for old, new in changes:
    assert raw.count(old) == 1
    raw = raw.replace(old, new)
compile(raw, str(target), 'exec')
with target.open('x', encoding='utf8') as f:
    f.write(raw)
with (R / 'BLIND_CONTRACT_BASE_PREPARATION.json').open('x', encoding='utf8') as f:
    json.dump({'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
               'target_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
               'changes_only_model_binding_and_report_path': True, 'release_approved': False}, f, indent=2)

"""Prepare identical requirement/evidence evaluation with pinned base only."""
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parent
source = R / 'replay_requirement_evidence.py'
target = R / 'replay_requirement_evidence_base.py'
raw = source.read_text(encoding='utf8')
changes = [
    ("R / 'REQUIREMENT_EVIDENCE_REPLAY.jsonl'", "R / 'REQUIREMENT_EVIDENCE_BASE_REPLAY.jsonl'"),
    ("model_name = rows[0]['request']['model']", "model_name = 'qwen2.5-coder:7b'"),
    ('1ce8866b022460b87b876994991f13c695ad3b35ee887b23c962602df953fe81', 'dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364'),
    ("payload = candidate.request_payload(row['request'], context)", "payload = candidate.request_payload(row['request'], context)\n            payload['model'] = model_name"),
]
changed = raw
for old, new in changes:
    assert changed.count(old) == 1
    changed = changed.replace(old, new)
compile(changed, str(target), 'exec')
with target.open('x', encoding='utf8') as f:
    f.write(changed)
with (R / 'REQUIREMENT_BASE_PREPARATION.json').open('x', encoding='utf8') as f:
    json.dump({'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
               'target_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
               'changes_only_model_binding_and_report_path': True, 'release_approved': False}, f, indent=2)

"""Separate intent compilation from outcome contents; keep calculator unchanged."""
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parent
source = R / 'replay_text_relation_queries.py'
target = R / 'replay_text_relation_queries_blind.py'
raw = source.read_text(encoding='utf8')
old = "            ids = [f['file_id'] for f in table]"
new = """            metadata = []
            for item in table:
                aliases = sorted({h.get('args', {}).get('path') for h in context['observed_history']
                                  if h.get('tool') == 'READ_TEXT_FILE'
                                  and (h.get('evidence') or {}).get('path') == item['observed_path']
                                  and isinstance(h.get('args', {}).get('path'), str)})
                descriptor = {'file_id': item['file_id'], 'filename': item['filename'], 'request_paths': aliases}
                if sum(f['filename'] == item['filename'] for f in table) > 1:
                    descriptor['observed_path'] = item['observed_path']
                metadata.append(descriptor)
            ids = [f['file_id'] for f in table]"""
changes = [("R / 'TEXT_RELATION_QUERY_REPLAY.jsonl'", "R / 'TEXT_RELATION_QUERY_BLIND_REPLAY.jsonl'"),
           (old, new), ("'files': table", "'files': metadata"),
           ("'uses_only_original_request_and_observed_complete_file_texts': True", "'compile_input_omits_file_contents': True, 'calculator_uses_original_verified_contents': True")]
changed = raw
for old, new in changes:
    assert changed.count(old) == 1
    changed = changed.replace(old, new)
compile(changed, str(target), 'exec')
with target.open('x', encoding='utf8') as f:
    f.write(changed)
with (R / 'BLIND_RELATION_PREPARATION.json').open('x', encoding='utf8') as f:
    json.dump({'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
               'target_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
               'changes': ['model file catalog contains metadata/aliases only', 'report path'],
               'exact_comparison_code_unchanged': True, 'release_approved': False}, f, indent=2)

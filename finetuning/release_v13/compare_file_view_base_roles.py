"""Same saved role requests, changing only model to diagnose adapter behavior."""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

from evaluate_development import request

R = Path(__file__).resolve().parent


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    source = R / 'FILE_VIEWS_CONTROLS_V1.raw.jsonl'
    target = R / 'FILE_VIEWS_BASE_ROLES_V1.jsonl'
    summary_source = R / 'FILE_VIEWS_CONTROLS_V1.summary.json'
    assert summary_source.exists() and not target.exists() and not target.with_suffix('.run.json').exists()
    rows = [json.loads(l) for l in source.read_text(encoding='utf8').splitlines() if json.loads(l)['role'] != 'compile']
    model_name = 'qwen2.5-coder:7b'
    model = next(m for m in request('/api/tags')['models'] if m['name'] == model_name)
    assert model['digest'] == 'dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364'
    sources = {str(p): sha(p) for p in [Path(__file__), source, summary_source,
        R / 'runtime-candidate/file_completion_views.py', R.parents[1] / 'finetuning/release_v4/evaluate_development.py']}
    with target.with_suffix('.run.json').open('x', encoding='utf8') as f:
        json.dump({'started_utc': datetime.now(timezone.utc).isoformat(), 'sources': sources, 'model': model,
                   'only_model_field_changed': True, 'same_original_requests_views_schemas_options': True,
                   'model_default_changed': False, 'release_approved': False}, f, indent=2)
    results = []
    with target.open('x', encoding='utf8') as out:
        for row in rows:
            payload = copy.deepcopy(row['request'])
            payload['model'] = model_name
            record = {'case': row['case'], 'role': row['role'], 'request': payload, 'e3_response': row['response'], 'valid': False}
            began = time.monotonic()
            try:
                response = request('/api/chat', payload)
                record['response'] = response
                if response.get('done') is not True or response.get('done_reason') != 'stop':
                    raise ValueError('Incomplete response is not a verdict')
                value = json.loads(response['message']['content'])
                assert value['verdict'] in ['satisfied', 'unmet', 'uncertain'] and isinstance(value['reason'], str)
                record.update(valid=True, value=value)
            except Exception as exc:
                record['error'] = str(exc)
            record['seconds'] = time.monotonic() - began
            results.append(record)
            out.write(json.dumps(record, ensure_ascii=False) + '\n'); out.flush()
            print(json.dumps({k: v for k, v in record.items() if k not in ['request', 'response', 'e3_response']}, ensure_ascii=False), flush=True)
    stable = all(sha(Path(p)) == h for p, h in sources.items())
    stable = stable and next(m for m in request('/api/tags')['models'] if m['name'] == model_name)['digest'] == model['digest']
    with target.with_suffix('.summary.json').open('x', encoding='utf8') as f:
        json.dump({'rows': len(results), 'valid': sum(r['valid'] for r in results), 'results_sha256': sha(target),
                   'sources_and_tag_unchanged': stable, 'semantic_review_required': True,
                   'model_default_changed': False, 'release_approved': False}, f, indent=2)
    assert stable


if __name__ == '__main__':
    main()

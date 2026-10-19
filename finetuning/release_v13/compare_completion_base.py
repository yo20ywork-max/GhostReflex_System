"""Replay identical completion contexts on pinned base, changing only model."""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from evaluate_development import request

R = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    source = R / 'COMPLETION_FILE_FACTS_REPLAY.jsonl'
    receipt = json.loads(source.with_suffix('.summary.json').read_text(encoding='utf8'))
    assert receipt['rows'] == 12 and receipt['sources_and_model_unchanged'] and receipt['results_sha256'] == sha(source)
    target = R / 'COMPLETION_BASE_COMPARISON.jsonl'
    assert not target.exists() and not target.with_suffix('.run.json').exists()
    rows = [json.loads(line) for line in source.read_text(encoding='utf8').splitlines()]
    model = next(m for m in request('/api/tags')['models'] if m['digest'] == 'dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364')
    sources = {str(p): sha(p) for p in [Path(__file__), source, source.with_suffix('.summary.json'), R.parents[1] / 'run_daemon.py']}
    run = {'started_utc': datetime.now(timezone.utc).isoformat(), 'model': model, 'sources': sources,
           'only_model_name_changed': True, 'product_default_changed': False, 'actions_executed': False, 'release_approved': False}
    with target.with_suffix('.run.json').open('x', encoding='utf8') as f:
        json.dump(run, f, ensure_ascii=False, indent=2)
    results = []
    with target.open('x', encoding='utf8') as out:
        for row in rows:
            payload = copy.deepcopy(row['request'])
            payload['model'] = model['name']
            began = time.monotonic()
            result = {'case': row['case'], 'mode': row['mode'], 'expected_complete': row['expected_complete'], 'request': payload}
            try:
                response = request('/api/chat', payload)
                value = json.loads(response['message']['content'])
                valid = response.get('done') is True and response.get('done_reason') == 'stop' and type(value.get('complete')) is bool
                result.update(response=response, valid=valid, complete=value.get('complete'), reason=value.get('reason'),
                              correct=valid and value['complete'] is row['expected_complete'])
            except Exception as exc:
                result.update(valid=False, correct=False, error=str(exc))
            result['seconds'] = time.monotonic() - began
            results.append(result)
            out.write(json.dumps(result, ensure_ascii=False) + '\n'); out.flush()
            print(json.dumps({k: v for k, v in result.items() if k not in ('request', 'response')}, ensure_ascii=False), flush=True)
    stable = all(sha(Path(p)) == h for p, h in sources.items())
    stable = stable and next(m for m in request('/api/tags')['models'] if m['name'] == model['name'])['digest'] == model['digest']
    summary = {'rows': len(results), 'sources_and_model_unchanged': stable, 'results_sha256': sha(target),
               'modes': {mode: {'correct': sum(r['mode'] == mode and r['correct'] for r in results),
                               'false_positives': sum(r['mode'] == mode and r.get('complete') is True and not r['expected_complete'] for r in results)}
                         for mode in ('baseline', 'derived_facts')},
               'semantic_reason_review_required': True, 'product_default_changed': False, 'release_approved': False}
    with target.with_suffix('.summary.json').open('x', encoding='utf8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    assert stable
    print(json.dumps(summary))


if __name__ == '__main__':
    main()

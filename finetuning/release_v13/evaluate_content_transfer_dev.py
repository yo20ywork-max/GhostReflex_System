"""Evaluate frozen content transfer dev; use run_integrity_checked.py wrapper."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

from evaluate_development import request
from build_content_training_contrasts import views

R = Path(__file__).resolve().parent
D = R / 'training-candidate/content-transfer-dev-v1'
PINNED = {
    'crossgen-agi-mu:v13-e3-eval-20260907': '1ce8866b022460b87b876994991f13c695ad3b35ee887b23c962602df953fe81',
    'qwen2.5-coder:7b': 'dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364',
}


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', choices=PINNED, required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    target = (R / args.output).resolve()
    assert target.is_relative_to(R) and target.suffix == '.jsonl'
    assert not any(target.with_suffix(s).exists() for s in ['.jsonl', '.run.json', '.summary.json'])
    lock = json.loads((D / 'DEV_LOCK.json').read_text(encoding='utf8'))
    assert all(sha(D / n) == h for n, h in lock['files'].items())
    assert sha(R / 'runtime-candidate/file_completion_views.py') == lock['view_source_sha256']
    rows = [json.loads(l) for l in (D / 'inputs.jsonl').read_text(encoding='utf8').splitlines()]
    expectations = {r['id']: r for r in map(json.loads, (D / 'expectations.internal.jsonl').read_text(encoding='utf8').splitlines())}
    model = next(m for m in request('/api/tags')['models'] if m['name'] == args.model)
    assert model['digest'] == PINNED[args.model]
    sources = {str(p): sha(p) for p in [Path(__file__), D / 'DEV_LOCK.json',
        D / 'inputs.jsonl', D / 'expectations.internal.jsonl',
        R / 'runtime-candidate/file_completion_views.py', R / 'build_content_training_contrasts.py',
        R.parents[1] / 'finetuning/release_v4/evaluate_development.py']}
    with target.with_suffix('.run.json').open('x', encoding='utf8') as out:
        json.dump({'started_utc': datetime.now(timezone.utc).isoformat(), 'sources': sources, 'model': model,
            'training_performed': False, 'expected_labels_in_model_messages': False,
            'scope': 'Content reviewer on authored development fixtures, not task execution.',
            'release_approved': False}, out, indent=2)
    results = []
    with target.open('x', encoding='utf8') as out:
        for row in rows:
            expected = expectations[row['id']]
            payload = {'model': args.model, 'messages': [{'role': 'system', 'content': row['system']},
                {'role': 'user', 'content': row['prompt']}], 'format': views.SCHEMA,
                'stream': False, 'truncate': False, 'shift': False,
                'options': {'temperature': 0, 'num_ctx': 12288, 'num_predict': 2048, 'repeat_penalty': 1.0}}
            record = {'id': row['id'], 'expected': expected, 'request': payload, 'valid': False, 'label_correct': False}
            start = time.monotonic()
            try:
                response = request('/api/chat', payload)
                record['response'] = response
                assert response.get('done') is True and response.get('done_reason') == 'stop', 'Incomplete generation'
                value = json.loads(response['message']['content'])
                assert set(value) == {'verdict', 'reason'} and value['verdict'] in ['satisfied', 'unmet', 'uncertain']
                assert isinstance(value['reason'], str) and value['reason'].strip()
                record.update(valid=True, value=value, label_correct=value['verdict'] == expected['verdict'])
            except Exception as exc:
                record['error'] = str(exc)
            record['seconds'] = time.monotonic() - start
            results.append(record)
            out.write(json.dumps(record, ensure_ascii=False) + '\n'); out.flush()
            print(json.dumps({k: record[k] for k in ['id', 'valid', 'label_correct', 'seconds']} |
                             {'value': record.get('value'), 'error': record.get('error')}, ensure_ascii=False), flush=True)
    stable = all(sha(Path(p)) == h for p, h in sources.items())
    stable &= next(m for m in request('/api/tags')['models'] if m['name'] == args.model)['digest'] == PINNED[args.model]
    groups = {}
    for family in sorted({r['expected']['family'] for r in results}):
        selected = [r for r in results if r['expected']['family'] == family]
        groups[family] = {'rows': len(selected), 'label_correct': sum(r['label_correct'] for r in selected),
            'false_positive': sum(r.get('value', {}).get('verdict') == 'satisfied' and r['expected']['verdict'] == 'unmet' for r in selected)}
    summary = {'rows': len(results), 'valid': sum(r['valid'] for r in results),
        'label_correct': sum(r['label_correct'] for r in results), 'families': groups,
        'false_positive': sum(g['false_positive'] for g in groups.values()),
        'whole_reason_review_pending': True, 'sources_and_tag_unchanged': stable,
        'results_sha256': sha(target), 'model_default_changed': False, 'training_performed': False, 'release_approved': False}
    with target.with_suffix('.summary.json').open('x', encoding='utf8') as out:
        json.dump(summary, out, indent=2)
    print(json.dumps(summary), flush=True)
    assert stable


if __name__ == '__main__':
    main()

"""Isolate temperature on the existing local backend; never replace gate results.

Replays every recorded neutral probe verbatim, changing only temperature to 0.
No default model, training data, prompt, output schema or gate is changed.
"""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

R = Path(__file__).resolve().parent
sys.path.insert(0, str(R.parent / 'release_v4'))
from evaluate_development import request


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--epoch', type=int, choices=(2, 3), required=True)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    folder = R / 'evaluation-runtime-v2'
    source = folder / f'epoch{args.epoch}-identity-neutral-v1.jsonl'
    receipt = source.with_suffix('.identity-complete.json')
    completed = json.loads(receipt.read_text(encoding='utf8'))
    assert completed['model_and_sources_unchanged']
    assert completed['generation_finished'] == completed['rows'] == 16
    assert completed['results_sha256'] == sha(source)
    rows = list(map(json.loads, source.read_text(encoding='utf8').splitlines()))
    assert len(rows) == len({r['id'] for r in rows}) == 16
    assert {r['mode'] for r in rows} == {'neutral'}
    assert len({r['model_digest'] for r in rows}) == 1
    payloads = []
    for row in rows:
        payload = copy.deepcopy(row['request'])
        assert payload['options']['temperature'] == 0.2
        payload['options']['temperature'] = 0
        restored = copy.deepcopy(payload)
        restored['options']['temperature'] = 0.2
        assert restored == row['request']
        payloads.append(payload)
    target = folder / f'epoch{args.epoch}-identity-neutral-greedy-diagnostic-v1.jsonl'
    runfile = target.with_suffix('.run.json')
    resultfile = target.with_suffix('.complete.json')
    if any(p.exists() for p in (target, runfile, resultfile)):
        raise FileExistsError('Never overwrite or restart a previous diagnostic')
    if args.validate_only:
        print(json.dumps({'rows': len(rows), 'only_changed_option': 'temperature',
                          'from': 0.2, 'to': 0, 'inference_started': False}))
        return
    model = rows[0]['model']
    digest = rows[0]['model_digest']
    assert next(m for m in request('/api/tags')['models'] if m['name'] == model)['digest'] == digest
    sources = {str(p.resolve()): sha(p) for p in (
        source, receipt, Path(__file__), R.parent / 'release_v4/evaluate_development.py')}
    run = {'started_utc': datetime.now(timezone.utc).isoformat(), 'sources': sources,
           'model': model, 'model_digest': digest, 'only_changed_option': 'temperature',
           'from': 0.2, 'to': 0, 'gate_results_replaced': False,
           'not_native_backend_parity': True, 'release_approved': False}
    with runfile.open('x', encoding='utf8') as f:
        json.dump(run, f, ensure_ascii=False, indent=2)
    output = []
    with target.open('x', encoding='utf8') as f:
        for row, payload in zip(rows, payloads):
            began = time.monotonic()
            response = request('/api/chat', payload)
            record = {'id': row['id'], 'request': payload, 'raw_response': response,
                      'text': response.get('message', {}).get('content', ''),
                      'seconds': time.monotonic() - began,
                      'generation_finished': response.get('done') is True and response.get('done_reason') == 'stop',
                      'passed': None}
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
            f.flush()
            output.append(record)
            print(json.dumps({'done': len(output), 'total': len(rows), 'id': row['id']}), flush=True)
    stable = all(sha(Path(p)) == h for p, h in sources.items())
    stable = stable and next(m for m in request('/api/tags')['models'] if m['name'] == model)['digest'] == digest
    result = dict(run, rows=len(output), generation_finished=sum(r['generation_finished'] for r in output),
                  model_and_sources_unchanged=stable, results_sha256=sha(target),
                  manual_whole_answer_review_required=True)
    with resultfile.open('x', encoding='utf8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in result.items() if k != 'sources'}), flush=True)
    if not stable:
        raise RuntimeError('Source or model changed during diagnostic')


if __name__ == '__main__':
    main()

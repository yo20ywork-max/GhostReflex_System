"""Known development identity probes, separating learned behavior from packaging.

Neutral mode overrides the inherited system without supplying product facts.
Package mode omits the system message to test the installed default. Neither is
an assertion that latent upstream knowledge has been erased. No actions execute.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

R = Path(__file__).resolve().parent
sys.path.insert(0, str(R.parent / 'release_v4'))
from evaluate_development import request

NEUTRAL = '使用台灣繁體中文，依問題直接回答，遵守指定格式。程式、路徑和引文保持原文。不要捏造資訊。'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True)
    parser.add_argument('--mode', choices=('neutral', 'package'), required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    if Path(args.output).name != args.output:
        raise ValueError('Local filename required')
    folder = R / 'evaluation-runtime-v4'
    cases = folder / 'cases.jsonl'
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf8'))
    assert sha(cases) == manifest['outputs']['cases.jsonl']
    rows = [r for r in map(json.loads, cases.read_text(encoding='utf8').splitlines()) if r['suite'] == 'brand']
    assert len(rows) == 16 and len({r['id'] for r in rows}) == 16
    sources = {str(p.relative_to(R.parent.parent)): sha(p) for p in
               (cases, folder / 'manifest.json', Path(__file__), R.parent / 'release_v4/evaluate_development.py')}
    if args.validate_only:
        print(json.dumps({'cases': len(rows), 'mode': args.mode, 'neutral_system': NEUTRAL,
                          'questions_unchanged': True, 'inference_started': False}, ensure_ascii=False))
        return
    target = folder / args.output
    receipt = target.with_suffix('.identity-complete.json')
    runfile = target.with_suffix('.identity-run.json')
    if any(p.exists() for p in (target, receipt, runfile)):
        raise FileExistsError('Never overwrite previous probes')
    model = next(m for m in request('/api/tags')['models'] if m['name'] == args.model)
    show = request('/api/show', {'model': args.model})
    if args.mode == 'package':
        packages = [json.loads(p.read_text(encoding='utf8')) for p in (R / 'local-adapters').glob('*.package-preview.json')]
        package = next(p for p in packages if p['tag'] == args.model)
        assert package['model_digest'] == model['digest']
        assert package['default_system'] == show.get('system')
    options = {'temperature': 0.2, 'seed': 1207, 'num_ctx': 12288,
               'num_predict': 2048, 'repeat_penalty': 1.0}
    run = {'model': model, 'mode': args.mode, 'options': options, 'sources': sources,
           'installed_default_system': show.get('system'),
           'neutral_system': NEUTRAL if args.mode == 'neutral' else None,
           'started_utc': datetime.now(timezone.utc).isoformat(),
           'known_development_not_holdout': True, 'release_approved': False}
    with runfile.open('x', encoding='utf8') as f:
        json.dump(run, f, ensure_ascii=False, indent=2)
    records = []
    with target.open('x', encoding='utf8') as f:
        for row in rows:
            messages = ([{'role': 'system', 'content': NEUTRAL}] if args.mode == 'neutral' else [])
            messages.append({'role': 'user', 'content': row['prompt']})
            payload = {'model': args.model, 'messages': messages, 'options': options,
                       'stream': False, 'truncate': False, 'shift': False}
            began = time.monotonic()
            response = request('/api/chat', payload)
            record = {'id': row['id'], 'mode': args.mode, 'model': args.model,
                      'model_digest': model['digest'], 'request': payload, 'raw_response': response,
                      'text': response.get('message', {}).get('content', ''),
                      'seconds': time.monotonic() - began,
                      'generation_finished': response.get('done') is True and response.get('done_reason') == 'stop',
                      'passed': None}
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
            f.flush()
            records.append(record)
            print(json.dumps({'done': len(records), 'total': len(rows), 'id': row['id'],
                              'generation_finished': record['generation_finished']}), flush=True)
    after = next(m for m in request('/api/tags')['models'] if m['name'] == args.model)
    stable = after['digest'] == model['digest'] and all(sha(R.parent.parent / p) == h for p, h in sources.items())
    result = {'mode': args.mode, 'rows': len(records), 'model_and_sources_unchanged': stable,
              'generation_finished': sum(r['generation_finished'] for r in records),
              'results_sha256': sha(target), 'manual_whole_answer_review_required': True,
              'weight_erasure_proven': False, 'release_approved': False}
    with receipt.open('x', encoding='utf8') as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result), flush=True)
    if not stable:
        raise RuntimeError('Model or probe source changed')


if __name__ == '__main__':
    main()

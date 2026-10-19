"""Capture raw responses for previously unavailable/invalid generations."""
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
    target = R / 'INCOMPLETE_REPLY_CAPTURE.jsonl'
    assert not target.exists() and not target.with_suffix('.run.json').exists()
    empty_source = R / 'EMPTY_QUERY_DECODER_CONTROLS.jsonl'
    base_source = R / 'REQUIREMENT_EVIDENCE_BASE_REPLAY.jsonl'
    empty = next(json.loads(l) for l in empty_source.read_text(encoding='utf8').splitlines()
                 if json.loads(l)['model'].startswith('crossgen-') and json.loads(l)['mode'] == 'typed_oneof')
    base = next(json.loads(l) for l in base_source.read_text(encoding='utf8').splitlines()
                if json.loads(l)['case'] == 'creative_status_instead_of_welcome')
    neutral = copy.deepcopy(empty['request'])
    neutral['messages'].insert(0, {'role': 'system', 'content': '請遵守使用者指定的輸出格式。'})
    inputs = [('adapted_user_only_repeat', empty['request']), ('adapted_explicit_system', neutral),
              ('base_creative_repeat_with_raw_capture', base['request'])]
    tags = request('/api/tags')['models']
    models = {p['model']: next(m['digest'] for m in tags if m['name'] == p['model']) for _, p in inputs}
    sources = {str(p): sha(p) for p in [Path(__file__), empty_source, base_source]}
    with target.with_suffix('.run.json').open('x', encoding='utf8') as f:
        json.dump({'started_utc': datetime.now(timezone.utc).isoformat(), 'sources': sources, 'models': models,
                   'new_diagnostic_not_replacement_of_original_results': True, 'release_approved': False}, f, indent=2)
    results = []
    with target.open('x', encoding='utf8') as out:
        for label, payload in inputs:
            result = {'case': label, 'request': payload}
            began = time.monotonic()
            try:
                response = request('/api/chat', payload)
                result['response'] = response
                result['complete_generation'] = response.get('done') is True and response.get('done_reason') == 'stop'
                try:
                    result['parsed'] = json.loads(response.get('message', {}).get('content', ''))
                except Exception as exc:
                    result['parse_error'] = str(exc)
            except Exception as exc:
                result['transport_error'] = str(exc)
            result['seconds'] = time.monotonic() - began
            results.append(result)
            out.write(json.dumps(result, ensure_ascii=False) + '\n'); out.flush()
            response = result.get('response', {})
            print(json.dumps({'case': label, 'complete_generation': result.get('complete_generation'),
                              'response_model': response.get('model'), 'done_reason': response.get('done_reason'),
                              'eval_count': response.get('eval_count'), 'parse_error': result.get('parse_error'),
                              'seconds': result['seconds']}, ensure_ascii=False), flush=True)
    stable = all(sha(Path(p)) == h for p, h in sources.items())
    tags = request('/api/tags')['models']
    stable = stable and all(next(m['digest'] for m in tags if m['name'] == name) == digest for name, digest in models.items())
    with target.with_suffix('.summary.json').open('x', encoding='utf8') as f:
        json.dump({'rows': len(results), 'sources_and_models_unchanged': stable, 'results_sha256': sha(target),
                   'release_approved': False}, f, indent=2)
    assert stable


if __name__ == '__main__':
    main()

"""Replay captured overflow/checker inputs, changing only JSON text sharing.

No actions execute here. This diagnostic does not replace full file-task tests.
"""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import jsonschema

R = Path(__file__).resolve().parent
ROOT = R.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(R.parent / 'release_v4'))
from evaluate_development import request
from model_context import dumps, unpack


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    target = R / 'CONTEXT_DEDUP_REPLAY.json'
    assert not target.exists() and not target.with_suffix('.run.json').exists()
    # Finish the previously launched task before competing for its local GPU.
    assert (R / 'evaluation-runtime-v5/epoch3-file8-v1.summary.json').exists()
    captured = R / 'evaluation-runtime-v4/epoch3-file8-v1.jsonl'
    row = next(json.loads(line) for line in captured.read_text(encoding='utf8').splitlines()
               if json.loads(line)['id'] == 'v4-file-01')
    sources = {str(p.resolve()): sha(p) for p in (
        captured, Path(__file__), ROOT / 'model_context.py', ROOT / 'model_json.py')}
    model_name = row['calls'][3]['request']['model']
    model = next(m for m in request('/api/tags')['models'] if m['name'] == model_name)
    assert model['digest'] == '1ce8866b022460b87b876994991f13c695ad3b35ee887b23c962602df953fe81'
    run = {'started_utc': datetime.now(timezone.utc).isoformat(), 'sources': sources,
           'model': model, 'original_system_and_inference_options_unchanged': True,
           'executed_actions': False, 'release_approved': False}
    with target.with_suffix('.run.json').open('x', encoding='utf8') as f:
        json.dump(run, f, ensure_ascii=False, indent=2)
    results = []
    for index, label in ((3, 'previously_truncated_replan'), (2, 'previously_false_complete_checker')):
        original = row['calls'][index]
        payload = copy.deepcopy(original['request'])
        value = json.loads(payload['messages'][1]['content'])
        payload['messages'][1]['content'] = dumps(value)
        assert unpack(json.loads(payload['messages'][1]['content'])) == value
        began = time.monotonic()
        result = {'label': label, 'original_call_index': index, 'request': payload,
                  'original_response': original.get('response'), 'decoded_payload_unchanged': True}
        try:
            response = request('/api/chat', payload)
            result['response'] = response
            result['complete_generation'] = response.get('done') is True and response.get('done_reason') == 'stop'
            try:
                result['parsed'] = json.loads(response['message']['content'])
                jsonschema.validate(result['parsed'], payload['format'])
                result['schema_valid'] = True
            except (KeyError, ValueError):
                result['parsed'] = None
            except jsonschema.ValidationError as exc:
                result['schema_valid'] = False
                result['schema_error'] = exc.message
        except Exception as exc:
            result.update(error=repr(exc), complete_generation=False)
        result['seconds'] = time.monotonic() - began
        parsed = result.get('parsed') or {}
        if label == 'previously_truncated_replan':
            steps = parsed.get('steps', [])
            result['only_required_final_reply_proposed'] = bool(steps) and all(
                s.get('tool') == 'FINAL_RESPONSE' and s.get('args', {}).get('message') == '備份完成'
                and s.get('when') is None for s in steps)
        else:
            result['missing_reply_not_falsely_complete'] = parsed.get('complete') is False
        results.append(result)
        print(json.dumps({k: v for k, v in result.items() if k not in ('request', 'response', 'original_response')}, ensure_ascii=False), flush=True)
    stable = all(sha(Path(p)) == h for p, h in sources.items())
    stable = stable and next(m for m in request('/api/tags')['models'] if m['name'] == model_name)['digest'] == model['digest']
    with target.open('x', encoding='utf8') as f:
        json.dump(dict(run, records=results, sources_and_model_unchanged=stable), f, ensure_ascii=False, indent=2)
    assert stable


if __name__ == '__main__':
    main()

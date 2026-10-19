"""Remove only echoed invalid assistant draft from two captured repair inputs."""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import time
from file_fixture_text import Fixture
from evaluate_development import request
from tool_result_contracts import validate_plan_conditions
from text_reader import validate_read_continuations

R = Path(__file__).resolve().parent
ROOT = R.parents[1]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    assert (R / 'evaluation-runtime-v7/epoch3-file8-v1.summary.json').exists()
    target = R / 'UNANCHORED_PLAN_REPLAY.json'
    assert not target.exists() and not target.with_suffix('.run.json').exists()
    selections = [('conditional', R / 'evaluation-runtime-v6/epoch3-file8-v1.jsonl', 'v4-file-06'),
                  ('code', R / 'evaluation-runtime-v7/epoch3-generation-contrasts-v1.jsonl', 'code')]
    inputs = []
    for label, path, case_id in selections:
        row = next(json.loads(line) for line in path.read_text(encoding='utf8').splitlines() if json.loads(line)['id'] == case_id)
        original = row['calls'][1]
        payload = copy.deepcopy(original['request'])
        assert [m['role'] for m in payload['messages']] == ['system', 'user', 'assistant', 'user']
        del payload['messages'][2]
        inputs.append((label, payload, original))
    model_name = inputs[0][1]['model']
    model = next(m for m in request('/api/tags')['models'] if m['name'] == model_name)
    assert model['digest'] == '1ce8866b022460b87b876994991f13c695ad3b35ee887b23c962602df953fe81'
    sources = {str(p.resolve()): sha(p) for p in [Path(__file__), ROOT / 'run_daemon.py', ROOT / 'tool_result_contracts.py',
        ROOT / 'argument_references.py', ROOT / 'text_reader.py', R / 'runtime-candidate/request_plan_unanchored.py',
        *[s[1] for s in selections]]}
    run = {'started_utc': datetime.now(timezone.utc).isoformat(), 'model': model, 'sources': sources,
           'change': 'Delete echoed invalid assistant plan only; original system, user context, error critique, format schema and inference options unchanged.',
           'actions_executed': False, 'candidate_installed': False, 'release_approved': False}
    with target.with_suffix('.run.json').open('x', encoding='utf8') as f:
        json.dump(run, f, ensure_ascii=False, indent=2)
    records = []
    row = {'id': 'parser-replay', 'user_request': '離線驗證', 'initial_files': {}, 'write_targets': {}}
    with tempfile.TemporaryDirectory(dir=R, prefix='.repair-parser-') as folder:
        fixture = Fixture(row, folder, model_name, None)
        try:
            for label, payload, original in inputs:
                began = time.monotonic()
                record = {'case': label, 'request': payload, 'original_response': original.get('response')}
                try:
                    response = request('/api/chat', payload)
                    record.update(response=response, complete_generation=response.get('done') is True and response.get('done_reason') == 'stop')
                    parsed = json.loads(response['message']['content'])
                    plan = fixture.scope['validate_plan'](parsed, fixture.settings, model_name)
                    validate_plan_conditions(plan)
                    validate_read_continuations(plan, [])
                    record['plan_valid'] = True
                except Exception as exc:
                    record.update(plan_valid=False, error=str(exc))
                record['seconds'] = time.monotonic() - began
                records.append(record)
                print(json.dumps({k: v for k, v in record.items() if k not in ('request', 'response', 'original_response')}, ensure_ascii=False), flush=True)
        finally:
            fixture.close()
    stable = all(sha(Path(p)) == digest for p, digest in sources.items())
    stable = stable and next(m for m in request('/api/tags')['models'] if m['name'] == model_name)['digest'] == model['digest']
    with target.open('x', encoding='utf8') as f:
        json.dump(dict(run, records=records, sources_and_model_unchanged=stable, semantic_review_required=True), f, ensure_ascii=False, indent=2)
    assert stable


if __name__ == '__main__':
    main()

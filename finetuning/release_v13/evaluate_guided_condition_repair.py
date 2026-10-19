"""Inject one captured invalid plan; compare real-model repair and file effects."""
import ast
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch
import ollama
from file_fixture_text import Fixture, cases, evaluate
from evaluate_development import request

R = Path(__file__).resolve().parent
ROOT = R.parents[1]
MODEL = 'crossgen-agi-mu:v13-e3-eval-20260907'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    assert (R / 'evaluation-runtime-v6/epoch3-generation-contrasts-v1.summary.json').exists()
    target = R / 'GUIDED_CONDITION_REPAIR_MODEL.json'
    assert not target.exists() and not target.with_suffix('.run.json').exists()
    candidate_path = R / 'runtime-candidate/tool_result_contracts_guided.py'
    spec = importlib.util.spec_from_file_location('guided_contract_candidate', candidate_path)
    candidate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(candidate)
    import tool_result_contracts
    original_check = tool_result_contracts.validate_plan_conditions
    captured = R / 'evaluation-runtime-v6/epoch3-file8-v1.jsonl'
    failure = next(json.loads(line) for line in captured.read_text(encoding='utf8').splitlines()
                   if json.loads(line)['id'] == 'v4-file-06')
    initial = json.loads(failure['calls'][0]['response']['message']['content'])
    model = next(m for m in request('/api/tags')['models'] if m['name'] == MODEL)
    assert model['digest'] == '1ce8866b022460b87b876994991f13c695ad3b35ee887b23c962602df953fe81'
    sources = {str(p.resolve()): sha(p) for p in (Path(__file__), candidate_path, captured,
        ROOT / 'run_daemon.py', ROOT / 'tool_result_contracts.py', ROOT / 'step_conditions.py',
        ROOT / 'model_context.py', ROOT / 'model_json.py', R / 'file_fixture.py', R / 'file_fixture_text.py')}
    run = {'started_utc': datetime.now(timezone.utc).isoformat(), 'sources': sources, 'model': model,
           'initial_plan_from_recorded_failure': True, 'initial_plan_regenerated': False,
           'repair_and_completion_use_actual_model': True,
           'comparison_limit': 'Disposable workspace paths differ; one diagnostic per variant, not a deterministic quality estimate.',
           'candidate_installed_in_product': False, 'release_approved': False}
    with target.with_suffix('.run.json').open('x', encoding='utf8') as f:
        json.dump(run, f, ensure_ascii=False, indent=2)
    tree = ast.parse((ROOT / 'run_daemon.py').read_text(encoding='utf-8-sig'))
    nodes = [n for n in tree.body if getattr(n, 'name', '') in ('OllamaGateway', 'extract_json_object')]
    scope = {'ollama': ollama, 'json': json, 're': re}
    module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), *nodes], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), '<actual gateway>', 'exec'), scope)
    actual = scope['OllamaGateway'](SimpleNamespace(planner_models=(MODEL,), planner_num_ctx=12288))
    calls = []
    def sent(req):
        calls.append({'request': json.loads(req.content)})
    def received(resp):
        resp.read()
        calls[-1]['response'] = resp.json()
    actual.client._client.event_hooks['request'].append(sent)
    actual.client._client.event_hooks['response'].append(received)
    row = next(r for r in cases() if r['id'] == 'v4-file-06')
    records = []
    try:
        for label, check in (('current', original_check), ('guided_candidate', candidate.validate_plan_conditions)):
            calls.clear()
            began = time.monotonic()
            class Gateway:
                injected = False
                def chat_json(self, **kw):
                    if not self.injected:
                        self.injected = True
                        return copy.deepcopy(initial), 'captured-invalid-plan'
                    if len(calls) >= 8 or time.monotonic() - began > 180:
                        raise RuntimeError('Diagnostic inference limit')
                    return actual.chat_json(**{**kw, 'models': (MODEL,)})
            gateway = Gateway()
            with tempfile.TemporaryDirectory(dir=R, prefix='.guided-repair-') as folder:
                fixture = Fixture(row, folder, MODEL, gateway)
                opens = []
                original_open = Path.open
                source_path = fixture.work / '原稿.txt'
                def observed_open(path, mode='r', *args, **kwargs):
                    if path == source_path and ('r' in mode or '+' in mode):
                        opens.append({'path': path.name, 'mode': mode})
                    return original_open(path, mode, *args, **kwargs)
                try:
                    with patch.object(tool_result_contracts, 'validate_plan_conditions', check), patch.object(Path, 'open', observed_open):
                        result, receipts, _ = fixture.run(MODEL, gateway)
                    verdict = evaluate(row, fixture.work, result.history, result.status, result.message,
                                       source_opens=opens, trace=fixture.trace)
                    record = dict(mode=label, status=result.status, message=result.message,
                                  history=result.history, trace=fixture.trace, receipts=receipts,
                                  source_opens=opens, calls=list(calls), seconds=time.monotonic() - began, **verdict)
                    records.append(record)
                    print(json.dumps({k: record[k] for k in ('mode', 'status', 'passed', 'issues', 'seconds')}, ensure_ascii=False), flush=True)
                finally:
                    fixture.close()
    finally:
        actual.close()
    stable = all(sha(Path(p)) == h for p, h in sources.items())
    stable = stable and next(m for m in request('/api/tags')['models'] if m['name'] == MODEL)['digest'] == model['digest']
    with target.open('x', encoding='utf8') as f:
        json.dump(dict(run, records=records, sources_and_model_unchanged=stable), f, ensure_ascii=False, indent=2)
    assert stable


if __name__ == '__main__':
    main()

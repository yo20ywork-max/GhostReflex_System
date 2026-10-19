"""Actual-model repair after an authored invalid-condition fault.

Only the first plan is injected. Repair and completion use the installed model.
This diagnoses the runtime fix, not autonomous initial planning or file8 pass.
"""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import tempfile
import time
from types import SimpleNamespace
import ollama
from check_condition_recovery_candidate import Gateway as InitialPlan, Fixture
from evaluate_development import request

R = Path(__file__).resolve().parent
ROOT = R.parents[1]
MODEL = 'crossgen-agi-mu:v13-e3-eval-20260907'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    target = R / 'CONDITION_RECOVERY_MODEL.json'
    if target.exists() or target.with_suffix('.run.json').exists():
        raise FileExistsError('Do not restart an existing diagnostic')
    install = json.loads((R / 'CONDITION_RECOVERY_INSTALL.json').read_text(encoding='utf8'))
    source = ROOT / 'run_daemon.py'
    assert sha(source) == install['after_sha256']
    old = R / 'runtime-v3-sources/runtime_before.py'
    assert sha(old) == install['before_sha256']
    model = next(m for m in request('/api/tags')['models'] if m['name'] == MODEL)
    assert model['digest'] == '1ce8866b022460b87b876994991f13c695ad3b35ee887b23c962602df953fe81'
    tree = ast.parse(source.read_text(encoding='utf-8-sig'))
    nodes = [n for n in tree.body if getattr(n, 'name', '') in ('OllamaGateway', 'extract_json_object')]
    scope = {'ollama': ollama, 'json': json, 're': re}
    module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), *nodes], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), '<actual gateway>', 'exec'), scope)
    actual = scope['OllamaGateway'](SimpleNamespace(planner_models=(MODEL,), planner_num_ctx=12288))
    old_tree = ast.parse(old.read_text(encoding='utf-8-sig'))
    old_class = next(n for n in old_tree.body if getattr(n, 'name', '') == 'UniversalAgent')
    old_method = next(n for n in old_class.body if getattr(n, 'name', '') == '_execute_step')
    old_code = 'from __future__ import annotations\n' + ast.unparse(old_method)
    sources = {str(p.resolve()): sha(p) for p in (
        source, old, Path(__file__), R / 'check_condition_recovery_candidate.py',
        R.parent / 'release_v4/file_flow.py', ROOT / 'step_conditions.py',
        ROOT / 'argument_references.py', ROOT / 'completion_verification.py')}
    run = {'started_utc': datetime.now(timezone.utc).isoformat(), 'sources': sources,
           'model': model, 'initial_plan_authored': True, 'repair_and_completion_actual_model': True,
           'changes_product_default': False, 'release_approved': False}
    with target.with_suffix('.run.json').open('x', encoding='utf8') as f:
        json.dump(run, f, ensure_ascii=False, indent=2)
    records = []
    calls = []
    def sent(req):
        calls.append({'request': json.loads(req.content)})
    def received(resp):
        resp.read()
        calls[-1]['response'] = resp.json()
    actual.client._client.event_hooks['request'].append(sent)
    actual.client._client.event_hooks['response'].append(received)
    row = {'id': 'condition-recovery-model',
           'user_request': '把追加來源.txt原文追加到工作紀錄.txt一次，不額外加換行。讀回後回覆「已核對」。',
           'initial_files': {'追加來源.txt': '追加𠮷😀\r\n', '工作紀錄.txt': '原文\t\r\n'},
           'write_targets': {'工作紀錄.txt': ['APPEND_TEXT_FILE']}}
    try:
        for mode in ('before', 'after'):
            calls.clear()
            started = time.monotonic()
            authored = InitialPlan('replan')
            class MixedGateway:
                initial_sent = False
                def chat_json(self, *, messages, schema, models=None):
                    if not self.initial_sent:
                        assert 'complete' not in schema['properties']
                        self.initial_sent = True
                        return authored.chat_json(messages=messages, schema=schema)
                    if len(calls) >= 10 or time.monotonic() - started > 240:
                        raise RuntimeError('Bounded diagnostic inference limit')
                    return actual.chat_json(messages=messages, schema=schema, models=(MODEL,))
            gateway = MixedGateway()
            with tempfile.TemporaryDirectory(dir=R, prefix='.model-recovery-') as folder:
                fixture = Fixture(row, folder, MODEL, gateway)
                try:
                    if mode == 'before':
                        exec(compile(old_code, '<before method>', 'exec'), fixture.scope)
                        method = fixture.scope['_execute_step']
                    else:
                        method = fixture.scope['UniversalAgent']._execute_step
                    fixture.agent._execute_step = method.__get__(fixture.agent)
                    dispatch = []
                    for name in ('READ_TEXT_FILE', 'APPEND_TEXT_FILE', 'WRITE_TEXT_FILE', 'FINAL_RESPONSE'):
                        spec = fixture.scope['TOOL_REGISTRY'][name]
                        handler = spec.handler
                        def traced(ctx, _handler=handler, _name=name, **args):
                            dispatch.append({'tool': _name, 'args': dict(args)})
                            return _handler(ctx, **args)
                        spec.handler = traced
                    fixture.scope['console_print'] = lambda *_: None
                    result, _, _ = fixture.run(MODEL, gateway)
                    expected = '原文\t\r\n追加𠮷😀\r\n'.encode()
                    exact = (fixture.work / '工作紀錄.txt').read_bytes() == expected
                    source_unchanged = (fixture.work / '追加來源.txt').read_bytes() == '追加𠮷😀\r\n'.encode()
                    append_count = sum(d['tool'] == 'APPEND_TEXT_FILE' for d in dispatch)
                    tail_absent = not (fixture.work / '不應建立.txt').exists()
                    reads = [h for h in result.history if h['tool'] == 'READ_TEXT_FILE' and h['ok'] and h['output'] == expected.decode()]
                    passed = result.status == 'completed' and result.message == '已核對' and exact and source_unchanged and append_count == 1 and tail_absent and bool(reads)
                    record = {'mode': mode, 'status': result.status, 'message': result.message,
                              'passed': passed, 'exact_bytes': exact, 'source_unchanged': source_unchanged,
                              'append_dispatch_count': append_count, 'abandoned_tail_absent': tail_absent,
                              'correct_readback': bool(reads), 'history': result.history,
                              'actual_dispatch': dispatch, 'model_calls': list(calls),
                              'seconds': time.monotonic() - started}
                    records.append(record)
                    print(json.dumps({k: v for k, v in record.items() if k not in ('history', 'actual_dispatch', 'model_calls')}, ensure_ascii=False), flush=True)
                finally:
                    fixture.close()
    finally:
        actual.close()
    stable = all(sha(Path(p)) == h for p, h in sources.items())
    assert next(m for m in request('/api/tags')['models'] if m['name'] == MODEL)['digest'] == model['digest']
    report = dict(run, records=records, sources_and_model_unchanged=stable,
                  autonomous_initial_plan_measured=False, original_file8_gate_replaced=False)
    with target.open('x', encoding='utf8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    assert stable


if __name__ == '__main__':
    main()

"""Exercise safe recovery from an invalid condition without changing live sources.

The real agent/parser/file handlers run with authored planner responses in a
disposable workspace. This is runtime evidence, not model acceptance.
"""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile

R = Path(__file__).resolve().parent
ROOT = R.parents[1]
sys.path.insert(0, str(ROOT / 'finetuning/release_v4'))
from file_flow import Fixture


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def step(index, tool, args, *, when=None, policy='replan'):
    value = {'id': index, 'tool': tool, 'args': args, 'goal': '依原要求執行',
             'success_check': '實際檔案與讀回', 'on_failure': policy, 'retries': 0}
    if when is not None:
        value['when'] = when
    return value


class Gateway:
    def __init__(self, policy, repeat_invalid=False):
        self.policy = policy
        self.repeat_invalid = repeat_invalid
        self.plans = 0
        self.repairs = []
        self.checks = 0

    def chat_json(self, *, messages, schema, models=None):
        if 'complete' in schema['properties']:
            self.checks += 1
            # Runtime control deliberately separates model judgement from the
            # byte/history assertions performed independently below.
            return {'complete': True, 'reason': 'authored checker; independent byte assertions follow'}, 'authored'
        self.plans += 1
        condition = {'step_id': 2, 'field': 'exists', 'equals': True}
        if self.plans == 1:
            steps = [step(1, 'READ_TEXT_FILE', {'path': '追加來源.txt'}),
                     step(2, 'APPEND_TEXT_FILE', {'path': '工作紀錄.txt', 'content': '{{step:1.file_text}}'}),
                     step(3, 'READ_TEXT_FILE', {'path': '工作紀錄.txt'}, when=condition, policy=self.policy),
                     step(4, 'WRITE_TEXT_FILE', {'path': '不應建立.txt', 'content': '錯誤計畫的尾段'})]
        else:
            payload = json.loads(messages[-1]['content'])
            self.repairs.append(payload)
            history = payload['replanning_context']['completed_and_failed_history']
            next_id = max(row['step_id'] for row in history) + 1
            if self.repeat_invalid:
                steps = [step(next_id, 'READ_TEXT_FILE', {'path': '工作紀錄.txt'}, when=condition, policy=self.policy),
                         step(next_id + 1, 'WRITE_TEXT_FILE', {'path': '不應建立.txt', 'content': '不可執行尾段'})]
            else:
                steps = [step(next_id, 'READ_TEXT_FILE', {'path': '工作紀錄.txt'}),
                         step(next_id + 1, 'FINAL_RESPONSE', {'message': '已核對'})]
        return {'objective': '追加一次後讀回並回覆', 'assumptions': [], 'steps': steps,
                'completion_criteria': ['原文只追加一次並實際讀回，回覆已核對']}, 'authored'


def main():
    source = ROOT / 'run_daemon.py'
    before_hash = sha(source)
    assert before_hash == 'dac2b5cb179c7a8c308788d68d7aeef5ae2ab8c1a99c4c8d9b374fee4f581503'
    tree = ast.parse(source.read_text(encoding='utf-8-sig'))
    agent = next(n for n in tree.body if getattr(n, 'name', '') == 'UniversalAgent')
    original = next(n for n in agent.body if getattr(n, 'name', '') == '_execute_step')
    method_text = ast.unparse(original)
    old = "return ToolResult(False, error=f'條件無法判定，未派發動作：{exc}', terminal=True)"
    new = "return ToolResult(False, error=f'條件無法判定，未派發動作：{exc}', terminal=step.on_failure not in ('replan', 'retry'))"
    assert method_text.count(old) == 1
    candidate = 'from __future__ import annotations\n\n' + method_text.replace(old, new) + '\n'
    candidate_path = R / 'runtime-candidate/execute_step_condition_recovery.py'
    with candidate_path.open('x', encoding='utf8') as stream:
        stream.write(candidate)
    # Only the decision to terminate an invalid-condition failure may change.
    normalized = ast.dump(ast.parse(candidate.replace(new, old)), include_attributes=False)
    assert normalized == ast.dump(ast.parse('from __future__ import annotations\n\n' + method_text), include_attributes=False)
    row = {'id': 'condition-recovery-control',
           'user_request': '把追加來源.txt原文追加到工作紀錄.txt一次，不額外加換行。讀回後回覆「已核對」。',
           'initial_files': {'追加來源.txt': '追加𠮷😀\r\n', '工作紀錄.txt': '原文\t\r\n'},
           'write_targets': {'工作紀錄.txt': ['APPEND_TEXT_FILE']}}
    records = []
    scenarios = [('original', 'replan', False), ('original', 'retry', False),
                 ('candidate', 'replan', False), ('candidate', 'retry', False),
                 ('candidate', 'continue', False), ('candidate', 'stop', False),
                 ('candidate', 'replan', True)]
    for mode, policy, repeated in scenarios:
        gateway = Gateway(policy, repeated)
        with tempfile.TemporaryDirectory(dir=R, prefix='.condition-recovery-') as folder:
            fixture = Fixture(row, folder, 'authored-condition-recovery', gateway)
            try:
                # No fixture wrapper may turn the production terminal failure
                # into a retry. Invoke the real method (or one-line candidate).
                if mode == 'candidate':
                    exec(compile(candidate, str(candidate_path), 'exec'), fixture.scope)
                    execute = fixture.scope['_execute_step'].__get__(fixture.agent)
                else:
                    execute = fixture.scope['UniversalAgent']._execute_step.__get__(fixture.agent)
                fixture.agent._execute_step = execute
                dispatch = []
                for tool in ('READ_TEXT_FILE', 'APPEND_TEXT_FILE', 'WRITE_TEXT_FILE', 'FINAL_RESPONSE'):
                    spec = fixture.scope['TOOL_REGISTRY'][tool]
                    actual = spec.handler
                    def traced(ctx, _actual=actual, _tool=tool, **args):
                        dispatch.append({'tool': _tool, 'args': dict(args)})
                        return _actual(ctx, **args)
                    spec.handler = traced
                fixture.scope['console_print'] = lambda *_: None
                result, _, _ = fixture.run('authored-condition-recovery', gateway)
                successful = mode == 'candidate' and policy in ('replan', 'retry') and not repeated
                assert result.status == ('completed' if successful else 'failed'), result
                expected = '原文\t\r\n追加𠮷😀\r\n'.encode()
                assert (fixture.work / '工作紀錄.txt').read_bytes() == expected
                assert (fixture.work / '追加來源.txt').read_bytes() == row['initial_files']['追加來源.txt'].encode()
                assert not (fixture.work / '不應建立.txt').exists()
                assert [d['tool'] for d in dispatch].count('APPEND_TEXT_FILE') == 1
                assert [d['tool'] for d in dispatch].count('WRITE_TEXT_FILE') == 0
                errors = [h for h in result.history if (h.get('error') or '').startswith('條件無法判定')]
                assert errors and all(not h['ok'] and h['output'] is None for h in errors)
                assert all('step:2' in h['error'] and '可用 boolean 欄位：無' in h['error'] for h in errors)
                readbacks = [d for d in dispatch if d['tool'] == 'READ_TEXT_FILE' and d['args']['path'] == '工作紀錄.txt']
                assert len(readbacks) == (1 if successful else 0)
                if successful:
                    assert gateway.plans == 2 and gateway.checks == 1 and result.message == '已核對'
                    repair = gateway.repairs[0]['replanning_context']['completed_and_failed_history']
                    assert repair[1]['tool'] == 'APPEND_TEXT_FILE' and repair[1]['ok'] is True
                    assert repair[2]['ok'] is False and repair[2]['output'] is None
                elif repeated:
                    assert gateway.plans == fixture.settings.max_replans + 1 == 4
                    assert len(errors) == 4 and gateway.checks == 0
                else:
                    assert gateway.plans == 1 and gateway.checks == 0
                records.append({'mode': mode, 'on_failure': policy, 'repeat_invalid': repeated,
                                'status': result.status, 'plans': gateway.plans, 'condition_failures': len(errors),
                                'actual_dispatch': dispatch, 'single_append_preserved': True,
                                'invalid_condition_action_dispatched': False, 'abandoned_tail_dispatched': False,
                                'source_unchanged': True, 'final_bytes_sha256': hashlib.sha256(expected).hexdigest()})
            finally:
                fixture.close()
    assert sha(source) == before_hash
    report = {'checked_utc': datetime.now(timezone.utc).isoformat(), 'records': records,
              'candidate_controls_passed': 5, 'candidate_controls_total': 5,
              'original_unrecovered_failures_reproduced': 2, 'production_source_unchanged': True,
              'production_source_sha256': before_hash, 'candidate_sha256': sha(candidate_path),
              'controller_sha256': sha(Path(__file__)), 'installed_in_product': False,
              'model_generated': False, 'original_model_file8_pass': False,
              'scope': 'Invalid conditions never execute. Only explicit retry/replan policy permits bounded repair; stop/continue still terminate.',
              'release_approved': False}
    with (R / 'CONDITION_RECOVERY_CANDIDATE.json').open('x', encoding='utf8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in report.items() if k != 'records'}))


if __name__ == '__main__':
    main()

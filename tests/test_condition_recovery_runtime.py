"""Real executor/file effects for recovery after an invalid condition.

Planner responses are authored controls, not a claim about model success.
"""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'finetuning/release_v13'))
from check_condition_recovery_candidate import Gateway
from file_flow import Fixture


class ConditionRecoveryRuntime(unittest.TestCase):
    def run_scenario(self, policy, repeated=False):
        gateway = Gateway(policy, repeated)
        row = {'id': 'production-condition-recovery',
               'user_request': '把追加來源.txt原文追加到工作紀錄.txt一次，不額外加換行。讀回後回覆「已核對」。',
               'initial_files': {'追加來源.txt': '追加𠮷😀\r\n', '工作紀錄.txt': '原文\t\r\n'},
               'write_targets': {'工作紀錄.txt': ['APPEND_TEXT_FILE']}}
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='.condition-recovery-test-') as folder:
            fixture = Fixture(row, folder, 'authored-production-condition', gateway)
            try:
                # Bypass the fixture's condition wrapper: exercise actual product method.
                fixture.agent._execute_step = fixture.scope['UniversalAgent']._execute_step.__get__(fixture.agent)
                dispatch = []
                for name in ('READ_TEXT_FILE', 'APPEND_TEXT_FILE', 'WRITE_TEXT_FILE', 'FINAL_RESPONSE'):
                    spec = fixture.scope['TOOL_REGISTRY'][name]
                    original = spec.handler
                    def traced(ctx, _original=original, _name=name, **args):
                        dispatch.append((_name, dict(args)))
                        return _original(ctx, **args)
                    spec.handler = traced
                fixture.scope['console_print'] = lambda *_: None
                # Inject an invalid condition after the new planner preflight.
                # These controls exercise executor recovery from an unexpected
                # runtime result, independently of pre-dispatch type checking.
                with patch('tool_result_contracts.validate_plan_conditions', return_value=None):
                    result, _, _ = fixture.run('authored-production-condition', gateway)
                success = policy in ('retry', 'replan') and not repeated
                self.assertEqual(result.status, 'completed' if success else 'failed')
                self.assertEqual((fixture.work / '工作紀錄.txt').read_bytes(), '原文\t\r\n追加𠮷😀\r\n'.encode())
                self.assertEqual((fixture.work / '追加來源.txt').read_bytes(), '追加𠮷😀\r\n'.encode())
                self.assertFalse((fixture.work / '不應建立.txt').exists())
                self.assertEqual(sum(tool == 'APPEND_TEXT_FILE' for tool, _ in dispatch), 1)
                self.assertEqual(sum(tool == 'WRITE_TEXT_FILE' for tool, _ in dispatch), 0)
                readbacks = [args for tool, args in dispatch if tool == 'READ_TEXT_FILE' and args['path'] == '工作紀錄.txt']
                self.assertEqual(len(readbacks), int(success))
                failures = [h for h in result.history if (h.get('error') or '').startswith('條件無法判定')]
                self.assertTrue(failures)
                self.assertTrue(all(not h['ok'] and h['output'] is None for h in failures))
                if success:
                    self.assertEqual(gateway.plans, 2)
                    self.assertEqual(result.message, '已核對')
                    history = gateway.repairs[0]['replanning_context']['completed_and_failed_history']
                    self.assertTrue(history[1]['ok'])
                    self.assertFalse(history[2]['ok'])
                elif repeated:
                    self.assertEqual(gateway.plans, fixture.settings.max_replans + 1)
                    self.assertEqual(len(failures), fixture.settings.max_replans + 1)
                else:
                    self.assertEqual(gateway.plans, 1)
                self.assertEqual(gateway.checks, int(success))
            finally:
                fixture.close()

    def test_replan_repairs_without_repeating_successful_append(self):
        self.run_scenario('replan')

    def test_retry_repairs_without_executing_abandoned_tail(self):
        self.run_scenario('retry')

    def test_stop_does_not_execute_unknown_branch(self):
        self.run_scenario('stop')

    def test_continue_does_not_bypass_unknown_condition(self):
        self.run_scenario('continue')

    def test_repeated_invalid_condition_stops_at_replan_limit(self):
        self.run_scenario('replan', repeated=True)


if __name__ == '__main__':
    unittest.main()

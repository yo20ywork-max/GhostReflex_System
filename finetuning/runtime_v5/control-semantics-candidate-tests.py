"""Checker outages cannot authorize extra actions or erase completed receipts."""
import copy
import json
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from completion_verification import VerificationUnavailable, VerificationCancelled, verify_with_retry
from completion_observations import checker_history
from test_explicit_reply_runtime import ROOT, Fixture, ScriptedGateway, step


class OutageGateway(ScriptedGateway):
    def __init__(self, outcomes):
        super().__init__([step(1, 'APPEND_TEXT_FILE', {'path': '工作記錄.txt', 'content': '收尾\t😀\r\n'})], '')
        self.outcomes = iter(outcomes)
        self.observations = []

    def chat_json(self, *, messages, schema, models=None):
        if 'complete' not in schema['properties']:
            return super().chat_json(messages=messages, schema=schema, models=models)
        self.observations.append(copy.deepcopy(messages))
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        if callable(outcome):
            outcome = outcome()
        return outcome, 'scripted'


class CompletionVerificationTests(unittest.TestCase):
    def run_fixture(self, outcomes, expected_status, checks, event=None):
        gateway = OutageGateway(outcomes)
        row = {'id': 'checker-outage', 'user_request': '在工作記錄末尾追加收尾原文，不要重複追加。',
               'initial_files': {'工作記錄.txt': '原本\r\n'},
               'write_targets': {'工作記錄.txt': ['APPEND_TEXT_FILE']}}
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='.verification-runtime-') as folder:
            fixture = Fixture(row, folder, 'scripted', gateway)
            try:
                run = fixture.agent.run
                fixture.agent.run = lambda prompt: run(prompt, cancel_event=event)
                with patch('completion_verification.time.sleep'):
                    result, receipts, _ = fixture.run('scripted', gateway)
                self.assertEqual(result.status, expected_status)
                self.assertEqual((fixture.work / '工作記錄.txt').read_bytes(), '原本\r\n收尾\t😀\r\n'.encode())
                self.assertEqual(gateway.plans, 1)
                self.assertEqual(len(result.history), 1)
                self.assertEqual(len(fixture.trace), 1)
                self.assertTrue(result.history[0]['verified'])
                self.assertTrue(receipts)
                self.assertEqual(len(gateway.observations), checks)
                self.assertTrue(all(item == gateway.observations[0] for item in gateway.observations))
                observed = json.loads(gateway.observations[0][-1]['content'])['observed_history'][0]
                self.assertNotIn('terminal', observed)
                self.assertIs(observed['failure_requires_stop'], False)
                self.assertIn('terminal', result.history[0])
                if expected_status == 'blocked':
                    self.assertIn('操作紀錄已保留', result.message)
                return result
            finally:
                fixture.close()

    def test_http500_then_recovery_does_not_repeat_real_append(self):
        self.run_fixture([RuntimeError('HTTP 500 runner load failed'), {'complete': True, 'reason': '完成'}], 'completed', 2)

    def test_persistent_outage_blocks_and_keeps_real_file_and_receipt(self):
        self.run_fixture([RuntimeError('HTTP 500')] * 3, 'blocked', 3)

    def test_malformed_responses_are_unavailable_not_a_new_action_request(self):
        self.run_fixture([{'complete': 'yes', 'reason': '不合格式'}, [], {'reason': '缺少狀態'}], 'blocked', 3)

    def test_cancel_during_check_does_not_retry_or_replan(self):
        event = threading.Event()
        def cancel():
            event.set()
            return {'complete': True, 'reason': '完成'}
        self.run_fixture([cancel], 'cancelled', 1, event)

    def test_valid_negative_result_is_not_retried(self):
        checker = Mock(return_value=(False, '尚未讀回'))
        self.assertEqual(verify_with_retry(checker, '工作', []), (False, '尚未讀回'))
        checker.assert_called_once()

    def test_nonretryable_capacity_failure_is_not_retried(self):
        checker = Mock(side_effect=VerificationUnavailable('證據過大', retryable=False))
        with self.assertRaises(VerificationUnavailable):
            verify_with_retry(checker, '工作', [])
        checker.assert_called_once()

    def test_each_attempt_receives_same_immutable_source(self):
        history = [{'output': {'text': '  原文\n'}}]
        original = copy.deepcopy(history)
        calls = []
        def checker(prompt, evidence):
            calls.append(copy.deepcopy(evidence))
            evidence[0]['output']['text'] = 'changed'
            if len(calls) == 1:
                raise VerificationUnavailable('temporary')
            return True, '完成'
        verify_with_retry(checker, '工作', history, retry_delay=0)
        self.assertEqual(history, original)
        self.assertEqual(calls, [original, original])

    def test_cancel_interrupts_retry_backoff(self):
        event = threading.Event()
        checker = Mock(side_effect=VerificationUnavailable('temporary'))
        with self.assertRaises(VerificationCancelled):
            verify_with_retry(checker, '工作', [], cancel_event=event,
                              on_unavailable=lambda *_: event.set(), retry_delay=60)
        checker.assert_called_once()

    def test_projection_only_renames_control_metadata(self):
        row = {'terminal': True, 'step_id': 41, 'ok': False,
               'args': {'terminal': 'literal'}, 'output': '  原文\n', 'evidence': {'url': 'about:blank'}}
        original = copy.deepcopy(row)
        result = checker_history([row])
        self.assertEqual(row, original)
        expected = copy.deepcopy(row)
        expected['failure_requires_stop'] = expected.pop('terminal')
        self.assertEqual(result, [expected])


if __name__ == '__main__':
    unittest.main()

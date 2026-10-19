import unittest
from finetuning.release_v4.review_full_loop import summarize


class FullLoopAccounting(unittest.TestCase):
    def test_failed_task_with_correct_artifact_is_not_complete_success(self):
        rows = [
            {'id': 'correct', 'passed': True, 'agent_status': 'completed'},
            {'id': 'artifact-only', 'passed': True, 'agent_status': 'failed'},
            {'id': 'false-complete', 'passed': False, 'agent_status': 'completed'},
            {'id': 'failed', 'passed': False, 'agent_status': 'failed'},
        ]
        result = summarize({'records': rows, 'total': 4, 'passed': 2, 'agent_completed': 2, 'false_completions': 1})
        self.assertEqual(result['joint_oracle_and_completed'], 1)
        self.assertEqual(result['original_oracle_passed'], 2)
        self.assertEqual(result['oracle_passed_but_agent_not_completed'], ['artifact-only'])
        self.assertFalse(result['release_approved'])

    def test_stale_summary_is_rejected(self):
        with self.assertRaises(ValueError):
            summarize({'records': [{'id': 'x', 'passed': True, 'agent_status': 'failed'}], 'total': 1, 'passed': 1, 'agent_completed': 1, 'false_completions': 0})

    def test_initial_out_of_scope_plan_remains_a_failed_case(self):
        report = {'records': [{'id': 'duplicate-download', 'passed': False, 'agent_status': None,
                              'error': 'Plan requests a tool outside the fixture scope'}],
                  'total': 1, 'passed': 0, 'agent_completed': 0, 'false_completions': 0}
        result = summarize(report)
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['joint_oracle_and_completed'], 0)
        self.assertEqual(result['rejected_before_agent_run'], ['duplicate-download'])

    def test_missing_status_without_recorded_rejection_is_invalid(self):
        with self.assertRaises(ValueError):
            summarize({'records': [{'id': 'x', 'passed': False, 'agent_status': None}],
                       'total': 1, 'passed': 0, 'agent_completed': 0, 'false_completions': 0})

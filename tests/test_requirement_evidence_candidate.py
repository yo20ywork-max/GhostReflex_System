import copy
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / 'finetuning/release_v13/runtime-candidate/requirement_evidence_check.py'
spec = importlib.util.spec_from_file_location('requirement_evidence_check', PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def row(quote, verdict='satisfied', indices=None):
    return {'request_quote': quote, 'kind': 'content', 'verdict': verdict,
            'evidence_sequence_indices': [1] if indices is None else indices, 'explanation': '測試判定'}


class RequirementEvidence(unittest.TestCase):
    def setUp(self):
        self.context = {'user_request': '讀甲；不要送出。回覆「好」。',
                        'observed_history': [{'step_id': 70, 'tool': 'READ_TEXT_FILE', 'ok': True, 'verified': True}]}

    def test_each_original_request_span_must_be_covered(self):
        checks = [row('讀甲'), row('不要送出'), row('回覆「好」')]
        self.assertTrue(module.validate({'checks': checks}, self.context)['complete'])
        incomplete = module.validate({'checks': [checks[0], checks[2]]}, self.context)
        self.assertFalse(incomplete['complete'])
        self.assertIn('original_request_not_fully_covered', incomplete['validation_problems'])

    def test_made_up_quote_or_no_evidence_cannot_complete(self):
        for check in [row('讀乙'), row(self.context['user_request'], indices=[])]:
            self.assertFalse(module.validate({'checks': [check]}, self.context)['complete'])

    def test_actual_chronological_index_not_step_number(self):
        self.assertTrue(module.validate({'checks': [row(self.context['user_request'])]}, self.context)['complete'])
        with self.assertRaises(Exception):
            module.validate({'checks': [row(self.context['user_request'], indices=[70])]}, self.context)

    def test_failed_unverified_or_skipped_witness_cannot_support_satisfied(self):
        for change in [{'ok': False}, {'verified': False}, {'tool': 'CONDITION_SKIP'},
                       {'evidence': {'condition_skipped': True}}]:
            context = copy.deepcopy(self.context)
            context['observed_history'][0].update(change)
            self.assertFalse(module.validate({'checks': [row(context['user_request'])]}, context)['complete'])

    def test_negative_or_uncertain_with_no_witness_is_not_complete(self):
        for verdict in ['unmet', 'uncertain']:
            result = module.validate({'checks': [row(self.context['user_request'], verdict, [])]}, self.context)
            self.assertFalse(result['complete'])
            self.assertEqual(result['validation_problems'], [])

    def test_later_success_can_be_cited_without_promoting_earlier_failure(self):
        context = copy.deepcopy(self.context)
        context['observed_history'].insert(0, {'step_id': 2, 'tool': 'READ_TEXT_FILE', 'ok': False, 'verified': False})
        self.assertTrue(module.validate({'checks': [row(context['user_request'], indices=[2])]}, context)['complete'])
        self.assertFalse(module.validate({'checks': [row(context['user_request'], indices=[1])]}, context)['complete'])

    def test_build_keeps_exact_evidence_model_options_and_callers(self):
        payload = {'model': 'test', 'messages': [{'role': 'system', 'content': 'old'}, {'role': 'user', 'content': 'unchanged 😀\t\r\n'}],
                   'format': {'type': 'object'}, 'options': {'temperature': 0}, 'stream': False}
        before = copy.deepcopy(payload)
        result = module.request_payload(payload, self.context)
        self.assertEqual(payload, before)
        for key in ['model', 'options', 'stream']:
            self.assertEqual(result[key], payload[key])
        self.assertEqual(result['messages'][1], payload['messages'][1])

    def test_empty_checks_invalid_and_quote_coverage_is_not_semantic_proof(self):
        with self.assertRaises(Exception):
            module.validate({'checks': []}, self.context)
        # Broad quotes can pass syntax/coverage while the model is wrong about
        # intent. Keep the explicit requirement for independent semantic eval.
        result = module.validate({'checks': [row(self.context['user_request'])]}, self.context)
        self.assertTrue(result['semantic_review_required'])


if __name__ == '__main__':
    unittest.main()

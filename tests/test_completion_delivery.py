import copy
import json
import unittest
from completion_delivery import candidate_visible_reply, project_delivery_messages


class CompletionDeliveryTests(unittest.TestCase):
    def test_empty_read_is_empty_delivery_not_success_reply(self):
        result = candidate_visible_reply([{'tool': 'READ_TEXT_FILE', 'ok': True, 'verified': True, 'output': ''}])
        self.assertTrue(result['known'])
        self.assertEqual(result['text'], '')

    def test_last_explicit_response_takes_precedence_over_later_read(self):
        history = [{'tool': 'FINAL_RESPONSE', 'ok': True, 'output': '  μ\n'},
                   {'tool': 'READ_TEXT_FILE', 'ok': True, 'output': '原稿'}]
        self.assertEqual(candidate_visible_reply(history)['text'], '  μ\n')
        history.append({'tool': 'FINAL_RESPONSE', 'ok': False, 'output': None})
        self.assertFalse(candidate_visible_reply(history)['known'])

    def test_copy_receipt_is_generic_summary_not_requested_reply(self):
        history = [{'tool': 'COPY_FILE_VERIFIED', 'ok': True, 'verified': True, 'output': {'skipped_existing': True}}]
        result = candidate_visible_reply(history)
        self.assertEqual(result['basis'], 'generic_runtime_summary')
        self.assertIn('成功步驟 1/1', result['text'])

    def test_output_projection_preserves_evidence_and_does_not_mutate_input(self):
        row = {'tool': 'READ_TEXT_FILE', 'goal': '回覆「完成」', 'ok': True, 'verified': True,
               'args': {'path': 'α.txt'}, 'output': '原文\t\r\n', 'evidence': {'sha256': 'test'}}
        messages = [{'role': 'system', 'content': '核對'}, {'role': 'user', 'content': json.dumps({'observed_history': [row]}, ensure_ascii=False)}]
        original = copy.deepcopy(messages)
        revised, removed = project_delivery_messages(messages)
        payload = json.loads(revised[-1]['content'])
        self.assertEqual(messages, original)
        self.assertEqual(payload['observed_history'], [{k: v for k, v in row.items() if k != 'goal'}])
        self.assertEqual(payload['candidate_user_visible_reply']['text'], row['output'])
        self.assertEqual(removed, [{'sequence_index': 1, 'planned_goal': row['goal']}])

    def test_non_string_direct_output_uses_runtime_json_limit(self):
        result = candidate_visible_reply([{'tool': 'HTTP_GET', 'ok': True, 'output': {'中文': 'x' * 31000}}])
        self.assertEqual(len(result['text']), 30001)
        self.assertTrue(result['text'].endswith('…'))


if __name__ == '__main__':
    unittest.main()

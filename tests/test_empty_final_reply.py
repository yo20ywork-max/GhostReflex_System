import sys
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'finetuning/runtime_v6'))
from conditional_flow import ConditionalFixture
from completion_delivery import candidate_visible_reply


class EmptyFinalReply(unittest.TestCase):
    def test_explicit_empty_reply_is_not_replaced_by_a_status_summary(self):
        class Gateway:
            def chat_json(self, *, messages, schema, models=None):
                if 'complete' in schema['properties']:
                    return {'complete': True, 'reason': 'scripted'}, 'scripted'
                return {'objective': '回覆空字串', 'assumptions': [], 'completion_criteria': ['字面空字串'],
                        'steps': [{'id': 1, 'goal': '原樣回覆', 'tool': 'FINAL_RESPONSE',
                                   'args': {'message': {'$literal': ''}}, 'success_check': '空字串'}]}, 'scripted'
        row = {'id': 'empty-final', 'user_request': '回覆空字串，不要加任何說明。', 'initial_files': {}, 'write_targets': {}}
        gateway = Gateway()
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='.empty-final-') as folder:
            fixture = ConditionalFixture(row, folder, 'scripted', gateway)
            try:
                result, receipts, _ = fixture.run('scripted', gateway)
                self.assertEqual(result.status, 'completed')
                self.assertEqual(result.message, '')
                self.assertEqual(receipts[0]['result']['output'], '')
            finally:
                fixture.close()

    def test_delivery_reconstruction_preserves_explicit_empty_reply(self):
        reply = candidate_visible_reply([{'tool': 'FINAL_RESPONSE', 'ok': True, 'verified': True, 'output': ''}])
        self.assertTrue(reply['known'])
        self.assertEqual(reply['text'], '')
        self.assertEqual(reply['basis'], 'explicit_final_response')

    def test_skipped_tail_does_not_replace_actual_direct_read(self):
        reply = candidate_visible_reply([
            {'tool': 'READ_TEXT_FILE', 'ok': True, 'verified': True, 'output': ''},
            {'tool': 'CONDITION_SKIP', 'ok': True, 'verified': True, 'output': None},
        ])
        self.assertEqual(reply['text'], '')
        self.assertEqual(reply['basis'], 'direct_last_output')
        self.assertEqual(reply['sequence_index'], 1)


if __name__ == '__main__':
    unittest.main()

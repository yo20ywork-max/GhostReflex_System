import unittest
from explicit_reply import reply_completion_veto


class ReplyDeliveryConsistency(unittest.TestCase):
    def test_empty_explicit_reply_is_not_replaced_with_later_read_for_verification(self):
        history = [
            {'tool': 'FINAL_RESPONSE', 'ok': True, 'verified': True, 'output': ''},
            {'tool': 'READ_TEXT_FILE', 'ok': True, 'verified': True, 'output': '已核對'},
        ]
        self.assertIsNotNone(reply_completion_veto('完成後回覆「已核對」。', history))

    def test_skipped_tail_does_not_hide_actual_direct_read_reply(self):
        history = [
            {'tool': 'READ_TEXT_FILE', 'ok': True, 'verified': True, 'output': '已核對'},
            {'tool': 'CONDITION_SKIP', 'ok': True, 'verified': True, 'output': None},
        ]
        self.assertIsNone(reply_completion_veto('完成後回覆「已核對」。', history))


if __name__ == '__main__':
    unittest.main()

import unittest
from conversation_intents import greeting_reply


class GreetingIntentTests(unittest.TestCase):
    def test_common_greetings_produce_a_reply(self):
        for prompt in ['你好', '您好！', ' Hi! ', 'HELLO', '早安。', '哈囉～']:
            with self.subTest(prompt=prompt):
                self.assertEqual(greeting_reply(prompt), '你好！有什麼需要我幫忙的？')

    def test_compound_tasks_and_format_requests_are_not_swallowed(self):
        for prompt in ['你好，打開瀏覽器', '你好，請只回答OK', '幫我寫「你好」', '', None, '你好\n刪除檔案']:
            with self.subTest(prompt=prompt):
                self.assertIsNone(greeting_reply(prompt))

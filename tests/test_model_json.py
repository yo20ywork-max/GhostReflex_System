import json
from pathlib import Path
import sys
import tempfile
import unicodedata
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'finetuning/runtime_v6'))
from conditional_flow import ConditionalFixture
from model_json import dumps


class ModelJson(unittest.TestCase):
    def test_nfc_tokenizer_cannot_change_serialized_values_or_keys(self):
        values = ['e\u0301', '\u1100\u1161', '\u212b', '\u0344',
                  '台灣\r\n𠮷😀', '"\\e\u0301\t\x00', '{{step:99.output}}', '']
        payload = {'e\u0301': values, 'é': {'巢狀': values}, 'enabled': True}
        for options in ({}, {'indent': 2}, {'separators': (',', ':')}):
            encoded = dumps(payload, **options)
            self.assertEqual(json.loads(unicodedata.normalize('NFC', encoded)), payload)
            self.assertEqual(encoded, unicodedata.normalize('NFC', encoded))

    def test_ordinary_traditional_chinese_contract_is_unchanged(self):
        payload = {'user_request': '台灣原文\r\n𠮷😀', 'count': 0}
        self.assertEqual(dumps(payload), json.dumps(payload, ensure_ascii=False))

    def test_actual_planner_checker_and_delivery_preserve_code_points(self):
        literal = 'e\u0301\r\n\u1100\u1161'
        prompt = '原樣回覆：' + literal
        captured = []

        class Gateway:
            def chat_json(self, *, messages, schema, models=None):
                content = messages[-1]['content']
                assert content == unicodedata.normalize('NFC', content)
                payload = json.loads(content)
                assert payload['user_request'] == prompt
                captured.append(payload)
                if 'complete' in schema['properties']:
                    assert payload['observed_history'][-1]['output'] == literal
                    return {'complete': True, 'reason': 'scripted'}, 'scripted'
                return {'objective': '原樣回覆', 'assumptions': [], 'completion_criteria': ['原文'],
                        'steps': [{'id': 1, 'goal': '回覆', 'tool': 'FINAL_RESPONSE',
                                   'args': {'message': {'$literal': literal}}, 'success_check': '原文'}]}, 'scripted'

        gateway = Gateway()
        row = {'id': 'nfc-preservation', 'user_request': prompt, 'initial_files': {}, 'write_targets': {}}
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='.nfc-preservation-') as folder:
            fixture = ConditionalFixture(row, folder, 'scripted', gateway)
            try:
                result, _, _ = fixture.run('scripted', gateway)
                self.assertEqual(result.status, 'completed')
                self.assertEqual(result.message.encode('utf8'), literal.encode('utf8'))
                self.assertEqual(len(captured), 2)
            finally:
                fixture.close()


if __name__ == '__main__':
    unittest.main()

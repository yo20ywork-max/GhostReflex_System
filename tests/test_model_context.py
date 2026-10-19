import copy
import json
import unicodedata
import unittest

from model_context import dumps, pack, unpack
from model_json import dumps as original_dumps


class ModelContextTests(unittest.TestCase):
    def test_exact_roundtrip_preserves_order_paths_and_unicode(self):
        text = ('台灣 e\u0301\t\r\n𠮷😀 {{step:800.output}}  ' * 90)
        payload = {'user_request': '保留原文', 'history': [
            {'step_id': 1, 'path': '來源.txt', 'ok': True, 'output': text},
            {'step_id': 2, 'args': {'path': '副本.txt', 'content': text}, 'ok': False},
            {'step_id': 3, 'path': '副本.txt', 'ok': True, 'output': text}],
            'literal': {'context_text_id': 't1'}}
        before = copy.deepcopy(payload)
        encoded = dumps(payload)
        restored = unpack(json.loads(unicodedata.normalize('NFC', encoded)))
        self.assertEqual(restored, before)
        self.assertEqual(original_dumps(restored).encode(), original_dumps(before).encode())
        self.assertEqual(payload, before)
        self.assertLess(len(encoded), len(original_dumps(before)))

    def test_unique_text_is_never_truncated(self):
        payload = {'output': '台灣原文\n' * 2000, 'another': '另一份資料'}
        self.assertEqual(dumps(payload), original_dumps(payload))

    def test_similar_text_and_lookalike_references_are_not_merged(self):
        text = '原文' * 800
        payload = {'a': text, 'b': text, 'c': text + '\n',
                   'literal': {'context_text_id': 't1'},
                   'nested': {'shared_context_text': {'texts': 'user data'}}}
        self.assertEqual(unpack(pack(payload)), payload)

    def test_reserved_top_level_key_leaves_user_payload_unchanged(self):
        payload = {'shared_context_text': {'texts': 'user data'}, 'a': '字' * 1000, 'b': '字' * 1000}
        self.assertEqual(dumps(payload), original_dumps(payload))

    def test_small_input_representation_is_unchanged(self):
        payload = {'history': [{'output': '字' * 256}, {'output': '字' * 256}]}
        self.assertEqual(dumps(payload), original_dumps(payload))


if __name__ == '__main__':
    unittest.main()

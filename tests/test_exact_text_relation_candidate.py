import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / 'finetuning/release_v13/runtime-candidate/exact_text_relation.py'
spec = importlib.util.spec_from_file_location('exact_text_relation', PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ExactTextRelation(unittest.TestCase):
    def test_exact_order_whitespace_empty_parts_and_unicode(self):
        parts = ['\ufeff甲\t', '', '乙\r\n', ' e\u0301𠮷😀  ']
        expected = ''.join(parts)
        self.assertTrue(module.compare(parts, expected)['text_equal'])
        self.assertFalse(module.compare(parts[::-1], expected)['text_equal'])
        self.assertTrue(module.compare(['', ''], '')['text_equal'])
        self.assertTrue(module.compare(['甲', '甲'], '甲甲')['text_equal'])
        self.assertFalse(module.compare(['e\u0301'], 'é')['text_equal'])

    def test_reports_first_changed_missing_or_added_character(self):
        for actual, index, source, target in [('甲 乙\n', 1, '\t', ' '), ('甲\t乙', 3, '\n', None),
                                               ('甲\t乙\nX', 4, None, 'X')]:
            result = module.compare(['甲\t', '乙\n'], actual)
            self.assertFalse(result['text_equal'])
            self.assertEqual(result['first_difference'], {'character_index': index, 'source_character': source, 'target_character': target})

    def test_declared_relation_is_not_implicitly_task_success(self):
        files = {'a': {'text': 'wrong', 'total_chars': 5}, 'b': {'text': 'wrong', 'total_chars': 5}}
        before = copy.deepcopy(files)
        with patch.object(Path, 'open', side_effect=AssertionError('No I/O')):
            result = module.from_verified_files(files, ['a'], 'b')
        self.assertTrue(result['text_equal'])
        self.assertNotIn('complete', result)
        self.assertEqual(files, before)

    def test_missing_or_invalid_sources_never_default_to_empty_text(self):
        for sources in [[], 'abc', [1]]:
            with self.assertRaises((TypeError, ValueError)):
                module.from_verified_files({}, sources, 'b')
        with self.assertRaises(KeyError):
            module.from_verified_files({}, ['a'], 'b')
        with self.assertRaises(ValueError):
            module.from_verified_files({'a': {'text': '', 'total_chars': 1}}, ['a'], 'a')


if __name__ == '__main__':
    unittest.main()

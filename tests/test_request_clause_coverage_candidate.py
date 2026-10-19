import importlib.util
from pathlib import Path
import unittest
from jsonschema import ValidationError

P = Path(__file__).resolve().parents[1] / 'finetuning/release_v13/runtime-candidate/request_clause_coverage.py'
spec = importlib.util.spec_from_file_location('clause_coverage_candidate', P)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ClauseCoverage(unittest.TestCase):
    def test_all_characters_and_offsets_preserved(self):
        prompt = '讀甲.txt，保留來源。讀回後回覆「完成」。\r\n'
        parts = m.split(prompt)
        self.assertEqual(''.join(p['text'] for p in parts.values()), prompt)
        for p in parts.values(): self.assertEqual(prompt[p['start']:p['end']], p['text'])

    def test_quoted_command_punctuation_is_not_split(self):
        parts = m.split('讀回後回覆「不必讀回，也不用回覆」。保留來源。')
        self.assertEqual(len(parts), 2)
        self.assertIn('不必讀回，也不用回覆', parts['c1']['text'])

    def test_nested_quotes_and_literal_code_are_kept(self):
        for prompt in ['輸出「他說『不要，謝謝』」。保留來源。', '寫入 `f(a,b); g()`，再讀回。', '輸出 "a,\\\"b;c"；讀回。']:
            self.assertEqual(len(m.split(prompt)), 2)

    def test_numeric_commas_and_filename_dots_not_split(self):
        self.assertEqual(len(m.split('金額1,000元存到note.txt，讀回。')), 2)

    def test_missing_clause_is_rejected(self):
        prompt = '讀甲.txt，保留來源。'
        with self.assertRaises(ValidationError): m.bind({'c1': ['content_requirement']}, prompt)

    def test_extra_or_empty_classification_is_rejected(self):
        for value in [{'c1': []}, {'c1': ['preserve_sources'], 'invented': ['exact_reply']}]:
            with self.assertRaises(ValidationError): m.bind(value, '保留來源。')

    def test_multiple_obligations_remain_representable(self):
        result = m.bind({'c1': ['destination_readback', 'reply_after_readback', 'exact_reply']}, '讀回後回覆「完成」。')
        self.assertEqual(len(result['clauses'][0]['kinds']), 3)
        self.assertFalse(result['whole_task_completion_inferred'])
        self.assertFalse(result['semantic_classification_proven'])

    def test_unclosed_quote_preserves_entire_suffix(self):
        prompt = '輸出「未完成，另存新檔。'
        self.assertEqual(m.split(prompt)['c1']['text'], prompt)


if __name__ == '__main__':
    unittest.main()

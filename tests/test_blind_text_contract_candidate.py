import copy
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / 'finetuning/release_v13/runtime-candidate/blind_text_contract.py'
spec = importlib.util.spec_from_file_location('blind_text_contract', PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BlindContract(unittest.TestCase):
    def test_single_or_empty_catalog_cannot_compare_a_file_with_itself(self):
        for catalog in [[], [{'file_id': 'f1'}]]:
            module.bind({'queries': []}, '保留原文', catalog)
            with self.assertRaises(Exception):
                module.bind({'queries': [{'source_file_ids': ['f1'], 'destination_file_id': 'f1'}]}, '保留原文', catalog)

    def test_no_self_sources_unknown_identifiers_or_empty_sources(self):
        catalog = [{'file_id': 'f1'}, {'file_id': 'f2'}, {'file_id': 'f3'}]
        for sources, target in [(['f1'], 'f1'), (['f1', 'f3'], 'f3'), (['f9'], 'f3'), ([], 'f3')]:
            with self.assertRaises(Exception):
                module.bind({'queries': [{'source_file_ids': sources, 'destination_file_id': target}]}, '原樣串接', catalog)

    def test_order_and_repetition_preserved_and_provenance_bound_by_host(self):
        catalog = [{'file_id': 'f1'}, {'file_id': 'f2'}, {'file_id': 'f3'}]
        value = {'queries': [{'source_file_ids': ['f2', 'f1', 'f2'], 'destination_file_id': 'f3'}]}
        before = copy.deepcopy(value)
        first = module.bind(value, '原要求\r\n', catalog)
        second = module.bind(value, '不同要求\r\n', catalog)
        self.assertEqual(value, before)
        self.assertEqual(first['queries'], value['queries'])
        self.assertNotEqual(first['request_sha256'], second['request_sha256'])
        self.assertNotIn('complete', first)


if __name__ == '__main__':
    unittest.main()

import copy
import importlib.util
from pathlib import Path
import unittest

P = Path(__file__).resolve().parents[1] / 'finetuning/release_v13/runtime-candidate/artifact_intent_contract.py'
spec = importlib.util.spec_from_file_location('artifact_intent_contract', P)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ArtifactIntent(unittest.TestCase):
    def setUp(self):
        self.catalog = [{'file_id': 'f1', 'filename': '原.txt', 'request_paths': ['dir/原.txt']},
                        {'file_id': 'f2', 'filename': '新.txt', 'request_paths': ['dir/新.txt']}]

    def test_mixed_exact_and_semantic_are_not_collapsed(self):
        values = {'artifacts': [
            {'kind': 'exact_copy', 'source_file_ids': ['f1'], 'destination_file_id': 'f2', 'destination_name': '新.txt'},
            {'kind': 'semantic_generation', 'source_file_ids': ['f1'], 'destination_file_id': 'unobserved', 'destination_name': '摘要.txt'}]}
        before = copy.deepcopy(values)
        bound = module.bind(values, '另存新檔，並產生摘要.txt', self.catalog)
        self.assertEqual([a['kind'] for a in bound['artifacts']], ['exact_copy', 'semantic_generation'])
        self.assertFalse(bound['artifacts'][1]['destination_observed'])
        self.assertEqual(values, before)
        self.assertNotIn('complete', bound)

    def test_exact_source_count_and_self_reference_validated(self):
        for kind, sources, target in [('exact_copy', [], 'f2'), ('exact_copy', ['f1', 'f1'], 'f2'),
                                       ('exact_concat', ['f1'], 'f2'), ('exact_copy', ['f1'], 'f1')]:
            value = {'artifacts': [{'kind': kind, 'source_file_ids': sources, 'destination_file_id': target,
                                    'destination_name': '新.txt'}]}
            with self.assertRaises(ValueError):
                module.bind(value, '原樣另存', self.catalog)

    def test_new_creative_content_can_have_no_file_source(self):
        value = {'artifacts': [{'kind': 'semantic_generation', 'source_file_ids': [],
                                'destination_file_id': 'unobserved', 'destination_name': '詩.txt'}]}
        self.assertEqual(module.bind(value, '寫一首詩存為詩.txt', [])['artifacts'][0]['source_file_ids'], [])

    def test_destination_cannot_be_invented_or_contradict_observed_id(self):
        for target, name in [('unobserved', '不存在於要求.txt'), ('f2', '原.txt')]:
            with self.assertRaises(ValueError):
                module.bind({'artifacts': [{'kind': 'exact_copy', 'source_file_ids': ['f1'],
                                           'destination_file_id': target, 'destination_name': name}]}, '另存新.txt', self.catalog)

    def test_repeated_ordered_sources_are_preserved(self):
        item = {'kind': 'exact_concat', 'source_file_ids': ['f1', 'f1'], 'destination_file_id': 'f2', 'destination_name': '新.txt'}
        self.assertEqual(module.bind({'artifacts': [item]}, '重複兩次存為新.txt', self.catalog)['artifacts'][0]['source_file_ids'], ['f1', 'f1'])


if __name__ == '__main__':
    unittest.main()

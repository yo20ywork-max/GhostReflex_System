import importlib.util
from pathlib import Path
import unittest
from jsonschema import Draft202012Validator, ValidationError

P = Path(__file__).resolve().parents[1] / 'finetuning/release_v13/runtime-candidate/artifact_intent_contract_v2.py'
spec = importlib.util.spec_from_file_location('artifact_v2', P)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ArtifactV2(unittest.TestCase):
    def value(self, kind, sources, destination, name):
        return {'artifacts': [{'kind': kind, 'source_file_ids': sources, 'destination_file_id': destination, 'destination_name': name}]}

    def test_missing_target_has_valid_new_destination_but_no_self_copy(self):
        catalog = [{'file_id': 'source', 'filename': '來源.txt'}]
        validator = Draft202012Validator(m.schema(catalog))
        validator.validate(self.value('exact_copy', ['source'], 'unobserved', '新檔.txt'))
        for kind, sources in [('exact_copy', ['source']), ('exact_concat', ['source', 'source'])]:
            with self.assertRaises(ValidationError):
                validator.validate(self.value(kind, sources, 'source', '來源.txt'))

    def test_semantic_in_place_edit_remains_expressible(self):
        catalog = [{'file_id': 'f', 'filename': '草稿.txt'}]
        bound = m.bind(self.value('semantic_generation', ['f'], 'f', '草稿.txt'), '改寫草稿.txt', catalog)
        self.assertEqual(bound['artifacts'][0]['destination_file_id'], 'f')

    def test_repeated_sources_preserved_but_copy_requires_one_source(self):
        catalog = [{'file_id': 'a', 'filename': '甲.txt'}, {'file_id': 'b', 'filename': '乙.txt'}]
        bound = m.bind(self.value('exact_concat', ['a', 'a'], 'b', '乙.txt'), '甲重複兩次存乙', catalog)
        self.assertEqual(bound['artifacts'][0]['source_file_ids'], ['a', 'a'])
        for kind, sources in [('exact_copy', []), ('exact_copy', ['a', 'a']), ('exact_concat', ['a'])]:
            with self.assertRaises(ValidationError):
                m.bind(self.value(kind, sources, 'b', '乙.txt'), '甲存乙', catalog)

    def test_no_catalog_supports_source_free_generation_and_no_artifact(self):
        m.bind(self.value('semantic_generation', [], 'unobserved', '新詩.txt'), '寫新詩.txt', [])
        m.bind({'artifacts': []}, '說早安', [])
        with self.assertRaises(ValidationError):
            m.bind(self.value('exact_copy', ['no_source'], 'unobserved', '新詩.txt'), '寫新詩.txt', [])

    def test_unobserved_name_is_grounded_and_observed_aliases_are_constrained(self):
        catalog = [{'file_id': 'f', 'filename': '結果.txt', 'request_paths': ['資料/結果.txt']}]
        m.bind(self.value('semantic_generation', [], 'f', '資料/結果.txt'), '寫入資料/結果.txt', catalog)
        with self.assertRaises(ValidationError):
            m.bind(self.value('semantic_generation', [], 'f', '無關.txt'), '寫入結果.txt', catalog)
        with self.assertRaises(ValueError):
            m.bind(self.value('semantic_generation', [], 'unobserved', '無關.txt'), '寫入结果.txt', catalog)


if __name__ == '__main__':
    unittest.main()

import importlib.util
from pathlib import Path
import unittest

from tests import test_artifact_evidence_candidate as fixtures

P = Path(__file__).resolve().parents[1] / 'finetuning/release_v13/runtime-candidate/artifact_completion_guard.py'
spec = importlib.util.spec_from_file_location('artifact_guard_candidate', P)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class ArtifactGuard(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ArtifactEvidence()
        self.fixture.setUp()

    def tearDown(self):
        self.fixture.tearDown()

    def assess(self, verdict, kind='exact_copy'):
        f = self.fixture
        catalog = guard.evidence.catalog_from_history(f.history)
        ids = {row['filename']: row['file_id'] for row in catalog}
        value = {'artifacts': [{'kind': kind, 'source_file_ids': [ids['a.txt']],
                               'destination_file_id': ids.get('b.txt', 'unobserved'), 'destination_name': 'b.txt'}]}
        return guard.assess(value, '將 a.txt 存到 b.txt', f.history, verdict)

    def test_false_success_overridden_with_actual_difference(self):
        f = self.fixture
        f.source('a.txt', '甲\t\n'); f.read('a.txt')
        f.write('b.txt', '甲\n'); f.read('b.txt')
        result = self.assess({'complete': True, 'reason': '最後說完成'})
        self.assertFalse(result['complete'])
        self.assertEqual(result['host_blockers'][0]['first_difference']['character_index'], 1)

    def test_matching_empty_copy_does_not_override_model_failure(self):
        f = self.fixture
        f.source('a.txt', ''); f.copied()
        result = self.assess({'complete': False, 'reason': '缺少回覆'})
        self.assertFalse(result['complete'])
        self.assertEqual(result['reason'], '缺少回覆')
        self.assertEqual(result['host_blockers'], [])

    def test_missing_target_overrules_model_success(self):
        f = self.fixture
        f.source('a.txt', ''); f.read('a.txt')
        result = self.assess({'complete': True, 'reason': '完成'})
        self.assertFalse(result['complete'])
        self.assertEqual(result['host_blockers'][0]['kind'], 'insufficient_exact_file_evidence')

    def test_semantic_generation_is_not_forced_to_copy(self):
        f = self.fixture
        f.source('a.txt', '長文'); f.read('a.txt')
        f.write('b.txt', '摘要'); f.read('b.txt')
        result = self.assess({'complete': False, 'reason': '需要核對摘要'}, 'semantic_generation')
        self.assertEqual(result['host_blockers'], [])
        self.assertFalse(result['complete'])

    def test_later_overwrite_requires_reconciliation(self):
        f = self.fixture
        f.source('a.txt', 'before'); f.copied(); f.write('b.txt', 'after', overwrite=True)
        result = self.assess({'complete': True, 'reason': '曾經核對過'})
        self.assertFalse(result['complete'])
        self.assertEqual(result['host_blockers'][0]['kind'], 'later_observation_requires_reconciliation')

    def test_unavailable_checker_never_becomes_success(self):
        f = self.fixture
        f.source('a.txt', ''); f.copied()
        for invalid in [None, {}, {'complete': 'true', 'reason': '完成'}]:
            with self.assertRaises(ValueError):
                self.assess(invalid)


if __name__ == '__main__':
    unittest.main()

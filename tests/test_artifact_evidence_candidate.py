import importlib.util
from pathlib import Path
import tempfile
import unittest

from text_reader import read_text_segment
from verified_copy import copy_verified

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / 'finetuning/release_v13/runtime-candidate/artifact_evidence.py'
spec = importlib.util.spec_from_file_location('artifact_evidence_candidate', P)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ArtifactEvidence(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='artifact-evidence-', dir=ROOT / 'finetuning/release_v13')
        self.work = Path(self.temp.name).resolve()
        self.history = []

    def tearDown(self):
        self.assertTrue(self.work.is_relative_to(ROOT))
        self.temp.cleanup()

    def event(self, tool, args, output, evidence=None, **kwargs):
        event = dict(tool=tool, args=args, output=output, evidence=evidence or {},
                     ok=True, verified=True, step_id=len(self.history) + 1)
        event.update(kwargs)
        self.history.append(event)

    def source(self, name, text):
        (self.work / name).write_bytes(text.encode('utf8'))

    def read(self, name, **kwargs):
        text, evidence = read_text_segment(self.work / name, **kwargs)
        self.event('READ_TEXT_FILE', {'path': name}, text, evidence)

    def write(self, name, text, overwrite=False):
        with (self.work / name).open('w' if overwrite else 'x', encoding='utf8', newline='') as f:
            f.write(text)
        self.event('WRITE_TEXT_FILE', {'path': name, 'content': text, 'overwrite': overwrite},
                   {'path': str(self.work / name), 'bytes': len(text.encode())})

    def copied(self, name='a.txt', dest='b.txt'):
        output = copy_verified(name, dest, workspace=self.work)
        self.event('COPY_FILE_VERIFIED', {'source': name, 'destination': dest, 'if_exists': 'error'}, output)

    def result(self, kind='exact_copy', sources=('a.txt',), target='b.txt'):
        catalog = m.catalog_from_history(self.history)
        ids = {row['observed_path']: row['file_id'] for row in catalog}
        value = {'artifacts': [{'kind': kind, 'source_file_ids': [ids[str(self.work / n)] for n in sources],
                 'destination_file_id': ids.get(str(self.work / target), 'unobserved'), 'destination_name': target}]}
        return m.build(value, f'操作 {sources} 到 {target}', self.history)

    def test_empty_copy_actual_handler_is_positive_evidence_without_full_completion(self):
        self.source('a.txt', '')
        self.copied()
        self.event('FINAL_RESPONSE', {'message': '完成'}, '完成')
        report = self.result()
        self.assertEqual(report['artifacts'][0]['content_relation']['status'], 'byte_copy_observed')
        self.assertEqual(report['artifacts'][0]['content_relation']['bytes'], 0)
        self.assertTrue(report['artifacts'][0]['copy_observations'][0]['exclusive_creation'])
        self.assertFalse(report['whole_task_completion_inferred'])
        self.assertEqual(report['verified_response_observations'][0]['text'], '完成')

    def test_missing_destination_is_unknown_not_empty(self):
        self.source('a.txt', '')
        self.read('a.txt')
        self.assertEqual(self.result()['artifacts'][0]['content_relation']['status'], 'unknown')

    def test_exact_concat_preserves_tabs_newlines_and_combining_characters(self):
        for n, t in [('a.txt', '\t\r\n'), ('c.txt', 'e\u0301\n')]:
            self.source(n, t)
            self.read(n)
        self.write('b.txt', '\t\r\ne\u0301\n')
        self.read('b.txt')
        result = self.result('exact_concat', ('a.txt', 'c.txt'))['artifacts'][0]
        self.assertEqual(result['content_relation']['status'], 'text_equal')
        self.assertTrue(result['destination_creation_observations'][0]['exclusive_creation'])
        self.assertEqual(result['source_write_observations'], [])

    def test_missing_character_is_located(self):
        self.source('a.txt', 'x\t\n')
        self.read('a.txt')
        self.write('b.txt', 'x\n')
        self.read('b.txt')
        result = self.result()['artifacts'][0]['content_relation']
        self.assertEqual(result['status'], 'text_different')
        self.assertEqual(result['comparison']['first_difference']['character_index'], 1)

    def test_repeated_sources_not_deduplicated(self):
        self.source('a.txt', '甲')
        self.read('a.txt')
        self.write('b.txt', '甲甲')
        self.read('b.txt')
        self.assertEqual(self.result('exact_concat', ('a.txt', 'a.txt'))['artifacts'][0]['content_relation']['status'], 'text_equal')

    def test_summary_equality_never_proves_semantic_quality(self):
        self.source('a.txt', '不完整摘要')
        self.copied()
        self.assertEqual(self.result('semantic_generation')['artifacts'][0]['content_relation']['status'], 'semantic_review_required')

    def test_no_response_and_skipped_response_are_not_delivery(self):
        self.source('a.txt', 'ok')
        self.copied()
        self.event('FINAL_RESPONSE', {'message': '完成'}, '完成', {'condition_skipped': True})
        self.assertEqual(self.result()['verified_response_observations'], [])

    def test_later_overwrite_does_not_disappear(self):
        self.source('a.txt', 'ok')
        self.copied()
        self.write('b.txt', 'changed', overwrite=True)
        report = self.result()['artifacts'][0]
        self.assertEqual(report['later_file_actions'], [2])
        self.assertFalse(report['destination_creation_observations'][0]['exclusive_creation'])

    def test_failed_later_write_is_visible(self):
        self.source('a.txt', 'ok')
        self.copied()
        self.event('WRITE_TEXT_FILE', {'path': 'b.txt'}, None, ok=False, verified=False)
        self.assertEqual(self.result()['artifacts'][0]['later_file_actions'], [2])

    def test_unknown_shell_side_effect_flagged_even_on_failure(self):
        self.source('a.txt', 'ok')
        self.copied()
        self.event('RUN_SHELL', {}, None, ok=False, verified=False)
        self.assertEqual(self.result()['artifacts'][0]['later_unclassified_actions'], [2])

    def test_source_write_visible_even_if_result_equal(self):
        self.source('a.txt', 'old')
        self.write('a.txt', 'new', overwrite=True)
        self.copied()
        self.assertEqual(len(self.result()['artifacts'][0]['source_write_observations']), 1)

    def test_partial_text_cannot_prove_exact_copy(self):
        self.source('a.txt', 'a' * 200)
        self.read('a.txt', max_chars=100)
        self.write('b.txt', 'a' * 100)
        self.read('b.txt')
        self.assertEqual(self.result()['artifacts'][0]['content_relation']['status'], 'unknown')

    def test_invalid_byte_copy_digest_does_not_prove_copy(self):
        self.source('a.txt', 'ok')
        self.copied()
        self.history[0]['output']['sha256'] = 'not-a-hash'
        self.assertEqual(self.result()['artifacts'][0]['content_relation']['status'], 'unknown')

    def test_existing_destination_skip_is_not_a_copy(self):
        self.source('a.txt', 'source')
        self.read('a.txt')
        self.source('b.txt', 'unrelated')
        result = copy_verified('a.txt', 'b.txt', workspace=self.work, if_exists='skip')
        self.event('COPY_FILE_VERIFIED', {'source': 'a.txt', 'destination': 'b.txt', 'if_exists': 'skip'}, result)
        self.assertEqual(self.result()['artifacts'][0]['content_relation']['status'], 'unknown')

    def test_empty_contract_has_no_overall_verdict(self):
        report = m.build({'artifacts': []}, '說早安', [])
        self.assertFalse(report['whole_task_completion_inferred'])
        self.assertNotIn('complete', report)


if __name__ == '__main__':
    unittest.main()

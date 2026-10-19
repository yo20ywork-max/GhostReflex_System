import importlib.util
from pathlib import Path
import unittest

from tests import test_artifact_evidence_candidate as fixtures

P = Path(__file__).resolve().parents[1] / 'finetuning/release_v13/runtime-candidate/file_operation_obligations.py'
spec = importlib.util.spec_from_file_location('file_obligations_candidate', P)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class OperationObligations(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.ArtifactEvidence(); self.f.setUp()
        self.prompt = '先讀 a.txt，存成新的 b.txt。保留來源，讀回後回覆「完成」。'

    def tearDown(self):
        self.f.tearDown()

    def declarations(self):
        return {'artifact_obligations': [{'artifact_id': 'a1',
            'preserve_sources': {'requirement': 'required', 'request_quote': '保留來源'},
            'new_destination': {'requirement': 'required', 'request_quote': '存成新的 b.txt'},
            'destination_readback': {'requirement': 'required', 'request_quote': '讀回'},
            'read_sources_before_write': {'requirement': 'required', 'request_quote': '先讀 a.txt'}}],
            'final_reply': {'mode': 'exact', 'text': '完成', 'request_quote': '回覆「完成」'},
            'reply_after_readback': {'requirement': 'required', 'request_quote': '讀回後回覆「完成」'},
            'other_operation_requirements': []}

    def artifact(self):
        catalog = m.evidence.catalog_from_history(self.f.history)
        ids = {row['filename']: row['file_id'] for row in catalog}
        return {'artifacts': [{'kind': 'exact_copy', 'source_file_ids': [ids['a.txt']],
                 'destination_file_id': ids.get('b.txt', 'unobserved'), 'destination_name': 'b.txt'}]}

    def check(self, declarations=None):
        return m.check(declarations or self.declarations(), self.artifact(), self.prompt, self.f.history)

    def reply(self, text='完成', **kwargs):
        self.f.event('FINAL_RESPONSE', {'message': text}, text, **kwargs)

    def good_copy(self):
        self.f.source('a.txt', ''); self.f.copied(); self.reply()

    def status(self, result, kind):
        return next(c for c in result['checks'] if c['kind'] == kind)['status']

    def test_verified_empty_copy_and_reply_prove_declared_operations_only(self):
        self.good_copy()
        r = self.check()
        self.assertFalse(r['blocks_completion'])
        self.assertFalse(r['whole_task_completion_inferred'])

    def test_source_overwrite_before_copy_is_unmet(self):
        self.f.source('a.txt', 'old'); self.f.write('a.txt', 'new', overwrite=True)
        self.f.copied(); self.reply()
        self.assertEqual(self.status(self.check(), 'preserve_sources'), 'unmet')

    def test_readback_missing_after_write_is_uncertain(self):
        self.f.source('a.txt', 'data'); self.f.read('a.txt')
        self.f.write('b.txt', 'data'); self.reply()
        self.assertEqual(self.status(self.check(), 'destination_readback'), 'uncertain')

    def test_full_readback_after_write_is_satisfied(self):
        self.f.source('a.txt', 'data'); self.f.read('a.txt')
        self.f.write('b.txt', 'data'); self.f.read('b.txt'); self.reply()
        self.assertFalse(self.check()['blocks_completion'])

    def test_read_before_later_write_is_not_readback(self):
        self.f.source('a.txt', 'data'); self.f.read('a.txt')
        self.f.write('b.txt', 'data'); self.f.read('b.txt')
        self.f.write('b.txt', 'changed', overwrite=True); self.reply()
        self.assertEqual(self.status(self.check(), 'destination_readback'), 'uncertain')

    def test_copy_readback_does_not_cover_later_write(self):
        self.good_copy()
        self.f.write('b.txt', 'changed', overwrite=True); self.reply()
        self.assertEqual(self.status(self.check(), 'destination_readback'), 'uncertain')

    def test_later_correct_readback_reconciles_write(self):
        self.good_copy()
        self.f.write('b.txt', '', overwrite=True); self.f.read('b.txt'); self.reply()
        self.assertEqual(self.status(self.check(), 'destination_readback'), 'satisfied')

    def test_latest_wrong_reply_not_rescued_by_earlier_correct_reply(self):
        self.good_copy(); self.reply('完成了')
        self.assertEqual(self.status(self.check(), 'final_reply'), 'unmet')

    def test_reply_before_readback_fails_order(self):
        self.f.source('a.txt', 'a'); self.f.read('a.txt')
        self.f.write('b.txt', 'a'); self.reply(); self.f.read('b.txt')
        self.assertEqual(self.status(self.check(), 'reply_after_readback'), 'unmet')

    def test_failed_source_write_never_proves_preservation(self):
        self.good_copy()
        self.f.event('WRITE_TEXT_FILE', {'path': 'a.txt', 'content': 'x'}, None, ok=False, verified=False)
        self.assertEqual(self.status(self.check(), 'preserve_sources'), 'uncertain')

    def test_unknown_side_effects_never_prove_preservation_or_readback(self):
        self.good_copy(); self.f.event('RUN_SHELL', {}, None, ok=False, verified=False)
        r = self.check()
        self.assertEqual(self.status(r, 'preserve_sources'), 'uncertain')
        self.assertEqual(self.status(r, 'destination_readback'), 'uncertain')

    def test_nonexclusive_write_is_unknown_not_invented_preexisting(self):
        self.f.source('a.txt', 'a'); self.f.read('a.txt')
        self.f.write('b.txt', 'a', overwrite=True); self.f.read('b.txt'); self.reply()
        self.assertEqual(self.status(self.check(), 'new_destination'), 'uncertain')

    def test_not_required_preservation_does_not_prohibit_requested_edits(self):
        self.prompt = self.prompt.replace('保留來源', '允許修改來源')
        self.f.source('a.txt', 'old'); self.f.write('a.txt', 'new', overwrite=True)
        self.f.copied(); self.reply()
        value = self.declarations()
        value['artifact_obligations'][0]['preserve_sources'] = {'requirement': 'not_required', 'request_quote': ''}
        self.assertEqual(self.status(self.check(value), 'preserve_sources'), 'not_required')

    def test_fabricated_quote_is_rejected(self):
        self.good_copy(); value = self.declarations()
        value['artifact_obligations'][0]['preserve_sources']['request_quote'] = '不存在的要求'
        with self.assertRaises(ValueError): self.check(value)

    def test_unresolved_conditional_never_disappears(self):
        self.good_copy(); value = self.declarations()
        value['other_operation_requirements'] = ['保留來源']
        self.assertTrue(self.check(value)['blocks_completion'])

    def test_compiler_context_has_no_file_contents_or_outcomes(self):
        self.good_copy()
        catalog = m.evidence.catalog_from_history(self.f.history)
        c = m.compiler_context(self.artifact(), self.prompt, catalog)
        self.assertEqual(set(c), {'user_request', 'files', 'artifacts'})
        self.assertNotIn('observed_history', c)
        self.assertNotIn('verified_file_contents', c)


if __name__ == '__main__':
    unittest.main()

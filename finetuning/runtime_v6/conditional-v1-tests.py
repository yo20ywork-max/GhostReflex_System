import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'finetuning/runtime_v6'))
from conditional_flow import ConditionalFixture, authored_plan
from step_conditions import check_condition, validate_condition
from path_metadata import inspect_path
from test_plan_execution_integrity import load


class Gateway:
    def __init__(self):
        self.plans = 0
        self.observations = []
    def chat_json(self, *, messages, schema, models=None):
        if 'complete' in schema['properties']:
            self.observations.append(json.loads(messages[-1]['content']))
            return {'complete': True, 'reason': 'scripted checker; files independently asserted'}, 'scripted'
        self.plans += 1
        return authored_plan(), 'scripted'


class StepConditions(unittest.TestCase):
    def conditional_file_run(self, exists, source_exists=True):
        original = '  原文\r\n\t😀𠮷\r\n'
        files = {'原稿.txt': original} if source_exists else {}
        if exists:
            files['副本.txt'] = '不可更動\n'
        row = {'id': 'conditional-flow', 'user_request': '副本存在就保持不變，只有不存在才讀來源複製並讀回。',
               'initial_files': files, 'write_targets': {}}
        gateway = Gateway()
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='.conditional-test-') as folder:
            fixture = ConditionalFixture(row, folder, 'scripted', gateway)
            try:
                result, receipts, _ = fixture.run('scripted', gateway)
                self.assertEqual(result.status, 'completed')
                expected_tools = ['PATH_INFO', 'FINAL_RESPONSE'] if exists else ['PATH_INFO', 'READ_TEXT_FILE', 'WRITE_TEXT_FILE', 'READ_TEXT_FILE', 'FINAL_RESPONSE']
                self.assertEqual([r['tool'] for r in receipts], expected_tools)
                self.assertEqual(result.message, '副本已存在，保持不變' if exists else '新副本完成')
                self.assertEqual((fixture.work / '副本.txt').read_bytes(), ('不可更動\n' if exists else original).encode())
                if source_exists:
                    self.assertEqual((fixture.work / '原稿.txt').read_bytes(), original.encode())
                else:
                    self.assertFalse((fixture.work / '原稿.txt').exists())
                skips = [h for h in result.history if h['tool'] == 'CONDITION_SKIP']
                self.assertEqual(len(skips), 4 if exists else 1)
                self.assertTrue(all(h['executed'] is False and h['output'] is None for h in skips))
                self.assertEqual(gateway.observations[0]['observed_history'], [{**h, 'sequence_index': i} for i, h in enumerate(result.history, 1)])
                self.assertEqual(gateway.plans, 1)
            finally:
                fixture.close()

    def test_existing_destination_skips_source_read_and_write(self):
        self.conditional_file_run(True)

    def test_missing_source_is_not_touched_when_destination_exists(self):
        self.conditional_file_run(True, False)

    def test_absent_destination_executes_copy_readback_and_correct_reply(self):
        self.conditional_file_run(False)

    def test_unverified_failed_skipped_or_wrong_type_cannot_choose_branch(self):
        condition = {'step_id': 1, 'field': 'exists', 'equals': False}
        for ok, verified, evidence, output in [(False, True, {}, {'exists': False}), (True, False, {}, {'exists': False}),
                                             (True, True, {'condition_skipped': True}, {'exists': False}),
                                             (True, True, {}, {}), (True, True, {}, {'exists': 'false'}),
                                             (True, True, {}, {'exists': 0})]:
            with self.assertRaises(ValueError):
                check_condition(condition, {1: SimpleNamespace(ok=ok, verified=verified, evidence=evidence, output=output)})

    def test_boolean_conditions_are_strict_and_cannot_reference_future_steps(self):
        for bad in [None, {}, {'step_id': True, 'field': 'exists', 'equals': False},
                    {'step_id': 2, 'field': 'exists', 'equals': False},
                    {'step_id': 1, 'field': '', 'equals': False},
                    {'step_id': 1, 'field': 'exists', 'equals': 0}]:
            with self.assertRaises(ValueError):
                validate_condition(bad, {1})

    def test_unknown_control_field_rejected_instead_of_silently_executed(self):
        scope = load()
        settings = SimpleNamespace(max_plan_steps=12, default_tool_retries=0)
        raw = {'objective': '保留', 'assumptions': [], 'completion_criteria': [],
               'steps': [{'id': 1, 'tool': 'READ_TEXT_FILE', 'args': {'path': 'a'}, 'condition': 'never'}]}
        with self.assertRaisesRegex(ValueError, '未知欄位'):
            scope['validate_plan'](raw, settings, 'test')
        del raw['steps'][0]['condition']
        raw['if_exists'] = 'skip'
        with self.assertRaisesRegex(ValueError, '未知欄位'):
            scope['validate_plan'](raw, settings, 'test')

    def test_reference_to_skipped_step_cannot_feed_later_write(self):
        scope = load()
        result = SimpleNamespace(ok=True, output=None, evidence={'condition_skipped': True})
        with self.assertRaisesRegex(ValueError, '未執行'):
            scope['resolve_references']('{{step:1.output}}', {1: result})

    def test_path_observation_does_not_open_contents(self):
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='.metadata-test-') as folder:
            target = Path(folder) / '秘密.txt'
            target.write_text('不可讀取', encoding='utf8')
            with patch.object(Path, 'open', side_effect=AssertionError('Content opened')):
                result = inspect_path('秘密.txt', folder)
                self.assertTrue(result['exists'])
                self.assertTrue(result['is_file'])
                self.assertIs(result['content_read'], False)
                self.assertFalse(inspect_path('不存在.txt', folder)['exists'])
                with self.assertRaises(ValueError):
                    inspect_path('../outside', folder)

    def test_permission_error_is_not_reported_as_absence(self):
        with patch('path_metadata.os.lstat', side_effect=PermissionError('denied')):
            with self.assertRaises(PermissionError):
                inspect_path('a', ROOT)

    def test_unknown_condition_blocks_before_real_read_or_write_dispatch(self):
        gateway = Gateway()
        row = {'id': 'unknown-condition', 'user_request': '依條件處理',
               'initial_files': {'原稿.txt': '保持'}, 'write_targets': {}}
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='.conditional-unknown-') as folder:
            fixture = ConditionalFixture(row, folder, 'scripted', gateway)
            try:
                fixture.scope['TOOL_REGISTRY']['PATH_INFO'].handler = lambda *_a, **_k: fixture.scope['ToolResult'](True, output={'exists': 'false'}, verified=True)
                result, receipts, _ = fixture.run('scripted', gateway)
                self.assertNotEqual(result.status, 'completed')
                self.assertIn('條件無法判定', result.message)
                self.assertEqual([r['tool'] for r in receipts], ['PATH_INFO'])
                self.assertEqual((fixture.work / '原稿.txt').read_text(encoding='utf8'), '保持')
                self.assertFalse((fixture.work / '副本.txt').exists())
            finally:
                fixture.close()


if __name__ == '__main__':
    unittest.main()

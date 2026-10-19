import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'finetuning/release_v13'))
from file_fixture_text import Fixture
from tool_result_contracts import BOOLEAN_FIELDS, describe_catalog, validate_plan_conditions


def step(i, tool, field=None, source=1):
    return SimpleNamespace(id=i, tool=tool, when=None if field is None else
                           {'step_id': source, 'field': field, 'equals': False})


class ResultContracts(unittest.TestCase):
    def test_impossible_fields_rejected_without_rewriting_conditions(self):
        for tool, field in [('MAKE_DIRECTORY', 'exists'), ('READ_TEXT_FILE', 'file_text'),
                            ('WRITE_TEXT_FILE', 'write_succeeded'), ('APPEND_TEXT_FILE', 'exists'),
                            ('MODEL_GENERATE', 'complete'), ('PATH_INFO', 'bytes')]:
            plan = SimpleNamespace(steps=[step(1, tool), step(2, 'READ_TEXT_FILE', field)])
            original = copy.deepcopy(plan)
            with self.assertRaisesRegex(ValueError, '頂層 boolean'):
                validate_plan_conditions(plan)
            self.assertEqual(plan, original)

    def test_valid_optional_and_unknown_tool_fields_remain_runtime_checked(self):
        for tool, field in [('PATH_INFO', 'exists'), ('COPY_FILE_VERIFIED', 'copied'),
                            ('COPY_FILE_VERIFIED', 'destination_readback_verified'),
                            ('PLUGIN_OBSERVATION', 'ready')]:
            validate_plan_conditions(SimpleNamespace(steps=[step(1, tool), step(2, 'FINAL_RESPONSE', field)]))

    def test_observed_field_requires_actual_boolean_and_trusted_success(self):
        plan = SimpleNamespace(steps=[step(2, 'FINAL_RESPONSE', 'ready')])
        base = {'step_id': 1, 'tool': 'PLUGIN_OBSERVATION', 'output': {'ready': True},
                'ok': True, 'verified': True, 'evidence': {}}
        # Predicate is false, but valid; preflight must not delete/reject it.
        validate_plan_conditions(plan, [base])
        for patch in ({'ok': False}, {'verified': False}, {'evidence': {'condition_skipped': True}},
                      {'output': {'ready': 'false'}}, {'output': {'ready': 0}}, {'output': {}}):
            with self.assertRaises(ValueError):
                validate_plan_conditions(plan, [{**base, **patch}])

    def test_catalog_is_copied_and_no_fields_invented_for_unknown_tools(self):
        catalog = [{'name': 'MAKE_DIRECTORY', 'parameters': {'path': 'schema'}},
                   {'name': 'PATH_INFO'}, {'name': 'PLUGIN_OBSERVATION'}]
        before = copy.deepcopy(catalog)
        shown = describe_catalog(catalog)
        self.assertEqual(catalog, before)
        self.assertEqual(shown[0]['when_boolean_fields'], [])
        self.assertIn('exists', shown[1]['when_boolean_fields'])
        self.assertNotIn('when_boolean_fields', shown[2])

    def test_declared_fields_match_real_file_and_generation_results(self):
        class Gateway:
            def chat_text(self, **_):
                return '生成文字', 'scripted'
        row = {'id': 'result-fields', 'user_request': '控制',
               'initial_files': {'來源.txt': '原文'}, 'write_targets': {}}
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='.result-fields-') as folder:
            fixture = Fixture(row, folder, 'scripted', Gateway())
            try:
                ctx = SimpleNamespace(settings=fixture.settings, gateway=Gateway())
                def call(name, **args):
                    result = fixture.scope['TOOL_REGISTRY'][name].handler(ctx, **args)
                    self.assertTrue(result.ok, result.error)
                    actual = {k for k, v in result.output.items() if type(v) is bool} if isinstance(result.output, dict) else set()
                    self.assertLessEqual(actual, set(BOOLEAN_FIELDS[name]))
                    return result
                call('MAKE_DIRECTORY', path='交付')
                call('READ_TEXT_FILE', path='來源.txt')
                call('WRITE_TEXT_FILE', path='文字.txt', content='內容')
                call('APPEND_TEXT_FILE', path='文字.txt', content='追加')
                call('MODEL_GENERATE', prompt='產生文字')
                present = call('PATH_INFO', path='來源.txt')
                absent = call('PATH_INFO', path='不存在.txt')
                self.assertIs(present.output['exists'], True)
                self.assertIs(absent.output['exists'], False)
                self.assertEqual(set(BOOLEAN_FIELDS['PATH_INFO']), set(present.output) - {'path'})
                copied = call('COPY_FILE_VERIFIED', source='來源.txt', destination='交付/副本.txt')
                skipped = call('COPY_FILE_VERIFIED', source='不存在來源.txt', destination='交付/副本.txt', if_exists='skip')
                self.assertIs(copied.output['copied'], True)
                self.assertIs(skipped.output['copied'], False)
                self.assertIs(skipped.output['source_read'], False)
                self.assertNotIn('destination_readback_verified', skipped.output)
                plan = SimpleNamespace(steps=[step(2, 'FINAL_RESPONSE', 'destination_readback_verified')])
                with self.assertRaises(ValueError):
                    validate_plan_conditions(plan, [{'step_id': 1, 'tool': 'COPY_FILE_VERIFIED',
                        'output': skipped.output, 'ok': True, 'verified': True, 'evidence': skipped.evidence}])
            finally:
                fixture.close()

    def run_actual_planner(self, repair):
        def item(i, tool, args, when=None):
            out = {'id': i, 'tool': tool, 'args': args, 'goal': '依使用者需求處理',
                   'success_check': '實際檔案及讀回', 'on_failure': 'replan', 'retries': 0}
            if when is not None:
                out['when'] = when
            return out
        raw = {'objective': '建立資料夾並原樣保存來源', 'assumptions': [], 'completion_criteria': ['完整交付'],
               'steps': [item(1, 'MAKE_DIRECTORY', {'path': '交付'}),
                         item(2, 'READ_TEXT_FILE', {'path': '來源.txt'},
                              {'step_id': 1, 'field': 'exists', 'equals': True}),
                         item(3, 'WRITE_TEXT_FILE', {'path': '交付/副本.txt', 'content': '{{step:2.file_text}}'}),
                         item(4, 'READ_TEXT_FILE', {'path': '交付/副本.txt'}),
                         item(5, 'FINAL_RESPONSE', {'message': '交付完成'})]}
        class Gateway:
            calls = 0
            def chat_json(inner, *, messages, schema, models=None):
                if 'complete' in schema['properties']:
                    return {'complete': True, 'reason': 'scripted; independent bytes/readback assertions'}, 'scripted'
                inner.calls += 1
                if inner.calls == 2:
                    self.assertFalse((fixture.work / '交付').exists())
                    self.assertEqual(fixture.trace, [])
                    self.assertIn('頂層 boolean', messages[-1]['content'])
                value = copy.deepcopy(raw)
                if repair and inner.calls == 2:
                    del value['steps'][1]['when']
                return value, 'scripted'
        text = '原樣 e\u0301\t\r\n𠮷😀  '
        row = {'id': 'result-contract', 'user_request': '建立交付資料夾，讀取來源.txt，原樣另存交付/副本.txt。读回後回覆「交付完成」。',
               'initial_files': {'來源.txt': text},
               'write_targets': {'交付': ['MAKE_DIRECTORY'], '交付/副本.txt': ['WRITE_TEXT_FILE']}}
        gateway = Gateway()
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='.result-contract-') as folder:
            fixture = Fixture(row, folder, 'scripted', gateway)
            try:
                result, receipts, _ = fixture.run('scripted', gateway)
                self.assertEqual(gateway.calls, 2)
                self.assertEqual((fixture.work / '來源.txt').read_bytes(), text.encode())
                if repair:
                    self.assertEqual(result.status, 'completed')
                    self.assertEqual(result.message, '交付完成')
                    self.assertEqual((fixture.work / '交付/副本.txt').read_bytes(), text.encode())
                    self.assertEqual([r['tool'] for r in receipts],
                                     ['MAKE_DIRECTORY', 'READ_TEXT_FILE', 'WRITE_TEXT_FILE', 'READ_TEXT_FILE', 'FINAL_RESPONSE'])
                else:
                    self.assertEqual(result.status, 'blocked')
                    self.assertFalse((fixture.work / '交付').exists())
                    self.assertFalse(any(r['tool'] != 'BLOCKED' for r in receipts))
            finally:
                fixture.close()

    def test_actual_planner_repairs_before_first_effect_and_delivers_exact_bytes(self):
        self.run_actual_planner(True)

    def test_actual_planner_never_dispatches_unrepaired_invalid_plan(self):
        self.run_actual_planner(False)


if __name__ == '__main__':
    unittest.main()

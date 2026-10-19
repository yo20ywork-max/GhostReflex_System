import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

from test_plan_execution_integrity import load
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'finetuning/runtime_v6'))
from conditional_flow import ConditionalFixture, ROOT


class ArgumentReferences(unittest.TestCase):
    def setUp(self):
        self.scope = load()
    def test_unknown_and_unterminated_reference_is_rejected_before_dispatch(self):
        for text in ['{{step:2.content}}', 'prefix {{step:2.wrong}} suffix', '{{step:2.output', '{{step:x.output}}']:
            with self.assertRaisesRegex(ValueError, '不支援的步驟輸出引用'):
                self.scope['resolve_references'](text, {2: SimpleNamespace(ok=True, output='actual')})

    def test_explicit_literal_preserves_all_whitespace_and_reference_spellings(self):
        literal = '  {{step:2.content}}\r\n\t{{step:999.output}} {{step: 未完成😀  '
        self.assertEqual(self.scope['resolve_references']({'$literal': literal}, {}), literal)
        self.scope['validate_tool_arguments']({'$literal': literal}, {'type': 'string'}, allow_references=True)
        with self.assertRaises(ValueError):
            self.scope['validate_tool_arguments']({'$literal': False}, {'type': 'string'}, allow_references=True)

    def test_literal_contents_are_not_dependency_references(self):
        raw = {'objective': '原文', 'assumptions': [], 'completion_criteria': [],
               'steps': [{'id': 1, 'tool': 'READ_TEXT_FILE', 'args': {'path': {'$literal': '{{step:999.output}}'}}}]}
        plan = self.scope['validate_plan'](raw, SimpleNamespace(max_plan_steps=2, default_tool_retries=0), 'scripted')
        self.assertEqual(plan.steps[0].args['path'], raw['steps'][0]['args']['path'])

    def test_resolved_output_is_not_reinterpreted_as_another_reference(self):
        literal = '{{step:999.content}}'
        self.assertEqual(self.scope['resolve_references']('{{step:2.output}}', {2: SimpleNamespace(ok=True, output=literal)}), literal)

    def test_real_file_literal_roundtrip_and_bad_reference_never_creates_file(self):
        literal = '  {{step:2.content}}\r\n\t{{step:999.output}} 😀\n'
        class Gateway:
            def chat_json(self, *, messages, schema, models=None):
                if 'complete' in schema['properties']:
                    return {'complete': True, 'reason': 'scripted'}, 'scripted'
                raise AssertionError('No model generation expected')
        row = {'id': 'literal-file', 'user_request': '保持字面', 'initial_files': {}, 'write_targets': {}}
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='.literal-reference-') as folder:
            fixture = ConditionalFixture(row, folder, 'scripted', Gateway())
            try:
                step = fixture.scope['PlanStep'](1, '字面', 'WRITE_TEXT_FILE', {'path': '原文.txt', 'content': {'$literal': literal}, 'overwrite': False}, '原樣')
                result = fixture.agent._execute_step(fixture.ctx, step)
                self.assertTrue(result.ok)
                self.assertEqual((fixture.work / '原文.txt').read_bytes(), literal.encode())
                step = fixture.scope['PlanStep'](2, '錯誤引用', 'WRITE_TEXT_FILE', {'path': '不應建立.txt', 'content': '{{step:1.content}}', 'overwrite': False}, '拒絕')
                result = fixture.agent._execute_step(fixture.ctx, step)
                self.assertFalse(result.ok)
                self.assertFalse((fixture.work / '不應建立.txt').exists())
                self.assertEqual(len(fixture.journal.read(fixture.ctx.request_id)), 1)
            finally:
                fixture.close()

    def test_live_schema_supports_literal_without_allowing_wrong_type(self):
        from jsonschema import Draft202012Validator
        from build_product_data import contract
        _, schema, _, _ = contract()
        row = {'objective': '原樣輸出', 'assumptions': [], 'completion_criteria': [],
               'steps': [{'id': 1, 'goal': '輸出', 'tool': 'FINAL_RESPONSE',
                          'args': {'message': {'$literal': '{{step:88.output}}'}}, 'success_check': '原樣'}]}
        validator = Draft202012Validator(schema)
        validator.validate(row)
        row['steps'][0]['args']['message']['$literal'] = False
        self.assertFalse(validator.is_valid(row))


if __name__ == '__main__':
    unittest.main()

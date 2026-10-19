import copy
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest

from argument_references import validate_file_text_sources
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'finetuning/release_v13'))
from file_fixture_text import Fixture


def step(i, tool, value=None):
    return NS(id=i, tool=tool, args={'value': value})


class FileTextSources(unittest.TestCase):
    def test_only_reads_can_anchor_file_text(self):
        for tool in ['WRITE_TEXT_FILE', 'MODEL_GENERATE', 'PATH_INFO', 'PLUGIN_TEXT']:
            with self.subTest(tool=tool), self.assertRaisesRegex(ValueError, '唯一 READ_TEXT_FILE'):
                validate_file_text_sources(NS(steps=[step(1, tool), step(2, 'MODEL_GENERATE', '{{step:1.file_text}}')]))
        validate_file_text_sources(NS(steps=[step(1, 'READ_TEXT_FILE'), step(2, 'MODEL_GENERATE', '{{step:1.file_text}}')]))

    def test_nested_embedded_references_checked_and_inputs_unchanged(self):
        plan = NS(steps=[step(7, 'WRITE_TEXT_FILE'), step(8, 'MODEL_GENERATE', {'a': [1, 'prefix {{step:7.file_text}} suffix']})])
        before = copy.deepcopy(plan)
        with self.assertRaises(ValueError):
            validate_file_text_sources(plan)
        self.assertEqual(plan, before)

    def test_literals_and_outputs_are_not_reinterpreted(self):
        text = '  {{step:999.file_text}}\r\n\t{{step:x.output}}😀'
        plan = NS(steps=[step(1, 'MODEL_GENERATE'), step(2, 'WRITE_TEXT_FILE', [{'x': {'$literal': text}}, '{{step:1.output}}'])])
        before = copy.deepcopy(plan)
        validate_file_text_sources(plan)
        self.assertEqual(plan, before)
        with self.assertRaises(ValueError):
            validate_file_text_sources(NS(steps=[step(1, 'MODEL_GENERATE', {'$literal': text, 'other': 'not literal'})]))

    def test_forward_missing_self_and_ambiguous_anchors_rejected(self):
        for plan, history in [
            (NS(steps=[step(1, 'MODEL_GENERATE', '{{step:2.file_text}}'), step(2, 'READ_TEXT_FILE')]), []),
            (NS(steps=[step(1, 'READ_TEXT_FILE', '{{step:1.file_text}}')]), []),
            (NS(steps=[step(3, 'MODEL_GENERATE', '{{step:1.file_text}}')]), []),
            (NS(steps=[step(3, 'MODEL_GENERATE', '{{step:1.file_text}}')]), [{'step_id': 1, 'tool': 'READ_TEXT_FILE'}] * 2),
        ]:
            with self.assertRaises(ValueError):
                validate_file_text_sources(plan, history)

    def test_partial_historical_read_can_be_completed_later(self):
        history = [{'step_id': 1, 'tool': 'READ_TEXT_FILE', 'ok': True, 'verified': True,
                    'output': '片段', 'evidence': {'truncated': True}}]
        plan = NS(steps=[step(2, 'READ_TEXT_FILE'), step(3, 'WRITE_TEXT_FILE', '{{step:1.file_text}}')])
        before = copy.deepcopy(history)
        validate_file_text_sources(plan, history)
        self.assertEqual(history, before)
        history[0]['tool'] = 'WRITE_TEXT_FILE'
        with self.assertRaises(ValueError):
            validate_file_text_sources(plan, history)

    def run_planner(self, repaired):
        def item(i, tool, args):
            return {'id': i, 'tool': tool, 'args': args, 'goal': '依需求執行',
                    'success_check': '確認實際結果', 'on_failure': 'replan', 'retries': 0}
        raw = {'objective': '原樣複製', 'assumptions': [], 'completion_criteria': ['完整交付'], 'steps': [
            item(1, 'READ_TEXT_FILE', {'path': '來源.txt'}),
            item(2, 'WRITE_TEXT_FILE', {'path': '副本.txt', 'content': '{{step:1.file_text}}'}),
            item(3, 'READ_TEXT_FILE', {'path': '副本.txt'}),
            item(4, 'FINAL_RESPONSE', {'message': '{{step:2.file_text}}'})]}
        text = '原文 e\u0301\t\r\n𠮷😀  '
        row = {'id': 'anchor-preflight', 'user_request': '讀取來源.txt，原樣另存副本.txt，讀回後逐字回覆內容。',
               'initial_files': {'來源.txt': text}, 'write_targets': {'副本.txt': ['WRITE_TEXT_FILE']}}
        class Gateway:
            calls = 0
            def chat_json(inner, *, messages, schema, models=None):
                if 'complete' in schema['properties']:
                    return {'complete': True, 'reason': 'scripted; separate exact byte assertions'}, 'scripted'
                inner.calls += 1
                if inner.calls == 2:
                    self.assertEqual(fixture.trace, [])
                    self.assertFalse((fixture.work / '副本.txt').exists())
                    self.assertIn('全文引用只能指向', messages[-1]['content'])
                value = copy.deepcopy(raw)
                if repaired and inner.calls == 2:
                    value['steps'][-1]['args']['message'] = '{{step:3.file_text}}'
                return value, 'scripted'
        gateway = Gateway()
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='.anchor-preflight-') as folder:
            fixture = Fixture(row, folder, 'scripted', gateway)
            try:
                result, receipts, _ = fixture.run('scripted', gateway)
                self.assertEqual(gateway.calls, 2)
                self.assertEqual((fixture.work / '來源.txt').read_bytes(), text.encode())
                if repaired:
                    self.assertEqual(result.status, 'completed')
                    self.assertEqual(result.message, text)
                    self.assertEqual((fixture.work / '副本.txt').read_bytes(), text.encode())
                    self.assertEqual([r['tool'] for r in receipts], ['READ_TEXT_FILE', 'WRITE_TEXT_FILE', 'READ_TEXT_FILE', 'FINAL_RESPONSE'])
                else:
                    self.assertEqual(result.status, 'blocked')
                    self.assertFalse((fixture.work / '副本.txt').exists())
                    self.assertFalse(any(r['tool'] != 'BLOCKED' for r in receipts))
            finally:
                fixture.close()

    def test_repair_happens_before_any_effect_and_preserves_bytes(self):
        self.run_planner(True)

    def test_unrepaired_plan_has_no_effects(self):
        self.run_planner(False)


if __name__ == '__main__':
    unittest.main()

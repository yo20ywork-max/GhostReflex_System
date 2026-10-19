import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unicodedata
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'finetuning/release_v13'))
from file_fixture_text import Fixture
from generation_context import prepare
from model_context import unpack
from text_reader import read_text_segment


def decoded(text):
    value = json.loads(unicodedata.normalize('NFC', text))
    return unpack(value) if 'shared_context_text' in value else value


class GenerationContext(unittest.TestCase):
    def test_standalone_explicit_inputs_unchanged(self):
        self.assertEqual(prepare(SimpleNamespace(), '  原文 e\u0301\r\n', '只輸出程式\t'),
                         ('  原文 e\u0301\r\n', '只輸出程式\t'))

    def test_request_is_preserved_even_before_first_observation(self):
        ctx = SimpleNamespace(original_prompt='兩句歡迎詞，不要自我介紹。', history=[])
        prompt, system = prepare(ctx, '寫歡迎詞', '只用繁體中文。  ')
        self.assertEqual(decoded(prompt)['original_request'], ctx.original_prompt)
        self.assertEqual(decoded(prompt)['generation_instruction'], '寫歡迎詞')
        self.assertTrue(system.startswith('只用繁體中文。  \n\n'))

    def test_history_roles_and_task_isolation(self):
        items = [{'step_id': i, 'tool': tool, 'ok': ok, 'verified': verified, 'output': text, 'evidence': {}}
                 for i, (tool, ok, verified, text) in enumerate([
                     ('BROWSER_GET_TEXT', True, True, '本次網頁原文'),
                     ('MODEL_GENERATE', True, True, '先前草稿'),
                     ('TRANSLATE_TEXT', True, True, '先前譯文'),
                     ('BROWSER_GET_TEXT', False, False, '失敗結果'),
                     ('BROWSER_CLICK', True, False, '僅送出'),
                     ('CONDITION_SKIP', True, True, None)], 1)]
        saved = copy.deepcopy(items)
        ctx = SimpleNamespace(original_prompt='摘要本次網頁', history=items,
                              runtime=SimpleNamespace(history=[{'output': '其他任務秘密'}]))
        payload = decoded(prepare(ctx, '摘要')[0])
        self.assertEqual([x['generation_context_role'] for x in payload['observed_history']],
                         ['tool_result', 'generated_draft', 'generated_draft', 'failed', 'unverified', 'skipped'])
        self.assertNotIn('其他任務秘密', json.dumps(payload, ensure_ascii=False))
        self.assertEqual(items, saved)
        self.assertNotIn('本次網頁原文', prepare(SimpleNamespace(original_prompt='另一個任務', history=[]), '問候')[0])

    def test_partial_read_stays_partial_and_prepare_does_no_io(self):
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='.generation-partial-') as folder:
            p = Path(folder) / '資料.txt'
            p.write_text('字' * 400, encoding='utf8')
            text, evidence = read_text_segment(p, 100)
            history = [{'step_id': 1, 'tool': 'READ_TEXT_FILE', 'ok': True, 'verified': True,
                        'args': {'path': str(p)}, 'output': text, 'evidence': evidence}]
            ctx = SimpleNamespace(original_prompt='摘要已讀到的片段', history=history)
            with patch.object(Path, 'open', side_effect=AssertionError('Unexpected file open')):
                payload = decoded(prepare(ctx, '摘要')[0])
            self.assertEqual(payload['verified_file_contents'], {})
            self.assertFalse(payload['file_read_progress']['files'][0]['whole_file_observed'])
            self.assertEqual(payload['observed_history'][0]['output'], text)

    def test_complete_unicode_source_roundtrip_and_original_context_unchanged(self):
        text = ('原文 e\u0301\t\r\n𠮷😀 {{step:800.output}}  ' * 80)
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='.generation-unicode-') as folder:
            p = Path(folder) / '來源.txt'; p.write_bytes(text.encode())
            output, evidence = read_text_segment(p, 50000)
            history = [{'step_id': 1, 'tool': 'READ_TEXT_FILE', 'ok': True, 'verified': True,
                        'args': {'path': str(p)}, 'output': output, 'evidence': evidence}]
            before = copy.deepcopy(history)
            payload = decoded(prepare(SimpleNamespace(original_prompt='原樣處理 e\u0301', history=history), '保留原文')[0])
            self.assertEqual(payload['verified_file_contents'][str(p)]['text'].encode(), text.encode())
            self.assertEqual(payload['observed_history'][0]['output'].encode(), text.encode())
            self.assertEqual(history, before)

    def test_actual_handler_receives_source_despite_omitted_reference(self):
        text = '活動在4月12日上午10點於三樓舉行，4月5日截止，預算兩萬元。'
        output = '一、4月12日上午10點，三樓。\n二、4月5日截止。\n三、預算兩萬元。'
        prompt = '讀取來源.txt並摘要三點至摘要.txt，讀回後回覆「摘要完成」。'
        received = []
        def step(i, tool, args):
            return {'id': i, 'goal': '依原需求處理', 'tool': tool, 'args': args,
                    'success_check': '實際內容', 'on_failure': 'stop', 'retries': 0}
        class Gateway:
            def chat_json(self, *, schema, **_):
                if 'complete' in schema['properties']:
                    return {'complete': True, 'reason': 'scripted; independent artifact assertions'}, 'scripted'
                return {'objective': prompt, 'assumptions': [], 'completion_criteria': ['三點摘要及交付'],
                        'steps': [step(1, 'READ_TEXT_FILE', {'path': '來源.txt'}),
                                  step(2, 'MODEL_GENERATE', {'prompt': '摘要三點', 'system': '不要前言。'}),
                                  step(3, 'WRITE_TEXT_FILE', {'path': '摘要.txt', 'content': '{{step:2.output}}'}),
                                  step(4, 'READ_TEXT_FILE', {'path': '摘要.txt'}),
                                  step(5, 'FINAL_RESPONSE', {'message': '摘要完成'})]}, 'scripted'
            def chat_text(inner, *, prompt: str, system: str):
                value = decoded(prompt)
                self.assertEqual(value['original_request'], row['user_request'])
                self.assertEqual(value['generation_instruction'], '摘要三點')
                self.assertEqual(next(iter(value['verified_file_contents'].values()))['text'], text)
                self.assertTrue(system.startswith('不要前言。\n\n'))
                received.append(value)
                return output, 'scripted'
        row = {'id': 'generation-context', 'user_request': prompt, 'initial_files': {'來源.txt': text},
               'write_targets': {'摘要.txt': ['WRITE_TEXT_FILE']}}
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='.generation-handler-') as folder:
            gateway = Gateway(); fixture = Fixture(row, folder, 'scripted', gateway)
            try:
                result, receipts, _ = fixture.run('scripted', gateway)
                self.assertEqual(result.status, 'completed')
                self.assertEqual(result.message, '摘要完成')
                self.assertEqual((fixture.work / '摘要.txt').read_bytes(), output.encode())
                self.assertEqual((fixture.work / '來源.txt').read_bytes(), text.encode())
                self.assertEqual(len(received), 1)
                self.assertEqual([r['tool'] for r in receipts], ['READ_TEXT_FILE', 'MODEL_GENERATE', 'WRITE_TEXT_FILE', 'READ_TEXT_FILE', 'FINAL_RESPONSE'])
            finally:
                fixture.close()


if __name__ == '__main__':
    unittest.main()

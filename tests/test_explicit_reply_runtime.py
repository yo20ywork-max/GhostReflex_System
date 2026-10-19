"""Actual agent/file-handler recovery with scripted model responses, no UI/network."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'finetuning/release_v4'))
from file_flow import Fixture
from explicit_reply import install_reply_completion_guard


def step(index, tool, args):
    return {'id': index, 'goal': '執行要求', 'tool': tool, 'args': args,
            'success_check': '實際工具觀察', 'on_failure': 'stop', 'retries': 0}


class ScriptedGateway:
    def __init__(self, steps, reply):
        self.steps, self.reply, self.plans, self.replans = steps, reply, 0, []

    def chat_json(self, *, messages, schema, models=None):
        if 'complete' in schema['properties']:
            # Deliberately overconfident checker; guard must detect missing reply.
            return {'reason': '工具已完成', 'complete': True}, 'scripted'
        self.plans += 1
        if self.plans == 1:
            steps = self.steps
        else:
            self.replans.append(json.loads(messages[-1]['content']))
            if self.plans > 2:
                raise AssertionError('Unexpected repeated recovery')
            steps = [step(len(self.steps) + 1, 'FINAL_RESPONSE', {'message': self.reply})]
        return {'objective': '完成原要求', 'assumptions': [], 'steps': steps,
                'completion_criteria': ['依真實結果與回覆核對']}, 'scripted'


class ExplicitReplyRuntimeTests(unittest.TestCase):
    def test_missing_reply_recovers_without_repeating_append(self):
        self.check_append_recovery('')

    def test_missing_reply_with_trailing_constraint_recovers_without_repeating_append(self):
        self.check_append_recovery('已成功的寫入不要重做。')

    def check_append_recovery(self, suffix):
        reply = '  已核對𠮷\n\t保留  '
        gateway = ScriptedGateway([
            step(1, 'READ_TEXT_FILE', {'path': '片尾來源.txt'}),
            step(2, 'APPEND_TEXT_FILE', {'path': '工作記錄.txt', 'content': '{{step:1.file_text}}'}),
            step(3, 'READ_TEXT_FILE', {'path': '工作記錄.txt'}),
        ], reply)
        row = {'id': 'reply-recovery',
               'user_request': '將片尾原文追加到工作記錄，不自行加換行。讀回確認後只回覆「' + reply + '」。' + suffix,
               'initial_files': {'片尾來源.txt': '收尾\t😀\r\n', '工作記錄.txt': '原本\r\n'},
               'write_targets': {'工作記錄.txt': ['APPEND_TEXT_FILE']}}
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='.reply-runtime-test-') as folder:
            fixture = Fixture(row, folder, 'scripted', gateway)
            try:
                install_reply_completion_guard(fixture.scope['Planner'])
                result, _, _ = fixture.run('scripted', gateway)
                self.assertEqual(result.status, 'completed')
                self.assertEqual(result.message, reply)
                self.assertEqual((fixture.work / '工作記錄.txt').read_bytes(), '原本\r\n收尾\t😀\r\n'.encode())
                self.assertEqual((fixture.work / '片尾來源.txt').read_bytes(), '收尾\t😀\r\n'.encode())
                self.assertEqual([x['tool'] for x in result.history],
                                 ['READ_TEXT_FILE', 'APPEND_TEXT_FILE', 'READ_TEXT_FILE', 'FINAL_RESPONSE'])
                self.assertEqual(gateway.plans, 2)
                self.assertIn('尚未提供原始需求指定的最後回覆', json.dumps(gateway.replans, ensure_ascii=False))
            finally:
                fixture.close()

    def test_matching_direct_read_renders_without_extra_response_tool(self):
        reply = '字面 {{step:88.output}}  '
        gateway = ScriptedGateway([step(1, 'READ_TEXT_FILE', {'path': '便條.txt'})], reply)
        row = {'id': 'reply-direct-read', 'user_request': '讀取便條。讀完後回覆「' + reply + '」。',
               'initial_files': {'便條.txt': reply}, 'write_targets': {}}
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='.reply-runtime-test-') as folder:
            fixture = Fixture(row, folder, 'scripted', gateway)
            try:
                install_reply_completion_guard(fixture.scope['Planner'])
                result, _, _ = fixture.run('scripted', gateway)
                self.assertEqual((result.status, result.message), ('completed', reply))
                self.assertEqual(gateway.plans, 1)
                self.assertEqual(len(result.history), 1)
            finally:
                fixture.close()


if __name__ == '__main__':
    unittest.main()

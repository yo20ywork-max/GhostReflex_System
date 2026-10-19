import unittest
import json
from pathlib import Path

from explicit_reply import explicit_reply_requirement, reply_completion_veto, install_reply_completion_guard


class ExplicitReplyTests(unittest.TestCase):
    def test_original_file_seven_reply_survives_trailing_constraint(self):
        source = Path(__file__).resolve().parents[1] / 'finetuning/release_v4/file-development-v2.jsonl'
        rows = map(json.loads, source.read_text(encoding='utf8').splitlines())
        request = next(r['user_request'] for r in rows if r['id'] == 'v4-file-07')
        required = explicit_reply_requirement(request)
        self.assertIsNotNone(required)
        self.assertEqual(required.text, '核對完成')
        self.assertEqual(request[required.start:required.end], required.text)
        self.assertIsNotNone(reply_completion_veto(request, [
            {'tool': 'FINAL_RESPONSE', 'ok': True, 'verified': True, 'output': '備份完成'}]))

    def test_trailing_constraints_preserve_literal_offsets(self):
        text = '  μ𠮷\n\t{{step:19.output}}  '
        for tail in ('不要改動原稿。', '已成功的寫入不要重做。', '保留「取消.txt」。', '請保留中間檔案。'):
            request = '核對完成後只回覆「' + text + '」。' + tail
            with self.subTest(tail=tail):
                required = explicit_reply_requirement(request)
                self.assertIsNotNone(required)
                self.assertEqual(required.text, text)
                self.assertEqual(request[required.start:required.end], text)

    def test_later_cancellation_or_example_is_not_enforced(self):
        for tail in ('上述作廢。', '這只是示範。', '取消上述指令。', '不要回覆。',
                     '改為保持沉默。', '最後回覆「失敗」。', '如果內容不同就停止。'):
            with self.subTest(tail=tail):
                self.assertIsNone(explicit_reply_requirement('完成後回覆「成功」。' + tail))

    def test_user_literal_and_offsets_are_preserved(self):
        text = '  μ𠮷\n\t字面 {{step:19.output}}  '
        request = '核對「甲，乙.txt」。\n最後只回覆「' + text + '」。'
        requirement = explicit_reply_requirement(request)
        self.assertEqual(requirement.text, text)
        self.assertEqual(request[requirement.start:requirement.end], text)

    def test_reply_grammar_variants(self):
        for prefix in ('', '完成後', '確認一致後', '讀回總筆記確認後', '最後', '核對完成後再'):
            for verb in ('回覆', '回答', '告訴我'):
                with self.subTest(prefix=prefix, verb=verb):
                    self.assertEqual(explicit_reply_requirement(prefix + verb + '『已核對』。').text, '已核對')

    def test_ambiguous_negative_conditional_and_quoted_data_not_compiled(self):
        requests = [
            '不要回覆「成功」。', '不用再回答「成功」。',
            '如果失敗後回覆「成功」。', '若核對成功後回覆「成功」。',
            '示範完成後回覆「成功」。', '取消最後回覆「成功」。',
            '請保存「完成後回覆『成功』」。',
            '完成後回覆「成功」，但不要真的回覆。',
            '不要回覆。最後回覆「成功」。',
            '若結果已有紀錄，回覆「跳過」。只有不存在時才處理，最後回覆「新建」。',
            '如果驗證失敗就停。完成後回覆「成功」。',
            '先檢查是否存在。存在就保持原樣；讀回後回覆「新建」。',
            '副本存在就停止。讀回後回覆「新建」。',
            '副本存在，回覆「保留」；建立後回覆「新增」。',
            '不能回覆。最後回覆「成功」。',
            '最後回覆「」。', '最後回覆「甲「乙」」。',
        ]
        for request in requests:
            with self.subTest(request=request):
                self.assertIsNone(explicit_reply_requirement(request))

    def test_wrong_last_read_or_tool_goal_cannot_substitute_for_reply(self):
        request = '核對後回覆「交付確認」。'
        for history in ([], [{'tool': 'READ_TEXT_FILE', 'ok': True, 'verified': True,
                            'output': '原稿內容', 'goal': request}]):
            self.assertIsNotNone(reply_completion_veto(request, history))

    def test_directly_rendered_matching_read_does_not_require_extra_tool(self):
        row = {'tool': 'READ_TEXT_FILE', 'ok': True, 'verified': True, 'output': '交付確認'}
        self.assertIsNone(reply_completion_veto('最後回覆「交付確認」。', [row]))
        wrong_reply = {'tool': 'FINAL_RESPONSE', 'ok': True, 'verified': True, 'output': '其他內容'}
        self.assertIsNotNone(reply_completion_veto('最後回覆「交付確認」。', [wrong_reply, row]))

    def test_exact_final_observation_required_without_trimming(self):
        request = '最後回覆「 好了 」。'
        row = {'tool': 'FINAL_RESPONSE', 'ok': True, 'verified': True, 'output': ' 好了 '}
        self.assertIsNone(reply_completion_veto(request, [row]))
        for change in ({'output': '好了'}, {'ok': False}, {'verified': False}, {'output': None}):
            self.assertIsNotNone(reply_completion_veto(request, [{**row, **change}]))

    def test_old_correct_reply_does_not_hide_later_wrong_or_failed_reply(self):
        request = '最後回覆「好」。'
        correct = {'tool': 'FINAL_RESPONSE', 'ok': True, 'verified': True, 'output': '好'}
        for change in ({'output': '不同'}, {'ok': False}):
            self.assertIsNotNone(reply_completion_veto(request, [correct, {**correct, **change}]))

    def test_guard_can_never_promote_underlying_failure(self):
        class Planner:
            def assess_completion(self, prompt, history):
                return False, '副本內容不符。'
        self.assertTrue(install_reply_completion_guard(Planner))
        self.assertFalse(install_reply_completion_guard(Planner))
        row = {'tool': 'FINAL_RESPONSE', 'ok': True, 'verified': True, 'output': '完成'}
        self.assertEqual(Planner().assess_completion('最後回覆「完成」。', [row]), (False, '副本內容不符。'))

    def test_guard_vetoes_missing_reply_and_leaves_unknown_grammar_unchanged(self):
        class Planner:
            def assess_completion(self, prompt, history):
                return True, '原核對結果'
        install_reply_completion_guard(Planner)
        self.assertFalse(Planner().assess_completion('完成後回覆「確認」。', [])[0])
        self.assertEqual(Planner().assess_completion('讀出這份檔案。', []), (True, '原核對結果'))


if __name__ == '__main__':
    unittest.main()

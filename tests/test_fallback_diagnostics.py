"""Fallback diagnostics are literal text, never another instruction to resolve."""
from types import SimpleNamespace
import unittest
from tests.test_plan_execution_integrity import load


class FallbackDiagnostics(unittest.TestCase):
    def setUp(self):
        self.scope = load()

    def resolve_reason(self, reason, results=None):
        plan = self.scope['fallback_blocked_plan']('完成原始任務', reason)
        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].tool, 'BLOCKED')
        return self.scope['resolve_references'](plan.steps[0].args, results or {})['reason']

    def test_invalid_reference_in_error_is_preserved(self):
        for reason in ('不支援 {{step:5.message}}。', '錯誤 {{step:N.content}}。',
                       '{"$literal":"{{step:1.bad}}"}\r\n臺灣🎞️'):
            with self.subTest(reason=reason):
                self.assertEqual(self.resolve_reason(reason), reason)

    def test_valid_reference_in_error_cannot_expand_other_output(self):
        reason = '驗證失敗：{{step:99.output}}'
        results = {99: SimpleNamespace(ok=True, output='其他工具的回傳內容')}
        self.assertEqual(self.resolve_reason(reason, results), reason)

    def test_missing_full_file_reference_is_only_diagnostic_text(self):
        reason = '尚未取得 {{step:8.file_text}} 的完整內容。'
        self.assertEqual(self.resolve_reason(reason), reason)

    def test_ordinary_diagnostic_and_action_validation_are_preserved(self):
        self.assertEqual(self.resolve_reason('目前無法連線。'), '目前無法連線。')
        with self.assertRaises(ValueError):
            self.scope['resolve_references']({'path': '{{step:5.message}}'}, {})


if __name__ == '__main__':
    unittest.main()

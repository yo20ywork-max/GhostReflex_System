"""Replay the observed unwanted-submit proposal without any browser or input."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from test_executor_recovery import load


class ConfirmationDispatch(unittest.TestCase):
    def setUp(self):
        self.scope = load()
        self.scope.update(compact_json=lambda value, *_: json.dumps(value, ensure_ascii=False),
                          safe_log_value=lambda value: value, APP_NAME='CrossGen-AGI-μ')
        self.ui = SimpleNamespace(confirm=Mock(return_value=False))
        self.scope['UI'] = self.ui
        self.handler = Mock(return_value=self.scope['ToolResult'](True, verified=True))
        self.scope['TOOL_REGISTRY'] = {'BROWSER_CLICK': SimpleNamespace(
            risk='medium', handler=self.handler,
            parameters={'type': 'object', 'properties': {'by': {'type': 'string'}, 'target': {'type': 'string'}, 'exact': {'type': 'boolean'}}, 'additionalProperties': False})}
        self.settings = SimpleNamespace(auto_approve_high_risk=False)
        self.agent = self.scope['UniversalAgent'].__new__(self.scope['UniversalAgent'])
        self.agent.settings = self.settings
        self.ctx = SimpleNamespace(settings=self.settings, request_id='mock-confirmation', step_results={})
        self.step = self.scope['PlanStep'](
            4, '依观察结果点击指定按钮；如遇问题请诚实地回报失败，不要臆测结果。',
            'BROWSER_CLICK', {'by': 'text', 'target': '正式送出', 'exact': True},
            '依工具回傳的實際結果確認此步驟；未驗證的後續結果不可宣稱已完成。', 'replan', 0)

    def test_denied_observed_submit_never_dispatches(self):
        result = self.agent._execute_step(self.ctx, self.step)
        self.assertFalse(result.ok)
        self.assertTrue(result.terminal)
        self.handler.assert_not_called()
        self.ui.confirm.assert_called_once()
        self.assertIn('正式送出', self.ui.confirm.call_args.args[1])

    def test_approved_observed_submit_dispatches_once(self):
        self.ui.confirm.return_value = True
        result = self.agent._execute_step(self.ctx, self.step)
        self.assertTrue(result.ok)
        self.ui.confirm.assert_called_once()
        self.handler.assert_called_once_with(self.ctx, **self.step.args)

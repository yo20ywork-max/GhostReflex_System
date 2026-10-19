"""Actual desktop file handlers, restricted to disposable fixture workspaces."""
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'finetuning/runtime_v6'))
from conditional_flow import ConditionalFixture
from desktop_contract import extend_scope
from desktop_session import install as install_desktop_guard
from explicit_reply import install_reply_completion_guard


class CopyFixture(ConditionalFixture):
    def __init__(self, row, folder, model, gateway):
        super().__init__(row, folder, model, gateway)
        try:
            self._configure_desktop()
        except Exception:
            self.close()
            raise

    def _configure_desktop(self):
        extend_scope(self.scope, self.catalog)
        self.catalog = self.scope['build_tool_catalog']()
        self.schema = self.scope['build_plan_schema'](self.settings)
        install_desktop_guard(SimpleNamespace(**self.scope))
        install_reply_completion_guard(self.scope['Planner'])
        self.settings.max_replans = 0
        prior = self.agent._execute_step
        actual = self.scope['UniversalAgent']._execute_step.__get__(self.agent)

        def bounded(ctx, step):
            if step.tool != 'COPY_FILE_VERIFIED':
                return prior(ctx, step)
            if len(self.trace) >= 30:
                return self.scope['ToolResult'](False, error='Fixture action budget exhausted', terminal=True)
            result = actual(ctx, step)
            self.trace.append({'id': step.id, 'tool': step.tool, 'when': step.when,
                               'skipped': bool((result.evidence or {}).get('condition_skipped')),
                               'ok': result.ok, 'error': result.error})
            return result
        self.agent._execute_step = bounded
        self.scope['console_print'] = lambda *_: None

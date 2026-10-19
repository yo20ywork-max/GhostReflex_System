"""Actual runtime in disposable files; no native UI or network tools allowed."""
import ast
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE.parent / 'release_v4'))
from file_flow import Fixture


class ConditionalFixture(Fixture):
    def __init__(self, row, folder, model, gateway):
        super().__init__(row, folder, model, gateway)
        tree = ast.parse((ROOT / 'run_daemon.py').read_text(encoding='utf-8-sig'))
        node = next(n for n in tree.body if getattr(n, 'name', '') == 'tool_path_info')
        node.decorator_list = []
        module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), node], type_ignores=[])
        exec(compile(ast.fix_missing_locations(module), '<actual PATH_INFO>', 'exec'), self.scope)
        self.scope['TOOL_REGISTRY']['PATH_INFO'].handler = self.scope['tool_path_info']
        self.settings.max_replans = 2
        actual = self.scope['UniversalAgent']._execute_step.__get__(self.agent)
        allowed = {'PATH_INFO', 'READ_TEXT_FILE', 'WRITE_TEXT_FILE', 'FINAL_RESPONSE', 'BLOCKED'}
        def bounded(ctx, step):
            if step.tool not in allowed or len(self.trace) >= 30:
                return self.scope['ToolResult'](False, error='Outside disposable conditional fixture scope', terminal=True)
            if step.tool == 'FINAL_RESPONSE' and step.args.get('copy_to_clipboard'):
                return self.scope['ToolResult'](False, error='Clipboard outside fixture', terminal=True)
            result = actual(ctx, step)
            self.trace.append({'id': step.id, 'tool': step.tool, 'when': step.when,
                               'skipped': bool((result.evidence or {}).get('condition_skipped')),
                               'ok': result.ok, 'error': result.error})
            return result
        self.agent._execute_step = bounded


def authored_plan():
    def step(index, tool, args, equals=None):
        row = {'id': index, 'goal': '依原始條件執行', 'tool': tool, 'args': args,
               'success_check': '真實觀察或正確條件略過', 'on_failure': 'stop', 'retries': 0}
        if equals is not None:
            row['when'] = {'step_id': 1, 'field': 'exists', 'equals': equals}
        return row
    return {'objective': '若副本已存在則保留，否則讀取來源並建立副本', 'assumptions': [],
            'steps': [step(1, 'PATH_INFO', {'path': '副本.txt'}),
                      step(2, 'FINAL_RESPONSE', {'message': '副本已存在，保持不變'}, True),
                      step(3, 'READ_TEXT_FILE', {'path': '原稿.txt'}, False),
                      step(4, 'WRITE_TEXT_FILE', {'path': '副本.txt', 'content': '{{step:3.file_text}}', 'overwrite': False}, False),
                      step(5, 'READ_TEXT_FILE', {'path': '副本.txt'}, False),
                      step(6, 'FINAL_RESPONSE', {'message': '新副本完成'}, False)],
            'completion_criteria': ['選擇正確分支；存在時不讀來源；不存在時原樣建立並讀回；正確回覆']}

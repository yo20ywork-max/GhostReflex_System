"""Use committed receipts for display; a missing receipt stays an explicit summary."""
import json
import sqlite3
import time
from pathlib import Path


def display_detail(event):
    if event.get('tool') == 'CONDITION_SKIP':
        proof = event.get('evidence') or {}
        condition = proof.get('condition') or event.get('condition') or {}
        actual = proof.get('observed', event.get('observed'))
        return (f"條件不符，已略過此步驟，沒有執行操作。\n"
                f"依據步驟 {condition.get('step_id', '?')} 的 {condition.get('field', '?')}："
                f"觀察值為 {actual}，要求值為 {condition.get('equals', '?')}。")
    def text(value):
        if value is None:
            return ''
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    error, output = event.get('error'), event.get('output')
    if error is not None and output is not None:
        return '錯誤：' + text(error) + '\n\n工具輸出：\n' + text(output)
    return text(error if error is not None else output)


def step_display(event):
    skipped = event.get('tool') == 'CONDITION_SKIP'
    status = ('結果待核對' if event.get('outcome_recorded') is False else
              '條件不符，已略過' if skipped else '工具已回應' if event.get('ok') else '步驟未成功')
    return {'label': f"步驟 {event['step_id']}" + (f" · 第 {event['attempt']} 次" if 'attempt' in event and not skipped else ''),
            'status': status, 'detail': display_detail(event), 'full': not event.get('evidence_summary', False)}


def completed_progress(workspace, event):
    summary = {**event, 'evidence_summary': True}
    try:
        if (not isinstance(event.get('request_id'), str) or type(event.get('step_id')) is not int or
                type(event.get('attempt')) is not int):
            return summary
        path = Path(workspace) / 'workspace_state/execution.sqlite3'
        if not path.is_file():
            return summary
        # This runs on the engine worker after journal.finish, never on the UI
        # thread. A slow/missing/ambiguous receipt must not fail a successful tool.
        deadline = time.monotonic() + 0.25
        connection = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=0.2)
        try:
            connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            rows = connection.execute('SELECT tool,goal,arguments,result FROM attempts WHERE request_id=? AND step_id=? AND attempt=? LIMIT 2',
                                      (event['request_id'], event['step_id'], event['attempt'])).fetchall()
        finally:
            connection.close()
        if len(rows) != 1 or rows[0][3] is None or rows[0][0] != event.get('tool'):
            return summary
        tool, goal, arguments, encoded = rows[0]
        result = json.loads(encoded)
        if not isinstance(result, dict) or type(result.get('ok')) is not bool or result['ok'] != event.get('ok'):
            return summary
        return {**event, **{key: result.get(key) for key in ('ok', 'verified', 'output', 'error', 'terminal', 'evidence')},
                'tool': tool, 'goal': goal, 'args': json.loads(arguments), 'evidence_summary': False}
    except (OSError, sqlite3.Error, ValueError, TypeError):
        return summary

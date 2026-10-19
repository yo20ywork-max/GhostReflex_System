"""Bounded actual-file pipeline; a seeded partial read forces continuation.

All later planning, writes, reads and completion checks are the real runtime.
Only the temporary source, a new destination, and final responses are allowed.
No native input, network, clipboard, shell or outside-workspace actions run.
"""
import argparse
import ast
import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

R = Path(__file__).resolve().parent
ROOT = R.parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(R.parent))
from execute_plan_fixtures import load
from build_product_data import contract
from evaluate_local import request
from task_journal import TaskJournal
from text_reader import uncovered_file_reads


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = R / args.output
    if output.exists():
        raise FileExistsError(output)
    paths = [ROOT/'run_daemon.py', ROOT/'text_reader.py', ROOT/'task_journal.py', R/'execute_plan_fixtures.py', R/'evaluate_local.py', R.parent/'build_product_data.py', Path(__file__)]
    source_at_start = {str(p.relative_to(ROOT)): {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'text': p.read_text(encoding='utf-8-sig')} for p in paths}
    scope, runtime_hash = load('training-contract.json')
    # Load this one additional actual handler without importing desktop hooks.
    tree = ast.parse(source_at_start['run_daemon.py']['text'])
    write_handler = next(n for n in tree.body if getattr(n, 'name', None) == 'tool_write_text_file')
    write_handler.decorator_list = []
    module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), write_handler], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), '<actual write handler>', 'exec'), scope)
    catalog, schema, _, _ = contract(max_plan_steps=8)
    scope['TOOL_REGISTRY'] = {x['name']: SimpleNamespace(parameters=x['parameters'], risk=x['risk'], handler=scope.get('tool_'+x['name'].lower())) for x in catalog}
    model = next(x for x in request('/api/tags')['models'] if x['name'] == args.model)
    options = {'temperature': 0, 'num_ctx': 12288, 'num_predict': 2048, 'repeat_penalty': 1.0}
    calls, trace = [], []
    started = time.monotonic()

    class Gateway:
        def chat_json(self, *, messages, schema, models=None):
            if len(calls) >= 10 or time.monotonic() - started > 240:
                raise RuntimeError('Finite diagnostic inference budget exhausted')
            payload = {'model': args.model, 'messages': messages, 'format': schema, 'stream': False, 'options': options, 'truncate': False, 'shift': False}
            record = {'request': payload}; calls.append(record)
            try:
                response = request('/api/chat', payload)
                record['response'] = response
            except Exception as exc:
                record['error'] = repr(exc)
                raise
            if response.get('done_reason') != 'stop':
                raise ValueError('Incomplete generation')
            return json.loads(response['message']['content']), args.model

    with tempfile.TemporaryDirectory(dir=R, prefix='file-pipeline-') as folder:
        work = Path(folder).resolve()
        if not work.is_relative_to(R.resolve()):
            raise ValueError('Fixture workspace escaped')
        source = work/'工作稿.txt'; destination = work/'副本.txt'
        content = '  台灣製作\t\r\n' + ''.join(f'第{i:02}行原稿。' for i in range(30)) + '\r\n原文字面：{{step:999.output}}\r\n片尾  '
        original = content.encode('utf8'); source.write_bytes(original)
        settings = SimpleNamespace(workspace=work, allow_outside_workspace=False, max_plan_steps=8, default_tool_retries=0, log_prompts=False, max_replans=3, planner_num_ctx=12288, planner_models=(args.model,), review_plans=False)
        journal = TaskJournal(work/'receipt.sqlite3')
        runtime = SimpleNamespace(journal=journal)
        gateway = Gateway()
        planner = scope['Planner'].__new__(scope['Planner'])
        planner.settings=settings; planner.catalog=catalog; planner.schema=schema; planner.hint_engine=None; planner.gateway=gateway
        actual_plan = planner.plan
        first = True

        def plan(*a, **kw):
            nonlocal first
            if first:
                first = False
                return scope['TaskPlan']('讀取後另存並核對', [], [scope['PlanStep'](1, '讀取首段', 'READ_TEXT_FILE', {'path': '工作稿.txt', 'max_chars': 100}, '已取得首段', 'replan', 0)], ['副本原文完整且已讀回核對'], model=args.model)
            return actual_plan(*a, **kw)

        planner.plan = plan
        agent = scope['UniversalAgent'].__new__(scope['UniversalAgent'])
        agent.settings=settings; agent.runtime=runtime; agent.gateway=gateway; agent.planner=planner
        agent.runtime_context=lambda: {'workspace': str(work)}
        agent.print_plan=lambda _: None
        execute = agent._execute_step

        def permitted(ctx, step, resolved):
            if step.tool == 'READ_TEXT_FILE':
                return scope['resolve_user_path'](ctx, resolved['path']) in (source, destination)
            if step.tool == 'WRITE_TEXT_FILE':
                return scope['resolve_user_path'](ctx, resolved['path']) == destination and resolved.get('overwrite', False) is False
            return step.tool in {'FINAL_RESPONSE', 'BLOCKED'} and not resolved.get('copy_to_clipboard', False)

        def bounded(ctx, step):
            if len(trace) >= 16:
                return scope['ToolResult'](False, error='Finite fixture dispatch limit', terminal=True)
            try:
                resolved = scope['resolve_references'](step.args, ctx.step_results, ctx.history)
                if not permitted(ctx, step, resolved):
                    result = scope['ToolResult'](False, error='Action outside isolated file pipeline', terminal=True)
                else:
                    result = execute(ctx, step)
            except Exception as exc:
                result = scope['ToolResult'](False, error=f'Fixture pre-dispatch reference check: {exc}')
            trace.append({'step_id': step.id, 'tool': step.tool, 'args': step.args, 'ok': result.ok, 'error': result.error, 'terminal': result.terminal})
            return result

        agent._execute_step = bounded
        agent._confirm_step = lambda *_: True  # Only permitted fixture paths reach the executor.
        try:
            result = agent.run('完整讀取「工作稿.txt」，不要修改原檔。把完整原文另存為新的「副本.txt」，保留每個字元、空白和換行；寫入後讀回副本核對，確認一致才回覆「已完成」。')
            source_unchanged = source.read_bytes() == original
            output_bytes = destination.read_bytes() if destination.exists() else None
            exact_copy = output_bytes == original
            readback = any(x.get('tool') == 'READ_TEXT_FILE' and x.get('ok') is True and x.get('verified') is True and (x.get('evidence') or {}).get('path') == str(destination) for x in result.history)
            gaps = uncovered_file_reads(result.history)
            artifact_ok = source_unchanged and exact_copy and readback and not gaps
            report = {'status': result.status, 'message': result.message, 'passed': artifact_ok and result.status == 'completed' and result.message == '已完成', 'artifact_ok': artifact_ok, 'source_unchanged': source_unchanged, 'exact_copy': exact_copy, 'verified_readback_observed': readback, 'gaps': gaps, 'false_completion': result.status == 'completed' and not artifact_ok, 'source_text': content, 'destination_text': None if output_bytes is None else output_bytes.decode('utf8', errors='replace'), 'source_sha256': hashlib.sha256(original).hexdigest(), 'destination_sha256': None if output_bytes is None else hashlib.sha256(output_bytes).hexdigest(), 'history': result.history, 'trace': trace, 'calls': calls, 'receipts': journal.read(result.request_id)}
        finally:
            journal.close()
    report.update(model=args.model, model_digest=model['digest'], inference_options=options, seconds=time.monotonic()-started, runtime_normalized_sha256=runtime_hash, source_at_start=source_at_start, source_files_unchanged=all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest() == v['sha256'] for p,v in source_at_start.items()), product_release_approved=False, scope='Known-development real-file pipeline with manually seeded first100-character read; all subsequent planning and completion is model-driven. Not arbitrary long tasks, target hardware, native UI or full product qualification.')
    with output.open('x', encoding='utf8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: report[k] for k in ['model','passed','artifact_ok','status','false_completion','exact_copy','verified_readback_observed','source_files_unchanged','seconds']}), flush=True)


if __name__ == '__main__':
    main()

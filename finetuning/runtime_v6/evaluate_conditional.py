"""Model-authored conditional tasks on real disposable files; development only."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import time

from conditional_flow import ConditionalFixture, ROOT, HERE
from evaluate_development import request
from explicit_reply import install_reply_completion_guard


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if Path(args.output).name != args.output:
        raise ValueError('Output must be filename')
    target = HERE / args.output
    if target.exists():
        raise FileExistsError(target)
    prompt = '先確認「副本.txt」是否存在；若存在，保持所有檔案不變並回覆「副本已存在，保持不變」。只有它不存在時，才讀取「原稿.txt」並原樣建立副本，讀回確認後回覆「新副本完成」。'
    cases = []
    for name, exists, source in [('existing', True, '新原稿\r\n'), ('existing-missing-source', True, None),
                                 ('absent', False, '  原文\t😀𠮷\r\n\r\n'), ('absent-empty', False, '')]:
        initial = {'原稿.txt': source} if source is not None else {}
        if exists:
            initial['副本.txt'] = '其他人的既有版本\r\n'
        expected = dict(initial)
        if not exists:
            expected['副本.txt'] = source
        cases.append(dict(id='v6-conditional-' + name, user_request=prompt, initial_files=initial,
                          expected_files=expected, expected_reply='副本已存在，保持不變' if exists else '新副本完成',
                          destination_existed=exists, write_targets={}))
    paths = [Path(__file__), HERE / 'conditional_flow.py', ROOT / 'run_daemon.py', ROOT / 'step_conditions.py',
             ROOT / 'argument_references.py',
             ROOT / 'path_metadata.py', ROOT / 'completion_verification.py', ROOT / 'text_reader.py', ROOT / 'task_journal.py',
             ROOT / 'explicit_reply.py', ROOT / 'finetuning/build_product_data.py',
             ROOT / 'finetuning/release_v4/file_flow.py', ROOT / 'finetuning/release_v4/evaluate_development.py',
             ROOT / 'finetuning/release_v3/execute_plan_fixtures.py']
    hashes = {str(p.relative_to(ROOT)): sha(p) for p in paths}
    model = next(m for m in request('/api/tags')['models'] if m['name'] == args.model)
    options = {'temperature': 0, 'num_ctx': 12288, 'num_predict': 2048, 'repeat_penalty': 1.0}
    with target.with_suffix('.manifest.json').open('x', encoding='utf8') as output:
        json.dump(dict(started_utc=datetime.now(timezone.utc).isoformat(), model=model, sources=hashes, cases=cases,
                       options=options, scope='New four-case conditional capability development; actual files, model plans and checker. No expected answers/files sent to model. Not original file8 or native release score.',
                       explicit_reply_guard=True, release_approved=False), output, ensure_ascii=False, indent=2)
    rows = []
    with target.open('x', encoding='utf8') as output:
        for case in cases:
            calls, began = [], time.monotonic()
            class Gateway:
                def chat_json(self, *, messages, schema, models=None):
                    if len(calls) >= 12 or time.monotonic() - began > 300:
                        raise RuntimeError('Development inference budget exhausted')
                    body = dict(model=args.model, messages=messages, format=schema, options=options,
                                stream=False, truncate=False, shift=False)
                    record = dict(request=body)
                    calls.append(record)
                    try:
                        result = request('/api/chat', body)
                        record['response'] = result
                        if result.get('done') is not True or result.get('done_reason') != 'stop':
                            raise ValueError('Incomplete model generation')
                        return json.loads(result['message']['content']), args.model
                    except Exception as exc:
                        record['error'] = str(exc)
                        raise
            gateway = Gateway()
            with tempfile.TemporaryDirectory(dir=HERE, prefix='.model-conditional-') as folder:
                fixture = ConditionalFixture(case, folder, args.model, gateway)
                try:
                    install_reply_completion_guard(fixture.scope['Planner'])
                    result, receipts, _ = fixture.run(args.model, gateway)
                    actual = {str(p.relative_to(fixture.work)): p.read_bytes() for p in fixture.work.rglob('*') if p.is_file()}
                    expected = {k: v.encode('utf8') for k, v in case['expected_files'].items()}
                    issues = []
                    if actual != expected:
                        issues.append('Final file set/bytes differ from full original requirement')
                    if result.message != case['expected_reply']:
                        issues.append('Required branch reply missing or wrong')
                    reads = [r for r in receipts if r['tool'] == 'READ_TEXT_FILE']
                    source_reads = [r for r in reads if Path(r['arguments']['path']).name == '原稿.txt']
                    if case['destination_existed']:
                        if source_reads:
                            issues.append('Forbidden source read was dispatched, regardless of success')
                        if any(r['tool'] == 'WRITE_TEXT_FILE' for r in receipts):
                            issues.append('Forbidden write was dispatched, regardless of success')
                    else:
                        writes = [r for r in receipts if r['tool'] == 'WRITE_TEXT_FILE' and (r['result'] or {}).get('ok')]
                        readbacks = [r for r in reads if Path(r['arguments']['path']).name == '副本.txt' and (r['result'] or {}).get('ok')]
                        if not source_reads or not writes or not readbacks or receipts.index(readbacks[-1]) <= receipts.index(writes[-1]):
                            issues.append('Missing actual source-read/write/post-write-read order')
                    row = dict(id=case['id'], status=result.status, message=result.message, issues=issues,
                               passed=result.status == 'completed' and not issues,
                               false_completion=result.status == 'completed' and bool(issues),
                               history=result.history, receipts=receipts, trace=fixture.trace,
                               file_sha256={k: hashlib.sha256(v).hexdigest() for k, v in actual.items()}, calls=calls,
                               seconds=time.monotonic() - began)
                except Exception as exc:
                    row = dict(id=case['id'], passed=False, false_completion=False, evaluation_error=str(exc),
                               calls=calls, trace=fixture.trace, seconds=time.monotonic() - began)
                finally:
                    fixture.close()
            rows.append(row)
            output.write(json.dumps(row, ensure_ascii=False) + '\n')
            output.flush()
            print(json.dumps({k: v for k, v in row.items() if k in ('id', 'status', 'passed', 'false_completion', 'issues', 'evaluation_error', 'seconds')}, ensure_ascii=False), flush=True)
    end = next(m for m in request('/api/tags')['models'] if m['name'] == args.model)
    stable = all(sha(ROOT / p) == h for p, h in hashes.items())
    summary = dict(cases=len(rows), passed=sum(r['passed'] for r in rows), false_completions=sum(r['false_completion'] for r in rows),
                   evaluation_errors=sum('evaluation_error' in r for r in rows), sources_unchanged=stable,
                   model_unchanged=model['digest'] == end['digest'], output_sha256=sha(target), release_approved=False)
    with target.with_suffix('.summary.json').open('x', encoding='utf8') as output:
        json.dump(summary, output, indent=2)
    print(json.dumps(summary), flush=True)
    if not stable or model['digest'] != end['digest']:
        raise RuntimeError('Mixed sources/model')


if __name__ == '__main__':
    main()

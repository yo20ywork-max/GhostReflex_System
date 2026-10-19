"""Known development replay through the revised Planner; no user actions."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = HERE.parent / 'release_v4'
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(OLD))
from file_flow import runtime, cases as file_cases
from evaluate_development import inputs, request
from completion_delivery import project_delivery_messages
from completion_verification import verify_with_retry, VerificationUnavailable


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default='qwen3.5:4b')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if Path(args.output).name != args.output:
        raise ValueError('Output must be a file name')
    target = HERE / args.output
    if target.exists():
        raise FileExistsError(target)
    dev, _, _, locked = inputs()
    cases = []
    paths = [Path(__file__), ROOT / 'run_daemon.py', ROOT / 'completion_verification.py',
             ROOT / 'completion_observations.py', ROOT / 'completion_delivery.py', ROOT / 'text_reader.py',
             OLD / 'file_flow.py', OLD / 'evaluate_development.py', OLD / 'FILE_CONDITIONAL_SCOPE_REVIEW.json']
    for row in dev:
        if row['category'] == 'completion':
            p = json.loads(row['prompt'])
            cases.append(dict(group='completion32', id=row['id'], prompt=p['user_request'],
                              history=p['observed_history'], expected=row['oracle']['complete']))
    file_data = {row['id']: row for row in file_cases()}
    for stem, group in [('epoch3-file-development-v1', 'file8'),
                        ('epoch2-copy-extension-v1', 'copy2'),
                        ('epoch3-file-reply-guard-v1', 'file8_guard')]:
        source = OLD / (stem + '.jsonl')
        summary = source.with_suffix('.summary.json')
        manifest = source.with_suffix('.manifest.json')
        paths.extend([source, summary, manifest])
        marker = json.loads(summary.read_text(encoding='utf8'))
        count = 2 if group == 'copy2' else 8
        if marker['cases'] != count or marker['evaluation_errors']:
            raise ValueError('Incomplete original observations')
        if marker.get('output_sha256') and sha(source) != marker['output_sha256']:
            raise ValueError('Changed original observations')
        if not marker.get('source_files_unchanged', marker.get('sources_unchanged')):
            raise ValueError('Mixed original observation sources')
        if not marker.get('model_tag_digest_unchanged', marker.get('model_digest_unchanged')):
            raise ValueError('Mixed original observation model')
        data = file_data if group != 'copy2' else {r['id']: r for r in json.loads(manifest.read_text(encoding='utf8'))['cases']}
        rows = [json.loads(x) for x in source.read_text(encoding='utf8').splitlines()]
        if len(rows) != count or {r['id'] for r in rows} != set(data):
            raise ValueError('Missing observations')
        for row in rows:
            original = row['evidence_ok'] and row['response_ok']
            # Existing destination: original user forbids source reads. The old
            # oracle omitted this condition; preserve both labels explicitly.
            scope_failure = group.startswith('file8') and row['id'] == 'v4-file-06'
            cases.append(dict(group=group, id=row['id'], prompt=data[row['id']]['user_request'],
                              history=row['history'], expected=original and not scope_failure,
                              original_expected=original))
    full = OLD / 'epoch3-qwen35-delivery-full12-v1.json'
    paths.append(full)
    source = json.loads(full.read_text(encoding='utf8'))
    if sha(full) != 'b12ce070aebbf5d0c3838bc0e0d5e89f32cbe5d997274333fc6636346eb686f4':
        raise ValueError('Changed terminal full12 source')
    for row in source['records']:
        if row['id'].startswith('v2-dev-filled-continue-'):
            call = next(c for c in row['model_calls'] if 'complete' in c['request']['format']['properties'])
            p = json.loads(call['request']['messages'][-1]['content'])
            cases.append(dict(group='preview3', id=row['id'], prompt=p['user_request'],
                              history=p['observed_history'], expected=True))
    if len(cases) != 53:
        raise ValueError('Expected 53 known cases')
    paths.extend(OLD / name for name in locked)
    hashes = {str(p.relative_to(ROOT)): sha(p) for p in paths}
    model = next(m for m in request('/api/tags')['models'] if m['name'] == args.model)
    scope, _, _ = runtime()
    options = dict(temperature=0, num_ctx=12288, num_predict=1024, repeat_penalty=1.0, presence_penalty=0)
    with target.with_suffix('.manifest.json').open('x', encoding='utf8') as stream:
        json.dump(dict(model=model, sources=hashes, cases=[{k: v for k, v in c.items() if k not in ('history', 'prompt')} for c in cases],
                       options=options, scope='Revised runtime plus diagnostic delivery/checker role. Saved known observations; no task execution, default switch or blind holdout.',
                       release_approved=False), stream, ensure_ascii=False, indent=2)
    records = []
    with target.open('x', encoding='utf8') as output:
        for case in cases:
            calls = []
            began = time.monotonic()
            class Gateway:
                def chat_json(self, *, messages, schema, models=None):
                    projected, removed = project_delivery_messages(messages)
                    body = dict(model=args.model, messages=projected, format=schema, options=options,
                                stream=False, truncate=False, shift=False, think=False)
                    call = dict(request=body, removed_planned_goals=removed)
                    calls.append(call)
                    try:
                        out = request('/api/chat', body)
                        call['response'] = out
                        if out.get('done') is not True or out.get('done_reason') != 'stop':
                            raise ValueError('Incomplete generation')
                        return json.loads(out['message']['content']), args.model
                    except Exception as exc:
                        call['error'] = str(exc)
                        raise
            planner = scope['Planner'].__new__(scope['Planner'])
            planner.settings = SimpleNamespace(planner_num_ctx=12288)
            planner.gateway = Gateway()
            try:
                complete, reason = verify_with_retry(planner.assess_completion, case['prompt'], case['history'])
                valid = True
            except VerificationUnavailable as exc:
                complete, reason, valid = None, str(exc), False
            row = {k: v for k, v in case.items() if k not in ('history', 'prompt')}
            row.update(complete=complete, reason=reason, valid=valid,
                       correct=valid and complete == case['expected'], calls=calls, seconds=time.monotonic() - began)
            output.write(json.dumps(row, ensure_ascii=False) + '\n')
            output.flush()
            records.append(row)
            print(json.dumps({k: v for k, v in row.items() if k not in ('reason', 'calls')}, ensure_ascii=False), flush=True)
    end = next(m for m in request('/api/tags')['models'] if m['name'] == args.model)
    stable = all(sha(ROOT / p) == h for p, h in hashes.items())
    def stats(rows):
        return dict(rows=len(rows), correct=sum(r['correct'] for r in rows), invalid=sum(not r['valid'] for r in rows),
                    false_completion=sum(r['complete'] is True and not r['expected'] for r in rows),
                    false_incomplete=sum(r['complete'] is False and r['expected'] for r in rows))
    summary = dict(**stats(records), groups={g: stats([r for r in records if r['group'] == g]) for g in sorted({r['group'] for r in records})},
                   sources_unchanged=stable, model_unchanged=end['digest'] == model['digest'], output_sha256=sha(target), release_approved=False)
    with target.with_suffix('.summary.json').open('x', encoding='utf8') as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2)
    print(json.dumps(summary), flush=True)
    if not stable or model['digest'] != end['digest']:
        raise RuntimeError('Mixed sources/model')


if __name__ == '__main__':
    main()

"""Compare original checker and separated file checks on identical saved tasks."""
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import time

from evaluate_development import request
from model_context import dumps, unpack

R = Path(__file__).resolve().parent
ROOT = R.parents[1]
P = R / 'runtime-candidate/file_completion_views.py'
spec = importlib.util.spec_from_file_location('file_completion_views_replay', P)
views = importlib.util.module_from_spec(spec)
spec.loader.exec_module(views)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def decode(text):
    value = json.loads(text)
    return unpack(value) if 'shared_context_text' in value else value


def main():
    target = R / 'FILE_COMPLETION_VIEWS_V1.jsonl'
    assert not target.exists() and not target.with_suffix('.run.json').exists()
    old = R / 'ARTIFACT_EVIDENCE_REPLAY_V1.jsonl'
    old_raw = old.with_suffix('.raw.jsonl')
    original_rows = [json.loads(l) for l in old.read_text(encoding='utf8').splitlines()]
    raw_rows = [json.loads(l) for l in old_raw.read_text(encoding='utf8').splitlines()]
    cases = [r for r in original_rows if r['mode'] == 'artifact_evidence']
    inputs = {r['case']: r['request'] for r in raw_rows if r['mode'] == 'baseline'}
    name = inputs[cases[0]['case']]['model']
    model = next(m for m in request('/api/tags')['models'] if m['name'] == name)
    assert model['digest'] == '1ce8866b022460b87b876994991f13c695ad3b35ee887b23c962602df953fe81'
    sources = {str(p): sha(p) for p in [Path(__file__), P, old, old_raw,
        P.with_name('artifact_evidence.py'), P.with_name('artifact_intent_contract_v2.py'),
        P.with_name('artifact_intent_contract.py'), P.with_name('exact_text_relation.py'),
        ROOT / 'run_daemon.py', ROOT / 'model_context.py', ROOT / 'model_json.py', ROOT / 'text_reader.py',
        ROOT / 'finetuning/release_v4/evaluate_development.py']}
    with target.with_suffix('.run.json').open('x', encoding='utf8') as f:
        json.dump({'started_utc': datetime.now(timezone.utc).isoformat(), 'sources': sources, 'model': model,
                   'reuses_actual_model_artifact_compilations': True, 'expected_labels_not_sent_to_model': True,
                   'original_requests_and_history_unchanged': True,
                   'candidate_changes': 'Separate semantic content, operation metadata and final response checks; AND roles plus exact host constraints. Baseline unchanged.',
                   'candidate_installed': False, 'actions_executed': False, 'release_approved': False}, f, indent=2)
    results = []
    with target.open('x', encoding='utf8') as out, target.with_suffix('.raw.jsonl').open('x', encoding='utf8') as raw:
        def chat(case, mode, payload):
            begin = time.monotonic()
            response = request('/api/chat', payload)
            elapsed = time.monotonic() - begin
            raw.write(json.dumps({'case': case, 'mode': mode, 'request': payload, 'response': response, 'seconds': elapsed}, ensure_ascii=False) + '\n')
            raw.flush()
            if response.get('done') is not True or response.get('done_reason') != 'stop':
                raise ValueError('Incomplete response cannot be a verdict')
            return json.loads(response['message']['content']), elapsed

        for index, case in enumerate(cases):
            label, expected = case['case'], case['expected_complete']
            baseline = inputs[label]
            context = decode(baseline['messages'][1]['content'])
            prepared = views.build(case['compilation']['value'], context['user_request'], context['observed_history'])
            modes = ['baseline', 'separated_views'] if index % 2 == 0 else ['separated_views', 'baseline']
            for mode in modes:
                record = {'case': label, 'mode': mode, 'expected_complete': expected, 'valid': False, 'correct': False}
                try:
                    if mode == 'baseline':
                        verdict, elapsed = chat(label, mode, baseline)
                        assert type(verdict['complete']) is bool and isinstance(verdict['reason'], str)
                        record.update(complete=verdict['complete'], reason=verdict['reason'], seconds=elapsed)
                    else:
                        roles = ['content'] if prepared['content']['semantic_artifacts'] else []
                        roles += ['operations', 'delivery']
                        verdicts, elapsed = {}, 0
                        for role in roles:
                            payload = copy.deepcopy(baseline)
                            payload['messages'] = [{'role': 'system', 'content': views.SYSTEMS[role]},
                                                   {'role': 'user', 'content': dumps(prepared[role])}]
                            payload['format'] = views.SCHEMA
                            verdict, duration = chat(label, role, payload)
                            verdicts[role] = verdict
                            elapsed += duration
                            print(json.dumps({'case': label, 'role': role, 'verdict': verdict, 'seconds': duration}, ensure_ascii=False), flush=True)
                        combined = views.aggregate(prepared, verdicts)
                        record.update(complete=combined['complete'], aggregate=combined, role_verdicts=verdicts, views=prepared, seconds=elapsed)
                    record.update(valid=True, correct=record['complete'] is expected)
                except Exception as exc:
                    record['error'] = str(exc)
                results.append(record)
                out.write(json.dumps(record, ensure_ascii=False) + '\n'); out.flush()
                print(json.dumps({k: v for k, v in record.items() if k not in ['views', 'role_verdicts']}, ensure_ascii=False), flush=True)
    stable = all(sha(Path(p)) == h for p, h in sources.items())
    stable = stable and next(m for m in request('/api/tags')['models'] if m['name'] == name)['digest'] == model['digest']
    summary = {'rows': len(results), 'sources_and_tag_unchanged': stable, 'results_sha256': sha(target),
        'raw_sha256': sha(target.with_suffix('.raw.jsonl')),
        'modes': {mode: {'total': sum(r['mode'] == mode for r in results),
                         'correct': sum(r['mode'] == mode and r['correct'] for r in results),
                         'false_positives': sum(r['mode'] == mode and r.get('complete') is True and not r['expected_complete'] for r in results)}
                  for mode in ['baseline', 'separated_views']},
        'whole_reason_review_required': True, 'candidate_installed': False, 'release_approved': False}
    with target.with_suffix('.summary.json').open('x', encoding='utf8') as f:
        json.dump(summary, f, indent=2)
    assert stable
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()

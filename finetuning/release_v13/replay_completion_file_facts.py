"""Paired real-model completion checks with/without derived observation facts."""
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import time

from evaluate_development import request
from model_context import unpack, dumps

R = Path(__file__).resolve().parent
ROOT = R.parents[1]
CANDIDATE = R / 'runtime-candidate/completion_file_facts.py'
spec = importlib.util.spec_from_file_location('completion_file_facts_candidate', CANDIDATE)
facts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(facts)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def decode(text):
    value = json.loads(text)
    return unpack(value) if 'shared_context_text' in value else value


def main():
    assert (R / 'evaluation-runtime-v8/epoch3-file8-v1.summary.json').exists()
    target = R / 'COMPLETION_FILE_FACTS_REPLAY.jsonl'
    assert not target.exists() and not target.with_suffix('.run.json').exists()
    selections = [
        ('copy_correct', 'evaluation-runtime-v8/epoch3-file8-v1.jsonl', 'v4-file-01', True),
        ('merge_correct', 'evaluation-runtime-v8/epoch3-file8-v1.jsonl', 'v4-file-04', True),
        ('empty_copy_correct', 'evaluation-runtime-v8/epoch3-file8-v1.jsonl', 'v4-file-05', True),
        ('merge_altered', 'evaluation-runtime-v5/epoch3-file8-v1.jsonl', 'v4-file-04', False),
        ('creative_status_instead_of_welcome', 'evaluation-runtime-v7/epoch3-generation-contrasts-v1.jsonl', 'creative', False),
        ('summary_invented_facts', 'evaluation-runtime-v6/epoch3-generation-contrasts-v1.jsonl', 'summary', False),
    ]
    inputs = []
    for label, filename, case_id, expected in selections:
        path = R / filename
        row = next(json.loads(line) for line in path.read_text(encoding='utf8').splitlines() if json.loads(line)['id'] == case_id)
        call = next(c for c in row['calls'] if 'complete' in c['request'].get('format', {}).get('properties', {}))
        base = call['request']
        assert [m['role'] for m in base['messages']] == ['system', 'user']
        context = decode(base['messages'][1]['content'])
        candidate = copy.deepcopy(base)
        augmented = {**context, 'derived_file_observation_facts': facts.build(context['verified_file_contents'], context['observed_history'])}
        candidate['messages'][1]['content'] = dumps(augmented)
        restored = decode(candidate['messages'][1]['content'])
        del restored['derived_file_observation_facts']
        assert restored == context
        inputs.append((label, expected, base, candidate, call.get('response')))
    model_name = inputs[0][2]['model']
    model = next(m for m in request('/api/tags')['models'] if m['name'] == model_name)
    assert model['digest'] == '1ce8866b022460b87b876994991f13c695ad3b35ee887b23c962602df953fe81'
    sources = {str(p): sha(p) for p in [Path(__file__), CANDIDATE, ROOT / 'model_context.py', ROOT / 'model_json.py',
               ROOT / 'run_daemon.py', ROOT / 'argument_references.py', *[R / x[1] for x in selections]]}
    run = {'started_utc': datetime.now(timezone.utc).isoformat(), 'model': model, 'sources': sources,
           'candidate_installed': False, 'actions_executed': False, 'expected_labels_sent_to_model': False,
           'original_context_fields_preserved': True, 'system_schema_options_unchanged': True, 'release_approved': False}
    with target.with_suffix('.run.json').open('x', encoding='utf8') as f:
        json.dump(run, f, ensure_ascii=False, indent=2)
    records = []
    with target.open('x', encoding='utf8') as out:
        for case_index, (label, expected, baseline, candidate, old) in enumerate(inputs):
            # Alternate order, preserving two complete paired observations.
            modes = [('baseline', baseline), ('derived_facts', candidate)]
            if case_index % 2:
                modes.reverse()
            for mode, payload in modes:
                began = time.monotonic()
                record = {'case': label, 'mode': mode, 'expected_complete': expected, 'request': payload,
                          'historical_response': old}
                try:
                    response = request('/api/chat', payload)
                    value = json.loads(response['message']['content'])
                    valid = response.get('done') is True and response.get('done_reason') == 'stop' and type(value.get('complete')) is bool
                    record.update(response=response, valid=valid, complete=value.get('complete'), reason=value.get('reason'),
                                  correct=valid and value['complete'] is expected)
                except Exception as exc:
                    record.update(valid=False, correct=False, error=str(exc))
                record['seconds'] = time.monotonic() - began
                records.append(record)
                out.write(json.dumps(record, ensure_ascii=False) + '\n')
                out.flush()
                print(json.dumps({k: v for k, v in record.items() if k not in ('request', 'response', 'historical_response')}, ensure_ascii=False), flush=True)
    stable = all(sha(Path(p)) == digest for p, digest in sources.items())
    stable = stable and next(m for m in request('/api/tags')['models'] if m['name'] == model_name)['digest'] == model['digest']
    summary = {'rows': len(records), 'sources_and_model_unchanged': stable, 'results_sha256': sha(target),
               'modes': {mode: {'total': sum(r['mode'] == mode for r in records),
                                'correct': sum(r['mode'] == mode and r['correct'] for r in records),
                                'false_positives': sum(r['mode'] == mode and r.get('complete') is True and not r['expected_complete'] for r in records)}
                         for mode in ('baseline', 'derived_facts')},
               'semantic_reason_review_required': True, 'candidate_installed': False, 'release_approved': False}
    with target.with_suffix('.summary.json').open('x', encoding='utf8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    assert stable
    print(json.dumps(summary))


if __name__ == '__main__':
    main()

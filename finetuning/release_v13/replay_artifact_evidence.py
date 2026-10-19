"""Paired completion replay, with outcome-blind artifact compilation and facts."""
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
P = R / 'runtime-candidate/artifact_evidence.py'
spec = importlib.util.spec_from_file_location('artifact_evidence', P)
evidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def decode(text):
    value = json.loads(text)
    return unpack(value) if 'shared_context_text' in value else value


def selections():
    return [
        ('copy_correct', 'evaluation-runtime-v8/epoch3-file8-v1.jsonl', 'v4-file-01', True),
        ('merge_correct', 'evaluation-runtime-v8/epoch3-file8-v1.jsonl', 'v4-file-04', True),
        ('empty_copy_correct', 'evaluation-runtime-v8/epoch3-file8-v1.jsonl', 'v4-file-05', True),
        ('merge_altered', 'evaluation-runtime-v5/epoch3-file8-v1.jsonl', 'v4-file-04', False),
        ('creative_status_instead_of_welcome', 'evaluation-runtime-v7/epoch3-generation-contrasts-v1.jsonl', 'creative', False),
        ('summary_invented_facts', 'evaluation-runtime-v6/epoch3-generation-contrasts-v1.jsonl', 'summary', False),
        ('v9_empty_copy_correct', 'evaluation-runtime-v9/epoch3-file8-v1.jsonl', 'v4-file-05', True),
    ]


def main():
    target = R / 'ARTIFACT_EVIDENCE_REPLAY_V1.jsonl'
    assert not target.exists() and not target.with_suffix('.run.json').exists()
    inputs = []
    for label, filename, ident, expected in selections():
        row = next(json.loads(l) for l in (R / filename).read_text(encoding='utf8').splitlines() if json.loads(l)['id'] == ident)
        call = next(c for c in row['calls'] if 'complete' in c['request'].get('format', {}).get('properties', {}))
        inputs.append((label, expected, call['request']))
    # Counterfactual removes only actual reply evidence; all file evidence intact.
    missing_reply = copy.deepcopy(inputs[-1][2])
    context = decode(missing_reply['messages'][1]['content'])
    context['observed_history'] = [h for h in context['observed_history'] if h['tool'] != 'FINAL_RESPONSE']
    missing_reply['messages'][1]['content'] = dumps(context)
    inputs.append(('v9_empty_copy_without_reply', False, missing_reply))
    sources = {str(p): sha(p) for p in [Path(__file__), P,
        P.with_name('artifact_intent_contract_v2.py'), P.with_name('artifact_intent_contract.py'),
        P.with_name('exact_text_relation.py'), ROOT / 'text_reader.py', ROOT / 'verified_copy.py',
        ROOT / 'model_context.py', ROOT / 'model_json.py', ROOT / 'run_daemon.py',
        ROOT / 'finetuning/release_v4/evaluate_development.py',
        *[R / filename for _, filename, _, _ in selections()]]}
    name = inputs[0][2]['model']
    model = next(m for m in request('/api/tags')['models'] if m['name'] == name)
    assert model['digest'] == '1ce8866b022460b87b876994991f13c695ad3b35ee887b23c962602df953fe81'
    with target.with_suffix('.run.json').open('x', encoding='utf8') as f:
        json.dump({'started_utc': datetime.now(timezone.utc).isoformat(), 'sources': sources, 'model': model,
                   'expected_labels_not_sent_to_model': True, 'compiler_sees_only_original_request_and_path_catalog': True,
                   'completion_system_schema_options_unchanged': True, 'seven_historical_cases_plus_one_removed_reply_counterfactual': True,
                   'candidate_installed': False, 'actions_executed': False, 'release_approved': False}, f, indent=2)
    results = []
    with target.open('x', encoding='utf8') as out, target.with_suffix('.raw.jsonl').open('x', encoding='utf8') as raw:
        def chat(label, mode, payload):
            began = time.monotonic()
            response = request('/api/chat', payload)
            raw.write(json.dumps({'case': label, 'mode': mode, 'request': payload, 'response': response}, ensure_ascii=False) + '\n')
            raw.flush()  # Retain every response before any JSON or semantic check.
            if response.get('done') is not True or response.get('done_reason') != 'stop':
                raise ValueError('Incomplete model response; cannot treat as a semantic verdict')
            return json.loads(response['message']['content']), time.monotonic() - began

        for index, (label, expected, baseline) in enumerate(inputs):
            context = decode(baseline['messages'][1]['content'])
            catalog = evidence.catalog_from_history(context['observed_history'])
            compile_payload = {'model': name, 'messages': [
                {'role': 'system', 'content': evidence.intent.SYSTEM},
                {'role': 'user', 'content': dumps({'user_request': context['user_request'], 'files': catalog})}],
                'format': evidence.intent.schema(catalog), 'stream': False, 'truncate': False, 'shift': False,
                'options': {'temperature': 0, 'num_ctx': 12288, 'num_predict': 2048, 'repeat_penalty': 1.0}}
            try:
                value, compile_seconds = chat(label, 'compile', compile_payload)
                facts = evidence.build(value, context['user_request'], context['observed_history'])
                compiled = {'value': value, 'facts': facts, 'seconds': compile_seconds}
            except Exception as exc:
                compiled = {'error': str(exc)}
            candidate = copy.deepcopy(baseline)
            if 'facts' in compiled:
                candidate['messages'][1]['content'] = dumps({**context, 'artifact_evidence': compiled['facts']})
                restored = decode(candidate['messages'][1]['content'])
                del restored['artifact_evidence']
                assert restored == context
            modes = [('baseline', baseline), ('artifact_evidence', candidate)]
            if index % 2:
                modes.reverse()
            for mode, payload in modes:
                record = {'case': label, 'mode': mode, 'expected_complete': expected,
                          'compilation': compiled, 'valid': False, 'correct': False}
                try:
                    if mode == 'artifact_evidence' and 'facts' not in compiled:
                        raise ValueError('Artifact compilation unavailable; no candidate verdict')
                    value, seconds = chat(label, mode, payload)
                    if not isinstance(value, dict) or type(value.get('complete')) is not bool or not isinstance(value.get('reason'), str):
                        raise ValueError('Invalid completion response')
                    record.update(valid=True, complete=value['complete'], reason=value['reason'],
                                  correct=value['complete'] is expected, seconds=seconds)
                except Exception as exc:
                    record['error'] = str(exc)
                results.append(record)
                out.write(json.dumps(record, ensure_ascii=False) + '\n'); out.flush()
                print(json.dumps({k: v for k, v in record.items() if k != 'compilation'}, ensure_ascii=False), flush=True)
    stable = all(sha(Path(p)) == h for p, h in sources.items())
    stable = stable and next(m for m in request('/api/tags')['models'] if m['name'] == name)['digest'] == model['digest']
    summary = {'rows': len(results), 'sources_and_tag_unchanged': stable, 'results_sha256': sha(target),
               'raw_sha256': sha(target.with_suffix('.raw.jsonl')),
               'modes': {mode: {'total': sum(r['mode'] == mode for r in results),
                                'correct': sum(r['mode'] == mode and r['correct'] for r in results),
                                'false_positives': sum(r['mode'] == mode and r.get('complete') is True and not r['expected_complete'] for r in results)}
                         for mode in ('baseline', 'artifact_evidence')},
               'semantic_compilation_and_reason_review_required': True,
               'candidate_installed': False, 'release_approved': False}
    with target.with_suffix('.summary.json').open('x', encoding='utf8') as f:
        json.dump(summary, f, indent=2)
    assert stable
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()

"""Classify every losslessly segmented original request unit; no outcome inputs."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import time

from evaluate_development import request
from model_context import dumps

R = Path(__file__).resolve().parent


def load(name, p):
    spec = importlib.util.spec_from_file_location(name, p)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


P = R / 'runtime-candidate/request_clause_coverage.py'
clauses = load('clause_coverage_eval', P)
original = load('operation_obligation_inputs', R / 'evaluate_operation_obligations_v1.py')


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    target = R / 'REQUEST_CLAUSE_COVERAGE_V1.jsonl'
    assert not target.exists() and not target.with_suffix('.run.json').exists()
    model_name = 'crossgen-agi-mu:v13-e3-eval-20260907'
    model = next(m for m in request('/api/tags')['models'] if m['name'] == model_name)
    assert model['digest'] == '1ce8866b022460b87b876994991f13c695ad3b35ee887b23c962602df953fe81'
    earlier = json.loads((R / 'OPERATION_OBLIGATIONS_V1.run.json').read_text(encoding='utf8'))
    sources = {**earlier['sources'], **{str(p): sha(p) for p in [Path(__file__), P]}}
    with target.with_suffix('.run.json').open('x', encoding='utf8') as f:
        json.dump({'started_utc': datetime.now(timezone.utc).isoformat(), 'sources': sources, 'model': model,
                   'same24_original_requests': True, 'model_inputs_only_original_request_and_lossless_units': True,
                   'does_not_bind_artifact_targets_or_generate_literal_reply': True,
                   'expected_labels_not_sent_to_model': True, 'candidate_installed': False, 'release_approved': False}, f, indent=2)
    results = []
    with target.open('x', encoding='utf8') as out:
        for case in original.inputs():
            prompt = case['prompt']
            context = {'user_request': prompt, 'clauses': clauses.split(prompt)}
            payload = {'model': model_name, 'messages': [{'role': 'system', 'content': clauses.SYSTEM}, {'role': 'user', 'content': dumps(context)}],
                'format': clauses.schema(prompt), 'stream': False, 'truncate': False, 'shift': False,
                'options': {'temperature': 0, 'num_ctx': 12288, 'num_predict': 2048, 'repeat_penalty': 1.0}}
            record = {'case': case['case'], 'group': case['group'], 'request': payload, 'valid': False, 'selected_labels_correct': False}
            began = time.monotonic()
            try:
                response = request('/api/chat', payload)
                record['response'] = response
                if response.get('done') is not True or response.get('done_reason') != 'stop':
                    raise ValueError('Incomplete response cannot cover request units')
                value = json.loads(response['message']['content'])
                bound = clauses.bind(value, prompt)
                labels = {k for unit in bound['clauses'] for k in unit['kinds']}
                expected = {k: v == 'required' for k, v in case['expected'].items() if k in
                            ['preserve_sources', 'new_destination', 'destination_readback', 'reply_after_readback']}
                expected['other_operation'] = case['expected']['other']
                if case['expected']['reply_mode'] in ('exact', 'not_required'):
                    expected['exact_reply'] = case['expected']['reply_mode'] == 'exact'
                comparisons = {k: {'expected_present': expected_present, 'present': k in labels} for k, expected_present in expected.items()}
                record.update(valid=True, bound=bound, label_presence_checks=comparisons,
                              selected_labels_correct=all(v['expected_present'] == v['present'] for v in comparisons.values()))
            except Exception as exc:
                record['error'] = str(exc)
            record['seconds'] = time.monotonic() - began
            results.append(record)
            out.write(json.dumps(record, ensure_ascii=False) + '\n'); out.flush()
            print(json.dumps({k: v for k, v in record.items() if k not in ['request', 'response', 'bound']}, ensure_ascii=False), flush=True)
    stable = all(sha(Path(p)) == h for p, h in sources.items())
    stable = stable and next(m for m in request('/api/tags')['models'] if m['name'] == model_name)['digest'] == model['digest']
    summary = {'total': len(results), 'valid': sum(r['valid'] for r in results),
        'selected_labels_correct': sum(r['selected_labels_correct'] for r in results),
        'sources_and_tag_unchanged': stable, 'results_sha256': sha(target),
        'per_clause_semantic_review_required': True, 'score_scope': 'Selected label presence across request; not exact label-to-span attribution or whole operation contract accuracy.',
        'candidate_installed': False, 'release_approved': False}
    with target.with_suffix('.summary.json').open('x', encoding='utf8') as f:
        json.dump(summary, f, indent=2)
    assert stable
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()

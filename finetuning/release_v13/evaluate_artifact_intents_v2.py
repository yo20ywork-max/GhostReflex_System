"""Replay identical saved requests after restoring a corrupt content-addressed blob."""
from datetime import datetime, timezone
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import time
from evaluate_development import request

R = Path(__file__).resolve().parent
BLOB = Path.home() / '.ollama/models/blobs/sha256-2963b2e99d2df37f1393f3d8f16fde8cbeca37469620865ee721997b601c643e'
EXPECTED = BLOB.name.removeprefix('sha256-')
BASE = BLOB.with_name('sha256-60e05f2100071479f596b964f89f510f057ce397ea22f2833a0cfe029bfc2463')
CANDIDATE = R / 'runtime-candidate/artifact_intent_contract_v2.py'
spec = importlib.util.spec_from_file_location('artifact_intent_contract', CANDIDATE)
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def main():
    source = R / 'ARTIFACT_INTENT_E3_V1.jsonl'
    target = R / 'ARTIFACT_INTENT_E3_V2.jsonl'
    assert not target.exists() and not target.with_suffix('.run.json').exists()
    rows = [json.loads(l) for l in source.read_text(encoding='utf8').splitlines()]
    new_cases = [
        ('unobserved_concat', '依序把甲.txt、乙.txt全文直接接在一起，存成新的合稿.txt。',
         ['甲.txt', '乙.txt'], [('exact_concat', ['f1', 'f2'], 'unobserved')]),
        ('two_unobserved_artifacts', '將甲.txt原樣備份為備份.txt，另依甲.txt整理三點摘要存成重點.txt。',
         ['甲.txt'], [('exact_copy', ['f1'], 'unobserved'), ('semantic_generation', ['f1'], 'unobserved')]),
        ('repeat_to_unobserved', '將甲.txt完整內容連續重複三次，直接串接存入三份.txt，不加任何文字。',
         ['甲.txt'], [('exact_concat', ['f1', 'f1', 'f1'], 'unobserved')]),
        ('source_free_unobserved', '寫兩句欢迎新鄰居的話，存為迎賓.txt。',
         [], [('semantic_generation', [], 'unobserved')]),
    ]
    for label, prompt, names, expected in new_cases:
        payload = copy.deepcopy(rows[0]['request'])
        catalog = [{'file_id': f'f{i}', 'filename': name, 'request_paths': [name]} for i, name in enumerate(names, 1)]
        payload['messages'][1]['content'] = json.dumps({'user_request': prompt, 'files': catalog}, ensure_ascii=False)
        rows.append({'case': label, 'expected': expected, 'request': payload})
    for row in rows:
        context = json.loads(row['request']['messages'][1]['content'])
        row['request']['format'] = contract.schema(context['files'])
    expected_new_names = {
        'missing_observed_target': ['副本.txt'],
        'unobserved_concat': ['合稿.txt'],
        'two_unobserved_artifacts': ['備份.txt', '重點.txt'],
        'repeat_to_unobserved': ['三份.txt'],
        'source_free_unobserved': ['迎賓.txt'],
    }
    sources = {str(p): sha(p) for p in [Path(__file__), source, CANDIDATE, CANDIDATE.with_name('artifact_intent_contract.py'), BLOB, BASE]}
    assert sources[str(BLOB)] == EXPECTED and sources[str(BASE)] == BASE.name.removeprefix('sha256-')
    model_name = rows[0]['request']['model']
    model = next(m for m in request('/api/tags')['models'] if m['name'] == model_name)
    assert model['digest'] == '1ce8866b022460b87b876994991f13c695ad3b35ee887b23c962602df953fe81'
    with target.with_suffix('.run.json').open('x', encoding='utf8') as f:
        json.dump({'started_utc': datetime.now(timezone.utc).isoformat(), 'sources': sources, 'model': model,
                   'version': request('/api/version'), 'original14_changed_only_schema': True, 'additional_unobserved_destination_cases': 4,
                   'expected_contracts_not_sent_to_model': True, 'candidate_installed': False,
                   'release_approved': False}, f, indent=2)
    results = []
    with target.open('x', encoding='utf8') as out:
        for row in rows:
            assert sha(BLOB) == EXPECTED
            payload = row['request']
            context = json.loads(payload['messages'][1]['content'])
            names = iter(expected_new_names.get(row['case'], []))
            expected = [(k, s, d, next(names) if d == 'unobserved' else None) for k, s, d in row['expected']]
            result = {'case': row['case'], 'expected': expected, 'request': payload}
            began = time.monotonic()
            result['contract_correct'] = False
            try:
                response = request('/api/chat', payload)
                result['response'] = response
                valid = response.get('done') is True and response.get('done_reason') == 'stop'
                result['generation_complete'] = valid
                if not valid:
                    raise ValueError('Incomplete generation; not a semantic verdict')
                value = json.loads(response['message']['content'])
                bound = contract.bind(value, context['user_request'], context['files'])
                actual = [(a['kind'], a['source_file_ids'], a['destination_file_id'],
                           a['destination_name'] if a['destination_file_id'] == 'unobserved' else None) for a in bound['artifacts']]
                result.update(bound=bound, contract_correct=sorted(actual, key=str) == sorted(expected, key=str))
            except Exception as exc:
                result['error'] = str(exc)
            result['seconds'] = time.monotonic() - began
            result['adapter_sha256_after'] = sha(BLOB)
            result['loaded_models_after'] = request('/api/ps')
            results.append(result)
            out.write(json.dumps(result, ensure_ascii=False) + '\n'); out.flush()
            assert result['adapter_sha256_after'] == EXPECTED
            print(json.dumps({k: v for k, v in result.items() if k not in ['request', 'response', 'loaded_models_after']}, ensure_ascii=False), flush=True)
    stable = all(sha(Path(p)) == h for p, h in sources.items())
    stable = stable and next(m for m in request('/api/tags')['models'] if m['name'] == model_name)['digest'] == model['digest']
    with target.with_suffix('.summary.json').open('x', encoding='utf8') as f:
        json.dump({'total': len(results), 'contract_correct': sum(r['contract_correct'] for r in results),
                   'complete_generations': sum(r.get('generation_complete', False) for r in results),
                   'sources_and_actual_model_blobs_unchanged': stable, 'results_sha256': sha(target),
                   'whole_task_completion_inferred': False, 'candidate_installed': False, 'release_approved': False}, f, indent=2)
    assert stable


if __name__ == '__main__':
    main()

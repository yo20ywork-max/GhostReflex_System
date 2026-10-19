"""Replay identical saved requests after restoring a corrupt content-addressed blob."""
from datetime import datetime, timezone
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
CANDIDATE = R / 'runtime-candidate/artifact_intent_contract.py'
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
    target = R / 'ARTIFACT_INTENT_E3_REPAIRED_V1.jsonl'
    assert not target.exists() and not target.with_suffix('.run.json').exists()
    rows = [json.loads(l) for l in source.read_text(encoding='utf8').splitlines()]
    sources = {str(p): sha(p) for p in [Path(__file__), source, CANDIDATE, BLOB, BASE]}
    assert sources[str(BLOB)] == EXPECTED and sources[str(BASE)] == BASE.name.removeprefix('sha256-')
    model_name = rows[0]['request']['model']
    model = next(m for m in request('/api/tags')['models'] if m['name'] == model_name)
    assert model['digest'] == '1ce8866b022460b87b876994991f13c695ad3b35ee887b23c962602df953fe81'
    with target.with_suffix('.run.json').open('x', encoding='utf8') as f:
        json.dump({'started_utc': datetime.now(timezone.utc).isoformat(), 'sources': sources, 'model': model,
                   'version': request('/api/version'), 'requests_identical_to_saved_failed_run': True,
                   'expected_contracts_not_sent_to_model': True, 'candidate_installed': False,
                   'release_approved': False}, f, indent=2)
    results = []
    with target.open('x', encoding='utf8') as out:
        for row in rows:
            assert sha(BLOB) == EXPECTED
            payload = row['request']
            context = json.loads(payload['messages'][1]['content'])
            result = {'case': row['case'], 'expected': row['expected'], 'request': payload}
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
                actual = [(a['kind'], a['source_file_ids'], a['destination_file_id']) for a in bound['artifacts']]
                expected = [(k, s, d) for k, s, d in row['expected']]
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

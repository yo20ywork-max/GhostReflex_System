"""Retain eight authored variants; change only compiler prompt/schema/binding."""
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import time
from evaluate_development import request

R = Path(__file__).resolve().parent
CANDIDATE = R / 'runtime-candidate/blind_text_contract.py'
spec = importlib.util.spec_from_file_location('blind_text_contract', CANDIDATE)
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    source = R / 'BLIND_RELATION_VARIANTS.jsonl'
    summary = json.loads(source.with_suffix('.summary.json').read_text(encoding='utf8'))
    assert summary['results_sha256'] == sha(source) and summary['total'] == 8
    rows = [json.loads(l) for l in source.read_text(encoding='utf8').splitlines()]
    target = R / 'BLIND_CONTRACT_V2_VARIANTS.jsonl'
    assert not target.exists() and not target.with_suffix('.run.json').exists()
    model = next(m for m in request('/api/tags')['models'] if m['name'] == rows[0]['request']['model'])
    assert model['digest'] == '1ce8866b022460b87b876994991f13c695ad3b35ee887b23c962602df953fe81'
    sources = {str(p): sha(p) for p in [Path(__file__), source, CANDIDATE, R.parents[1] / 'run_daemon.py']}
    with target.with_suffix('.run.json').open('x', encoding='utf8') as f:
        json.dump({'started_utc': datetime.now(timezone.utc).isoformat(), 'sources': sources, 'model': model,
                   'changes': ['compiler instruction', 'schema excludes self-reference', 'host binds original request'],
                   'metadata_input_and_inference_options_unchanged': True, 'authored_controls': True,
                   'actions_executed': False, 'candidate_installed': False, 'release_approved': False}, f, ensure_ascii=False, indent=2)
    results = []
    with target.open('x', encoding='utf8') as out:
        for row in rows:
            payload = copy.deepcopy(row['request'])
            context = json.loads(payload['messages'][1]['content'])
            payload['messages'][0]['content'] = contract.SYSTEM
            payload['format'] = contract.schema(context['files'])
            result = {'case': row['case'], 'request': payload, 'expected_sources': row['expected_sources'], 'expected_target': row['expected_target']}
            began = time.monotonic()
            try:
                response = request('/api/chat', payload)
                result['response'] = response
                value = json.loads(response['message']['content'])
                bound = contract.bind(value, context['user_request'], context['files'])
                valid = response.get('done') is True and response.get('done_reason') == 'stop'
                expected = [] if not row['expected_sources'] else [{'source_file_ids': row['expected_sources'], 'destination_file_id': row['expected_target']}]
                result.update(bound=bound, generation_complete=valid, operands_correct=valid and bound['queries'] == expected)
            except Exception as exc:
                result.update(error=str(exc), operands_correct=False)
            result['seconds'] = time.monotonic() - began
            results.append(result)
            out.write(json.dumps(result, ensure_ascii=False) + '\n'); out.flush()
            print(json.dumps({k: v for k, v in result.items() if k not in ('request', 'response')}, ensure_ascii=False), flush=True)
    stable = all(sha(Path(p)) == h for p, h in sources.items())
    stable = stable and next(m for m in request('/api/tags')['models'] if m['name'] == model['name'])['digest'] == model['digest']
    with target.with_suffix('.summary.json').open('x', encoding='utf8') as f:
        json.dump({'total': len(results), 'operands_correct': sum(r['operands_correct'] for r in results),
                   'sources_and_model_unchanged': stable, 'results_sha256': sha(target), 'whole_task_completion_inferred': False,
                   'candidate_installed': False, 'release_approved': False}, f, indent=2)
    assert stable


if __name__ == '__main__':
    main()

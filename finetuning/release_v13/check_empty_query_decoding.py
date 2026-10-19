"""Can configured decoders represent an explicitly requested empty query list?"""
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


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    target = R / 'EMPTY_QUERY_DECODER_CONTROLS.jsonl'
    assert not target.exists() and not target.with_suffix('.run.json').exists()
    tags = request('/api/tags')['models']
    models = [next(m for m in tags if m['digest'] == digest) for digest in [
        'dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364',
        '1ce8866b022460b87b876994991f13c695ad3b35ee887b23c962602df953fe81']]
    typed = contract.schema([{'file_id': 'f1'}, {'file_id': 'f2'}])
    plain = copy.deepcopy(typed)
    plain['properties']['queries']['items'] = {
        'type': 'object', 'properties': {'source_file_ids': {'type': 'array', 'minItems': 1, 'items': {'type': 'string', 'enum': ['f1', 'f2']}},
                                        'destination_file_id': {'type': 'string', 'enum': ['f1', 'f2']}},
        'required': ['source_file_ids', 'destination_file_id'], 'additionalProperties': False}
    sources = {str(p): sha(p) for p in [Path(__file__), CANDIDATE]}
    with target.with_suffix('.run.json').open('x', encoding='utf8') as f:
        json.dump({'started_utc': datetime.now(timezone.utc).isoformat(), 'sources': sources, 'models': models,
                   'server_version': request('/api/version'), 'model_or_product_changes': False, 'release_approved': False}, f, indent=2)
    results = []
    with target.open('x', encoding='utf8') as out:
        for model in models:
            for label, schema in [('typed_oneof', typed), ('plain_items', plain), ('json_only', 'json')]:
                payload = {'model': model['name'], 'messages': [{'role': 'user', 'content': '只輸出這個 JSON，不加其他字或項目：{"queries":[]}'}],
                           'format': schema, 'stream': False, 'options': {'temperature': 0, 'num_ctx': 12288, 'num_predict': 256, 'repeat_penalty': 1.0}}
                result = {'model': model['name'], 'mode': label, 'request': payload}
                began = time.monotonic()
                try:
                    response = request('/api/chat', payload)
                    result['response'] = response
                    value = json.loads(response['message']['content'])
                    result['passed'] = response.get('done_reason') == 'stop' and value == {'queries': []}
                except Exception as exc:
                    result.update(error=str(exc), passed=False)
                result['seconds'] = time.monotonic() - began
                results.append(result)
                out.write(json.dumps(result, ensure_ascii=False) + '\n'); out.flush()
                print(json.dumps({k: v for k, v in result.items() if k not in ('request', 'response')}, ensure_ascii=False), flush=True)
    stable = all(sha(Path(p)) == h for p, h in sources.items())
    final = request('/api/tags')['models']
    stable = stable and all(next(m for m in final if m['name'] == model['name'])['digest'] == model['digest'] for model in models)
    with target.with_suffix('.summary.json').open('x', encoding='utf8') as f:
        json.dump({'total': len(results), 'passed': sum(r['passed'] for r in results), 'sources_and_models_unchanged': stable,
                   'results_sha256': sha(target), 'scope': 'Literal empty-output capability only, not semantic intent accuracy.', 'release_approved': False}, f, indent=2)
    assert stable


if __name__ == '__main__':
    main()

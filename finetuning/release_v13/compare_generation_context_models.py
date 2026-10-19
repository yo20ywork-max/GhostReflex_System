"""Same complete generation inputs on pinned base and E3; no action execution."""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

R = Path(__file__).resolve().parent
ROOT = R.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(R.parent / 'release_v4'))
from evaluate_development import request
from generation_context import prepare
from product_identity import generation_system


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    assert (R / 'evaluation-runtime-v7/epoch3-generation-contrasts-v1.summary.json').exists()
    target = R / 'GENERATION_CONTEXT_MODEL_COMPARISON.jsonl'
    assert not target.exists() and not target.with_suffix('.run.json').exists()
    historical = R / 'evaluation-runtime-v6/epoch3-generation-contrasts-v1.jsonl'
    rows = [json.loads(line) for line in historical.read_text(encoding='utf8').splitlines()]
    cases = {x['id']: x for x in json.loads(historical.with_suffix('.manifest.json').read_text(encoding='utf8'))['cases']}
    models = request('/api/tags')['models']
    base = next(x for x in models if x['digest'] == 'dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364')
    adapted = next(x for x in models if x['name'] == 'crossgen-agi-mu:v13-e3-eval-20260907')
    assert adapted['digest'] == '1ce8866b022460b87b876994991f13c695ad3b35ee887b23c962602df953fe81'
    inputs = []
    for row in rows:
        index = next(i for i, h in enumerate(row['history']) if h['tool'] == 'MODEL_GENERATE')
        args = row['history'][index]['args']
        ctx = SimpleNamespace(original_prompt=cases[row['id']]['request'], history=copy.deepcopy(row['history'][:index]))
        prompt, system = prepare(ctx, args['prompt'], args.get('system', ''))
        inputs.append({'id': row['id'], 'source_case': cases[row['id']],
                       'messages': [{'role': 'system', 'content': generation_system(system)},
                                    {'role': 'user', 'content': prompt}]})
    sources = {str(p.resolve()): sha(p) for p in (Path(__file__), historical, ROOT / 'run_daemon.py',
        ROOT / 'generation_context.py', ROOT / 'model_context.py', ROOT / 'model_json.py', ROOT / 'product_identity.py')}
    run = {'started_utc': datetime.now(timezone.utc).isoformat(), 'sources': sources,
           'models': [base, adapted], 'inputs': inputs, 'executed_actions': False,
           'same_input_and_inference_options': True, 'semantic_review_required': True,
           'default_model_changed': False, 'release_approved': False}
    with target.with_suffix('.run.json').open('x', encoding='utf8') as f:
        json.dump(run, f, ensure_ascii=False, indent=2)
    records = []
    with target.open('x', encoding='utf8') as out:
        for model in (base, adapted):
            for item in inputs:
                payload = {'model': model['name'], 'messages': item['messages'], 'stream': False,
                           'options': {'temperature': 0.2, 'num_ctx': 12288}}
                began = time.monotonic()
                record = {'model': model['name'], 'id': item['id'], 'request': payload}
                try:
                    response = request('/api/chat', payload)
                    record.update(response=response, complete_generation=response.get('done') is True and response.get('done_reason') == 'stop')
                except Exception as exc:
                    record.update(error=repr(exc), complete_generation=False)
                record['seconds'] = time.monotonic() - began
                out.write(json.dumps(record, ensure_ascii=False) + '\n'); out.flush()
                records.append(record)
                print(json.dumps({k: v for k, v in record.items() if k not in ('request', 'response')}, ensure_ascii=False), flush=True)
    final = request('/api/tags')['models']
    assert all(next(x for x in final if x['name'] == m['name'])['digest'] == m['digest'] for m in (base, adapted))
    stable = all(sha(Path(p)) == h for p, h in sources.items())
    with target.with_suffix('.summary.json').open('x', encoding='utf8') as f:
        json.dump({'rows': len(records), 'complete_generations': sum(x['complete_generation'] for x in records),
                   'sources_and_models_unchanged': stable, 'results_sha256': sha(target),
                   'semantic_review_required': True, 'executed_actions': False, 'release_approved': False}, f, indent=2)
    assert stable


if __name__ == '__main__':
    main()

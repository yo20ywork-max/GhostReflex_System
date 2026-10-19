"""Locked v4 development generation only; no tool execution or final holdout access."""
import argparse
import ast
import hashlib
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

R = Path(__file__).resolve().parent


def request(path, payload=None):
    data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    query = urllib.request.Request('http://127.0.0.1:11434' + path, data=data, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(query, timeout=180) as response:
        return json.load(response)


def inputs():
    lock = json.loads((R / 'DATA_LOCK.json').read_text(encoding='utf8'))
    sources = {}
    for name in ('dev.jsonl', 'training-contract.json', 'runtime_source.py'):
        data = (R / name).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != lock['sha256'][name]:
            raise ValueError('Locked input changed: ' + name)
        sources[name] = {'sha256': digest, 'text': data.decode('utf-8-sig')}
    # Extract the literal schema from the frozen runtime instead of importing it.
    completion_schemas = []
    for node in ast.walk(ast.parse(sources['runtime_source.py']['text'])):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'schema' for t in node.targets):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                continue
            if isinstance(value, dict) and set(value.get('properties', {})) == {'reason', 'complete'}:
                completion_schemas.append(value)
    if len(completion_schemas) != 1:
        raise ValueError('Ambiguous runtime completion schema')
    rows = list(map(json.loads, sources['dev.jsonl']['text'].splitlines()))
    if len(rows) != 105 or len({row['id'] for row in rows}) != 105:
        raise ValueError('Unexpected development rows')
    return rows, json.loads(sources['training-contract.json']['text'])['schema'], completion_schemas[0], sources


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    if Path(args.output).name != args.output:
        raise ValueError('Output must be a file name')
    rows, plan_schema, completion_schema, sources = inputs()
    if args.validate_only:
        print(json.dumps({'rows': len(rows), 'locked_sources_valid': True, 'completion_schema_from_frozen_runtime': True}))
        return
    target = R / args.output
    if target.exists():
        raise FileExistsError(target)
    source_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    model = next(m for m in request('/api/tags')['models'] if m['name'] == args.model)
    options = {'temperature': 0, 'num_ctx': 12288, 'num_predict': 1024, 'repeat_penalty': 1.0}
    manifest = {'started_utc': datetime.now(timezone.utc).isoformat(), 'model': model,
                'evaluator_sha256': source_hash, 'evaluator_text': Path(__file__).read_text(encoding='utf8'),
                'sources': sources, 'options': options, 'transport': {'truncate': False, 'shift': False},
                'expected_rows': len(rows), 'release_approved': False, 'scope': 'Development generation; not actual task execution.'}
    with target.with_suffix('.manifest.json').open('x', encoding='utf8') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
    with target.open('x', encoding='utf8') as stream:
        for index, row in enumerate(rows):
            payload = {'model': args.model, 'messages': [{'role': 'system', 'content': row['system']}, {'role': 'user', 'content': row['prompt']}],
                       'stream': False, 'options': options, 'truncate': False, 'shift': False, 'keep_alive': '10m'}
            kind = row['oracle']['type']
            if kind in ('plan', 'completion'):
                payload['format'] = plan_schema if kind == 'plan' else completion_schema
            began = time.monotonic()
            result = request('/api/chat', payload)
            record = {'id': row['id'], 'category': row['category'], 'group': row['group'], 'model': args.model,
                      'model_digest': model['digest'], 'text': result['message']['content'],
                      'completed': result.get('done') is True and result.get('done_reason') == 'stop',
                      'seconds': time.monotonic() - began, 'prompt_sha256': hashlib.sha256((row['system'] + '\n' + row['prompt']).encode()).hexdigest(),
                      'request': payload, 'raw_response': result, 'evaluator_sha256': source_hash}
            stream.write(json.dumps(record, ensure_ascii=False) + '\n')
            stream.flush()
            print(json.dumps({'done': index + 1, 'total': len(rows), 'seconds': record['seconds'], 'completed': record['completed']}), flush=True)
    end_model = next(m for m in request('/api/tags')['models'] if m['name'] == args.model)
    unchanged = all(hashlib.sha256((R / name).read_bytes()).hexdigest() == value['sha256'] for name, value in sources.items())
    stable = unchanged and end_model['digest'] == model['digest'] and hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == source_hash
    with target.with_suffix('.generation-complete.json').open('x', encoding='utf8') as stream:
        json.dump({'rows': len(rows), 'model_and_sources_unchanged': stable, 'release_approved': False,
                   'results_sha256': hashlib.sha256(target.read_bytes()).hexdigest()}, stream, indent=2)
    if not stable:
        raise RuntimeError('Mixed model or evaluator sources; results not valid for comparison')


if __name__ == '__main__':
    main()

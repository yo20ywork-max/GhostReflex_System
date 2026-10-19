"""Bounded, model-only known-case diagnostics; never execute generated actions."""
import hashlib
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
URL = 'http://127.0.0.1:11434/api/'


def api(path, payload=None):
    req = urllib.request.Request(URL + path, data=None if payload is None else json.dumps(payload, ensure_ascii=False).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=240) as response:
        return json.load(response)


def main():
    ids = ['regression-tw-dates', 'regression-election', 'regression-june4', 'regression-kent', 'regression-incomplete', 'regression-asr-negation', 'regression-unknown-count']
    source = ROOT / 'regression.jsonl'
    rows = {r['id']: r for r in map(json.loads, source.read_text(encoding='utf8').splitlines())}
    model = next(m for m in api('tags')['models'] if m['name'] == 'qwen3.5:4b')
    common = {'num_ctx': 12288, 'num_predict': 4096, 'repeat_penalty': 1.0, 'top_k': 20, 'min_p': 0.0, 'presence_penalty': 1.5, 'seed': 20260906}
    profiles = [
        {'name': 'official-nonthinking-general', 'think': False, 'options': dict(common, temperature=0.7, top_p=0.8)},
        {'name': 'official-thinking-general', 'think': True, 'options': dict(common, temperature=1.0, top_p=0.95)},
    ]
    manifest = {'model': model, 'server': api('version'), 'ids': ids, 'profiles': profiles, 'max_requests': 14, 'seed_count': 1, 'known_failure_selected': True, 'release_evaluation': False, 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'limitations': ['Selected known failures plus unknown-count control; not held-out generalization.', 'Sampling follows upstream recommendation but output ceiling 4096 is below upstream 32768; length stops fail.', 'No prompt edits or product brand insertion; one fixed seed does not establish sampling stability.'], 'upstream': 'https://huggingface.co/Qwen/Qwen3.5-4B'}
    out = ROOT / 'qwen35-profile-diagnostic.jsonl'
    with out.with_suffix('.manifest.json').open('x', encoding='utf8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    with out.open('x', encoding='utf8') as f:
        for profile in profiles:
            for id_ in ids:
                row = rows[id_]
                payload = {'model': model['name'], 'messages': [{'role': 'system', 'content': row['system']}, {'role': 'user', 'content': row['prompt']}], 'stream': False, 'think': profile['think'], 'options': profile['options'], 'truncate': False, 'shift': False, 'keep_alive': '10m'}
                record = {'profile': profile['name'], 'id': id_, 'request': payload, 'model_digest': model['digest']}
                started = time.monotonic()
                try:
                    record['response'] = api('chat', payload)
                except Exception as exc:
                    record['error'] = repr(exc)
                record['seconds'] = time.monotonic() - started
                record['residency_after'] = api('ps')
                f.write(json.dumps(record, ensure_ascii=False) + '\n')
                f.flush()
                print(json.dumps({'profile': profile['name'], 'id': id_, 'seconds': record['seconds'], 'done_reason': record.get('response', {}).get('done_reason'), 'error': record.get('error')}), flush=True)


if __name__ == '__main__':
    main()

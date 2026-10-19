"""Two fixed known failures on CPU with the existing model; no downloads."""
import hashlib
import json
import time
from pathlib import Path
from diagnose_qwen35_profiles import api

ROOT = Path(__file__).resolve().parent


def main():
    ids = ['regression-election', 'regression-kent']
    rows = {r['id']: r for r in map(json.loads, (ROOT / 'regression.jsonl').read_text(encoding='utf8').splitlines())}
    model = next(m for m in api('tags')['models'] if m['name'] == 'qwen3.5:4b')
    profile = {'num_ctx': 12288, 'num_predict': 1024, 'temperature': 0, 'repeat_penalty': 1.0, 'presence_penalty': 0.0, 'num_gpu': 0}
    manifest = {'model': model, 'server': api('version'), 'options': profile, 'think': False, 'ids': ids, 'max_requests': 2, 'release_evaluation': False, 'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'limitation': 'Same model and greedy profile, backend-request change only. CPU residency must be checked, not assumed from option.'}
    with (ROOT / 'qwen35-cpu-diagnostic.manifest.json').open('x', encoding='utf8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    with (ROOT / 'qwen35-cpu-diagnostic.jsonl').open('x', encoding='utf8') as f:
        for id_ in ids:
            row = rows[id_]
            payload = {'model': model['name'], 'messages': [{'role': 'system', 'content': row['system']}, {'role': 'user', 'content': row['prompt']}], 'stream': False, 'think': False, 'truncate': False, 'shift': False, 'options': profile, 'keep_alive': '2m'}
            record = {'id': id_, 'request': payload, 'model_digest': model['digest']}
            started = time.monotonic()
            try:
                record['response'] = api('chat', payload)
            except Exception as exc:
                record['error'] = repr(exc)
            record['seconds'] = time.monotonic() - started
            record['residency_after'] = api('ps')
            resident = next((m for m in record['residency_after']['models'] if m['digest'] == model['digest']), {})
            record['cpu_residency_confirmed'] = resident.get('size_vram') == 0
            f.write(json.dumps(record, ensure_ascii=False) + '\n'); f.flush()
            print(json.dumps({'id': id_, 'seconds': record['seconds'], 'cpu_residency_confirmed': record['cpu_residency_confirmed'], 'done_reason': record.get('response', {}).get('done_reason')}), flush=True)


if __name__ == '__main__':
    main()

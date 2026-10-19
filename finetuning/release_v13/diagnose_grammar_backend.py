"""Capture API envelopes with matching server-log byte ranges; no model edits."""
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from evaluate_development import request

R = Path(__file__).resolve().parent
LOG = Path(os.environ['LOCALAPPDATA']) / 'Ollama/server.log'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    target = R / 'GRAMMAR_BACKEND_ISOLATION_V1.jsonl'
    assert not target.exists() and not target.with_suffix('.run.json').exists()
    source = R / 'ARTIFACT_INTENT_E3_V1.jsonl'
    original = json.loads(source.read_text(encoding='utf8').splitlines()[0])['request']
    models = {m['name']: m['digest'] for m in request('/api/tags')['models']}
    inputs = [('e3_original_cold', copy.deepcopy(original))]
    for mode in ['json', 'unconstrained']:
        p = copy.deepcopy(original)
        if mode == 'json':
            p['format'] = 'json'
        else:
            p.pop('format')
        p['options']['num_predict'] = 256
        inputs.append(('e3_' + mode, p))
    p = copy.deepcopy(original)
    p['messages'] = [{'role': 'system', 'content': 'Follow the requested output format.'},
                     {'role': 'user', 'content': 'Return only {"queries":[]}'}]
    p['format'] = 'json'
    p['options']['num_predict'] = 256
    inputs.append(('e3_empty_json', p))
    p = copy.deepcopy(original)
    p['model'] = 'qwen2.5-coder:7b'
    inputs.append(('base_original', p))
    inputs.append(('e3_original_after_base', copy.deepcopy(original)))
    # CPU-only request changes the backend, never the model, schema or prompt.
    p = copy.deepcopy(original)
    p['options']['num_gpu'] = 0
    p['options']['num_predict'] = 256
    inputs.append(('e3_cpu_original_256', p))
    sources = {str(p): sha(p) for p in [Path(__file__), source]}
    with target.with_suffix('.run.json').open('x', encoding='utf8') as f:
        json.dump({'started_utc': datetime.now(timezone.utc).isoformat(), 'sources': sources,
                   'models': {k: models[k] for k in {p['model'] for _, p in inputs}},
                   'version': request('/api/version'), 'initial_loaded_models': request('/api/ps'),
                   'candidate_installed': False, 'release_approved': False}, f, indent=2)
    results = []
    with target.open('x', encoding='utf8') as out:
        for label, payload in inputs:
            began = time.monotonic()
            offset = LOG.stat().st_size
            result = {'case': label, 'request': payload, 'started_utc': datetime.now(timezone.utc).isoformat()}
            try:
                response = request('/api/chat', payload)
                result['response'] = response
                result['complete_generation'] = response.get('done') is True and response.get('done_reason') == 'stop'
            except Exception as exc:
                result['transport_error'] = str(exc)
            result['seconds'] = time.monotonic() - began
            size = LOG.stat().st_size
            result['server_log_range'] = {'path': str(LOG), 'start': offset, 'end': size, 'rotated': size < offset}
            if size >= offset:
                with LOG.open('rb') as f:
                    f.seek(offset)
                    log = f.read(min(size - offset, 1024 * 1024))
                result['server_log_delta'] = log.decode('utf8', errors='replace')
                result['server_log_delta_sha256'] = hashlib.sha256(log).hexdigest()
                result['log_truncated'] = len(log) < size - offset
            result['loaded_models_after'] = request('/api/ps')
            results.append(result)
            out.write(json.dumps(result, ensure_ascii=False) + '\n'); out.flush()
            print(json.dumps({'case': label, 'seconds': result['seconds'], 'response': result.get('response'),
                              'error': result.get('transport_error'),
                              'grammar_exception': 'Unexpected empty grammar stack' in result.get('server_log_delta', '')}, ensure_ascii=False), flush=True)
    stable = all(sha(Path(p)) == h for p, h in sources.items())
    now = {m['name']: m['digest'] for m in request('/api/tags')['models']}
    stable = stable and all(now[p['model']] == models[p['model']] for _, p in inputs)
    with target.with_suffix('.summary.json').open('x', encoding='utf8') as f:
        json.dump({'rows': len(results), 'sources_and_models_unchanged': stable, 'results_sha256': sha(target),
                   'release_approved': False}, f, indent=2)
    assert stable


if __name__ == '__main__':
    main()

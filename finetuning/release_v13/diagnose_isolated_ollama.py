"""Compare backend settings in owned, temporary local servers; reuse disk blobs."""
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.request
import psutil

R = Path(__file__).resolve().parent
EXE = Path(os.environ['LOCALAPPDATA']) / 'Programs/Ollama/ollama.exe'
HOST = 'http://127.0.0.1:11435'


def api(path, payload=None, timeout=180):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf8')
    req = urllib.request.Request(HOST + path, data=data, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    target = R / 'ISOLATED_OLLAMA_BACKEND_V1.jsonl'
    assert not target.exists() and not target.with_suffix('.run.json').exists()
    source = R / 'ARTIFACT_INTENT_E3_V1.jsonl'
    original = json.loads(source.read_text(encoding='utf8').splitlines()[0])['request']
    original['options']['num_predict'] = 256
    empty = copy.deepcopy(original)
    empty['messages'] = [{'role': 'system', 'content': 'Follow the requested output format.'},
                         {'role': 'user', 'content': 'Return only {"queries":[]}'}]
    empty['format'] = 'json'
    configurations = [('flash_q8', {'OLLAMA_FLASH_ATTENTION': '1', 'OLLAMA_KV_CACHE_TYPE': 'q8_0'}),
                      ('flash_f16', {'OLLAMA_FLASH_ATTENTION': '1', 'OLLAMA_KV_CACHE_TYPE': 'f16'}),
                      ('no_flash_f16', {'OLLAMA_FLASH_ATTENTION': '0', 'OLLAMA_KV_CACHE_TYPE': 'f16'})]
    sources = {str(p): sha(p) for p in [Path(__file__), source, EXE]}
    with target.with_suffix('.run.json').open('x', encoding='utf8') as f:
        json.dump({'started_utc': datetime.now(timezone.utc).isoformat(), 'sources': sources,
                   'configurations': configurations, 'host': HOST, 'global_environment_changed': False,
                   'models_modified': False, 'release_approved': False}, f, indent=2)
    results, cleanup = [], []
    with target.open('x', encoding='utf8') as out:
        for label, settings in configurations:
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', 11435))
            env = os.environ.copy()
            env.update(settings)
            env.update(OLLAMA_HOST=HOST, OLLAMA_NO_CLOUD='1', OLLAMA_NOPRUNE='1',
                       OLLAMA_NUM_PARALLEL='1', OLLAMA_MAX_LOADED_MODELS='1',
                       OLLAMA_MODELS=str(Path.home() / '.ollama/models'))
            log_path = R / ('isolated-' + label + '-v1.log')
            with log_path.open('xb') as log:
                proc = subprocess.Popen([str(EXE), 'serve'], env=env, stdout=log, stderr=log,
                                        creationflags=subprocess.CREATE_NO_WINDOW)
                try:
                    deadline = time.monotonic() + 45
                    while True:
                        if proc.poll() is not None:
                            raise RuntimeError('Owned Ollama server exited before readiness')
                        try:
                            version = api('/api/version', timeout=2)
                            break
                        except Exception:
                            if time.monotonic() >= deadline:
                                raise
                            time.sleep(.5)
                    initial = {m['name']: m['digest'] for m in api('/api/tags')['models']}
                    assert initial[original['model']] == '1ce8866b022460b87b876994991f13c695ad3b35ee887b23c962602df953fe81'
                    for case, payload in [('artifact_copy', original), ('literal_empty', empty)]:
                        start = log_path.stat().st_size
                        row = {'profile': label, 'case': case, 'request': payload, 'settings': settings,
                               'version': version, 'server_pid': proc.pid}
                        began = time.monotonic()
                        try:
                            row['response'] = api('/api/chat', payload)
                            r = row['response']
                            row['complete_generation'] = r.get('done') is True and r.get('done_reason') == 'stop'
                        except Exception as exc:
                            row['error'] = str(exc)
                        row['seconds'] = time.monotonic() - began
                        row['loaded_models'] = api('/api/ps')
                        with log_path.open('rb') as f:
                            f.seek(start)
                            delta = f.read(1024 * 1024)
                        row['server_log_delta'] = delta.decode('utf8', errors='replace')
                        results.append(row)
                        out.write(json.dumps(row, ensure_ascii=False) + '\n'); out.flush()
                        print(json.dumps({k: row[k] for k in ['profile', 'case', 'seconds', 'response'] if k in row}, ensure_ascii=False), flush=True)
                    final = {m['name']: m['digest'] for m in api('/api/tags')['models']}
                    assert final[original['model']] == initial[original['model']]
                    api('/api/generate', {'model': original['model'], 'keep_alive': 0})
                finally:
                    # Only this script's process and descendants; never the existing service.
                    try:
                        children = psutil.Process(proc.pid).children(recursive=True)
                    except psutil.NoSuchProcess:
                        children = []
                    owned = children + [psutil.Process(proc.pid)] if proc.poll() is None else children
                    for p in owned:
                        try:
                            p.terminate()
                        except psutil.NoSuchProcess:
                            pass
                    _, alive = psutil.wait_procs(owned, timeout=5)
                    for p in alive:
                        p.kill()
                    _, alive = psutil.wait_procs(alive, timeout=5)
                    proc.wait(timeout=5)
                    cleanup.append({'profile': label, 'owned_pid': proc.pid, 'owned_processes_stopped': not alive,
                                    'log_path': str(log_path), 'log_sha256': sha(log_path)})
                    assert not alive
                    print(json.dumps(cleanup[-1]), flush=True)
    stable = all(sha(Path(p)) == h for p, h in sources.items())
    with target.with_suffix('.summary.json').open('x', encoding='utf8') as f:
        json.dump({'rows': len(results), 'sources_unchanged': stable, 'results_sha256': sha(target),
                   'cleanup': cleanup, 'release_approved': False}, f, indent=2)
    assert stable


if __name__ == '__main__':
    main()

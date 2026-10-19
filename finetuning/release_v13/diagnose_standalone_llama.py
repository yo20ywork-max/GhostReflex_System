"""Independent official CPU/Vulkan runtimes with pinned base/adapter files."""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.error
import urllib.request
import psutil

R = Path(__file__).resolve().parent
HOST = 'http://127.0.0.1:11436'
MODEL = Path.home() / '.ollama/models/blobs/sha256-60e05f2100071479f596b964f89f510f057ce397ea22f2833a0cfe029bfc2463'
ADAPTER = Path.home() / '.ollama/models/blobs/sha256-2963b2e99d2df37f1393f3d8f16fde8cbeca37469620865ee721997b601c643e'


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def api(path, payload=None, timeout=180):
    req = urllib.request.Request(HOST + path, data=None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf8'),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as f:
        return json.load(f)


def main():
    target = R / 'STANDALONE_LLAMA_B10809_V1.jsonl'
    assert not target.exists() and not target.with_suffix('.run.json').exists()
    source = R / 'ARTIFACT_INTENT_E3_V1.jsonl'
    original = json.loads(source.read_text(encoding='utf8').splitlines()[0])['request']
    pairs = [('artifact_copy', original['messages'], original['format']),
             ('literal_empty', [{'role': 'system', 'content': 'Follow the requested output format.'},
                                {'role': 'user', 'content': 'Return only {"queries":[]}'}], {}),
             ('neutral_identity', [{'role': 'system', 'content': '使用台灣繁體中文，依問題直接回答，遵守指定格式。不要捏造資訊。'},
                                   {'role': 'user', 'content': '你叫什麼名字？'}], None)]
    sources = {str(p): sha(p) for p in [Path(__file__), source, MODEL, ADAPTER]}
    assert sources[str(MODEL)] == MODEL.name.removeprefix('sha256-')
    assert sources[str(ADAPTER)] == ADAPTER.name.removeprefix('sha256-')
    with target.with_suffix('.run.json').open('x', encoding='utf8') as f:
        json.dump({'sources': sources, 'release': 'b10809', 'request_scope': 'Explicit ChatML /completion; not token-parity proof with Ollama.',
                   'global_environment_changed': False, 'release_approved': False}, f, indent=2)
    cleanup, results = [], []
    with target.open('x', encoding='utf8') as out:
        for kind in ['cpu', 'vulkan']:
            exe = R / 'backend-tools/b10809' / kind / 'llama-server.exe'
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', 11436))
            command = [str(exe), '-m', str(MODEL), '--lora', str(ADAPTER), '--host', '127.0.0.1', '--port', '11436',
                       '--offline', '--no-webui', '-c', '12288', '-np', '1', '-b', '1024', '-ub', '1024',
                       '-ngl', '0' if kind == 'cpu' else '99', '--flash-attn', 'on', '--cache-type-k', 'q8_0', '--cache-type-v', 'q8_0']
            log_path = R / ('standalone-' + kind + '-b10809-v1.log')
            with log_path.open('xb') as log:
                proc = subprocess.Popen(command, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
                try:
                    deadline = time.monotonic() + 60
                    while True:
                        if proc.poll() is not None:
                            raise RuntimeError('Standalone server exited before readiness')
                        try:
                            api('/health', timeout=2)
                            break
                        except Exception:
                            if time.monotonic() >= deadline:
                                raise
                            time.sleep(.5)
                    for case, messages, schema in pairs:
                        prompt = ''.join('<|im_start|>' + m['role'] + '\n' + m['content'] + '<|im_end|>\n' for m in messages)
                        prompt += '<|im_start|>assistant\n'
                        payload = {'prompt': prompt, 'n_predict': 256, 'temperature': 0, 'top_k': 40, 'top_p': .9,
                                   'repeat_penalty': 1, 'cache_prompt': False, 'stream': False, 'stop': ['<|im_end|>'], 'n_probs': 3}
                        if schema is not None:
                            payload['json_schema'] = schema
                        start = log_path.stat().st_size
                        row = {'backend': kind, 'case': case, 'command': command, 'request': payload}
                        began = time.monotonic()
                        try:
                            row['response'] = api('/completion', payload)
                        except urllib.error.HTTPError as exc:
                            row.update(error=str(exc), error_body=exc.read().decode('utf8', errors='replace'))
                        except Exception as exc:
                            row['error'] = str(exc)
                        row['seconds'] = time.monotonic() - began
                        with log_path.open('rb') as f:
                            f.seek(start)
                            row['server_log_delta'] = f.read(1024 * 1024).decode('utf8', errors='replace')
                        results.append(row)
                        out.write(json.dumps(row, ensure_ascii=False) + '\n'); out.flush()
                        response = row.get('response', {})
                        print(json.dumps({'backend': kind, 'case': case, 'content': response.get('content'),
                                          'stop': response.get('stop'), 'stop_type': response.get('stop_type'),
                                          'seconds': row['seconds'], 'error': row.get('error')}, ensure_ascii=False), flush=True)
                finally:
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
                    cleanup.append({'backend': kind, 'owned_pid': proc.pid, 'owned_processes_stopped': not alive,
                                    'log_sha256': sha(log_path)})
                    assert not alive
                    print(json.dumps(cleanup[-1]), flush=True)
    stable = all(sha(Path(p)) == h for p, h in sources.items())
    with target.with_suffix('.summary.json').open('x', encoding='utf8') as f:
        json.dump({'rows': len(results), 'sources_unchanged': stable, 'results_sha256': sha(target),
                   'cleanup': cleanup, 'release_approved': False}, f, indent=2)
    assert stable


if __name__ == '__main__':
    main()

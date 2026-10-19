"""Bounded local inference measurements; never certifies product release or runs tools."""
import argparse
import hashlib
import json
import shutil
import subprocess
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

R = Path(__file__).resolve().parent
OPTIONS = {'temperature': 0, 'num_ctx': 12288, 'num_predict': 128, 'repeat_penalty': 1.0}
SYSTEM = '使用繁體中文，直接回答要求。不要執行任何動作。'
CASES = [
    {'id': 'short', 'prompt': '只回答「準備完成」。'},
    {'id': 'negation', 'prompt': '「不要刪除任何檔案，只列出資料夾內容。」請用一句話重述這個要求。'},
    {'id': 'long_input', 'prompt': '\n'.join(f'紀錄{i:04d}：檔案保留，不要修改。' for i in range(200)) + '\n以上資料請勿逐項重述，只回答紀錄筆數。'},
]


def request(path, payload=None, timeout=15):
    data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    req = urllib.request.Request('http://127.0.0.1:11434'+path, data=data, headers={'Content-Type': 'application/json'})
    return urllib.request.urlopen(req, timeout=timeout)


def api(path):
    with request(path) as response: return json.load(response)


def consume(response, began, clock=time.monotonic):
    records, terminal, first_content, chars = [], None, None, 0
    for line in response:
        if clock()-began > 180: raise TimeoutError('Streaming response exceeded 180 seconds')
        if len(line) > 200_000: raise ValueError('Oversized stream record')
        if not line.strip(): continue
        event = json.loads(line)
        if terminal is not None: raise ValueError('Content after terminal stream record')
        if event.get('error'): raise RuntimeError(str(event['error']))
        content = event.get('message', {}).get('content', '')
        if not isinstance(content, str): raise ValueError('Non-text message content')
        chars += len(content)
        if chars > 50_000 or len(records) >= 4096: raise ValueError('Response limit exceeded')
        if content and first_content is None: first_content = clock()-began
        records.append(event)
        if event.get('done') is True: terminal = event
    if terminal is None: raise ValueError('Stream ended without completion marker')
    # Length-limited output is retained as evidence, never counted complete.
    complete = terminal.get('done_reason') == 'stop'
    return {'first_content_seconds': first_content, 'wall_seconds': clock()-began,
            'generation_complete': complete, 'done_reason': terminal.get('done_reason'),
            'text': ''.join(e.get('message', {}).get('content', '') for e in records),
            'raw_stream': records, 'quality_verified': False,
            'model_metrics': {key: terminal.get(key) for key in
                              ['load_duration', 'prompt_eval_count', 'prompt_eval_duration', 'eval_count', 'eval_duration', 'total_duration']}}


def inventory(folder):
    shell = shutil.which('pwsh.exe') or shutil.which('powershell.exe')
    if shell is None: raise RuntimeError('PowerShell is required for Windows inventory')
    command = [shell, '-NoProfile', '-File', str(R/'collect_target_hardware.ps1'), '-OutputDirectory', str(folder)]
    output = subprocess.check_output(command, encoding='utf8', timeout=30).strip()
    path = Path(output.splitlines()[-1])
    if path.parent.resolve() != folder.resolve(): raise ValueError('Unexpected inventory destination')
    return json.loads(path.read_text(encoding='utf8'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True)
    parser.add_argument('--development', action='store_true', help='Explicitly permit a non-target machine; report remains non-target')
    args = parser.parse_args()
    folder = R/'hardware-reports'/('benchmark-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    folder.mkdir(parents=True, exist_ok=False)
    report = {'started_utc': datetime.now(timezone.utc).isoformat(), 'requested_model': args.model,
              'development_override': args.development, 'release_approved': False, 'quality_verified': False,
              'native_actions_tested': False, 'microphone_tested': False, 'cold_start_verified': False,
              'peak_ram_or_vram_measured': False, 'diagnostic_completed': False,
              'scope': 'Six sequential local chat requests only; no tool execution, download, model installation or explicit unloading.',
              'sources': {name: hashlib.sha256((R/name).read_bytes()).hexdigest() for name in ['benchmark_target.py', 'collect_target_hardware.ps1']},
              'cases': CASES, 'options': OPTIONS, 'measurements': []}
    try:
        report['inventory_before'] = inventory(folder)
        if not report['inventory_before']['inventory_matches_target'] and not args.development:
            raise RuntimeError('This is not the target RTX4050/24GB/Windows11 machine; no generation started')
        model = next(m for m in api('/api/tags')['models'] if m['name'] == args.model)
        report['model_before'] = model
        for repetition in range(2):
            for case in CASES:
                resident = api('/api/ps')
                payload = {'model': args.model, 'messages': [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': case['prompt']}],
                           'options': OPTIONS, 'stream': True, 'truncate': False, 'shift': False, 'keep_alive': '5m'}
                began = time.monotonic()
                with request('/api/chat', payload, timeout=30) as response:
                    result = consume(response, began)
                result.update(case=case['id'], repetition=repetition+1, request=payload, resident_before=resident,
                              resident_after=api('/api/ps'))
                report['measurements'].append(result)
                with (folder/'responses.jsonl').open('a', encoding='utf8') as stream:
                    stream.write(json.dumps(result, ensure_ascii=False)+'\n')
                print(json.dumps({key: result[key] for key in ['case', 'repetition', 'first_content_seconds', 'wall_seconds', 'generation_complete']}), flush=True)
        report['model_after'] = next(m for m in api('/api/tags')['models'] if m['name'] == args.model)
        report['inventory_after'] = inventory(folder)
        report['model_digest_unchanged'] = model['digest'] == report['model_after']['digest']
        report['sources_unchanged'] = all(hashlib.sha256((R/name).read_bytes()).hexdigest()==digest for name,digest in report['sources'].items())
        report['diagnostic_completed'] = report['model_digest_unchanged'] and report['sources_unchanged'] and all(m['generation_complete'] for m in report['measurements'])
        report['target_hardware_measured'] = bool(report['inventory_before']['inventory_matches_target'] and report['inventory_after']['inventory_matches_target'])
    except Exception as exc:
        report['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        (folder/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
        print(str(folder/'report.json'), flush=True)
    return 0 if report['diagnostic_completed'] else 1


if __name__ == '__main__': raise SystemExit(main())

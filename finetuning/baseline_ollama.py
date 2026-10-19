"""Read-only pilot baseline. Outputs are evidence, never executable actions."""
import argparse
import datetime
import json
from pathlib import Path
import time
import urllib.request
import sys


def request(path, data=None):
    req = urllib.request.Request(
        'http://127.0.0.1:11434/api/' + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=90) as response:
        return json.load(response)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default='qwen2.5-coder:7b')
    parser.add_argument('--data', default=str(Path(__file__).with_name('pilot_data.json')))
    parser.add_argument('--split', choices=['train','dev'], default='dev')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    data = json.loads(Path(args.data).read_text(encoding='utf-8'))
    model = next(m for m in request('tags')['models'] if m['name'] == args.model)
    out = root / 'results' / datetime.datetime.now(datetime.timezone.utc).strftime('baseline-%Y%m%dT%H%M%SZ.jsonl')
    out.parent.mkdir(exist_ok=True)
    with out.open('x', encoding='utf-8') as handle:
        for row in data['records']:
            if row['split'] != args.split:
                continue
            start = time.monotonic()
            system = row.get('system', data['system'])
            result = request('chat', {
                'model': args.model, 'stream': False,
                'messages': [{'role': 'system', 'content': system},
                             {'role': 'user', 'content': row['prompt']}],
                'options': {'temperature': 0, 'seed': 42, 'num_ctx': 4096, 'num_predict': 512}})
            record = {'id': row['id'], 'model': model, 'system': system,
                      'prompt': row['prompt'], 'rubric': row.get('rubric', row.get('chosen')),
                      'elapsed_seconds': time.monotonic() - start, 'response': result,
                      'assessment': 'pending; no automatic claim of correctness'}
            handle.write(json.dumps(record, ensure_ascii=False) + '\n')
            handle.flush()
            print(json.dumps({'id': row['id'], 'seconds': round(record['elapsed_seconds'], 2),
                              'answer': result['message']['content']}, ensure_ascii=False), flush=True)
    print(str(out), flush=True)


if __name__ == '__main__':
    main()

"""Run an existing evaluation unchanged, verifying actual model files around it."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import ollama

R = Path(__file__).resolve().parent
ROOT = R.parents[1]
sys.path.insert(0, str(ROOT))
from ollama_model_integrity import OllamaModelIntegrityGuard


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command and args.command[0] == '--' else args.command
    if not command:
        parser.error('Evaluation Python script required')
    script = Path(command[0]).resolve()
    if not script.is_relative_to(R) or not script.is_file() or script.suffix != '.py':
        raise ValueError('Existing local release_v13 Python evaluation required')
    target = args.receipt.resolve()
    if not target.is_relative_to(R) or target.exists() or target.with_suffix('.run.json').exists():
        raise ValueError('New local release_v13 receipt required')
    sources = {str(p): sha(p) for p in [Path(__file__), script, ROOT / 'model_blob_integrity.py', ROOT / 'ollama_model_integrity.py']}
    client = ollama.Client(timeout=180)
    guard = OllamaModelIntegrityGuard(client)
    try:
        before = guard.ensure(args.model)
        record = {'started_utc': datetime.now(timezone.utc).isoformat(), 'sources': sources,
                  'command': [sys.executable, '-X', 'utf8', *command], 'model': args.model, 'before': before,
                  'release_approved': False}
        with target.with_suffix('.run.json').open('x', encoding='utf8') as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        result = subprocess.run(record['command'], cwd=ROOT)
        record['child_exit_code'] = result.returncode
        guard.begin_task()
        try:
            after = guard.ensure(args.model)
            record['after'] = after
            record['actual_model_unchanged'] = before == after
        except Exception as exc:
            record.update(actual_model_unchanged=False, verification_error=str(exc))
        record['sources_unchanged'] = all(sha(Path(p)) == h for p, h in sources.items())
        record['finished_utc'] = datetime.now(timezone.utc).isoformat()
        with target.open('x', encoding='utf8') as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        assert record['actual_model_unchanged'] and record['sources_unchanged'], 'Evaluation integrity failed'
        raise SystemExit(result.returncode)
    finally:
        client._client.close()


if __name__ == '__main__':
    main()

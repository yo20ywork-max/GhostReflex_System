"""Run the production parser/recovery/reply checks once and save their evidence."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

R = Path(__file__).resolve().parent
ROOT = R.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--attempt', choices=('v1', 'v2'), default='v1')
    args = parser.parse_args()
    suffix = '' if args.attempt == 'v1' else '_V2'
    log_path = R / ('FALLBACK_PRODUCTION_TESTS' + suffix + '.log')
    report_path = R / ('FALLBACK_PRODUCTION_TESTS' + suffix + '.json')
    receipt_path = R / 'FALLBACK_LITERAL_INSTALL.json'
    receipt = json.loads(receipt_path.read_text(encoding='utf8'))
    assert receipt['installed_in_product'] and sha(ROOT / 'run_daemon.py') == receipt['after_sha256']
    tests = ['tests.test_fallback_diagnostics', 'tests.test_plan_execution_integrity',
             'tests.test_explicit_reply_runtime', 'tests.test_reply_delivery_consistency',
             'tests.test_completion_verification']
    command = [sys.executable, '-X', 'utf8', '-m', 'unittest', *tests]
    environment = dict(os.environ)
    environment['PYTHONPATH'] = str(ROOT / 'tests') + os.pathsep + environment.get('PYTHONPATH', '')
    result = subprocess.run(command, cwd=ROOT, env=environment, text=True, encoding='utf8', capture_output=True, timeout=90)
    log = result.stdout + result.stderr
    with log_path.open('x', encoding='utf8') as stream:
        stream.write(log)
    count = re.search(r'Ran (\d+) tests', log)
    report = {'checked_utc': datetime.now(timezone.utc).isoformat(), 'command': command,
              'exit_code': result.returncode, 'tests': int(count.group(1)) if count else None,
              'passed': result.returncode == 0 and count is not None,
              'source_sha256': sha(ROOT / 'run_daemon.py'),
              'test_sources': {name: sha(ROOT / (name.replace('.', '/') + '.py')) for name in tests},
              'log_sha256': sha(log_path), 'test_import_path': str(ROOT / 'tests'),
              'prior_failed_attempt_preserved': args.attempt == 'v2', 'release_approved': False}
    assert report['source_sha256'] == receipt['after_sha256'], 'Product changed during checks'
    with report_path.open('x', encoding='utf8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False))
    if not report['passed']:
        print(log)
        raise RuntimeError('Production checks failed')
    # Preserve the installation receipt's point-in-time state and profile hash.
    with (R / 'FALLBACK_PRODUCTION_VERIFIED.json').open('x', encoding='utf8') as stream:
        json.dump({'verified_utc': report['checked_utc'], 'source_sha256': report['source_sha256'],
                   'installation_receipt_sha256': sha(receipt_path), 'production_tests_passed': True,
                   'production_test_count': report['tests'], 'production_test_report': report_path.name,
                   'production_test_report_sha256': sha(report_path), 'release_approved': False}, stream, indent=2)


if __name__ == '__main__':
    main()

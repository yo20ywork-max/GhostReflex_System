"""Exercise destructive-cleanup prerequisites with small retained artifacts."""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from finish_cloud import local_receipt
from fetch_artifacts import R, sha, remote_inventory


def main():
    records = []
    with tempfile.TemporaryDirectory(dir=R, prefix='.delivery-control-') as temporary:
        root = Path(temporary)
        artifacts = root / 'artifacts'
        artifacts.mkdir()
        for folder in (root, artifacts):
            (folder / 'config.json').write_bytes(b'{"epochs":3}\n')
            (folder / 'DATA_LOCK.json').write_text(json.dumps({
                'sha256': {'config.json': sha(folder / 'config.json')}
            }), encoding='utf8')
        rows = [{'path': name, 'bytes': (artifacts / name).stat().st_size,
                 'sha256': sha(artifacts / name)} for name in ('config.json', 'DATA_LOCK.json')]
        original = {'epoch': None, 'terminal_run': True, 'transfer_verified': True,
                    'files': rows, 'total_bytes': sum(row['bytes'] for row in rows)}

        def check(name, receipt, accepted):
            (root / 'FINAL_TRANSFER_VERIFIED.json').write_text(json.dumps(receipt), encoding='utf8')
            with patch('subprocess.check_output', side_effect=AssertionError('Cloud access forbidden in local control')):
                try:
                    local_receipt(root)
                except (ValueError, FileNotFoundError):
                    actual = False
                else:
                    actual = True
            assert actual == accepted, name
            records.append({'case': name, 'accepted': actual, 'expected': accepted})

        check('Intact terminal backup permits readiness review', original, True)
        for key, value in [('terminal_run', False), ('transfer_verified', False), ('epoch', 1)]:
            changed = copy.deepcopy(original)
            changed[key] = value
            check('Reject non-final receipt: ' + key, changed, False)
        changed = copy.deepcopy(original)
        changed['files'].append(copy.deepcopy(changed['files'][0]))
        changed['total_bytes'] += changed['files'][0]['bytes']
        check('Reject duplicate inventory', changed, False)
        changed = copy.deepcopy(original)
        changed['files'][0]['path'] = '../outside.json'
        check('Reject path traversal', changed, False)
        changed = copy.deepcopy(original)
        changed['files'][0]['bytes'] = 400_000_001
        changed['total_bytes'] = sum(row['bytes'] for row in changed['files'])
        check('Reject oversized individual artifact before transfer', changed, False)
        changed = copy.deepcopy(original)
        changed['files'][0]['sha256'] = '0' * 64
        check('Reject mismatching retained bytes', changed, False)
        changed = copy.deepcopy(original)
        changed['files'] = changed['files'][1:]
        changed['total_bytes'] = sum(row['bytes'] for row in changed['files'])
        check('Reject missing locked training input', changed, False)
        saved = (artifacts / 'config.json').read_bytes()
        (artifacts / 'config.json').write_bytes(saved.replace(b'3', b'2'))
        check('Reject same-size tampering after transfer', original, False)
        (artifacts / 'config.json').write_bytes(saved)
        (root / 'config.json').write_bytes(saved.replace(b'3', b'1'))
        check('Reject local/cloud input disagreement', original, False)
        (root / 'config.json').write_bytes(saved)
        check('Original backup remains usable after controls', original, True)
    for epoch in (None, 1, 2, 3):
        compile(remote_inventory(epoch), '<read-only remote inventory>', 'exec')
    report = {'checked_utc': datetime.now(timezone.utc).isoformat(), 'cases': records,
              'passed': True, 'cloud_calls': 0, 'cloud_deletion_executed': False,
              'training_artifacts_verified': False, 'release_approved': False,
              'sources': {name: sha(R / name) for name in
                          ('check_delivery_guards.py', 'finish_cloud.py', 'fetch_artifacts.py')}}
    with (R / 'DELIVERY_GUARD_CONTROLS.json').open('x', encoding='utf8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'controls_passed': len(records), 'cloud_calls': 0,
                      'actual_training_artifacts_verified': False}))


if __name__ == '__main__':
    main()

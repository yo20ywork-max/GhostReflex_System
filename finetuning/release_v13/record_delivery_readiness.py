"""Record actual preparation evidence; does not imply trained-model readiness."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

R = Path(__file__).resolve().parent
ROOT = R.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    preparation = json.loads((R / 'DELIVERY_PREPARATION.json').read_text(encoding='utf8'))
    controls = json.loads((R / 'DELIVERY_GUARD_CONTROLS.json').read_text(encoding='utf8'))
    assert controls['passed'] and len(controls['cases']) == 12
    assert all(sha(R / name) == digest for name, digest in controls['sources'].items())
    names = [row['name'] for row in preparation['files']]
    for row in preparation['files']:
        assert sha(Path(row['source'])) == row['source_sha256']
        if row['name'] != 'install_candidate.py':
            assert sha(R / row['name']) == row['prepared_sha256']
    # The installer was deliberately tightened after version-specific preparation.
    assert 'parameter_binding_receipt_sha256' in (R / 'install_candidate.py').read_text(encoding='utf8')
    for name in names:
        compile((R / name).read_bytes(), str(R / name), 'exec')
    original = json.loads((R.parent / 'release_v12/FINAL_TRANSFER_VERIFIED.json').read_text(encoding='utf8'))
    native = [row for row in original['files'] if 'identity-backend-e3/' in row['path']]
    assert len(native) == 4
    record = {
        'checked_utc': datetime.now(timezone.utc).isoformat(),
        'sources': {name: sha(R / name) for name in names +
                    ['DELIVERY_PROTOCOL.md', 'check_delivery_guards.py', 'fetch_artifacts.py',
                     'run_native_identity.py', 'evaluate_native_adapter.py']},
        'helper_preparation_verified': True, 'cleanup_guard_controls': 12,
        'installer_requires_distributed_parameter_binding': True,
        'prior_terminal_backup_files': len(original['files']),
        'prior_terminal_backup_bytes': original['total_bytes'],
        'additional_two_native_probes_estimated_files': 2 * len(native),
        'file_cap': 150, 'backup_cap_bytes': 1_500_000_000,
        'new_local_artifact_and_one_partial_budget_bytes': 4_300_000_000,
        'capacity_estimate_is_not_actual_v13_inventory': True,
        'free_disk_bytes_at_check': shutil.disk_usage(R).free,
        'training_restarted': False, 'v13_artifacts_transferred': False,
        'v13_weights_converted': False, 'v13_model_installed': False,
        'release_approved': False,
    }
    locked = json.loads((R / 'DATA_LOCK.json').read_text(encoding='utf8'))
    assert all(sha(R / name) == digest for name, digest in locked['sha256'].items())
    record['launch_locked_inputs_unchanged'] = True
    with (R / 'DELIVERY_READINESS.json').open('x', encoding='utf8') as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
    print(json.dumps({key: record[key] for key in
                      ('helper_preparation_verified', 'cleanup_guard_controls',
                       'launch_locked_inputs_unchanged', 'free_disk_bytes_at_check',
                       'v13_model_installed', 'release_approved')}))


if __name__ == '__main__':
    main()

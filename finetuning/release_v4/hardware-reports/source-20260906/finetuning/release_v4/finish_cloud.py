"""Delete only this run's pod after rechecking terminal cloud and retained artifacts."""
import argparse
import json
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from fetch_artifacts import R, sha, validate_inventory, remote_inventory, transport


def local_receipt(root=R):
    receipt = json.loads((root/'FINAL_TRANSFER_VERIFIED.json').read_text(encoding='utf8'))
    if receipt.get('transfer_verified') is not True or receipt.get('terminal_run') is not True or receipt.get('epoch') is not None:
        raise ValueError('A verified terminal transfer is required, including for incomplete training')
    validate_inventory(receipt)
    artifacts = root/'artifacts'
    for row in receipt['files']:
        file = artifacts/row['path']
        if not file.resolve().is_relative_to(artifacts.resolve()) or file.is_symlink():
            raise ValueError('Artifact escapes retained directory')
        if file.stat().st_size != row['bytes'] or sha(file) != row['sha256']:
            raise ValueError('Retained artifact changed: '+row['path'])
    if sha(artifacts/'DATA_LOCK.json') != sha(root/'DATA_LOCK.json'):
        raise ValueError('Retained training lock differs')
    locked = json.loads((root/'DATA_LOCK.json').read_text(encoding='utf8'))
    inventory = {row['path']: row['sha256'] for row in receipt['files']}
    for name, digest in locked['sha256'].items():
        if inventory.get(name) != digest or sha(root/name) != digest:
            raise ValueError('Missing or changed training input: '+name)
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--delete', action='store_true')
    args = parser.parse_args()
    # No cloud mutation is reachable before this integrity check.
    receipt = local_receipt()
    state = json.loads((R/'CLOUD_RUN.json').read_text(encoding='utf8'))
    cli = str(R.parent/'tools/runpodctl.exe')
    def read(*args):
        return json.loads(subprocess.check_output([cli, *args], text=True, encoding='utf8', timeout=30))
    pods = read('pod', 'list')
    pod_id = state['pod']['id']
    active = next((p for p in pods if p['id']==pod_id), None)
    if active:
        if active['name'] != state['spec']['name']: raise ValueError('Cloud pod identity differs')
        host, port, options = transport.connection()
        command = 'python -c '+shlex.quote(remote_inventory(None))
        remote = json.loads(subprocess.check_output(['ssh', *options, '-p', port, host, command], text=True, timeout=90))
        validate_inventory(remote)
        if not remote['terminal_run'] or remote['files'] != receipt['files']:
            raise ValueError('Cloud data changed after transfer; preserve it before deletion')
        if args.delete:
            subprocess.run([cli, 'pod', 'delete', pod_id], check=True, capture_output=True, timeout=45)
    after = read('pod', 'list')
    absent = not any(p['id']==pod_id for p in after)
    user = read('user')
    report = {'checked_utc': datetime.now(timezone.utc).isoformat(), 'pod_id': pod_id,
              'delete_requested': args.delete, 'deletion_verified': absent,
              'local_transfer_verified': True, 'training_completed_and_reload_verified': receipt['training_completed_and_reload_verified'],
              'final_receipt_sha256': sha(R/'FINAL_TRANSFER_VERIFIED.json'),
              'account_balance': user['clientBalance'], 'account_spend_per_hour': user['currentSpendPerHr'],
              'account_balance_decrease_since_creation': state['starting_balance']-user['clientBalance'],
              'existing_network_volumes_untouched': True, 'release_approved': False,
              'billing_scope': 'Account balance change includes pre-existing storage and billing lag; not a pod invoice.'}
    destination = R/('CLOUD_CLEANUP.json' if absent else 'CLOUD_CLEANUP_READINESS.json')
    destination.write_text(json.dumps(report, indent=2)+'\n', encoding='utf8')
    if absent:
        state['status']='deleted'
        (R/'CLOUD_RUN.json').write_text(json.dumps(state, indent=2)+'\n', encoding='utf8')
    print(json.dumps(report), flush=True)
    if args.delete and not absent: raise RuntimeError('Deletion not yet verified; inspect the same pod, do not recreate')


if __name__ == '__main__': main()

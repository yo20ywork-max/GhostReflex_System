"""Fetch immutable completed epochs or terminal run evidence, without deleting the pod."""
import argparse
import hashlib
import importlib.util
import json
import re
import shlex
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

R = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('crossgen_v12_transport', R / 'remote.py')
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)
LIMIT = 1_500_000_000


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def validate_inventory(inventory):
    rows = inventory['files']
    if not rows or len(rows) > 150:
        raise ValueError('Unexpected file count')
    seen = set()
    for row in rows:
        path = PurePosixPath(row['path'])
        if (path.is_absolute() or path.as_posix() != row['path'] or
                any(part in ('.', '..') or not re.fullmatch(r'[A-Za-z0-9_.-]+', part) for part in path.parts)):
            raise ValueError('Unsafe artifact path')
        if row['path'] in seen or not re.fullmatch(r'[0-9a-f]{64}', row['sha256']):
            raise ValueError('Duplicate path or invalid digest')
        seen.add(row['path'])
        if not isinstance(row['bytes'], int) or not 0 <= row['bytes'] <= 400_000_000:
            raise ValueError('Unexpected file size')
    if sum(row['bytes'] for row in rows) != inventory['total_bytes'] or inventory['total_bytes'] > LIMIT:
        raise ValueError('Unexpected total size')


def remote_inventory(epoch):
    # Read only. A checkpoint is eligible for transfer only after its validation
    # metadata was published. Terminal evidence may document an unsuccessful run.
    return """import hashlib,json,os,stat
from pathlib import Path
r=Path('/workspace/crossgen-release-v12')
epoch=EPOCH
lock=json.loads((r/'DATA_LOCK.json').read_text())
entries=json.loads((r/'outputs/checkpoints.json').read_text()) if (r/'outputs/checkpoints.json').exists() else []
manifest=None
if epoch is not None:
    entry=next(x for x in entries if x['epoch']==epoch and x['full_epoch'])
    paths=list((r/'outputs'/('epoch-'+str(epoch))).iterdir())
else:
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name)==os.getpid():continue
        try:
            cwd=(proc/'cwd').resolve();argv=(proc/'cmdline').read_bytes().split(b'\\0')
        except (OSError,RuntimeError):continue
        active_names={'train.py','train_distributed.py','cloud_entry.py','run_distributed.sh','evaluate_native_adapter.py'}
        if cwd==r and any(Path(arg.decode('utf8',errors='replace')).name in active_names for arg in argv if arg):
            raise RuntimeError('Training or native evaluation still active; fetch a completed epoch instead')
    paths=[r/name for name in lock['sha256']]+[r/'DATA_LOCK.json']
    for name in ('preflight.log','training.log','preflight.pid','training.pid','preflight-runner.json','train-runner.json','PREFLIGHT_VERIFIED.json'):
        if (r/name).exists():paths.append(r/name)
    if (r/'preflight').exists():paths.extend(p for p in (r/'preflight').rglob('*') if not p.is_dir())
    if (r/'outputs').exists():paths.extend(p for p in (r/'outputs').rglob('*') if not p.is_dir())
    if (r/'outputs/manifest.json').exists():manifest=json.loads((r/'outputs/manifest.json').read_text())
records=[]
for path in sorted(set(paths)):
    assert path.resolve().is_relative_to(r) and not path.is_symlink() and stat.S_ISREG(path.stat().st_mode)
    assert all(not p.is_symlink() for p in path.parents if p!=r.parent)
    size=path.stat().st_size;assert 0<=size<=400_000_000
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(4*1024*1024),b''):h.update(chunk)
    records.append({'path':path.relative_to(r).as_posix(),'bytes':size,'sha256':h.hexdigest()})
assert len(records)<=150 and sum(x['bytes'] for x in records)<=1500000000
print(json.dumps({'epoch':epoch,'checkpoint_entries':entries,'manifest':manifest,'files':records,'total_bytes':sum(x['bytes'] for x in records),'terminal_run':epoch is None}))
""".replace('EPOCH', repr(epoch))


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--epoch', type=int, choices=(1, 2, 3))
    mode.add_argument('--final', action='store_true')
    args = parser.parse_args()
    host, port, options = transport.connection()
    command = 'python -c ' + shlex.quote(remote_inventory(args.epoch))
    inventory = json.loads(subprocess.check_output(['ssh', *options, '-p', port, host, command], timeout=90, text=True))
    validate_inventory(inventory)
    root = R / 'artifacts'
    root.mkdir(exist_ok=True)
    if root.is_symlink() or not root.resolve().is_relative_to(R.resolve()):
        raise ValueError('Unsafe artifact destination')
    if shutil.disk_usage(root).free < inventory['total_bytes'] + 512_000_000:
        raise ValueError('Insufficient disk headroom')
    for row in inventory['files']:
        target = root.joinpath(*PurePosixPath(row['path']).parts)
        if not target.resolve().is_relative_to(root.resolve()) or target.is_symlink():
            raise ValueError('Artifact escapes destination')
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.stat().st_size != row['bytes'] or sha(target) != row['sha256']:
                raise ValueError('Existing artifact differs: ' + row['path'])
        else:
            partial = target.with_name(target.name + '.part')
            if partial.is_symlink() or partial.exists():
                raise FileExistsError('Inspect prior partial before retry: ' + str(partial))
            subprocess.run(['scp', *options, '-P', port, host + ':' + transport.REMOTE + '/' + row['path'], str(partial)], check=True, timeout=300)
            if partial.stat().st_size != row['bytes'] or sha(partial) != row['sha256']:
                raise ValueError('Transfer verification failed: ' + row['path'])
            partial.replace(target)
        print(json.dumps({'verified': row['path'], 'bytes': row['bytes']}), flush=True)
    if args.final:
        locked = json.loads((root / 'DATA_LOCK.json').read_text(encoding='utf8'))
        for name, digest in locked['sha256'].items():
            if sha(root / name) != digest or sha(R / name) != digest:
                raise ValueError('Training input differs: ' + name)
        if sha(root / 'DATA_LOCK.json') != sha(R / 'DATA_LOCK.json'):
            raise ValueError('Cloud lock differs from local lock')
    manifest = inventory.get('manifest') or {}
    receipt = {**inventory, 'transfer_verified': True, 'verified_utc': datetime.now(timezone.utc).isoformat(),
               'training_completed_and_reload_verified': all(manifest.get(k) for k in ('adapter_changed', 'training_completed', 'disk_reload_logits_verified')),
               'release_approved': False, 'scope': 'Transfer integrity; final logit reload covers last epoch only. No model quality claim.'}
    label = 'FINAL' if args.final else 'EPOCH-' + str(args.epoch)
    destination = R / (label + '_TRANSFER_VERIFIED.json')
    with destination.open('x', encoding='utf8') as stream:
        json.dump(receipt, stream, indent=2)
    print(str(destination), flush=True)


if __name__ == '__main__':
    main()

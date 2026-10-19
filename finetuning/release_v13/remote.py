"""SSH transport for this pod; upload only bounded, locked training artifacts."""
import argparse
import hashlib
import json
import ipaddress
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path

R=Path(__file__).resolve().parent
REMOTE='/workspace/crossgen-release-v13'


def endpoint_options(info, strict=True):
    address=ipaddress.ip_address(info['ip'])
    if address.version!=4:raise ValueError('This established pod transport expects IPv4')
    port=int(info['port'])
    if not 1<=port<=65535:raise ValueError('Invalid SSH port')
    key=Path(info['ssh_key']['path']).resolve(strict=True)
    options=['-i',str(key),'-o','BatchMode=yes','-o','StrictHostKeyChecking='+('yes' if strict else 'accept-new'),
             '-o','UserKnownHostsFile='+str(R/'known_hosts'),'-o','ConnectTimeout=20','-o','ServerAliveInterval=20','-o','ServerAliveCountMax=3']
    return 'root@'+str(address),str(port),options


def verify_identity(value,state,require_lock=True):
    expected=hashlib.sha256((R/'DATA_LOCK.json').read_bytes()).hexdigest()
    if value.get('pod_id')!=state['pod']['id']:raise ValueError('SSH endpoint belongs to a different pod')
    actual=value.get('data_lock_sha256')
    if actual!=expected and (require_lock or actual is not None):raise ValueError('SSH training lock differs or is missing')


def probe(info,state,strict=True,require_lock=True):
    host,port,options=endpoint_options(info,strict)
    program="""import hashlib,json
from pathlib import Path
pairs=Path('/proc/1/environ').read_bytes().split(b'\\0')
pod=next((p.split(b'=',1)[1].decode() for p in pairs if p.startswith(b'RUNPOD_POD_ID=')),None)
lock=Path('/workspace/crossgen-release-v13/DATA_LOCK.json')
print(json.dumps({'pod_id':pod,'data_lock_sha256':hashlib.sha256(lock.read_bytes()).hexdigest() if lock.exists() else None}))
"""
    value=json.loads(subprocess.check_output(['ssh',*options,'-p',port,host,'python -c '+shlex.quote(program)],text=True,encoding='utf8',timeout=40))
    verify_identity(value,state,require_lock)
    return (host,port,options),value


def remember_endpoint(info,state):
    # Cache only after strict host-key and live pod/data-lock identity checks.
    connection,value=probe(info,state)
    endpoint={'ip':info['ip'],'port':info['port'],'ssh_key':{'path':info['ssh_key']['path']}}
    record={'pod_id':state['pod']['id'],'endpoint':endpoint,'identity':value,
            'verified_utc':datetime.now(timezone.utc).isoformat()}
    path=R/'SSH_ENDPOINT_VERIFIED.json';temporary=path.with_suffix('.tmp')
    with temporary.open('x',encoding='utf8') as stream:json.dump(record,stream,indent=2)
    temporary.replace(path)
    return connection


def connection():
    state=json.loads((R/'CLOUD_RUN.json').read_text(encoding='utf8'))
    if state.get('status')=='deleted':raise RuntimeError('This training pod has been deleted')
    try:
        info=json.loads(subprocess.check_output([str(R.parent/'tools/runpodctl.exe'),'ssh','info',state['pod']['id']],text=True,encoding='utf8',timeout=30))
        if 'error' in info:raise RuntimeError(info['error'])
    except (RuntimeError,subprocess.SubprocessError,json.JSONDecodeError) as exc:
        # Metadata outages are not proof that training stopped. Only an already
        # verified endpoint can be reused, and its live identity is checked anew.
        path=R/'SSH_ENDPOINT_VERIFIED.json'
        if not path.exists():raise RuntimeError('No verified SSH fallback; inspect the same pod') from exc
        cached=json.loads(path.read_text(encoding='utf8'))
        if cached['pod_id']!=state['pod']['id']:raise ValueError('Cached pod identity differs') from exc
        result,value=probe(cached['endpoint'],state)
        (R/'SSH_FALLBACK_OBSERVATION.json').write_text(json.dumps({'observed_utc':datetime.now(timezone.utc).isoformat(),
            'metadata_error':str(exc),'live_identity':value,'no_training_restart':True},indent=2),encoding='utf8')
        return result
    # Initial upload may not yet have a data lock; never cache that incomplete
    # identity. Established checkpoints always use strict, cached host keys.
    result,value=probe(info,state,strict=False,require_lock=False)
    if value['data_lock_sha256'] is not None:return remember_endpoint(info,state)
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--upload',action='store_true');parser.add_argument('--command');parser.add_argument('--fetch');args=parser.parse_args()
    host,port,options=connection()
    def ssh(command,**kwargs):return subprocess.run(['ssh',*options,'-p',port,host,command],check=True,**kwargs)
    if args.upload:
        archive=R/'upload.tar.gz';digest=hashlib.sha256(archive.read_bytes()).hexdigest()
        assert archive.stat().st_size<8_000_000
        ssh('mkdir -p '+shlex.quote(REMOTE),timeout=45)
        subprocess.run(['scp',*options,'-P',port,str(archive),host+':'+REMOTE+'/upload.tar.gz'],check=True,timeout=90)
        program="""import hashlib,json,tarfile
from pathlib import Path
r=Path('/workspace/crossgen-release-v13')
archive=r/'upload.tar.gz'
assert hashlib.sha256(archive.read_bytes()).hexdigest()==EXPECTED_SHA
with tarfile.open(archive) as tar:
    members=tar.getmembers()
    assert len(members)<=80 and sum(m.size for m in members)<30_000_000
    for member in members:
        assert member.isfile() and Path(member.name).name==member.name and member.name not in ('.','..')
        data=tar.extractfile(member).read();target=r/member.name
        if target.exists():assert not target.is_symlink() and target.read_bytes()==data
        else:
            with target.open('xb') as output:output.write(data)
lock=json.loads((r/'DATA_LOCK.json').read_text())
for name,digest in lock['sha256'].items():assert hashlib.sha256((r/name).read_bytes()).hexdigest()==digest
print(json.dumps({'upload_verified':True,'files':len(members),'archive_sha256':EXPECTED_SHA}))
""".replace('EXPECTED_SHA',repr(digest))
        ssh('python -c '+shlex.quote(program),timeout=45)
    if args.command:ssh('cd '+shlex.quote(REMOTE)+' && '+args.command)
    if args.fetch:
        relative=Path(args.fetch)
        if relative.is_absolute() or any(part in ('.','..') for part in relative.parts):raise ValueError('Safe relative artifact path required')
        target=R/'cloud-observations'/relative;target.parent.mkdir(parents=True,exist_ok=True)
        subprocess.run(['scp',*options,'-P',port,host+':'+REMOTE+'/'+relative.as_posix(),str(target)],check=True,timeout=90)


if __name__=='__main__':main()

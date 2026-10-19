"""Launch one explicitly authorized cloud stage with an atomic duplicate guard."""
import argparse
from datetime import datetime,timezone
import math
import json
from pathlib import Path
import shlex
import subprocess
from remote import connection,REMOTE

R=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=('preflight','train'));args=parser.parse_args()
    state=json.loads((R/'CLOUD_RUN.json').read_text(encoding='utf8'))
    if args.mode=='train':
        # Require the completed local transfer before starting; a command
        # returning a running session is not evidence its file is ready.
        report=json.loads((R/'cloud-observations/preflight/memory-time-preflight.json').read_text(encoding='utf8'))
        permit=json.loads((R/'LAUNCH_STATUS.json').read_text(encoding='utf8'))
        if report.get('world_size')!=permit['gpu_count'] or report.get('bundle_lock_sha256')!=state['launch_lock_sha256']:
            raise RuntimeError('Local preflight does not match approved launch')
        if report.get('forward_backward_optimizer_passed') is not True or report.get('adapter_saved') is not False:
            raise RuntimeError('Successful optimizer preflight required')
        if not all(math.isfinite(report[k]['grad_norm']) for k in ('stress_update','representative_update')):
            raise RuntimeError('Non-finite preflight')
        estimate=max(x['global_batch_probe_seconds'] for x in report['ranks'])*report['planned_optimizer_steps']
        remaining=(datetime.fromisoformat(permit['deadline_utc'])-datetime.now(timezone.utc)).total_seconds()
        if estimate*1.5+600>=remaining or estimate*1.5>=report['config']['max_train_seconds']:
            raise RuntimeError('Measured runtime exceeds launch bounds')
    host,port,options=connection()
    program="""import hashlib,json,os,subprocess,sys,time
from pathlib import Path
r=Path(REMOTE);mode=MODE
os.chdir(r)
lock=json.loads((r/'DATA_LOCK.json').read_text())
for n,h in lock['sha256'].items():assert hashlib.sha256((r/n).read_bytes()).hexdigest()==h
from launch_guard import require_launch
permit=require_launch(r,lock,mode=mode)
assert permit['pod_id']==__EXPECTED_POD__
pairs=Path('/proc/1/environ').read_bytes().split(b'\\0')
actual=next((p.split(b'=',1)[1].decode() for p in pairs if p.startswith(b'RUNPOD_POD_ID=')),None)
assert actual==__EXPECTED_POD__
claim=r/('.'+mode+'_launch_claim');claim.mkdir()
env=dict(os.environ,RUNPOD_POD_ID=actual,PYTHONUNBUFFERED='1')
log=r/('preflight.log' if mode=='preflight' else 'training.log')
with log.open('xb') as stream:
 proc=subprocess.Popen([sys.executable,'cloud_entry.py',mode],cwd=r,env=env,stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
record={'mode':mode,'pid':proc.pid,'pod_id':actual,'start_ticks':Path('/proc/'+str(proc.pid)+'/stat').read_text().split()[21],'data_lock_sha256':hashlib.sha256((r/'DATA_LOCK.json').read_bytes()).hexdigest(),'launched_unix':time.time()}
(claim/'process.json').write_text(json.dumps(record))
(r/('preflight.pid' if mode=='preflight' else 'training.pid')).write_text(str(proc.pid))
print(json.dumps(record))
""".replace('REMOTE',repr(REMOTE)).replace('MODE',repr(args.mode)).replace('__EXPECTED_POD__',repr(state['pod']['id']))
    compile(program,'remote-launch','exec')
    output=subprocess.check_output(['ssh',*options,'-p',port,host,'python -c '+shlex.quote(program)],text=True,encoding='utf8',timeout=45)
    record=json.loads(output)
    with (R/(args.mode.upper()+'_PROCESS.json')).open('x',encoding='utf8') as stream:json.dump(record,stream,indent=2)
    print(json.dumps(record))


if __name__=='__main__':main()

"""Foreground cloud runner; allocation/permission must be handled separately."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import time

from launch_guard import require_launch


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['preflight','train'])
    args=parser.parse_args()
    root=Path(__file__).resolve().parent
    lock=json.loads((root/'DATA_LOCK.json').read_text(encoding='utf8'))
    for name,digest in lock['sha256'].items():
        if sha(root/name)!=digest:raise RuntimeError('Locked source changed: '+name)
    permit=require_launch(root,lock,mode=args.mode)
    if os.environ.get('RUNPOD_POD_ID')!=permit['pod_id']:
        raise RuntimeError('Provider pod identity mismatch')
    if os.name!='posix':raise RuntimeError('Cloud runner requires the prepared Linux CUDA environment')
    deadline=datetime.fromisoformat(permit['deadline_utc'])
    remaining=(deadline-datetime.now(timezone.utc)).total_seconds()
    monotonic_deadline=time.monotonic()+min(remaining,permit['max_run_seconds'])
    env=dict(os.environ,HF_HOME=str(root/'hf-cache'),PIP_NO_CACHE_DIR='1',PYTHONUNBUFFERED='1',OMP_NUM_THREADS='4',TOKENIZERS_PARALLELISM='false',TORCH_NCCL_ASYNC_ERROR_HANDLING='1')
    def run(argv):
        seconds=min(monotonic_deadline-time.monotonic(),(deadline-datetime.now(timezone.utc)).total_seconds())
        if seconds<=0:raise RuntimeError('Cloud run deadline reached')
        process=subprocess.Popen(argv,cwd=root,env=env,start_new_session=True)
        try:
            code=process.wait(timeout=seconds)
            if code:raise subprocess.CalledProcessError(code,argv)
        except BaseException:
            # Killing only torchrun could leave its CUDA children alive. End
            # this invocation's process group, never unrelated host processes.
            try:os.killpg(process.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                process.wait(timeout=10)
            raise
    output=root/('preflight' if args.mode=='preflight' else 'outputs')
    if output.exists():raise RuntimeError('Refusing to overwrite an existing stage; inspect its status first')
    preflight_receipt=root/'PREFLIGHT_VERIFIED.json'
    if args.mode=='train':
        verified=json.loads(preflight_receipt.read_text(encoding='utf8'))
        report=root/'preflight/memory-time-preflight.json'
        if verified['lock_sha256']!=sha(root/'DATA_LOCK.json') or verified['report_sha256']!=sha(report):
            raise RuntimeError('Preflight is not for this exact bundle')
        observed=json.loads(report.read_text(encoding='utf8'))
        if observed.get('world_size')!=permit.get('gpu_count') or observed.get('forward_backward_optimizer_passed') is not True or observed.get('adapter_saved') is not False:
            raise RuntimeError('Optimizer preflight did not pass')
    receipt=root/(args.mode+'-runner.json')
    if receipt.exists():raise RuntimeError('Prior runner receipt exists; do not restart blindly')
    state=dict(mode=args.mode,status='running',pod_id=permit['pod_id'],lock_sha256=sha(root/'DATA_LOCK.json'),started_utc=datetime.now(timezone.utc).isoformat(),release_approved=False)
    def save():receipt.write_text(json.dumps(state,indent=2)+'\n',encoding='utf8')
    save()
    try:
        # Keep template CUDA torch; installs are bounded and share one HF cache.
        run([sys.executable,'-m','pip','install','--break-system-packages','--no-cache-dir','-r','requirements-cloud.txt'])
        count=permit.get('gpu_count')
        if type(count) is not int or not 1<=count<=2:raise RuntimeError('Expected approved single-node one/two GPU configuration')
        argv=[sys.executable,'-m','torch.distributed.run','--standalone','--nnodes=1','--nproc-per-node='+str(count),'--max-restarts=0','train_distributed.py','--output',output.name]
        if args.mode=='preflight':argv.append('--preflight-only')
        run(argv)
        if args.mode=='preflight':
            report=root/'preflight/memory-time-preflight.json';observed=json.loads(report.read_text(encoding='utf8'))
            if observed.get('world_size')!=permit.get('gpu_count') or observed.get('forward_backward_optimizer_passed') is not True or observed.get('adapter_saved') is not False:raise RuntimeError('Missing successful optimizer preflight')
            preflight_receipt.write_text(json.dumps(dict(lock_sha256=sha(root/'DATA_LOCK.json'),report_sha256=sha(report),pod_id=permit['pod_id']),indent=2)+'\n',encoding='utf8')
        state['status']='command_completed'
    except Exception as exc:
        state.update(status='failed',error=type(exc).__name__+': '+str(exc))
        raise
    finally:
        state['finished_utc']=datetime.now(timezone.utc).isoformat();save()


if __name__=='__main__':main()

"""Create an immutable multi-GPU candidate from audited data; no allocation."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf8'))
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')


def main():
    parent=HERE/'bundle-v3';dest=HERE/'bundle-v4'
    if dest.exists():raise FileExistsError(dest)
    lock=read(parent/'DATA_LOCK.json')
    assert all(sha(parent/n)==h for n,h in lock['sha256'].items())
    reports=['DISTRIBUTED_ENGINE_VERIFIED_V2.json','PEFT_DISTRIBUTED_VERIFIED.json']
    for name in reports:
        report=read(HERE/name)
        assert all(sha(HERE/n)==h for n,h in report['sources'].items()),'Verification source changed'
    authorization=read(ROOT/'finetuning/release_v4/SESSION_STATE.json')['cloud_temporary_storage_authorization']
    assert authorization['approved'] and authorization['multi_gpu_workflow_approved'] and authorization['max_gb']==30
    dest.mkdir()
    for path in parent.iterdir():
        if path.is_file() and path.name not in ('DATA_LOCK.json','LAUNCH_STATUS.json'):
            if path.is_symlink():raise ValueError('No symlink staging')
            (dest/path.name).write_bytes(path.read_bytes())
    files=['distributed_engine.py','distributed_update.py','train_distributed.py','cloud_entry.py','launch_guard.py']
    for name in files:
        source=HERE/name;compile(source.read_text(encoding='utf8'),name,'exec')
        (dest/name).write_bytes(source.read_bytes())
    for name in reports:(dest/name).write_bytes((HERE/name).read_bytes())
    (dest/'PROJECT_GOALS.md').write_bytes((ROOT/'PROJECT_GOALS.md').read_bytes())
    write(dest/'RUN_AUTHORIZATION.json',authorization)
    write(dest/'LAUNCH_STATUS.json',dict(launch_allowed=False,temporary_storage_user_approved=True,
        reason='Storage and multi-GPU work approved; exact provider pod, price/deadline and launch configuration not yet bound',training_started=False))
    cfg=read(dest/'config.json')
    cfg['draft_notes']['limitations']='Storage and multi-GPU work approved. CPU lifecycle and real PEFT callback verification passed; full-size NF4/NCCL GPU preflight and generation release gates still pending.'
    write(dest/'config.json',cfg)
    audit={'parent_lock_sha256':sha(parent/'DATA_LOCK.json'),'parent_data_and_gates_unchanged':all(sha(dest/n)==sha(parent/n) for n in ('train.jsonl','dev.jsonl','RELEASE_GATES.json')),
        'verification_reports':reports,'source_hashes':{n:sha(HERE/n) for n in files},'goal_snapshot_sha256':sha(ROOT/'PROJECT_GOALS.md'),
        'runtime':'Explicit synchronous data parallel, one process per GPU; global batch remains 8',
        'entry':'cloud_entry.py -> torchrun -> train_distributed.py',
        'training_started':False,'release_approved':False}
    assert audit['parent_data_and_gates_unchanged']
    write(dest/'DISTRIBUTED_AUDIT.json',audit)
    write(dest/'DATA_LOCK.json',{'sha256':{p.name:sha(p) for p in dest.iterdir() if p.is_file()},'release_approved':False})
    script="import runpy,sys;sys.path.insert(0,'.');sys.modules['torch']=None;sys.modules['transformers']=None;sys.argv=['train_distributed.py','--preflight-only'];runpy.run_path('train_distributed.py',run_name='__main__')"
    result=subprocess.run([sys.executable,'-X','utf8','-c',script],cwd=dest,capture_output=True,text=True,encoding='utf8',timeout=20)
    assert result.returncode==1 and 'Training launch disabled' in result.stderr,result.stderr
    assert not (dest/'outputs').exists()
    verified=read(dest/'DATA_LOCK.json');assert all(sha(dest/n)==h for n,h in verified['sha256'].items())
    receipt={'bundle':dest.name,'bytes':sum(p.stat().st_size for p in dest.iterdir() if p.is_file()),'lock_sha256':sha(dest/'DATA_LOCK.json'),
        'lock_verified':True,'all_data_and_gates_preserved':True,'actual_distributed_entry_blocked_before_model_imports':True,
        'cloud_storage_approved':True,'gpu_preflight_passed':False,'training_started':False,'release_approved':False}
    write(HERE/'PREPARATION_RECEIPT_V4.json',receipt);print(json.dumps(receipt))


if __name__=='__main__':main()

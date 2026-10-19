"""Bound one multi-GPU run to approved storage, budget, and verified sources."""
import argparse
from datetime import datetime,timedelta,timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tarfile

R=Path(__file__).resolve().parent
CLI=str(R.parent/'tools/runpodctl.exe')
PARENT=R.parent/'release_v11/bundle-v4'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(*args):return json.loads(subprocess.check_output([CLI,*args],text=True,encoding='utf8',timeout=30))
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--create',action='store_true');args=parser.parse_args()
    target=R/'CLOUD_RUN.json'
    if target.exists():raise RuntimeError('Creation already recorded; inspect exact pod/result before any further allocation')
    lock=json.loads((PARENT/'DATA_LOCK.json').read_text(encoding='utf8'))
    assert all(sha(PARENT/n)==h for n,h in lock['sha256'].items())
    approval=json.loads((PARENT/'RUN_AUTHORIZATION.json').read_text(encoding='utf8'))
    assert approval['approved'] and approval['multi_gpu_workflow_approved'] and approval['max_gb']==30
    user=read('user');pods=read('pod','list')
    remaining=min(100.,user['clientBalance']-8.74) # reserve all pre-topup credit; conservative budget bound
    if pods or user['currentSpendPerHr']>.02 or remaining<15:raise RuntimeError('Unexpected live spend/pods or insufficient bounded budget')
    gpu=next(x for x in read('gpu','list','--include-unavailable') if x['gpuId']=='NVIDIA A100-SXM4-80GB')
    if not gpu['available'] or gpu['securePricePerHr']>1.60:raise RuntimeError('GPU quote unavailable or above bound')
    available=[x['dataCenterId'] for x in gpu['dataCenterAvailability'] if str(x['stockStatus']).lower() not in ('none','unavailable')]
    dc=next((x for x in ('EUR-IS-1','US-MD-1') if x in available),None)
    if not dc:raise RuntimeError('No advertised datacenter')
    deadline=(datetime.now(timezone.utc)+timedelta(hours=4)).isoformat()
    spec=dict(name='crossgen-coder-release-v12',cloudType='SECURE',gpuTypeId=gpu['gpuId'],gpuCount=2,dataCenterId=dc,
        imageName='runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404',containerDiskInGb=30,volumeInGb=0,volumeMountPath='/workspace',
        ports='22/tcp',startSsh=True,startJupyter=False,supportPublicIp=True,terminateAfter=deadline,allowedCudaVersions=['12.8','12.9','13.0'])
    state=dict(status='proposal',spec=spec,starting_balance=user['clientBalance'],quote_gpu_hourly=gpu['securePricePerHr']*2,
        new_run_spend_ceiling=15.,cumulative_authorized_ceiling=100.,conservative_remaining_budget=remaining,
        existing_storage_hourly=user['currentSpendPerHr'],source_data_lock_sha256=sha(PARENT/'DATA_LOCK.json'),
        provider_termination_requested=False,provider_termination_observed=False,storage_approved=True,release_approved=False)
    write(R/'POD_PROPOSAL.json',state)
    if not args.create:print(json.dumps(state));return
    module_spec=importlib.util.spec_from_file_location('authenticated_provider',R.parent/'provision_pilot.py')
    helper=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(helper)
    state.update(status='creation_requested',provider_termination_requested=True)
    with target.open('x',encoding='utf8') as out:json.dump(state,out,indent=2)
    try:
        pod=helper.graphql('mutation($input:PodFindAndDeployOnDemandInput){podFindAndDeployOnDemand(input:$input){id name costPerHr containerDiskInGb volumeInGb desiredStatus}}',{'input':spec})['podFindAndDeployOnDemand']
    except Exception as exc:
        state.update(status='creation_result_uncertain_or_failed',error=str(exc));write(target,state);raise
    state.update(status='created',pod=pod);write(target,state)
    if pod['costPerHr']>3.30 or pod['containerDiskInGb']+pod['volumeInGb']>30:
        subprocess.run([CLI,'pod','delete',pod['id']],capture_output=True,check=True,timeout=45)
        raise RuntimeError('Allocation exceeded bounds; deletion requested, verify provider state')
    # Bind the exact approved node after provider allocation; preserve all
    # parent data and create a new launch lock instead of editing old bundles.
    for name in lock['sha256']:
        if (R/name).exists():raise FileExistsError(R/name)
        (R/name).write_bytes((PARENT/name).read_bytes())
    permit=dict(launch_allowed=True,temporary_storage_user_approved=True,allowed_modes=['preflight','train'],gpu_count=2,
        max_temporary_gib=30*1e9/2**30,max_charge_usd=15.,max_run_seconds=3.5*3600,pod_id=pod['id'],deadline_utc=deadline,
        authorization='User explicitly approved 30GB cloud temporary storage and completion of multi-GPU training workflow')
    write(R/'LAUNCH_STATUS.json',permit)
    write(R/'DATA_LOCK.json',{'sha256':{name:sha(R/name) for name in lock['sha256']},'release_approved':False})
    with tarfile.open(R/'upload.tar.gz','w:gz') as archive:
        for name in sorted([*lock['sha256'],'DATA_LOCK.json']):archive.add(R/name,arcname=name,recursive=False)
    assert (R/'upload.tar.gz').stat().st_size<8_000_000
    state['launch_lock_sha256']=sha(R/'DATA_LOCK.json');state['archive_bytes']=(R/'upload.tar.gz').stat().st_size
    write(target,state);print(json.dumps(state),flush=True)


if __name__=='__main__':main()

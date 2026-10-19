"""One bounded GPU allocation within the existing training authorization."""
import argparse
import datetime
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

R=Path(__file__).resolve().parent
CLI=str(R.parent/'tools/runpodctl.exe')


def read(*args):
    return json.loads(subprocess.check_output([CLI,*args],text=True,encoding='utf8',timeout=30))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--create',action='store_true');args=parser.parse_args()
    state_path=R/'CLOUD_RUN.json'
    if state_path.exists():raise RuntimeError('Creation already recorded; inspect the existing handle, never blindly duplicate')
    lock=json.loads((R/'DATA_LOCK.json').read_text(encoding='utf8'))
    for name,digest in lock['sha256'].items():
        if hashlib.sha256((R/name).read_bytes()).hexdigest()!=digest:raise ValueError('Locked input changed: '+name)
    user=read('user');pods=read('pod','list')
    if pods or user['currentSpendPerHr']>0.02 or user['clientBalance']<4:raise RuntimeError('Unexpected live spend/resources or insufficient bounded budget')
    gpu=next(x for x in read('gpu','list') if x['gpuId']=='NVIDIA A40')
    if not gpu['available'] or gpu['securePricePerHr']>0.60:raise RuntimeError('GPU price/availability outside bound')
    available=[x['dataCenterId'] for x in gpu['dataCenterAvailability'] if str(x['stockStatus']).lower() not in {'none','unavailable'}]
    dc=next((x for x in ['EU-SE-1','CA-MTL-1'] if x in available),None)
    if not dc:raise RuntimeError('No quoted compatible datacenter')
    deadline=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=4)).isoformat()
    spec={'name':'crossgen-coder-release-v4','cloudType':'SECURE','gpuTypeId':gpu['gpuId'],'gpuCount':1,'dataCenterId':dc,'imageName':'runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404','containerDiskInGb':30,'volumeInGb':0,'volumeMountPath':'/workspace','ports':'22/tcp','startSsh':True,'startJupyter':False,'supportPublicIp':True,'terminateAfter':deadline,'allowedCudaVersions':['12.8','12.9','13.0']}
    state={'status':'proposal','spec':spec,'starting_balance':user['clientBalance'],'quote_gpu_hourly':gpu['securePricePerHr'],'new_run_spend_ceiling':3.5,'cumulative_authorized_ceiling':100.0,'existing_storage_hourly':user['currentSpendPerHr'],'storage_scope':'Same previously authorized30GB ephemeral cloud training workspace; no additional local model download or existing volume mutation','provider_termination_requested':False,'provider_termination_observed':False,'source_data_lock_sha256':hashlib.sha256((R/'DATA_LOCK.json').read_bytes()).hexdigest()}
    (R/'POD_PROPOSAL.json').write_text(json.dumps(state,indent=2)+'\n',encoding='utf8')
    if not args.create:print(json.dumps(state));return
    helper_spec=importlib.util.spec_from_file_location('runpod_authenticated_control',R.parent/'provision_pilot.py')
    helper=importlib.util.module_from_spec(helper_spec);helper_spec.loader.exec_module(helper)
    state.update(status='creation_requested',provider_termination_requested=True)
    with state_path.open('x',encoding='utf8') as f:json.dump(state,f,indent=2)
    try:
        pod=helper.graphql('mutation($input:PodFindAndDeployOnDemandInput){podFindAndDeployOnDemand(input:$input){id name costPerHr containerDiskInGb volumeInGb desiredStatus}}',{'input':spec})['podFindAndDeployOnDemand']
    except Exception as exc:
        state.update(status='creation_result_uncertain_or_failed',error=str(exc));state_path.write_text(json.dumps(state,indent=2)+'\n',encoding='utf8');raise
    state.update(status='created',pod=pod);state_path.write_text(json.dumps(state,indent=2)+'\n',encoding='utf8')
    if pod['costPerHr']>0.65 or pod['containerDiskInGb']+pod['volumeInGb']>30:
        subprocess.run([CLI,'pod','delete',pod['id']],check=True,capture_output=True)
        raise RuntimeError('Allocation exceeded bounds and was deleted')
    print(json.dumps(state))


if __name__=='__main__':main()

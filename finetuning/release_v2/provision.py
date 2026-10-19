"""Create one bounded formal training pod using existing authorization."""
import datetime
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from provision_pilot import graphql

def main():
    if (ROOT/'CLOUD_RUN.json').exists():raise RuntimeError('Creation already recorded; inspect, do not duplicate')
    if not (ROOT/'DATA_LOCK.json').exists():raise RuntimeError('Data must be locked before renting GPU')
    cli=str(ROOT.parent/'tools/runpodctl.exe')
    user=json.loads(subprocess.check_output([cli,'user'],text=True))
    pods=json.loads(subprocess.check_output([cli,'pod','list'],text=True))
    failed_path=ROOT/'CLOUD_FAILED_HOST_1.json'
    previous=json.loads(failed_path.read_text()) if failed_path.exists() else None
    known_billing_lag=bool(previous and previous.get('deletion_verified') and not pods and user['currentSpendPerHr']<=previous['pod']['costPerHr']+0.02)
    if pods or (user['currentSpendPerHr']>0.02 and not known_billing_lag) or user['clientBalance']<4:raise RuntimeError('Unexpected resources or insufficient bounded budget')
    gpu=next(g for g in json.loads(subprocess.check_output([cli,'gpu','list'],text=True)) if g['gpuId']=='NVIDIA GeForce RTX 4090')
    if not gpu['available'] or gpu['securePricePerHr']>0.80:raise RuntimeError('Price/availability outside bound')
    deadline=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=4)).isoformat()
    spec={'name':'crossgen-coder-release-v2','cloudType':'SECURE','gpuTypeId':gpu['gpuId'],'gpuCount':1,'dataCenterId':'EU-RO-1','imageName':'runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404','containerDiskInGb':30,'volumeInGb':0,'volumeMountPath':'/workspace','ports':'22/tcp','startSsh':True,'startJupyter':False,'supportPublicIp':True,'terminateAfter':deadline}
    spec['allowedCudaVersions']=['12.8','12.9','13.0']
    state={'status':'creation_requested','starting_balance':user['clientBalance'],'spec':spec,'quote_gpu_hourly':gpu['securePricePerHr'],'new_run_spend_ceiling':3.5,'cumulative_authorized_ceiling':100.0,'existing_storage_hourly':user['currentSpendPerHr']}
    if previous:
        state.update(starting_balance=previous['starting_balance'],previous_deleted_host=previous['pod']['id'],billing_snapshot_lag=known_billing_lag,existing_storage_hourly=previous['existing_storage_hourly'])
    path=ROOT/'CLOUD_RUN.json';path.write_text(json.dumps(state,indent=2))
    result=graphql('mutation($input:PodFindAndDeployOnDemandInput){podFindAndDeployOnDemand(input:$input){id name costPerHr containerDiskInGb volumeInGb desiredStatus}}',{'input':spec})['podFindAndDeployOnDemand']
    state.update(status='created',pod=result);path.write_text(json.dumps(state,indent=2))
    if result['costPerHr']>0.85 or result['containerDiskInGb']+result['volumeInGb']>30:
        subprocess.run([cli,'pod','delete',result['id']],check=True);raise RuntimeError('Allocation exceeded bounds; deleted')
    print(json.dumps(state,indent=2))

if __name__=='__main__':main()

"""Create one approved short-lived Runpod training pod, never log credentials."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import tomllib
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parent
STATE = ROOT / 'results' / 'cloud_run.json'


def graphql(query, variables):
    config = tomllib.loads((Path.home()/'.runpod/config.toml').read_text())
    key = os.environ.get('RUNPOD_API_KEY') or config['apikey']
    req = urllib.request.Request('https://api.runpod.io/graphql',
        data=json.dumps({'query':query,'variables':variables}).encode(),
        headers={'Authorization':'Bearer '+key, 'Content-Type':'application/json',
                 'User-Agent':'CrossGen-Pilot/0.1'})
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        message = exc.read().decode(errors='replace').replace(key, '<redacted>')
        raise RuntimeError(f'Runpod HTTP {exc.code}: {message[:1500]}') from None
    if result.get('errors'):
        raise RuntimeError(json.dumps(result['errors']))
    return result['data']


def main():
    if STATE.exists():
        raise RuntimeError('Run already recorded; inspect existing state, do not duplicate pods')
    cli = str(ROOT/'tools/runpodctl.exe')
    user = json.loads(subprocess.check_output([cli,'user'], text=True))
    if user['clientBalance'] < 3 or user['currentSpendPerHr'] > 0.02:
        raise RuntimeError('Unexpected balance or pre-existing compute charges')
    gpus = json.loads(subprocess.check_output([cli,'gpu','list'],text=True))
    gpu = next(g for g in gpus if g['gpuId']=='NVIDIA GeForce RTX 4090')
    if not gpu['available'] or gpu['securePricePerHr'] > 0.80:
        raise RuntimeError('GPU quote exceeds pilot price ceiling')
    # Production disables introspection; terminateAfter is specified in the
    # provider's published PodFindAndDeployOnDemandInput schema.
    deadline = (datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=2)).isoformat()
    spec = {'name':'crossgen-coder-pilot','cloudType':'SECURE',
        'gpuTypeId':'NVIDIA GeForce RTX 4090','gpuCount':1,'dataCenterId':'EU-RO-1',
        'imageName':'runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404',
        'containerDiskInGb':30,'volumeInGb':0,'volumeMountPath':'/workspace',
        'ports':'22/tcp','startSsh':True,'startJupyter':False,'supportPublicIp':True,
        'terminateAfter':deadline}
    STATE.parent.mkdir(exist_ok=True)
    state = {'status':'creation_requested','starting_balance':user['clientBalance'],
        'existing_storage_per_hour':user['currentSpendPerHr'],'spec':spec,
        'quoted_gpu_per_hour':gpu['securePricePerHr'], 'budget_usd':8.74}
    STATE.write_text(json.dumps(state,indent=2),encoding='utf-8')
    result = graphql('''mutation($input:PodFindAndDeployOnDemandInput) {
        podFindAndDeployOnDemand(input:$input) {
          id name costPerHr containerDiskInGb volumeInGb desiredStatus
        }
    }''', {'input':spec})['podFindAndDeployOnDemand']
    state.update(status='created',pod=result)
    STATE.write_text(json.dumps(state,indent=2),encoding='utf-8')
    print(json.dumps(state),flush=True)
    if result['costPerHr'] > 0.85 or result['containerDiskInGb']+result['volumeInGb'] > 30:
        subprocess.run([cli,'pod','delete',result['id']],check=True)
        raise RuntimeError('Actual allocation exceeded approved bounds; deleted')


if __name__ == '__main__':
    main()

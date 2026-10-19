"""Explicit SSH transport for this run, without exposing account credentials."""
import argparse
import json
from pathlib import Path
import subprocess
import tarfile
ROOT=Path(__file__).resolve().parent

def connection():
    state=json.loads((ROOT/'CLOUD_RUN.json').read_text())
    cli=str(ROOT.parent/'tools/runpodctl.exe')
    info=json.loads(subprocess.check_output([cli,'ssh','info',state['pod']['id']],text=True))
    if 'error' in info:raise RuntimeError(info['error'])
    host='root@'+info['ip'];key=info['ssh_key']['path'];port=str(info['port'])
    options=['-i',key,'-o','BatchMode=yes','-o','StrictHostKeyChecking=accept-new','-o','UserKnownHostsFile='+str(ROOT.parent/'tools/known_hosts'),'-o','ConnectTimeout=20','-o','ServerAliveInterval=20']
    return host,port,options

def main():
    p=argparse.ArgumentParser();p.add_argument('--command');p.add_argument('--upload',action='store_true');p.add_argument('--download');p.add_argument('--push');p.add_argument('--push-many',nargs='+');p.add_argument('--fetch-many',nargs='+');args=p.parse_args()
    host,port,options=connection()
    if args.upload:
        files=['train.py','answer_loss.py','evaluate.py','score.py','code_sandbox.py','cloud_run.sh','train.jsonl','dev.jsonl','test.jsonl','regression.jsonl','config.json','contract.json','DATA_LOCK.json','DATA_MANIFEST.json','requirements-cloud.txt','build_data.py','preflight.py']
        with tarfile.open(ROOT/'upload.tar.gz','w:gz') as tar:
            for name in files:tar.add(ROOT/name,arcname=name)
            for name in ['build_product_data.py']:tar.add(ROOT.parent/name,arcname=name)
        subprocess.run(['ssh',*options,'-p',port,host,'mkdir -p /workspace/crossgen-release-v2'],check=True)
        subprocess.run(['scp',*options,'-P',port,str(ROOT/'upload.tar.gz'),host+':/workspace/crossgen-release-v2/upload.tar.gz'],check=True)
        subprocess.run(['ssh',*options,'-p',port,host,'tar -xzf /workspace/crossgen-release-v2/upload.tar.gz -C /workspace/crossgen-release-v2'],check=True)
    if args.download:
        if not args.download.replace('-','').replace('_','').replace('.','').isalnum():raise ValueError('Simple artifact filename only')
        subprocess.run(['scp',*options,'-P',port,host+':/workspace/crossgen-release-v2/'+args.download,str(ROOT/args.download)],check=True)
    if args.push:
        name=Path(args.push).name
        if name!=args.push or not (ROOT/name).is_file():raise ValueError('Existing local basename only')
        subprocess.run(['scp',*options,'-P',port,str(ROOT/name),host+':/workspace/crossgen-release-v2/'+name],check=True)
    if args.push_many:
        for name in args.push_many:
            if Path(name).name!=name or not (ROOT/name).is_file():raise ValueError('Existing local basenames only')
        subprocess.run(['scp',*options,'-P',port,*[str(ROOT/name) for name in args.push_many],host+':/workspace/crossgen-release-v2/'],check=True)
    if args.fetch_many:
        for name in args.fetch_many:
            if not all(part and part not in ('.','..') and part.replace('-','').replace('_','').replace('.','').isalnum() for part in name.split('/')):raise ValueError('Safe relative artifact paths only')
        subprocess.run(['scp',*options,'-P',port,*[host+':/workspace/crossgen-release-v2/'+name for name in args.fetch_many],str(ROOT)],check=True)
    if args.command:
        subprocess.run(['ssh',*options,'-p',port,host,args.command],check=True)

if __name__=='__main__':main()

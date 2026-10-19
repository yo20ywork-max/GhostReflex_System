"""Verify archive, safe bounded extraction and every saved member before cloud teardown."""
import hashlib
import json
from pathlib import Path
import tarfile
ROOT=Path(__file__).resolve().parent

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()

def main():
    receipt=json.loads((ROOT/'formal-deliverables.tar.gz.json').read_text())
    path=ROOT/receipt['file']
    if path.stat().st_size!=receipt['bytes'] or sha(path)!=receipt['sha256']:raise ValueError('Download hash mismatch')
    destination=ROOT/'artifacts'
    destination.mkdir(exist_ok=False)
    with tarfile.open(path,'r:gz') as archive:
        members=archive.getmembers()
        if len(members)>500 or sum(m.size for m in members)>2_000_000_000:raise ValueError('Archive bound exceeded')
        for member in members:
            target=(destination/member.name).resolve()
            if not target.is_relative_to(destination.resolve()) or not member.isfile():raise ValueError('Unsafe archive member')
        archive.extractall(destination,filter='data')
    integrity=json.loads((destination/'integrity.json').read_text())
    for name,info in integrity.items():
        file=destination/name
        if file.stat().st_size!=info['bytes'] or sha(file)!=info['sha256']:raise ValueError('Member mismatch: '+name)
    from safetensors import safe_open
    adapters=[]
    for weights in sorted(destination.glob('outputs/**/adapter_model.safetensors')):
        with safe_open(weights,framework='pt',device='cpu') as f:
            names=list(f.keys())
            if not names or not any('lora_B' in n for n in names):raise ValueError('Invalid adapter')
            params=sum(f.get_tensor(n).numel() for n in names)
        adapters.append({'path':str(weights.relative_to(destination)),'parameters':params,'sha256':sha(weights)})
    manifest={'download_verified':True,'all_members_verified':True,'adapters':adapters,'archive':receipt}
    (ROOT/'ARTIFACT_VERIFIED.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2))

if __name__=='__main__':main()

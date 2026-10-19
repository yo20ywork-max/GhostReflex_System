"""Verify a bounded incremental archive without touching the original snapshot."""
import hashlib,json,tarfile
from pathlib import Path
from verify_artifacts import sha
ROOT=Path(__file__).resolve().parent
def main():
    receipt=json.loads((ROOT/'fresh-deliverables.tar.gz.json').read_text())
    path=ROOT/receipt['file']
    if path.name!='fresh-deliverables.tar.gz' or path.stat().st_size!=receipt['bytes'] or sha(path)!=receipt['sha256']:raise ValueError('Archive mismatch')
    destination=ROOT/'fresh-artifacts'
    destination.mkdir(exist_ok=False)
    with tarfile.open(path,'r:gz') as tar:
        members=tar.getmembers()
        if len(members)>700 or sum(m.size for m in members)>750_000_000:raise ValueError('Bounds exceeded')
        for m in members:
            if not m.isfile() or not (destination/m.name).resolve().is_relative_to(destination.resolve()):raise ValueError('Unsafe member')
        tar.extractall(destination,filter='data')
    integrity=json.loads((destination/'incremental-integrity.json').read_text())
    for name,info in integrity.items():
        p=destination/name
        if p.stat().st_size!=info['bytes'] or sha(p)!=info['sha256']:raise ValueError('Member mismatch: '+name)
    from safetensors import safe_open
    adapters=[]
    for p in sorted(destination.glob('outputs/**/adapter_model.safetensors')):
        with safe_open(p,framework='pt',device='cpu') as f:
            names=list(f.keys())
            if not names or not any('lora_B' in n for n in names):raise ValueError('Invalid weights')
            params=sum(f.get_tensor(n).numel() for n in names)
        adapters.append({'path':str(p.relative_to(destination)),'parameters':params,'sha256':sha(p)})
    if len(adapters)!=3:raise ValueError('Expected both fresh epochs and the fused adapter')
    report={'download_verified':True,'all_members_verified':True,'archive':receipt,'adapters':adapters}
    (ROOT/'INCREMENTAL_VERIFIED.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()

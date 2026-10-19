"""Cloud: preserve only this run's completed fresh checkpoints and final small evidence."""
import hashlib,json,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()
def main():
    manifest=json.loads((ROOT/'outputs/fresh-r1/manifest.json').read_text())
    if not manifest.get('training_completed') or not manifest.get('disk_reload_logits_verified'):raise ValueError('Training must finish and reload')
    files=[]
    for p in ROOT.iterdir():
        if p.is_file() and not p.is_symlink() and p.suffix in {'.py','.json','.jsonl','.md','.txt','.sh','.log'}:
            if p.stat().st_size>20_000_000:raise ValueError('Unexpected large root evidence file')
            files.append(p)
    for directory in ['outputs/fresh-r1','outputs/fusion-r1']:
        for p in (ROOT/directory).rglob('*'):
            if p.is_symlink():raise ValueError('No symlinks')
            if p.is_file():files.append(p)
    for p in (ROOT/'outputs').glob('*.json*'):
        if p.is_file() and not p.is_symlink():files.append(p)
    files=sorted(set(files))
    if sum(p.stat().st_size for p in files)>750_000_000:raise ValueError('Bound exceeded')
    integrity={p.relative_to(ROOT).as_posix():{'bytes':p.stat().st_size,'sha256':sha(p)} for p in files}
    integrity_path=ROOT/'incremental-integrity.json'
    integrity_path.write_text(json.dumps(integrity,indent=2))
    archive=ROOT/'fresh-deliverables.tar.gz'
    if archive.exists():raise FileExistsError(archive)
    with tarfile.open(archive,'w:gz',compresslevel=1) as tar:
        for p in files:tar.add(p,arcname=p.relative_to(ROOT).as_posix(),recursive=False)
        tar.add(integrity_path,arcname='incremental-integrity.json',recursive=False)
    receipt={'file':archive.name,'bytes':archive.stat().st_size,'sha256':sha(archive),'members':len(files)+1,'scope':'Fresh checkpoints, fused adapter and final cloud generation evidence; local semantic review and cleanup receipts remain separate.'}
    (ROOT/(archive.name+'.json')).write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt))
if __name__=='__main__':main()

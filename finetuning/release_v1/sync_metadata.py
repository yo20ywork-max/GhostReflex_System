"""One-shot transfer of this run's authored metadata; no model caches or credentials."""
import hashlib,json,subprocess,tarfile
from pathlib import Path
from remote import connection
ROOT=Path(__file__).resolve().parent
def main():
    files=sorted(p for p in ROOT.iterdir() if p.is_file() and p.suffix in ('.py','.json','.jsonl','.md','.sh','.txt') and p.name!='metadata-upload.json')
    if any(p.is_symlink() or p.resolve().parent!=ROOT.resolve() for p in files):raise ValueError('Unexpected metadata link')
    if sum(p.stat().st_size for p in files)>100_000_000:raise ValueError('Metadata exceeds 100MB bound')
    archive=ROOT/'metadata-upload.tar.gz'
    with tarfile.open(archive,'w:gz',compresslevel=1) as output:
        for p in files:output.add(p,arcname=p.name,recursive=False)
    receipt={'files':len(files),'uncompressed_bytes':sum(p.stat().st_size for p in files),'archive_bytes':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'scope':'Authored release_v1 root metadata only. No credentials, base cache, model weights or generated execution.'}
    (ROOT/'metadata-upload.json').write_text(json.dumps(receipt,indent=2))
    host,port,options=connection()
    subprocess.run(['scp',*options,'-P',port,str(archive),str(ROOT/'metadata-upload.json'),host+':/workspace/crossgen-release-v1/'],check=True)
    # Archive was built from checked local basenames and contains regular files only.
    command='cd /workspace/crossgen-release-v1 && python -c "import hashlib,json; from pathlib import Path; assert hashlib.sha256(Path(\'metadata-upload.tar.gz\').read_bytes()).hexdigest()==json.load(open(\'metadata-upload.json\'))[\'sha256\']" && tar --no-same-owner -xzf metadata-upload.tar.gz'
    subprocess.run(['ssh',*options,'-p',port,host,command],check=True)
    print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()

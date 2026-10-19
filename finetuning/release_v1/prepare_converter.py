"""Fetch pinned official conversion source and verified CPU quantizer (small downloads)."""
import hashlib
from pathlib import Path
import subprocess
import tarfile
import urllib.request
ROOT=Path(__file__).resolve().parent
COMMIT='6a1a922d269908a29cbd4b49c27e6a8e7fd10fae'
URL='https://github.com/ggml-org/llama.cpp/releases/download/b10819/llama-b10819-bin-ubuntu-x64.tar.gz'
DIGEST='bff96585dfa126d2bc915367b3735982a5e67ddf887138a7c6e9d7cc9b438146'

def main():
    source=ROOT/'llama.cpp'
    if not source.exists():
        source.mkdir();subprocess.run(['git','init',str(source)],check=True)
        subprocess.run(['git','-C',str(source),'remote','add','origin','https://github.com/ggml-org/llama.cpp'],check=True)
        subprocess.run(['git','-C',str(source),'fetch','--depth','1','origin',COMMIT],check=True)
        subprocess.run(['git','-C',str(source),'checkout','--detach',COMMIT],check=True)
    if subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()!=COMMIT:raise ValueError('Source mismatch')
    archive=ROOT/'quantizer.tar.gz'
    if not archive.exists():
        with urllib.request.urlopen(URL,timeout=60) as r,archive.open('xb') as f:
            total=0
            while block:=r.read(1024*1024):
                total+=len(block)
                if total>30_000_000:raise ValueError('Download bound exceeded')
                f.write(block)
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=DIGEST:raise ValueError('Binary hash mismatch')
    target=ROOT/'quantizer';target.mkdir(exist_ok=True)
    with tarfile.open(archive) as tar:
        if sum(m.size for m in tar.getmembers())>200_000_000:raise ValueError('Extraction bound exceeded')
        tar.extractall(target,filter='data')
    import sys
    subprocess.run([sys.executable,'-m','pip','install','--break-system-packages','--no-cache-dir','--no-deps','-e',str(source/'gguf-py'),'sentencepiece==0.2.1'],check=True)
    print('CONVERTER_READY',flush=True)

if __name__=='__main__':main()

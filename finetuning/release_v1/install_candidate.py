"""Verify and import an approved weight candidate; never switch the product default."""
import hashlib,json,shutil,subprocess,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent
MODEL='crossgen-agi-mu:rc1'

def models():
    with urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=20) as r:return json.load(r)['models']

def main():
    gate=json.loads((ROOT/'RELEASE_GATE.json').read_text(encoding='utf8'))
    if not gate['release_approved']:raise RuntimeError('Model benchmark gate is not approved')
    receipt=json.loads((ROOT/'q4-receipt.json').read_text())
    path=(ROOT/receipt['file']).resolve()
    if path.parent!=ROOT.resolve() or path.suffix!='.gguf':raise ValueError('Unexpected model artifact path')
    if path.stat().st_size!=receipt['bytes']:raise ValueError('Incomplete model download')
    digest=hashlib.sha256()
    with path.open('rb') as f:
        if f.read(4)!=b'GGUF':raise ValueError('Not GGUF')
        f.seek(0)
        for block in iter(lambda:f.read(4*1024*1024),b''):digest.update(block)
    if digest.hexdigest()!=receipt['sha256']:raise ValueError('Model hash mismatch')
    (ROOT/'GGUF_VERIFIED.json').write_text(json.dumps({'sha256':digest.hexdigest(),'bytes':path.stat().st_size,'download_verified':True},indent=2))
    if any(m['name']==MODEL for m in models()):raise RuntimeError('Candidate tag already exists; inspect instead of overwriting')
    cli=shutil.which('ollama')
    if not cli:raise RuntimeError('Ollama CLI not found')
    modelfile=ROOT/'Modelfile.candidate'
    modelfile.write_text(f'FROM "{path.as_posix()}"\nPARAMETER temperature 0.1\nPARAMETER num_ctx 6144\n',encoding='utf8')
    started=time.monotonic()
    subprocess.run([cli,'create',MODEL,'-f',str(modelfile)],check=True)
    imported=next(m for m in models() if m['name']==MODEL)
    output={'candidate_installed':True,'model':MODEL,'model_digest':imported['digest'],'gguf_sha256':receipt['sha256'],'seconds':time.monotonic()-started,'product_default_changed':False,'runtime_release_approved':False,'identity_system_prompt_added':False}
    (ROOT/'CANDIDATE_INSTALLED.json').write_text(json.dumps(output,indent=2));print(json.dumps(output),flush=True)

if __name__=='__main__':main()

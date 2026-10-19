"""Bounded local extraction with member hashes and safetensors structure verification."""
import hashlib,json,tarfile
from pathlib import Path,PurePosixPath
R=Path(__file__).resolve().parent
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()
def main():
 receipt=json.loads((R/'adapters-v2.receipt.json').read_text());archive=R/'adapters-v2.tar.gz'
 if archive.stat().st_size!=receipt['bytes'] or sha(archive)!=receipt['sha256']:raise ValueError('Archive checksum mismatch')
 dest=R/'artifacts';dest.mkdir(exist_ok=False)
 with tarfile.open(archive,'r:gz') as t:
  members=t.getmembers();total=0;names=set()
  for m in members:
   p=PurePosixPath(m.name)
   if not m.isfile() or p.is_absolute() or any(x in ('..','.') or ':' in x or '\\' in x for x in p.parts) or m.name in names:raise ValueError('Unsafe archive member')
   target=dest.joinpath(*p.parts).resolve();assert target.is_relative_to(dest.resolve())
   names.add(m.name);total+=m.size
   if total>2_000_000_000:raise ValueError('Expanded package exceeds 2GB')
  for m in members:
   target=dest.joinpath(*PurePosixPath(m.name).parts);target.parent.mkdir(parents=True,exist_ok=True)
   with t.extractfile(m) as src,target.open('xb') as out:
    while b:=src.read(4*1024*1024):out.write(b)
 metadata=dest/'ARTIFACT_CONTENTS.json'
 if sha(metadata)!=receipt['contents_sha256']:raise ValueError('Member manifest checksum mismatch')
 contents=json.loads(metadata.read_text());models=[]
 from safetensors import safe_open
 for f in contents['files']:
  p=dest/f['path']
  if not p.resolve().is_relative_to(dest.resolve()):raise ValueError('Manifest path escapes artifact directory')
  if p.name=='adapter_model.safetensors' and not p.exists():
   mapping={'outputs/epoch-1/adapter_model.safetensors':'epoch-1','outputs/epoch-2/adapter_model.safetensors':'epoch-2','outputs-repair/epoch-1/adapter_model.safetensors':'repair'}
   if f['path'] not in mapping:raise ValueError('Unexpected weight path')
   local=R/'weight-downloads'/mapping[f['path']]/p.name
   if not local.is_file() or local.stat().st_size!=f['bytes'] or sha(local)!=f['sha256']:raise ValueError('Separately transferred weight mismatch')
   p.parent.mkdir(parents=True,exist_ok=True);local.replace(p)
  if p.stat().st_size!=f['bytes'] or sha(p)!=f['sha256']:raise ValueError('Member mismatch: '+f['path'])
  if p.name=='adapter_model.safetensors':
   with safe_open(str(p),framework='np') as sf:
    keys=list(sf.keys())
    if not keys or not all('lora_' in x for x in keys):raise ValueError('Unexpected adapter tensors')
    shapes={x:sf.get_slice(x).get_shape() for x in keys}
   models.append({**f,'tensors':len(keys),'shape_count':len(shapes)})
 if len(models)!=receipt['adapter_count'] or not 2<=len(models)<=3:raise ValueError('Missing adapter')
 report={'verified':True,'archive':receipt,'members_verified':len(contents['files']),'models':models,'release_approved':False}
 (R/'ARTIFACT_VERIFIED.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
if __name__=='__main__':main()

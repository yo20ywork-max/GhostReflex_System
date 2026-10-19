"""Fetch one completed cloud checkpoint, retaining path and checking every hash."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from remote import connection
R=Path(__file__).resolve().parent
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--epoch',type=int,choices=[1,2,3],required=True);a=p.parse_args()
 host,port,options=connection();remote=f'/workspace/crossgen-release-v3/outputs/epoch-{a.epoch}'
 # Checkpoint metadata is only written after save and validation finish.
 cmd="python -c 'import json; p=json.load(open(\"/workspace/crossgen-release-v3/outputs/checkpoints.json\")); assert any(x[\"epoch\"]=="+str(a.epoch)+" and x[\"full_epoch\"] for x in p); print(\"checkpoint complete\")'"
 subprocess.run(['ssh',*options,'-p',port,host,cmd],check=True,capture_output=True)
 dest=R/'artifacts'/'outputs'/f'epoch-{a.epoch}';dest.mkdir(parents=True,exist_ok=True);assert dest.resolve().is_relative_to(R.resolve())
 records=[]
 for name in ['adapter_config.json','adapter_model.safetensors']:
  query=f"sha256sum {remote}/{name}; stat -c %s {remote}/{name}"
  lines=subprocess.check_output(['ssh',*options,'-p',port,host,query],text=True).splitlines();expected=lines[0].split()[0];size=int(lines[-1])
  if len(expected)!=64 or not 0<size<400_000_000:raise ValueError('Unexpected artifact bounds')
  target=dest/name
  if target.exists():
   if target.stat().st_size!=size or sha(target)!=expected:raise ValueError('Existing verified artifact changed')
  else:
   partial=dest/(name+'.part')
   subprocess.run(['scp',*options,'-P',port,host+':'+remote+'/'+name,str(partial)],check=True)
   if partial.stat().st_size!=size or sha(partial)!=expected:raise ValueError('Transferred checksum mismatch')
   partial.replace(target)
  records.append({'name':name,'bytes':size,'sha256':expected})
 receipt={'epoch':a.epoch,'remote':remote,'verified':True,'files':records,'scope':'Transfer integrity; not model quality or release qualification'}
 (dest/'TRANSFER_VERIFIED.json').write_text(json.dumps(receipt,indent=2),encoding='utf8');print(json.dumps(receipt))
if __name__=='__main__':main()

"""Copy one completed checkpoint while later GPU work continues; verify before retaining."""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
from remote import connection
R=Path(__file__).resolve().parent
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--epoch',choices=['1','2','repair'],required=True);a=p.parse_args()
 name='repair' if a.epoch=='repair' else 'epoch-'+a.epoch
 remote_folder='outputs-repair/epoch-1' if a.epoch=='repair' else 'outputs/'+name
 host,port,options=connection();source=f'/workspace/crossgen-release-v2/{remote_folder}/adapter_model.safetensors'
 expected=subprocess.check_output(['ssh',*options,'-p',port,host,'sha256sum '+source],text=True).split()[0]
 if not re.fullmatch('[0-9a-f]{64}',expected):raise ValueError('Invalid remote digest')
 size=int(subprocess.check_output(['ssh',*options,'-p',port,host,'stat -c %s '+source],text=True).strip())
 if not 0<size<1_000_000_000:raise ValueError('Weight exceeds 1GB copy bound')
 folder=R/'weight-downloads'/name;folder.mkdir(parents=True,exist_ok=True);dest=folder/'adapter_model.safetensors';part=folder/'adapter_model.safetensors.part'
 if dest.exists():
  if sha(dest)!=expected:raise ValueError('Existing retained weight differs')
 else:
  subprocess.run(['scp',*options,'-P',port,host+':'+source,str(part)],check=True)
  if part.stat().st_size!=size or sha(part)!=expected:raise ValueError('Downloaded weight checksum mismatch')
  part.replace(dest)
 subprocess.run(['scp',*options,'-P',port,host+':/workspace/crossgen-release-v2/'+remote_folder+'/adapter_config.json',str(folder/'adapter_config.json')],check=True)
 config=json.loads((folder/'adapter_config.json').read_text())
 if config['r']!=32 or config['lora_alpha']!=64 or config['base_model_name_or_path']!='Qwen/Qwen2.5-Coder-7B-Instruct':raise ValueError('Wrong adapter configuration')
 receipt={'epoch':a.epoch,'file':dest.name,'bytes':size,'sha256':expected,'config_sha256':sha(folder/'adapter_config.json'),'verified':True}
 (folder/'receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
if __name__=='__main__':main()

"""Convert, verify and install an evaluation-only adapter; never changes product defaults."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
from evaluate_local import request
R=Path(__file__).resolve().parent
BASE_DIGEST='dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--epoch',type=int,choices=[1,2,3],required=True);a=p.parse_args()
 name=f'epoch-{a.epoch}';tag=f'crossgen-agi-mu:v3-e{a.epoch}-eval-20260906';folder=R/'artifacts'/'outputs'/name
 transfer=json.loads((folder/'TRANSFER_VERIFIED.json').read_text());assert transfer['verified']
 for row in transfer['files']:
  if sha(folder/row['name'])!=row['sha256']:raise ValueError('Transferred artifact changed')
 tags=request('/api/tags')['models']
 if any(m['name']==tag for m in tags):raise RuntimeError('Evaluation model already exists; do not overwrite')
 if next(m['digest'] for m in tags if m['name']=='qwen2.5-coder:7b')!=BASE_DIGEST:raise ValueError('Local base changed')
 library=R.parent/'release_v2/llama.cpp'
 commit=subprocess.check_output(['git','-C',str(library),'rev-parse','HEAD'],text=True).strip()
 if commit!='6a1a922d269908a29cbd4b49c27e6a8e7fd10fae':raise ValueError('Converter revision changed')
 adapters=R/'local-adapters';adapters.mkdir(exist_ok=True);dest=adapters/(name+'.gguf')
 if not dest.exists():
  converted=subprocess.run([sys.executable,'-X','utf8',str(library/'convert_lora_to_gguf.py'),'--base',str(R.parent/'release_v2/tokenizer'),'--outtype','f32','--outfile',str(dest),str(folder)],capture_output=True,text=True,encoding='utf8',errors='replace')
  (adapters/(name+'.convert.log')).write_text(converted.stdout+'\n'+converted.stderr,encoding='utf8');converted.check_returncode()
 subprocess.run([sys.executable,'-X','utf8',str(R/'verify_local_adapter.py'),'--epoch',str(a.epoch)],check=True)
 verification=json.loads(dest.with_suffix('.verified.json').read_text())
 modelfile=adapters/('Modelfile.'+name);modelfile.write_text('FROM qwen2.5-coder:7b\nADAPTER "'+dest.as_posix()+'"\n',encoding='utf8')
 installed=subprocess.run(['ollama','create',tag,'-f',str(modelfile)],capture_output=True,text=True,encoding='utf8',errors='replace')
 (adapters/(name+'.install.log')).write_text(installed.stdout+'\n'+installed.stderr,encoding='utf8');installed.check_returncode()
 model=next(m for m in request('/api/tags')['models'] if m['name']==tag)
 receipt={'tag':tag,'model':model,'base_digest':BASE_DIGEST,'adapter_verification':verification,'product_default_changed':False,'release_approved':False}
 dest.with_suffix('.installed.json').write_text(json.dumps(receipt,indent=2),encoding='utf8');print(json.dumps(receipt))
if __name__=='__main__':main()

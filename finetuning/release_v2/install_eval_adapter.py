"""Install a verified adapter under a fresh evaluation-only Ollama tag."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from evaluate_local import request
R=Path(__file__).resolve().parent

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',choices=['epoch-2','prior-fusion','repair'],required=True);a=p.parse_args()
 tag='crossgen-agi-mu:v2-'+('e2' if a.candidate=='epoch-2' else a.candidate)+'-eval-20260906'
 if any(m['name']==tag for m in request('/api/tags')['models']):raise RuntimeError('Evaluation tag already exists; will not overwrite')
 adapter=R/'local-adapters'/(a.candidate+'.gguf');receipt=json.loads(adapter.with_suffix('.verified.json').read_text())
 if not receipt['verified'] or hashlib.sha256(adapter.read_bytes()).hexdigest()!=receipt['gguf_sha256']:raise ValueError('Adapter verification mismatch')
 modelfile=adapter.with_name('Modelfile.'+a.candidate)
 modelfile.write_text('FROM qwen2.5-coder:7b\nADAPTER "'+adapter.as_posix()+'"\n',encoding='utf8')
 result=subprocess.run(['ollama','create',tag,'-f',str(modelfile)],capture_output=True,text=True,encoding='utf8',errors='replace')
 modelfile.with_suffix('.install.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf8');result.check_returncode()
 model=next(m for m in request('/api/tags')['models'] if m['name']==tag)
 output={'tag':tag,'model':model,'adapter_verification':receipt,'product_default_changed':False}
 adapter.with_suffix('.installed.json').write_text(json.dumps(output,indent=2),encoding='utf8');print(json.dumps(output))
if __name__=='__main__':main()

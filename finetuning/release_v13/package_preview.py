"""Create a separate branded default configuration; never rewrite eval tags.

This is packaging, not proof of identity unlearning or a release approval.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime,timezone

R=Path(__file__).resolve().parent;ROOT=R.parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(R.parent/'release_v4'))
from evaluate_development import request
from product_identity import GENERATION_SYSTEM

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--epoch',type=int,required=True,choices=(1,2,3));args=p.parse_args()
    folder=R/'local-adapters';stem=folder/f'epoch-{args.epoch}'
    original=json.loads(stem.with_suffix('.installed.json').read_text(encoding='utf8'))
    binding=json.loads((R/f'EPOCH-{args.epoch}_PARAMETER_BINDING.json').read_text(encoding='utf8'))
    verified=json.loads(stem.with_suffix('.verified.json').read_text(encoding='utf8'))
    assert binding['matches_both_rank_agreement'] and binding['serialized_sha256']==verified['source_sha256']
    assert original['adapter_sha256']==verified['gguf_sha256']==sha(stem.with_suffix('.gguf'))
    tags=request('/api/tags')['models'];source=next(x for x in tags if x['name']==original['tag'])
    assert source['digest']==original['model']['digest'],'Original evaluation model changed'
    tag=f'crossgen-agi-mu:v13-e{args.epoch}-package-preview-20260907'
    assert not any(x['name']==tag for x in tags),'Preview already exists; never overwrite'
    path=folder/f'Modelfile.epoch-{args.epoch}.package-preview'
    with path.open('x',encoding='utf8') as f:f.write(f'FROM {source["name"]}\nSYSTEM """{GENERATION_SYSTEM}"""\n')
    proc=subprocess.run(['ollama','create',tag,'-f',str(path)],text=True,encoding='utf8',errors='replace',capture_output=True,timeout=180)
    with (folder/f'epoch-{args.epoch}.package-preview.log').open('x',encoding='utf8') as f:f.write(proc.stdout+'\n'+proc.stderr)
    proc.check_returncode()
    after=request('/api/tags')['models'];model=next(x for x in after if x['name']==tag)
    assert next(x['digest'] for x in after if x['name']==source['name'])==source['digest']
    show=request('/api/show',{'model':tag})
    assert show.get('system','').strip()==GENERATION_SYSTEM.strip()
    assert verified['gguf_sha256'] in show['modelfile'],'Preview lost or changed its adapter'
    report={'created_utc':datetime.now(timezone.utc).isoformat(),'tag':tag,'model_digest':model['digest'],
        'source_eval_tag':source['name'],'source_eval_digest':source['digest'],'source_eval_unchanged':True,
        'adapter_sha256':verified['gguf_sha256'],'default_system':show['system'],'product_identity_sha256':sha(ROOT/'product_identity.py'),
        'model_file_sha256':sha(path),'package_script_sha256':sha(Path(__file__)),
        'weights_changed':False,'identity_in_weights_verified':False,'product_default_changed':False,'release_approved':False}
    with (folder/f'epoch-{args.epoch}.package-preview.json').open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:report[k] for k in ('tag','model_digest','source_eval_unchanged','weights_changed','identity_in_weights_verified','release_approved')}))

if __name__=='__main__':main()

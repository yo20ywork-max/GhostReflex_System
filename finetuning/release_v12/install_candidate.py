"""Install a verified v12 adapter under an evaluation-only local model name."""
import argparse
import json
import subprocess
from pathlib import Path
from convert_candidate import R, sha
import sys
sys.path.insert(0,str(R.parent/'release_v4'))
from evaluate_development import request

BASE = 'qwen2.5-coder:7b'
BASE_DIGEST = 'dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--epoch', type=int, choices=(1,2,3), required=True)
    args = parser.parse_args()
    folder = R/'local-adapters'
    adapter = folder/f'epoch-{args.epoch}.gguf'
    provenance = json.loads(adapter.with_suffix('.conversion-provenance.json').read_text(encoding='utf8'))
    verified = json.loads(adapter.with_suffix('.verified.json').read_text(encoding='utf8'))
    transfer_path = R/f'EPOCH-{args.epoch}_TRANSFER_VERIFIED.json'
    if (not provenance['conversion_verified'] or provenance['epoch'] != args.epoch or
            provenance['source_receipt_sha256'] != sha(transfer_path)):
        raise ValueError('Conversion provenance differs')
    if (not verified['verified'] or not verified['all_tensors_bitwise_equal'] or
            str(verified['epoch']) != str(args.epoch) or verified['tensor_count'] != 392 or
            sha(adapter) != verified['gguf_sha256'] or sha(adapter) != provenance['gguf_sha256']):
        raise ValueError('Converted adapter differs from verified tensors')
    source = R/'artifacts/outputs'/f'epoch-{args.epoch}'/'adapter_model.safetensors'
    if sha(source) != verified['source_sha256']: raise ValueError('Source adapter changed')
    tag = f'crossgen-agi-mu:v12-e{args.epoch}-eval-20260906'
    tags = request('/api/tags')['models']
    if any(m['name']==tag for m in tags): raise FileExistsError('Evaluation tag already exists; inspect rather than overwrite')
    if next(m['digest'] for m in tags if m['name']==BASE) != BASE_DIGEST:
        raise ValueError('Baseline model changed')
    modelfile = folder/f'Modelfile.epoch-{args.epoch}'
    with modelfile.open('x', encoding='utf8') as stream:
        stream.write(f'FROM {BASE}\nADAPTER "{adapter.as_posix()}"\n')
    result = subprocess.run(['ollama','create',tag,'-f',str(modelfile)],capture_output=True,text=True,encoding='utf8',errors='replace',timeout=180)
    with adapter.with_suffix('.install.log').open('x',encoding='utf8') as stream:
        stream.write(result.stdout+'\n'+result.stderr)
    result.check_returncode()
    end_tags = request('/api/tags')['models']
    model = next(m for m in end_tags if m['name']==tag)
    if next(m['digest'] for m in end_tags if m['name']==BASE) != BASE_DIGEST:
        raise ValueError('Baseline changed during install')
    show = request('/api/show', {'model': tag})
    if verified['gguf_sha256'] not in show.get('modelfile','') or BASE_DIGEST == model['digest']:
        raise ValueError('Installed model does not identify the expected adapter')
    receipt = {'tag':tag,'model':model,'show':show,'base_digest':BASE_DIGEST,
               'adapter_sha256':sha(adapter),'conversion_provenance_sha256':sha(adapter.with_suffix('.conversion-provenance.json')),
               'installer_sha256':sha(Path(__file__)),'product_default_changed':False,'release_approved':False,
               'scope':'Local evaluation adapter only. No quality or release claim.'}
    with adapter.with_suffix('.installed.json').open('x', encoding='utf8') as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'tag':tag,'digest':model['digest'],'adapter_verified':True,'release_approved':False}), flush=True)


if __name__ == '__main__': main()

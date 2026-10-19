"""Merge into full-precision CPU weights and export F16 GGUF without a duplicate HF checkpoint.

Requires a pinned llama.cpp checkout. This creates a candidate, never installs it.
The later Q4 conversion and generation checks are separate release requirements.
"""
import argparse
import hashlib
import json
import gc
import os
from pathlib import Path
import shutil
import sys
ROOT=Path(__file__).resolve().parent
LLAMA_COMMIT='6a1a922d269908a29cbd4b49c27e6a8e7fd10fae'

def write_merged_gguf(model,metadata_dir,llama_dir,output):
    import torch
    sys.path.insert(0,str(llama_dir));sys.path.insert(0,str(Path(llama_dir)/'gguf-py'))
    from conversion import ModelBase,ModelType,get_model_architecture,get_model_class
    from conversion.base import LazyTorchTensor
    import gguf
    hparams=ModelBase.load_hparams(metadata_dir,False)
    klass=get_model_class(get_model_architecture(hparams,ModelType.TEXT),mmproj=False)
    weights=model.state_dict()
    class MergedModel(klass):
        model_arch=klass.model_arch
        def index_tensors(self,remote_hf_model_id=None):
            return {name:(lambda tensor=tensor:LazyTorchTensor.from_eager(tensor)) for name,tensor in weights.items()}
    with torch.inference_mode():
        instance=MergedModel(metadata_dir,gguf.LlamaFileType.MOSTLY_F16,output,model_name='CrossGen-AGI-μ',hparams=hparams)
        instance.write()

def main():
    p=argparse.ArgumentParser();p.add_argument('--llama-dir',required=True);p.add_argument('--adapter',required=True);p.add_argument('--output',required=True);args=p.parse_args()
    import subprocess
    actual=subprocess.check_output(['git','-C',args.llama_dir,'rev-parse','HEAD'],text=True).strip()
    if actual!=LLAMA_COMMIT:raise ValueError('Converter revision mismatch')
    output=Path(args.output)
    if os.name!='posix' or ROOT.as_posix()!='/workspace/crossgen-release-v1':raise RuntimeError('Cloud workspace only')
    if output.exists():raise FileExistsError(output)
    cfg=json.loads((ROOT/'config.json').read_text())
    import torch
    from transformers import AutoModelForCausalLM,AutoTokenizer
    from peft import PeftModel
    torch.set_num_threads(8)
    # Reload original precision. Never merge into the training NF4 approximation.
    model=AutoModelForCausalLM.from_pretrained(cfg['base'],revision=cfg['revision'],torch_dtype=torch.bfloat16,device_map={'':'cpu'},trust_remote_code=False,local_files_only=True)
    tokenizer=AutoTokenizer.from_pretrained(cfg['base'],revision=cfg['revision'],local_files_only=True)
    model=PeftModel.from_pretrained(model,args.adapter,is_trainable=False)
    model=model.merge_and_unload(safe_merge=True);model.eval()
    from huggingface_hub import snapshot_download,hf_hub_download
    # Preserve foundation-model license and upstream model card with the derivative.
    for filename in ('LICENSE','README.md'):
        hf_hub_download(cfg['base'],filename,revision=cfg['revision'])
    snapshot=Path(snapshot_download(cfg['base'],revision=cfg['revision'],local_files_only=True))
    cache=(ROOT/'hf-cache').resolve()
    if not snapshot.resolve().is_relative_to(cache) or cache.parent!=ROOT.resolve():raise RuntimeError('Unexpected cache location; will not delete')
    metadata_dir=ROOT/'export-metadata';metadata_dir.mkdir(exist_ok=False)
    for path in snapshot.iterdir():
        if path.is_file() and (path.suffix in ('.json','.txt','.md','.model') or path.name in ('LICENSE','NOTICE')):
            if path.stat().st_size>100_000_000:raise RuntimeError('Unexpected metadata size')
            shutil.copyfile(path,metadata_dir/path.name)
    # Materialize all parameters in RAM before removing this run's disposable cache.
    # Metadata is copied above; the converter uses merged in-memory tensors below.
    with torch.no_grad():
        for parameter in model.parameters():parameter.data=parameter.data.clone()
    gc.collect()
    shutil.rmtree(cache)
    if shutil.disk_usage(output.parent).free<17_000_000_000:raise RuntimeError('Insufficient F16 export space')
    write_merged_gguf(model,metadata_dir,args.llama_dir,output)
    metadata={'base':cfg['base'],'revision':cfg['revision'],'adapter':args.adapter,'converter_commit':LLAMA_COMMIT,'merged_full_precision':True,'format':'F16','release_approved':False,'product_company':'跨世代媒體科技股份有限公司','region':'台灣','bytes':output.stat().st_size,'temporary_base_cache_removed_after_materialization':True}
    digest=hashlib.sha256()
    with output.open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''):digest.update(block)
    metadata['sha256']=digest.hexdigest()
    output.with_suffix('.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(metadata,ensure_ascii=False),flush=True)

if __name__=='__main__':main()

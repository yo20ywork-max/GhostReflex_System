"""Bind serialized epoch tensors to the exact hash agreed by both GPU ranks.

Instantiate architecture/PEFT metadata on meta only, never load base weights.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import torch
from safetensors import safe_open
from transformers import AutoConfig,AutoModelForCausalLM
from peft import LoraConfig,get_peft_model

R=Path(__file__).resolve().parent
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(4*1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--epoch',type=int,required=True,choices=(1,2,3));args=p.parse_args()
    receipt_path=R/f'EPOCH-{args.epoch}_TRANSFER_VERIFIED.json'
    receipt=json.loads(receipt_path.read_text(encoding='utf8'));assert receipt['transfer_verified']
    entry=next(e for e in receipt['checkpoint_entries'] if e['epoch']==args.epoch and e['full_epoch'])
    folder=R/'artifacts/outputs'/f'epoch-{args.epoch}'
    source=folder/'adapter_model.safetensors'
    expected=next(e for e in receipt['files'] if e['path']==f'outputs/epoch-{args.epoch}/adapter_model.safetensors')
    assert source.stat().st_size==expected['bytes'] and sha(source)==expected['sha256']
    config=AutoConfig.from_pretrained(R.parent/'release_v2/tokenizer',local_files_only=True)
    adapter=LoraConfig.from_pretrained(folder,local_files_only=True)
    # Adapter weights are read below; initializing values here is unnecessary.
    adapter.init_lora_weights=False;adapter.inference_mode=False
    with torch.device('meta'):
        model=get_peft_model(AutoModelForCausalLM.from_config(config),adapter)
    assert all(p.device.type=='meta' for p in model.parameters()),'No base allocation permitted'
    names=[(n,p.shape) for n,p in model.named_parameters() if p.requires_grad]
    assert len(names)==392
    h=hashlib.sha256();seen=set()
    with safe_open(str(source),framework='pt',device='cpu') as tensors:
        for name,shape in names:
            key=name.replace('.lora_A.default.weight','.lora_A.weight').replace('.lora_B.default.weight','.lora_B.weight')
            assert key!=name and key not in seen
            value=tensors.get_tensor(key)
            assert value.shape==shape and value.dtype==torch.float32 and torch.isfinite(value).all()
            h.update(name.encode());h.update(value.contiguous().view(torch.uint8).numpy().tobytes());seen.add(key)
        assert seen==set(tensors.keys())
    assert h.hexdigest()==entry['adapter_sha256'],'Serialized checkpoint does not match both-rank parameter agreement'
    report={'epoch':args.epoch,'verified_utc':datetime.now(timezone.utc).isoformat(),'tensor_count':len(names),
        'serialized_sha256':sha(source),'distributed_parameter_sha256':h.hexdigest(),'matches_both_rank_agreement':True,
        'source_receipt_sha256':sha(receipt_path),'verifier_sha256':sha(Path(__file__)),
        'base_weights_loaded':False,'scope':'Exact saved parameter binding; logits and quality are separate checks.','release_approved':False}
    with (R/f'EPOCH-{args.epoch}_PARAMETER_BINDING.json').open('x',encoding='utf8') as f:json.dump(report,f,indent=2)
    print(json.dumps(report))

if __name__=='__main__':main()

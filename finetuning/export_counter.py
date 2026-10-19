"""Export exact signed standard-LoRA composition as a loadable PEFT adapter."""
import argparse
import copy
import json
from pathlib import Path
import torch
from safetensors.torch import load_file, save_file
from counter_lora import combine


def export(chosen, error, output, alpha):
    if not 0 <= alpha <= 0.2:
        raise ValueError('Pilot alpha must be within [0, 0.2]')
    left = json.loads((chosen/'adapter_config.json').read_text())
    right = json.loads((error/'adapter_config.json').read_text())
    for key in ('base_model_name_or_path','target_modules','task_type','peft_type','revision'):
        lhs, rhs = left.get(key), right.get(key)
        if key == 'target_modules' and isinstance(lhs,list) and isinstance(rhs,list):
            lhs, rhs = sorted(lhs), sorted(rhs)
        if lhs != rhs:
            raise ValueError(f'Incompatible adapters: {key}')
    for config in (left,right):
        if config.get('peft_type')!='LORA' or config.get('bias','none')!='none':
            raise ValueError('Only standard Linear LoRA supported')
        for unsupported in ('use_dora','use_rslora','rank_pattern','alpha_pattern', 'modules_to_save','fan_in_fan_out'):
            if config.get(unsupported):
                raise ValueError(f'Unsupported feature: {unsupported}')
    lweights, rweights = load_file(chosen/'adapter_model.safetensors'), load_file(error/'adapter_model.safetensors')
    if set(lweights)!=set(rweights):
        raise ValueError('Module sets differ')
    composed = {}
    max_error = 0.0
    for name in sorted(lweights):
        if name.endswith('.lora_B.weight'):
            continue
        if not name.endswith('.lora_A.weight'):
            raise ValueError('Unexpected saved parameter '+name)
        bname = name.replace('.lora_A.weight','.lora_B.weight')
        a,b,c,d = [w.float() for w in (lweights[name],lweights[bname],rweights[name],rweights[bname])]
        ls,rs = left['lora_alpha']/left['r'], right['lora_alpha']/right['r']
        aa,bb = combine([(a,b,ls,1.0),(c,d,rs,-alpha)])
        # Test operator equivalence without allocating a dense 7B-model delta.
        probe = torch.linspace(-1,1,a.shape[1]).reshape(-1,1)
        expected = ls*b@(a@probe)-alpha*rs*d@(c@probe)
        actual = bb@(aa@probe)
        torch.testing.assert_close(actual,expected,rtol=1e-4,atol=1e-5)
        max_error=max(max_error,float((actual-expected).abs().max()))
        composed[name],composed[bname]=aa.contiguous(),bb.contiguous()
    if len(composed)!=len(lweights):
        raise ValueError('Incomplete factor pairing')
    config=copy.deepcopy(left)
    config.update(r=left['r']+right['r'],lora_alpha=left['r']+right['r'],inference_mode=True)
    output.mkdir(parents=True,exist_ok=False)
    save_file(composed,output/'adapter_model.safetensors')
    (output/'adapter_config.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
    (output/'composition.json').write_text(json.dumps({'formula':'delta_chosen - alpha * delta_error',
        'alpha':alpha,'max_operator_error':max_error,'release_approved':False},indent=2),encoding='utf-8')
    return {'output':str(output),'alpha':alpha,'max_operator_error':max_error}


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--chosen',type=Path,required=True)
    p.add_argument('--error',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--alpha',type=float,required=True)
    a=p.parse_args()
    print(json.dumps(export(a.chosen,a.error,a.output,a.alpha)))

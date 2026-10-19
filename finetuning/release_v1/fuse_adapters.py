"""Create one exact delta-sum LoRA, with numerical and disk-reload checks."""
import gc,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()
def check_delta_sum(model,names,weights,fused):
    import torch
    checked=0;maximum=0.0
    for module in model.modules():
        if not hasattr(module,'lora_A') or not all(n in module.lora_A for n in names+[fused]):continue
        out_size,in_size=module.lora_B[fused].weight.shape[0],module.lora_A[fused].weight.shape[1]
        rows=torch.linspace(0,out_size-1,min(out_size,32),device=module.lora_A[fused].weight.device).long()
        cols=torch.linspace(0,in_size-1,min(in_size,32),device=rows.device).long()
        def delta(name):return module.lora_B[name].weight[rows].float() @ module.lora_A[name].weight[:,cols].float()*module.scaling[name]
        expected=sum(w*delta(n) for n,w in zip(names,weights))
        actual=delta(fused)
        torch.testing.assert_close(actual,expected,atol=2e-6,rtol=2e-5)
        maximum=max(maximum,float((actual-expected).abs().max().detach()))
        checked+=1
    if not checked:raise ValueError('No fused layers checked')
    return {'layers_checked':checked,'sampled_rows_and_columns_per_layer':32,'max_absolute_delta_error':maximum,'all_sampled_delta_sums_passed':True}
def main():
    cfg=json.loads((ROOT/'FUSION_LOCK.json').read_text())
    out=ROOT/cfg['output']
    if out.exists():raise FileExistsError(out)
    for p in cfg['parents']:
        if sha(ROOT/p['path']/'adapter_model.safetensors')!=p['sha256']:raise ValueError('Parent hash mismatch')
        stage=json.loads((ROOT/p['path']).parent.joinpath('manifest.json').read_text())
        if stage['config']['base']!=cfg['base'] or stage['config']['revision']!=cfg['revision'] or not stage.get('training_completed') or not stage.get('disk_reload_logits_verified'):
            raise ValueError('Parent foundation or completion mismatch')
        adapter_cfg=json.loads((ROOT/p['path']/'adapter_config.json').read_text())
        if adapter_cfg['base_model_name_or_path']!=cfg['base'] or adapter_cfg['r']!=16 or adapter_cfg['bias']!='none' or adapter_cfg.get('modules_to_save'):raise ValueError('Unsupported parent configuration')
    import torch
    from transformers import AutoTokenizer,AutoModelForCausalLM,BitsAndBytesConfig
    from peft import PeftModel
    quant=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=torch.bfloat16)
    def base():return AutoModelForCausalLM.from_pretrained(cfg['base'],revision=cfg['revision'],quantization_config=quant,torch_dtype=torch.bfloat16,device_map={'':0},trust_remote_code=False,attn_implementation='sdpa')
    first=cfg['parents'][0]
    model=PeftModel.from_pretrained(base(),str(ROOT/first['path']),adapter_name=first['name'],is_trainable=False)
    for p in cfg['parents'][1:]:model.load_adapter(str(ROOT/p['path']),adapter_name=p['name'],is_trainable=False)
    names=[p['name'] for p in cfg['parents']];weights=[p['weight'] for p in cfg['parents']]
    model.add_weighted_adapter(names,weights,cfg['adapter_name'],combination_type='cat')
    model.set_adapter(cfg['adapter_name']);model.eval()
    with torch.inference_mode():delta_check=check_delta_sum(model,names,weights,cfg['adapter_name'])
    out.mkdir()
    model.save_pretrained(out,selected_adapters=[cfg['adapter_name']],safe_serialization=True)
    path=out/cfg['adapter_name']
    tokenizer=AutoTokenizer.from_pretrained(cfg['base'],revision=cfg['revision'])
    tokenizer.save_pretrained(path)
    probe=tokenizer('請以繁體中文說明模型來源。',return_tensors='pt').to('cuda')
    with torch.inference_mode():before=model(**probe).logits[0,-1].float().cpu()
    del model;gc.collect();torch.cuda.empty_cache()
    reloaded=PeftModel.from_pretrained(base(),str(path),is_trainable=False).eval()
    with torch.inference_mode():after=reloaded(**probe).logits[0,-1].float().cpu()
    torch.testing.assert_close(before,after,atol=1e-5,rtol=1e-5)
    manifest={**cfg,**delta_check,'adapter_path':str(path.relative_to(ROOT)),'adapter_sha256':sha(path/'adapter_model.safetensors'),'construction_complete':True,'disk_reload_logits_verified':True,'reload_max_abs_error':float((before-after).abs().max()),'optimizer_steps':0,'note':'One rank-32 adapter representing 0.5*delta_grounding + 0.5*delta_fresh. No SVD, no base-weight quantized merge, no claim of guaranteed capability addition.','script_sha256':sha(__file__)}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    (ROOT/'fusion-manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps(manifest),flush=True)
if __name__=='__main__':main()

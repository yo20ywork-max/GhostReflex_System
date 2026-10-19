"""Post-training NF4/local deployment diagnostic on already-known questions only."""
import argparse,hashlib,json,time
from pathlib import Path
R=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser();p.add_argument('--max-seconds',type=int,default=1200);a=p.parse_args()
    manifest=json.loads((R/'outputs/manifest.json').read_text())
    if not manifest.get('disk_reload_logits_verified'):raise RuntimeError('Wait for successful training and reload')
    if 'TRAINING_AND_RELOAD_COMPLETE' not in (R/'cloud_run.log').read_text():raise RuntimeError('Training process not finished')
    cfg=json.loads((R/'config.json').read_text());rows=[]
    for filename in ('dev.jsonl','regression.jsonl'):
        source=list(map(json.loads,(R/filename).read_text().splitlines()))
        rows.extend(x for x in source if filename=='regression.jsonl' or x['category'] in ('identity','asr'))
    if len(rows)!=26:raise ValueError('Expected 26 previously inspected questions')
    import torch
    from transformers import AutoModelForCausalLM,AutoTokenizer,BitsAndBytesConfig,set_seed
    from peft import PeftModel,prepare_model_for_kbit_training
    set_seed(cfg['seed']);began=time.monotonic()
    tokenizer=AutoTokenizer.from_pretrained(cfg['base'],revision=cfg['revision'],local_files_only=True,trust_remote_code=False)
    quant=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=torch.bfloat16)
    base=AutoModelForCausalLM.from_pretrained(cfg['base'],revision=cfg['revision'],local_files_only=True,quantization_config=quant,torch_dtype=torch.bfloat16,device_map={'':0},trust_remote_code=False,attn_implementation='sdpa')
    base=prepare_model_for_kbit_training(base,use_gradient_checkpointing=False);base.config.use_cache=True
    for candidate in ('base','epoch-1','epoch-2','epoch-3'):
        model=base if candidate=='base' else PeftModel.from_pretrained(base,str(R/'outputs'/candidate),is_trainable=False)
        model.eval();path=R/'outputs'/('known-nf4-'+candidate+'.jsonl')
        with path.open('x',encoding='utf8') as f:
            for row in rows:
                if time.monotonic()-began>a.max_seconds:raise RuntimeError('Diagnostic time bound reached; partial outputs are not a pass')
                messages=[{'role':'system','content':row['system']},{'role':'user','content':row['prompt']}]
                ids=tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,return_tensors='pt').to('cuda')
                start=time.monotonic()
                with torch.inference_mode(),torch.autocast('cuda',dtype=torch.bfloat16):
                    tokens=model.generate(input_ids=ids,attention_mask=torch.ones_like(ids),do_sample=False,repetition_penalty=1.0,max_new_tokens=1024,pad_token_id=tokenizer.eos_token_id)
                generated=tokens[0,ids.shape[1]:].tolist()
                eos=model.generation_config.eos_token_id;eos=[eos] if isinstance(eos,int) else eos
                record={'id':row['id'],'category':row['category'],'candidate':candidate,'text':tokenizer.decode(generated,skip_special_tokens=True),'completed':bool(generated and generated[-1] in eos),'seconds':time.monotonic()-start,'prompt_tokens':ids.shape[1],'generated_tokens':len(generated),'prompt_sha256':hashlib.sha256((row['system']+'\n'+row['prompt']).encode()).hexdigest(),'repetition_penalty':1.0,'max_new_tokens':1024,'quantization':'NF4 double quant BF16 compute, prepared base, BF16 autocast','base_revision':cfg['revision']}
                f.write(json.dumps(record,ensure_ascii=False)+'\n');f.flush();print(json.dumps({'candidate':candidate,'id':row['id'],'seconds':record['seconds']}),flush=True)
        if candidate!='base':base=model.unload();del model
    (R/'outputs/known-nf4-manifest.json').write_text(json.dumps({'completed':True,'rows_per_model':26,'models':4,'seconds':time.monotonic()-began,'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'scope':'Known development deployment diagnostic, no frozen final, no product release claim.'},indent=2))
if __name__=='__main__':main()

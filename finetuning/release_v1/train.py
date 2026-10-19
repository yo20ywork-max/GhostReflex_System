"""Release training: assistant-only SFT, retention KL, epoch checkpoints and dev selection."""
import argparse
import contextlib
import hashlib
import json
import math
from pathlib import Path
import random
import time

ROOT=Path(__file__).resolve().parent

def read_rows(name):
    return [json.loads(line) for line in (ROOT/name).read_text(encoding='utf8').splitlines() if line]

def verify_lock(name='DATA_LOCK.json'):
    lock=json.loads((ROOT/name).read_text(encoding='utf8'))
    for name,expected in lock['sha256'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=expected:
            raise ValueError('Locked input changed: '+name)
    return lock

def tokenize_row(tokenizer,row,max_length):
    messages=[{'role':'system','content':row['system']},{'role':'user','content':row['prompt']}]
    prefix=tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=True)
    full=tokenizer.apply_chat_template(messages+[{'role':'assistant','content':row['answer']}],tokenize=True,add_generation_prompt=False)
    if full[:len(prefix)]!=prefix or not len(prefix)<len(full)<=max_length:
        raise ValueError(f"Unsafe mask or overlength row {row['id']}: {len(full)}")
    return {'ids':full,'labels':[-100]*len(prefix)+full[len(prefix):],'prefix':len(prefix),'row':row}

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',default='outputs');p.add_argument('--tokenize-only',action='store_true');p.add_argument('--config',default='config.json');p.add_argument('--train-data',default='train.jsonl');p.add_argument('--lock',default='DATA_LOCK.json');p.add_argument('--init-adapter');args=p.parse_args()
    lock=verify_lock(args.lock)
    if args.config not in lock['sha256'] or args.train_data not in lock['sha256']:raise ValueError('Training inputs must be locked')
    cfg=json.loads((ROOT/args.config).read_text())
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(cfg['base'],revision=cfg['revision'],trust_remote_code=False)
    train=[tokenize_row(tokenizer,r,cfg['max_length']) for r in read_rows(args.train_data)]
    dev=[tokenize_row(tokenizer,r,cfg['max_length']) for r in read_rows('dev.jsonl')]
    print(json.dumps({'train_rows':len(train),'dev_rows':len(dev),'max_tokens':max(len(x['ids']) for x in train+dev),'train_tokens':sum(len(x['ids']) for x in train),'answer_tokens':sum(len(x['ids'])-x['prefix'] for x in train)}),flush=True)
    if args.tokenize_only:return
    import torch
    import torch.nn.functional as F
    from transformers import AutoModelForCausalLM,BitsAndBytesConfig,set_seed
    from peft import LoraConfig,get_peft_model,prepare_model_for_kbit_training,PeftModel
    if not torch.cuda.is_available():raise RuntimeError('CUDA required')
    out=Path(args.output);out.mkdir(parents=True,exist_ok=False)
    set_seed(cfg['seed']);started=time.monotonic()
    quant=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=torch.bfloat16)
    base=AutoModelForCausalLM.from_pretrained(cfg['base'],revision=cfg['revision'],quantization_config=quant,torch_dtype=torch.bfloat16,device_map={'':0},trust_remote_code=False,attn_implementation='sdpa')
    base=prepare_model_for_kbit_training(base,use_gradient_checkpointing=True)
    base.config.use_cache=False
    if args.init_adapter:
        model=PeftModel.from_pretrained(base,args.init_adapter,is_trainable=True)
    else:
        model=get_peft_model(base,LoraConfig(r=cfg['rank'],lora_alpha=cfg['alpha'],lora_dropout=0.0,target_modules=cfg['target_modules'],bias='none',task_type='CAUSAL_LM'))
    parameters=[p for p in model.parameters() if p.requires_grad]
    initial_probe=parameters[0].detach().cpu().clone()
    opt=torch.optim.AdamW(parameters,lr=cfg['learning_rate'],weight_decay=0.01)
    total_steps=math.ceil(len(train)/cfg['gradient_accumulation'])*cfg['epochs']
    warmup=max(1,int(total_steps*cfg['warmup_ratio']))
    log=(out/'train.jsonl').open('x',encoding='utf8')

    def tensors(sample):
        ids=torch.tensor([sample['ids']],device='cuda')
        labels=torch.tensor([sample['labels']],device='cuda')
        return ids,labels

    def dev_loss(disabled=False):
        model.eval();scores={}
        with model.disable_adapter() if disabled else contextlib.nullcontext(),torch.no_grad(),torch.autocast('cuda',dtype=torch.bfloat16,enabled=cfg.get('bf16_autocast',False)):
            for s in dev:
                ids,labels=tensors(s)
                loss=float(model(input_ids=ids,attention_mask=torch.ones_like(ids),labels=labels).loss)
                scores.setdefault(s['row']['category'],[]).append(loss)
        model.train()
        return {k:sum(v)/len(v) for k,v in scores.items()}

    baseline=dev_loss(True)
    (out/'base_dev_nll.json').write_text(json.dumps(baseline,indent=2))
    epochs=[];step=0;complete=True
    if cfg.get('longest_sample_preflight'):
        from answer_loss import answer_only_forward
        longest=max(train,key=lambda s:len(s['ids']));ids,labels=tensors(longest)
        opt.zero_grad(set_to_none=True);model.train()
        with torch.autocast('cuda',dtype=torch.bfloat16,enabled=cfg.get('bf16_autocast',False)):
            probe_output,probe_loss=answer_only_forward(model,ids,labels)
        probe_loss.backward()
        if not torch.isfinite(probe_loss):raise RuntimeError('Non-finite preflight loss')
        preflight={'tokens':len(longest['ids']),'row_id':longest['row']['id'],'loss':float(probe_loss.detach()),'forward_backward_passed':True,'optimizer_updated':False,'max_vram_gb':torch.cuda.max_memory_allocated()/2**30,'bf16_autocast':cfg.get('bf16_autocast',False)}
        (out/'longest-preflight.json').write_text(json.dumps(preflight,indent=2));print('LONGEST_SAMPLE_PREFLIGHT '+json.dumps(preflight),flush=True)
        opt.zero_grad(set_to_none=True);del probe_output,probe_loss;torch.cuda.empty_cache()
    for epoch in range(cfg['epochs']):
        order=list(range(len(train)));random.Random(cfg['seed']+epoch).shuffle(order)
        model.train()
        for start in range(0,len(order),cfg['gradient_accumulation']):
            if time.monotonic()-started>cfg['max_train_seconds']:
                complete=False;break
            batch=order[start:start+cfg['gradient_accumulation']]
            opt.zero_grad(set_to_none=True);sum_ce=0.0;sum_kl=0.0;retained=0
            scale=min(1.0,(step+1)/warmup)*0.5*(1+math.cos(math.pi*max(0,step-warmup)/max(1,total_steps-warmup)))
            for g in opt.param_groups:g['lr']=cfg['learning_rate']*scale
            for index in batch:
                sample=train[index];ids,labels=tensors(sample);teacher=None;positions=None
                if sample['row']['retain'] and cfg['retention_kl_weight']>0:
                    # On verified reference-code/literal tasks only. Do not anchor known wrong history or identity.
                    valid=torch.nonzero(labels[0,1:]!=-100).flatten()
                    stride=max(1,math.ceil(len(valid)/cfg['retention_positions']))
                    positions=valid[::stride]
                    model.eval()
                    with model.disable_adapter(),torch.no_grad():
                        teacher=model(input_ids=ids,attention_mask=torch.ones_like(ids)).logits[0,positions].float().detach()
                    model.train()
                with torch.autocast('cuda',dtype=torch.bfloat16,enabled=cfg.get('bf16_autocast',False)):
                    if cfg.get('answer_logits_only'):
                        if cfg['retention_kl_weight']!=0:raise ValueError('Selective logits currently require gold-only retention')
                        from answer_loss import answer_only_forward
                        output,ce=answer_only_forward(model,ids,labels)
                    else:
                        output=model(input_ids=ids,attention_mask=torch.ones_like(ids),labels=labels)
                        ce=output.loss
                kl=ce.new_zeros(())
                if teacher is not None:
                    student=output.logits[0,positions].float()
                    kl=F.kl_div(F.log_softmax(student,dim=-1),F.softmax(teacher,dim=-1),reduction='batchmean')
                    retained+=1
                loss=ce+cfg['retention_kl_weight']*kl
                if not torch.isfinite(loss):raise RuntimeError('Non-finite loss')
                (loss/len(batch)).backward()
                sum_ce+=float(ce.detach());sum_kl+=float(kl.detach())
                del output,loss,ce,kl,teacher
            grad=float(torch.nn.utils.clip_grad_norm_(parameters,1.0));opt.step();step+=1
            record={'step':step,'epoch':epoch+1,'rows_seen_epoch':min(start+len(batch),len(train)),'ce':sum_ce/len(batch),'kl':sum_kl/max(1,retained),'retained_rows':retained,'grad_norm':grad,'lr':opt.param_groups[0]['lr'],'seconds':time.monotonic()-started,'max_vram_gb':torch.cuda.max_memory_allocated()/2**30}
            log.write(json.dumps(record)+'\n');log.flush();print(json.dumps(record),flush=True)
        checkpoint=out/f'epoch-{epoch+1}'
        model.save_pretrained(checkpoint,safe_serialization=True);tokenizer.save_pretrained(checkpoint)
        scores=dev_loss()
        eligible=all(scores.get(c,0)<=baseline.get(c,0)+cfg['max_retention_dev_nll_increase'] for c in ('code','literal'))
        entry={'epoch':epoch+1,'path':str(checkpoint),'dev_nll':scores,'macro_nll':sum(scores.values())/len(scores),'retention_eligible':eligible,'full_epoch':complete}
        epochs.append(entry);(out/'checkpoints.json').write_text(json.dumps(epochs,indent=2))
        print('CHECKPOINT '+json.dumps(entry),flush=True)
        if not complete:break
    eligible=[e for e in epochs if e['retention_eligible'] and e['full_epoch']]
    selected=min(eligible,key=lambda e:e['macro_nll']) if eligible else None
    changed=not torch.equal(initial_probe,parameters[0].detach().cpu())
    manifest={'config':cfg,'data_lock':lock,'initial_adapter':args.init_adapter,'optimizer_state':'fresh AdamW; not exact optimizer resume','optimizer_steps':step,'epochs':epochs,'selected':selected,'adapter_changed':changed,'training_completed':complete,'release_approved':False,'selection_note':'Dev NLL selection is preliminary; independent generation and semantic gates still required.','seconds':time.monotonic()-started}
    manifest['trainer_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if cfg.get('answer_logits_only'):manifest['answer_loss_sha256']=hashlib.sha256((ROOT/'answer_loss.py').read_bytes()).hexdigest()
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    import subprocess,sys
    (out/'environment.txt').write_text(subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True),encoding='utf8')
    log.close()
    if not changed or not complete or selected is None:raise RuntimeError('Training incomplete or no retention-eligible checkpoint; do not release')
    # Verify on-disk adapter reconstruction against live last checkpoint before process exit.
    model.eval();probe=tensors(train[0])[0][:,:32]
    with torch.no_grad():expected=model(input_ids=probe).logits[:,-1].float().cpu()
    del opt,parameters
    base=model.unload();del model
    reload=PeftModel.from_pretrained(base,str(checkpoint),is_trainable=False);reload.eval()
    with torch.no_grad():actual=reload(input_ids=probe).logits[:,-1].float().cpu()
    torch.testing.assert_close(expected,actual,rtol=0.002,atol=0.002)
    manifest['disk_reload_logits_verified']=True
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    print('TRAINING_COMPLETE_RELOAD_VERIFIED',flush=True)

if __name__=='__main__':main()

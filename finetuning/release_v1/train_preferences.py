"""Bounded DPO refinement with immutable cached reference and code/literal retention."""
import argparse,hashlib,json,math,random,time
from pathlib import Path
from train import ROOT,verify_lock,tokenize_row,read_rows
from preference_math import dpo_loss,completion_log_probability

def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(4*1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--adapter',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    verify_lock('REPAIR_LOCK.json')
    data_manifest=json.loads((ROOT/'PREFERENCE_R2_MANIFEST.json').read_text())
    if sha(ROOT/data_manifest['data_file'])!=data_manifest['data_sha256']:raise ValueError('Preference data changed')
    if sha(ROOT/data_manifest['retention_file'])!=data_manifest['retention_sha256']:raise ValueError('Retention data changed')
    cfg=json.loads((ROOT/'config.json').read_text())
    settings={'epochs':2,'learning_rate':8e-6,'beta':0.1,'gradient_accumulation':4,'chosen_sft_weight':0.2,'retention_ce_weight':0.5,'retention_kl_weight':0.1,'seed':20260907,'max_seconds':3600}
    import torch
    import torch.nn.functional as F
    from transformers import AutoTokenizer,AutoModelForCausalLM,BitsAndBytesConfig,set_seed
    from peft import PeftModel,prepare_model_for_kbit_training
    set_seed(settings['seed']);out=Path(a.output);out.mkdir(parents=True,exist_ok=False)
    started=time.monotonic()
    tokenizer=AutoTokenizer.from_pretrained(cfg['base'],revision=cfg['revision'],local_files_only=True)
    pairs=[]
    for row in read_rows(data_manifest['data_file']):
        pair={'row':row}
        for kind in ('chosen','rejected'):pair[kind]=tokenize_row(tokenizer,{**row,'answer':row[kind]},cfg['max_length'])
        pairs.append(pair)
    retain=[tokenize_row(tokenizer,r,cfg['max_length']) for r in read_rows(data_manifest['retention_file'])]
    random.Random(settings['seed']).shuffle(retain)
    dev=[tokenize_row(tokenizer,r,cfg['max_length']) for r in read_rows('dev.jsonl')]
    quant=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=torch.bfloat16)
    base=AutoModelForCausalLM.from_pretrained(cfg['base'],revision=cfg['revision'],local_files_only=True,quantization_config=quant,torch_dtype=torch.bfloat16,device_map={'':0},trust_remote_code=False,attn_implementation='sdpa')
    base=prepare_model_for_kbit_training(base,use_gradient_checkpointing=True);base.config.use_cache=False
    model=PeftModel.from_pretrained(base,a.adapter,is_trainable=True);model.eval()
    params=[p for p in model.parameters() if p.requires_grad]
    initial=params[0].detach().cpu().clone()
    def tensors(s):
        ids=torch.tensor([s['ids']],device='cuda');labels=torch.tensor([s['labels']],device='cuda')
        return ids,labels
    def forward(s):
        ids,labels=tensors(s);result=model(input_ids=ids,attention_mask=torch.ones_like(ids))
        return completion_log_probability(result.logits,labels)
    references=[]
    with torch.no_grad(),(out/'reference-logps.jsonl').open('x') as f:
        for i,pair in enumerate(pairs):
            values={kind:float(forward(pair[kind])[0]) for kind in ('chosen','rejected')}
            references.append(values);f.write(json.dumps({'id':pair['row']['id'],**values})+'\n')
            if (i+1)%40==0:print(json.dumps({'reference_cached':i+1,'total':len(pairs)}),flush=True)
    # Reference values remain fixed for the entire stage; no second full model needed.
    reference_hash=sha(out/'reference-logps.jsonl')
    initial_hash=sha(Path(a.adapter)/'adapter_model.safetensors')
    retention_targets=[]
    with torch.no_grad():
        for sample in retain:
            if not sample['row']['reference_kl']:
                retention_targets.append(None)
                continue
            ids,labels=tensors(sample)
            positions=torch.nonzero(labels[0,1:]!=-100).flatten()[::max(1,math.ceil((len(sample['ids'])-sample['prefix'])/16))]
            teacher=model(input_ids=ids,attention_mask=torch.ones_like(ids)).logits[0,positions].to(dtype=torch.float16,device='cpu')
            retention_targets.append((positions.cpu(),teacher))
    # Preserve the selected, measured starting checkpoint instead of reintroducing original-base errors.
    # Reference logits stay in CPU memory and never change after optimization starts.
    print(json.dumps({'retention_reference_cached':len(retain),'reference_adapter_sha256':initial_hash}),flush=True)
    optimizer=torch.optim.AdamW(params,lr=settings['learning_rate'],weight_decay=0.01)
    steps_total=math.ceil(len(pairs)/settings['gradient_accumulation'])*settings['epochs']
    baseline=json.loads((ROOT/'outputs/base_dev_nll.json').read_text())
    checkpoints=[];step=0
    with (out/'train.jsonl').open('x') as log:
        for epoch in range(settings['epochs']):
            order=list(range(len(pairs)));random.Random(settings['seed']+epoch).shuffle(order)
            model.train()
            for start in range(0,len(order),settings['gradient_accumulation']):
                if time.monotonic()-started>settings['max_seconds']:raise TimeoutError('Stage budget reached; incomplete candidate is not released')
                batch=order[start:start+settings['gradient_accumulation']];optimizer.zero_grad(set_to_none=True)
                rate=settings['learning_rate']*min(1,(step+1)/8)*0.5*(1+math.cos(math.pi*step/steps_total))
                for group in optimizer.param_groups:group['lr']=rate
                pref_sum=0.;ce_sum=0.
                for index in batch:
                    chosen,ce=forward(pairs[index]['chosen']);rejected,_=forward(pairs[index]['rejected'])
                    ref=references[index]
                    pref=dpo_loss(chosen,rejected,ref['chosen'],ref['rejected'],settings['beta'])
                    loss=(pref+settings['chosen_sft_weight']*ce)/len(batch)
                    if not torch.isfinite(loss):raise ValueError('Non-finite DPO loss')
                    loss.backward();pref_sum+=float(pref.detach());ce_sum+=float(ce.detach())
                    del chosen,rejected,pref,ce,loss
                sample=retain[step%len(retain)];ids,labels=tensors(sample)
                model.train();result=model(input_ids=ids,attention_mask=torch.ones_like(ids));_,retain_ce=completion_log_probability(result.logits,labels)
                target=retention_targets[step%len(retain)]
                teacher=None
                if target is None:
                    kl=torch.zeros((),device='cuda')
                else:
                    cached_positions,cached_teacher=target
                    positions=cached_positions.to('cuda');teacher=cached_teacher.to(device='cuda',dtype=torch.float32)
                    kl=F.kl_div(F.log_softmax(result.logits[0,positions].float(),dim=-1),F.softmax(teacher,dim=-1),reduction='batchmean')
                retention=settings['retention_ce_weight']*retain_ce+settings['retention_kl_weight']*kl
                if not torch.isfinite(retention):raise ValueError('Non-finite retention loss')
                retention.backward();grad=float(torch.nn.utils.clip_grad_norm_(params,1.0));optimizer.step();step+=1
                record={'step':step,'epoch':epoch+1,'dpo':pref_sum/len(batch),'chosen_ce':ce_sum/len(batch),'retention_ce':float(retain_ce.detach()),'retention_kl':float(kl.detach()),'grad_norm':grad,'lr':rate,'seconds':time.monotonic()-started,'max_vram_gb':torch.cuda.max_memory_allocated()/2**30}
                log.write(json.dumps(record)+'\n');log.flush();print(json.dumps(record),flush=True)
                del result,teacher,retain_ce,kl,retention
            checkpoint=out/f'epoch-{epoch+1}';model.save_pretrained(checkpoint,safe_serialization=True);tokenizer.save_pretrained(checkpoint)
            scores={};model.eval()
            with torch.no_grad():
                for sample in dev:scores.setdefault(sample['row']['category'],[]).append(float(forward(sample)[1]))
            scores={k:sum(v)/len(v) for k,v in scores.items()}
            eligible=all(scores[c]<=baseline[c]+cfg['max_retention_dev_nll_increase'] for c in ('code','literal'))
            entry={'path':str(checkpoint),'epoch':epoch+1,'dev_nll':scores,'macro_nll':sum(scores.values())/len(scores),'retention_eligible':eligible,'full_epoch':True}
            checkpoints.append(entry);print('CHECKPOINT '+json.dumps(entry),flush=True)
    eligible=[e for e in checkpoints if e['retention_eligible']]
    selected=min(eligible,key=lambda e:e['macro_nll']) if eligible else None
    changed=not torch.equal(initial,params[0].detach().cpu())
    manifest={'method':'DPO sigmoid plus chosen SFT and code/literal/ASR/locale CE+KL retention','retention_reference':'Frozen initial selected adapter, not original base','training_code_sha256':sha(__file__),'math_code_sha256':sha(ROOT/'preference_math.py'),'settings':settings,'initial_adapter':a.adapter,'initial_adapter_sha256':initial_hash,'data_manifest':data_manifest,'reference_logps_sha256':reference_hash,'reference_updated_during_training':False,'epochs':checkpoints,'selected':selected,'optimizer_steps':step,'adapter_changed':changed,'training_completed':True,'release_approved':False,'seconds':time.monotonic()-started}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    if selected is None or not changed:raise RuntimeError('No eligible updated checkpoint')
    model.eval();probe=tensors(retain[0])[0][:,:32]
    with torch.no_grad():expected=model(input_ids=probe).logits[:,-1].float().cpu()
    del optimizer,params
    base=model.unload();del model
    reloaded=PeftModel.from_pretrained(base,str(checkpoint),is_trainable=False);reloaded.eval()
    with torch.no_grad():actual=reloaded(input_ids=probe).logits[:,-1].float().cpu()
    torch.testing.assert_close(expected,actual,rtol=0.002,atol=0.002)
    manifest['disk_reload_logits_verified']=True
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    print('PREFERENCE_TRAINING_COMPLETE_RELOAD_VERIFIED',flush=True)

if __name__=='__main__':main()

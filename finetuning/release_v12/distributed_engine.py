"""Shared synchronous training lifecycle for CPU verification and CUDA QLoRA.

One process/device, explicit gradient SUM, true global sequence mean. The same
engine runs sharding, evaluation, optimizer updates and rank-zero checkpoints.
Model construction and serialization are supplied by the production adapter.
"""
import hashlib
import json
import math
import random
import time
from pathlib import Path

import torch
import torch.distributed as dist
from distributed_update import rank_batch, synchronize_gradients


class Coordinator:
    def __init__(self, device):
        self.device=torch.device(device)
        self.active=dist.is_available() and dist.is_initialized()
        self.rank=dist.get_rank() if self.active else 0
        self.world=dist.get_world_size() if self.active else 1

    def sum(self, values):
        value=torch.tensor(values,device=self.device,dtype=torch.float64)
        if self.active:dist.all_reduce(value,op=dist.ReduceOp.SUM)
        return value.cpu().tolist()

    def check(self, error, phase):
        # All peers reach this checkpoint even if one Python/model operation
        # failed. Fatal process/device loss is instead bounded by torchrun and
        # the process-group timeout; do not claim recovery from such failures.
        count=self.sum([int(error is not None)])[0]
        if count:raise RuntimeError(f'{phase} failed on {int(count)} rank(s); local error: {error}') from error

    def call(self, operation, phase, *, rank_zero=False):
        result=None;error=None
        try:
            if not rank_zero or self.rank==0:result=operation()
        except Exception as exc:error=exc
        self.check(error,phase)
        return result

    def agree(self, value, phase):
        digest=list(hashlib.sha256(json.dumps(value,sort_keys=True).encode()).digest())
        local=torch.tensor(digest,device=self.device,dtype=torch.uint8)
        if self.active:
            gathered=[torch.empty_like(local) for _ in range(self.world)]
            dist.all_gather(gathered,local)
            if any(not torch.equal(local,other) for other in gathered):raise RuntimeError(phase+' differs across ranks')

    def initialize_parameters(self, named_parameters):
        named=list(named_parameters)
        self.agree([(n,list(p.shape),str(p.dtype)) for n,p in named],'Trainable parameter layout')
        if not named:raise ValueError('No trainable parameters')
        with torch.no_grad():
            for _,parameter in named:
                if parameter.device!=self.device:raise ValueError('Parameter on wrong rank device')
                if self.active:dist.broadcast(parameter,src=0)

    def verify_parameters(self, named_parameters):
        # Exact adapter equality after synchronized AdamW; independent device
        # reductions should produce the same tensor for every rank.
        digest=hashlib.sha256()
        for name,p in named_parameters:
            digest.update(name.encode())
            digest.update(p.detach().contiguous().view(torch.uint8).cpu().numpy().tobytes())
        self.agree(digest.hexdigest(),'Updated adapter parameters')
        return digest.hexdigest()


class TrainingEngine:
    def __init__(self, *, model, train, dev, config, coordinator, loss_fn,
                 save_fn, reload_fn, output):
        self.model=model;self.train=train;self.dev=dev;self.cfg=config;self.comm=coordinator
        self.loss_fn=loss_fn;self.save_fn=save_fn;self.reload_fn=reload_fn;self.out=Path(output)
        self.named=[(n,p) for n,p in model.named_parameters() if p.requires_grad]
        self.parameters=[p for _,p in self.named]
        self.batch=config['gradient_accumulation'] # fixed GLOBAL batch, not per rank
        if type(self.batch) is not int or self.batch<1:raise ValueError('Invalid global batch')
        if not train or not dev:raise ValueError('Nonempty train and dev required')
        if config.get('retention_kl_weight',0)!=0:raise ValueError('This engine requires configured gold-only retention')
        self.comm.agree({'config':config,'train':[s['row'] for s in train],'dev':[s['row'] for s in dev]},'Data and configuration')
        self.comm.initialize_parameters(self.named)
        self.initial=[p.detach().cpu().clone() for p in self.parameters]
        self.opt=torch.optim.AdamW(self.parameters,lr=config['learning_rate'],weight_decay=0.01)
        self.total=math.ceil(len(train)/self.batch)*config['epochs']
        self.warmup=max(1,int(self.total*config['warmup_ratio']))
        self.step=0;self.started=time.monotonic();self.epochs=[]
        self.comm.call(lambda:self.out.mkdir(parents=True,exist_ok=False),'Create output directory',rank_zero=True)

    def write(self, name, value):
        def save():
            target=self.out/name
            temporary=target.with_name(target.name+'.writing')
            temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
            temporary.replace(target)
        self.comm.call(save,'Write '+name,rank_zero=True)

    def evaluation(self, disabled=False):
        categories=sorted({s['row']['category'] for s in self.dev})
        positions={c:i for i,c in enumerate(categories)}
        sums=[0.]*(2*len(categories));error=None
        self.model.eval()
        try:
            with torch.no_grad():
                for index in rank_batch(list(range(len(self.dev))),self.comm.rank,self.comm.world):
                    sample=self.dev[index]
                    loss=self.loss_fn(sample,disabled)
                    value=float(loss)
                    if not math.isfinite(value):raise RuntimeError('Non-finite development loss')
                    position=positions[sample['row']['category']]*2
                    sums[position]+=value;sums[position+1]+=1
        except Exception as exc:error=exc
        self.comm.check(error,'Development loss')
        sums=self.comm.sum(sums);self.model.train()
        if int(sum(sums[1::2]))!=len(self.dev):raise RuntimeError('Development sample count mismatch')
        return {c:sums[i*2]/sums[i*2+1] for i,c in enumerate(categories)}

    def update(self, batch):
        chosen=rank_batch(batch,self.comm.rank,self.comm.world)
        self.opt.zero_grad(set_to_none=True);self.model.train()
        scale=min(1.,(self.step+1)/self.warmup)*.5*(1+math.cos(math.pi*max(0,self.step-self.warmup)/max(1,self.total-self.warmup)))
        for group in self.opt.param_groups:group['lr']=self.cfg['learning_rate']*scale
        total_loss=0.;error=None
        try:
            for index in chosen:
                loss=self.loss_fn(self.train[index],False)
                if not torch.isfinite(loss).item():raise RuntimeError('Non-finite training loss')
                loss.backward() # synchronize_gradients divides by true global count
                total_loss+=float(loss.detach())
                del loss
        except Exception as exc:error=exc
        self.comm.check(error,'Forward/backward')
        synchronize_gradients(self.parameters,local_samples=len(chosen),global_samples=len(batch))
        grad=float(torch.nn.utils.clip_grad_norm_(self.parameters,1.0))
        self.comm.check(None if math.isfinite(grad) else RuntimeError('Non-finite reduced gradient'),'Gradient clipping')
        self.comm.call(self.opt.step,'AdamW update')
        self.step+=1
        loss_sum=self.comm.sum([total_loss])[0]
        return dict(step=self.step,global_samples=len(batch),ce=loss_sum/len(batch),grad_norm=grad,
                    lr=self.opt.param_groups[0]['lr'],seconds=time.monotonic()-self.started)

    def run(self):
        completed=False;selected=None;baseline=None;error_text=None;reload_verified=False;changed=False
        try:
            baseline=self.evaluation(True);self.write('base_dev_nll.json',baseline)
            for epoch in range(self.cfg['epochs']):
                order=list(range(len(self.train)));random.Random(self.cfg['seed']+epoch).shuffle(order)
                for start in range(0,len(order),self.batch):
                    expired=time.monotonic()-self.started>=self.cfg['max_train_seconds']
                    if self.comm.sum([int(expired)])[0]:raise TimeoutError('Training time bound reached; incomplete epoch is not eligible')
                    record=self.update(order[start:start+self.batch])
                    record.update(epoch=epoch+1,rows_seen_epoch=min(start+self.batch,len(order)))
                    def log():
                        with (self.out/'train.jsonl').open('a',encoding='utf8') as stream:stream.write(json.dumps(record)+'\n')
                    self.comm.call(log,'Write training log',rank_zero=True)
                adapter_hash=self.comm.verify_parameters(self.named)
                checkpoint=self.out/f'epoch-{epoch+1}'
                self.comm.call(lambda:self.save_fn(checkpoint),'Save epoch checkpoint',rank_zero=True)
                scores=self.evaluation()
                eligible=all(scores.get(c,0)<=baseline.get(c,0)+self.cfg['max_retention_dev_nll_increase'] for c in ('code','literal'))
                entry=dict(epoch=epoch+1,path=str(checkpoint),dev_nll=scores,macro_nll=sum(scores.values())/len(scores),
                           retention_eligible=eligible,full_epoch=True,adapter_sha256=adapter_hash)
                self.epochs.append(entry);self.write('checkpoints.json',self.epochs)
            completed=self.step==self.total
            choices=[e for e in self.epochs if e['retention_eligible'] and e['full_epoch']]
            selected=min(choices,key=lambda e:e['macro_nll']) if choices else None
            changed=any(not torch.equal(before,p.detach().cpu()) for before,p in zip(self.initial,self.parameters))
            self.comm.check(None if changed and completed and selected else RuntimeError('Incomplete/unchanged/no eligible checkpoint'),'Training eligibility')
            # Validate last saved adapter against live last-epoch logits before
            # unloading; development selection is separate and not a release pass.
            self.comm.call(lambda:self.reload_fn(Path(self.epochs[-1]['path'])),'Disk reload logits',rank_zero=True)
            reload_verified=True
        except Exception as exc:
            error_text=type(exc).__name__+': '+str(exc)
            raise
        finally:
            report=dict(config=self.cfg,optimizer_steps=self.step,planned_optimizer_steps=self.total,
                epochs=self.epochs,selected=selected,training_completed=completed,
                disk_reload_logits_verified=reload_verified,world_size=self.comm.world,
                global_batch=self.batch,rank_local_batch='strided partition without duplicate padding',
                error=error_text,seconds=time.monotonic()-self.started,release_approved=False,
                adapter_changed=changed,optimizer_state='Fresh AdamW; no exact optimizer resume',
                selection_note='Development NLL only; original generation and semantic release gates still required.')
            # Best-effort local rank-zero failure report: no additional collective
            # in finally, because a failed/dead peer may never reach it.
            if self.comm.rank==0:
                (self.out/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        return report

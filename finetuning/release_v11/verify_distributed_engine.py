"""Exercise the real lifecycle on two CPU workers, not just its reducer."""
from datetime import timedelta
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import sys
import tempfile
import time
from types import SimpleNamespace

import torch
import torch.distributed as dist
import torch.multiprocessing as mp
from distributed_engine import Coordinator, TrainingEngine

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'bundle-v3'))
from answer_loss import answer_only_forward


class TinyAdapter(torch.nn.Module):
    def __init__(self):
        super().__init__();self.disabled=False
        self.embedding=torch.nn.Embedding(17,8);self.base=torch.nn.Linear(8,17,bias=False)
        self.a=torch.nn.Linear(8,3,bias=False);self.b=torch.nn.Linear(3,17,bias=False)
        self.embedding.requires_grad_(False);self.base.requires_grad_(False)
    def forward(self,input_ids,attention_mask=None,logits_to_keep=None):
        hidden=self.embedding(input_ids)
        if logits_to_keep is not None:hidden=hidden[:,logits_to_keep,:]
        logits=self.base(hidden)
        if not self.disabled:logits=logits+self.b(self.a(hidden))
        return SimpleNamespace(logits=logits)


def initial():
    torch.manual_seed(417);return TinyAdapter().double()


def samples(n):
    result=[]
    for i in range(n):
        ids=[(i*3+j)%17 for j in range(3+i%5)]
        result.append({'ids':ids,'labels':[-100,-100]+ids[2:],'row':{'id':str(i),'category':['code','literal','locale'][i%3]}})
    return result


def config():
    return dict(gradient_accumulation=8,retention_kl_weight=0.,learning_rate=.01,epochs=3,
                seed=731,warmup_ratio=.05,max_train_seconds=45,max_retention_dev_nll_increase=10.)


def loss(model,sample,disabled=False):
    model.disabled=disabled
    try:return answer_only_forward(model,torch.tensor([sample['ids']]),torch.tensor([sample['labels']]))[1]
    finally:model.disabled=False


def reference():
    model=initial();cfg=config();data=samples(9);params=[p for p in model.parameters() if p.requires_grad]
    opt=torch.optim.AdamW(params,lr=cfg['learning_rate'],weight_decay=.01)
    step=0;total=6;warmup=1
    for epoch in range(3):
        order=list(range(9));random.Random(cfg['seed']+epoch).shuffle(order)
        for start in range(0,9,8):
            batch=order[start:start+8];opt.zero_grad(set_to_none=True)
            scale=min(1.,(step+1)/warmup)*.5*(1+math.cos(math.pi*max(0,step-warmup)/max(1,total-warmup)))
            for group in opt.param_groups:group['lr']=cfg['learning_rate']*scale
            for i in batch:(loss(model,data[i])/len(batch)).backward()
            torch.nn.utils.clip_grad_norm_(params,1.);opt.step();step+=1
    return model


def worker(rank,folder,mode):
    torch.set_num_threads(1);root=Path(folder)
    dist.init_process_group('gloo',init_method=(root/'rendezvous').as_uri(),rank=rank,world_size=2,timeout=timedelta(seconds=15))
    try:
        model=initial()
        if rank==1:
            with torch.no_grad():model.a.weight.add_(2.) # must be overwritten by broadcast
        if mode=='nan' and rank==1:model.a.weight.register_hook(lambda grad:grad*float('nan'))
        seen=[];saved=[];reloaded=[]
        def compute(sample,disabled):
            if torch.is_grad_enabled():
                if mode=='forward-fail' and rank==1:raise RuntimeError('Injected forward failure')
                seen.append(sample['row']['id'])
            return loss(model,sample,disabled)
        def save(path):
            if mode=='save-fail':raise OSError('Injected checkpoint write failure')
            path.mkdir();torch.save(model.state_dict(),path/'adapter.pt');saved.append(str(path.name))
        def reload(path):
            restored=initial();restored.load_state_dict(torch.load(path/'adapter.pt',weights_only=True))
            probe=torch.tensor([[2,4,5]])
            with torch.no_grad():torch.testing.assert_close(model(probe).logits,restored(probe).logits,rtol=0,atol=0)
            reloaded.append(str(path.name))
        engine=TrainingEngine(model=model,train=samples(9),dev=samples(5),config=config(),coordinator=Coordinator('cpu'),
            loss_fn=compute,save_fn=save,reload_fn=reload,output=root/'outputs')
        error=None;report=None
        try:report=engine.run()
        except RuntimeError as exc:error=str(exc)
        result=dict(rank=rank,mode=mode,error=error,report=report,steps=engine.step,seen=seen,saved=saved,reloaded=reloaded,
            state={k:v.detach().tolist() for k,v in model.state_dict().items()})
        (root/f'rank-{rank}.json').write_text(json.dumps(result),encoding='utf8')
    finally:dist.destroy_process_group()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='DISTRIBUTED_ENGINE_VERIFIED.json');args=parser.parse_args()
    if Path(args.output).name!=args.output or (HERE/args.output).exists():raise ValueError('New report filename required')
    torch.set_num_threads(1);expected=reference();original=initial();started=time.monotonic();results={}
    for mode in ('success','forward-fail','nan','save-fail'):
        with tempfile.TemporaryDirectory(prefix='engine-check-',dir=HERE) as folder:
            began=time.monotonic();ctx=mp.spawn(worker,args=(folder,mode),nprocs=2,join=False)
            try:
                while not ctx.join(timeout=1):
                    if time.monotonic()-began>45:raise TimeoutError('Worker verification exceeded bound')
            finally:
                for process in ctx.processes:
                    if process.is_alive():process.terminate();process.join(timeout=5)
            current=[json.loads((Path(folder)/f'rank-{r}.json').read_text(encoding='utf8')) for r in range(2)]
            manifest=json.loads((Path(folder)/'outputs/manifest.json').read_text(encoding='utf8'))
            if mode=='success':
                assert all(r['error'] is None and r['steps']==6 for r in current)
                assert current[0]['saved']==['epoch-1','epoch-2','epoch-3'] and current[1]['saved']==[]
                assert current[0]['reloaded']==['epoch-3'] and current[1]['reloaded']==[]
                seen=current[0]['seen']+current[1]['seen']
                assert all(seen.count(str(i))==3 for i in range(9)) and len(seen)==27
                errors=[]
                for result in current:
                    for name,values in result['state'].items():
                        actual=torch.tensor(values,dtype=torch.float64)
                        error=(actual-expected.state_dict()[name]).abs().max().item();errors.append(error)
                        assert error<1e-7,(name,error)
                        if name.startswith(('embedding.','base.')):assert torch.equal(actual,original.state_dict()[name])
                assert manifest['training_completed'] and manifest['disk_reload_logits_verified']
                results[mode]={'optimizer_steps':6,'epochs':3,'per_epoch_samples':9,'no_duplicates_or_omissions':True,
                    'rank_zero_only_checkpoints_and_reload':True,'max_error_vs_independent_reference':max(errors),
                    'frozen_weights_unchanged':True,'ranks_identical':current[0]['state']==current[1]['state']}
            else:
                assert all(r['error'] for r in current)
                expected_steps=2 if mode=='save-fail' else 0
                assert all(r['steps']==expected_steps for r in current)
                assert not manifest['training_completed'] and not manifest['disk_reload_logits_verified'] and manifest['selected'] is None
                assert not list((Path(folder)/'outputs').glob('epoch-*'))
                results[mode]={'both_ranks_stopped':True,'steps_before_failure':expected_steps,'eligible_checkpoint':False}
    report=dict(backend='CPU/Gloo',two_real_workers=True,shared_production_engine=True,results=results,seconds=time.monotonic()-started,
        sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),HERE/'distributed_engine.py',HERE/'distributed_update.py']},
        limitations='Tiny adapter model; not NF4/CUDA/NCCL/PEFT serialization or speed verification.',release_approved=False)
    with (HERE/args.output).open('x',encoding='utf8') as out:json.dump(report,out,indent=2)
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()

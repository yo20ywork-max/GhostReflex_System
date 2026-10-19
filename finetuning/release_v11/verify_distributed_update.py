"""Two real CPU/Gloo processes vs one process; no model downloads or CUDA."""
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time

import torch
import torch.distributed as dist
import torch.multiprocessing as mp
from distributed_update import rank_batch, synchronize_gradients

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'contract_v8/training-bundle-v1'))
from answer_loss import answer_only_forward
from types import SimpleNamespace


class TinyAdapter(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.embedding=torch.nn.Embedding(17,8)
        self.base=torch.nn.Linear(8,17,bias=False)
        self.a=torch.nn.Linear(8,3,bias=False)
        self.b=torch.nn.Linear(3,17,bias=False)
        self.embedding.requires_grad_(False);self.base.requires_grad_(False)
    def forward(self,input_ids,attention_mask,logits_to_keep):
        hidden=self.embedding(input_ids)[:,logits_to_keep,:]
        return SimpleNamespace(logits=self.base(hidden)+self.b(self.a(hidden)))


def initial():
    torch.manual_seed(417)
    return TinyAdapter().double()


def sample(index):
    length=3+index%5
    ids=torch.tensor([[(index*3+j)%17 for j in range(length)]])
    labels=ids.clone();labels[:,:2]=-100
    return ids,labels


def run_steps(model,rank=None):
    params=[p for p in model.parameters() if p.requires_grad]
    opt=torch.optim.AdamW(params,lr=0.01,weight_decay=0.01)
    seen=[]
    # Last update is one sequence: rank 1 has no backward call.
    for batch in [list(range(8)),[8]]:
        chosen=batch if rank is None else rank_batch(batch,rank,2)
        opt.zero_grad(set_to_none=True)
        for i in chosen:
            ids,labels=sample(i)
            _,loss=answer_only_forward(model,ids,labels)
            (loss/len(batch) if rank is None else loss).backward()
            seen.append(i)
        if rank is not None:synchronize_gradients(params,local_samples=len(chosen),global_samples=len(batch),bucket_bytes=256)
        torch.nn.utils.clip_grad_norm_(params,1.0)
        opt.step()
    return seen


def worker(rank,folder):
    torch.set_num_threads(1)
    root=Path(folder)
    try:
        dist.init_process_group('gloo',init_method=(root/'rendezvous').as_uri(),rank=rank,world_size=2,timeout=timedelta(seconds=30))
        model=initial();seen=run_steps(model,rank)
        state={k:v.detach().tolist() for k,v in model.state_dict().items()}
        params=[p for p in model.parameters() if p.requires_grad]
        for p in params:p.grad=torch.zeros_like(p)
        if rank==1:params[0].grad.flatten()[0]=float('nan')
        rejected=False
        try:synchronize_gradients(params,local_samples=1,global_samples=2)
        except RuntimeError as exc:rejected='Non-finite local gradient' in str(exc)
        (root/f'rank-{rank}.json').write_text(json.dumps(dict(seen=seen,state=state,nonfinite_rejected=rejected)),encoding='utf8')
    finally:
        if dist.is_initialized():dist.destroy_process_group()


def main():
    torch.set_num_threads(1)
    if not dist.is_gloo_available():raise RuntimeError('Gloo unavailable; no verification claimed')
    expected=initial();original={k:v.detach().clone() for k,v in expected.state_dict().items()};run_steps(expected)
    started=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='distributed-check-',dir=HERE) as folder:
        ctx=mp.spawn(worker,args=(folder,),nprocs=2,join=False)
        try:
            while not ctx.join(timeout=1):
                if time.monotonic()-started>55:raise TimeoutError('Distributed verification exceeded 55 seconds')
        finally:
            for process in ctx.processes:
                if process.is_alive():process.terminate();process.join(timeout=5)
        results=[json.loads((Path(folder)/f'rank-{r}.json').read_text(encoding='utf8')) for r in range(2)]
    errors=[]
    for result in results:
        assert result['nonfinite_rejected']
        for name,values in result['state'].items():
            actual=torch.tensor(values,dtype=torch.float64)
            err=(actual-expected.state_dict()[name]).abs().max().item();errors.append(err)
            assert err<1e-7,(name,err)
            if name.startswith(('base.','embedding.')):assert torch.equal(actual,original[name])
    assert sorted(results[0]['seen']+results[1]['seen'])==list(range(9))
    assert not set(results[0]['seen'])&set(results[1]['seen'])
    report=dict(two_real_processes=True,backend='gloo',device='CPU',sequence_count=9,global_batches=[8,1],padding_duplicates=0,
        empty_rank_final_batch_handled=True,single_process_max_parameter_error=max(errors),frozen_weights_unchanged=True,
        all_ranks_rejected_nonfinite=True,seconds=time.monotonic()-started,
        sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),HERE/'distributed_update.py']},
        limitations='Small float64 adapter-shaped CPU model; actual selective-logit CE uses float32. Not NF4, NCCL, checkpoint/reload or GPU speed verification.',
        full_distributed_trainer_integrated=False,release_approved=False)
    target=HERE/'DISTRIBUTED_UPDATE_VERIFIED.json'
    if target.exists():raise FileExistsError(target)
    target.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()

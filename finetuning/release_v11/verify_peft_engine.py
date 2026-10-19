"""Actual PEFT + Transformers, two CPU workers, production lifecycle/callbacks."""
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
from distributed_engine import Coordinator,TrainingEngine
from train_distributed import AdapterOperations
from verify_distributed_engine import samples,config

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'bundle-v3'))


def worker(rank,folder):
    torch.set_num_threads(1)
    from transformers import Qwen2Config,Qwen2ForCausalLM,PreTrainedTokenizerFast
    from tokenizers import Tokenizer
    from tokenizers.models import WordLevel
    from peft import LoraConfig,get_peft_model
    root=Path(folder)
    dist.init_process_group('gloo',init_method=(root/'rendezvous').as_uri(),rank=rank,world_size=2,timeout=timedelta(seconds=30))
    try:
        torch.manual_seed(891)
        base=Qwen2ForCausalLM(Qwen2Config(vocab_size=32,hidden_size=16,intermediate_size=32,num_hidden_layers=1,
            num_attention_heads=2,num_key_value_heads=2,max_position_embeddings=64,pad_token_id=0,eos_token_id=2))
        base.config.use_cache=False
        model=get_peft_model(base,LoraConfig(r=2,lora_alpha=4,lora_dropout=0.,target_modules='all-linear',bias='none',task_type='CAUSAL_LM'))
        frozen={n:p.detach().clone() for n,p in model.named_parameters() if not p.requires_grad}
        tokenizer=PreTrainedTokenizerFast(tokenizer_object=Tokenizer(WordLevel({f't{i}':i for i in range(32)},unk_token='t0')),unk_token='t0')
        cfg=config();cfg['bf16_autocast']=False
        data=samples(9);operations=AdapterOperations(model,tokenizer,torch.device('cpu'),cfg,data[0])
        # Count actual production callbacks rather than mocking their effects.
        save_calls=[];reload_calls=[]
        def save(path):operations.save(path);save_calls.append(path.name)
        def reload(path):operations.reload(path);reload_calls.append(path.name)
        engine=TrainingEngine(model=model,train=data,dev=samples(5),config=cfg,coordinator=Coordinator('cpu'),
            loss_fn=operations.loss,save_fn=save,reload_fn=reload,output=root/'outputs')
        report=engine.run()
        # Rank zero has unloaded wrappers while reloading; compare frozen base
        # weights before callback separately via named lookup on rank one.
        unchanged=True
        if rank==1:unchanged=all(torch.equal(frozen[n],p.detach()) for n,p in model.named_parameters() if n in frozen)
        (root/f'rank-{rank}.json').write_text(json.dumps(dict(report=report,save_calls=save_calls,reload_calls=reload_calls,
            frozen_weights_unchanged=unchanged)),encoding='utf8')
    finally:dist.destroy_process_group()


def main():
    target=HERE/'PEFT_DISTRIBUTED_VERIFIED.json'
    if target.exists():raise FileExistsError(target)
    torch.set_num_threads(1);started=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='peft-engine-check-',dir=HERE) as folder:
        ctx=mp.spawn(worker,args=(folder,),nprocs=2,join=False)
        try:
            while not ctx.join(timeout=1):
                if time.monotonic()-started>55:raise TimeoutError('PEFT verification exceeded bound')
        finally:
            for process in ctx.processes:
                if process.is_alive():process.terminate();process.join(timeout=5)
        root=Path(folder);results=[json.loads((root/f'rank-{r}.json').read_text(encoding='utf8')) for r in range(2)]
        for result in results:
            assert result['report']['optimizer_steps']==6 and result['report']['training_completed']
            assert result['report']['disk_reload_logits_verified'] and result['report']['adapter_changed']
            assert result['frozen_weights_unchanged']
        assert results[0]['save_calls']==['epoch-1','epoch-2','epoch-3'] and not results[1]['save_calls']
        assert results[0]['reload_calls']==['epoch-3'] and not results[1]['reload_calls']
        artifacts=[]
        for epoch in range(1,4):
            path=root/'outputs'/f'epoch-{epoch}'
            for name in ('adapter_model.safetensors','adapter_config.json','tokenizer.json','tokenizer_config.json'):
                file=path/name;assert file.is_file()
                artifacts.append(dict(path=f'epoch-{epoch}/{name}',bytes=file.stat().st_size,sha256=hashlib.sha256(file.read_bytes()).hexdigest()))
        report=dict(two_real_workers=True,backend='CPU/Gloo',model='Random tiny Qwen2 transformer architecture with real PEFT LoRA; no model download',
            production_callbacks_verified=True,epochs=3,optimizer_steps=6,adapter_changed=True,
            rank_zero_only_save_and_reload=True,actual_safetensors_and_tokenizer_files_verified=True,disk_reload_logits_verified=True,
            frozen_weights_checked_on_rank_one=True,artifacts=artifacts,seconds=time.monotonic()-started,
            sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),HERE/'distributed_engine.py',HERE/'train_distributed.py']},
            limitations='No CUDA/NF4/NCCL, full-size model, GPU memory, or speed verification; temporary fixture artifacts cleaned after checks.',release_approved=False)
    target.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k!='artifacts'}),flush=True)


if __name__=='__main__':main()

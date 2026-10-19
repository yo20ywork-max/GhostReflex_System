"""Single-node torchrun QLoRA entry. Launch policy is checked before imports."""
import argparse
import contextlib
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parent


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


class AdapterOperations:
    """Production PEFT loss/save/reload callbacks, also exercised on CPU PEFT."""
    def __init__(self,model,tokenizer,device,config,probe):
        self.model=model;self.tokenizer=tokenizer;self.device=device;self.cfg=config;self.probe=probe

    def loss(self,sample,disabled=False):
        import torch
        from answer_loss import answer_only_forward
        ids=torch.tensor([sample['ids']],device=self.device)
        labels=torch.tensor([sample['labels']],device=self.device)
        with self.model.disable_adapter() if disabled else contextlib.nullcontext(),torch.autocast(
                self.device.type,dtype=torch.bfloat16,enabled=self.cfg.get('bf16_autocast',False)):
            _,loss=answer_only_forward(self.model,ids,labels)
        return loss

    def save(self,path):
        self.model.save_pretrained(path,safe_serialization=True)
        self.tokenizer.save_pretrained(path)

    def reload(self,path):
        import torch
        from peft import PeftModel
        model=self.model;model.eval()
        probe=torch.tensor([self.probe['ids'][:32]],device=self.device)
        with torch.no_grad():expected=model(input_ids=probe).logits[:,-1].float().cpu()
        base=model.unload()
        restored=PeftModel.from_pretrained(base,str(path),is_trainable=False);restored.eval()
        with torch.no_grad():actual=restored(input_ids=probe).logits[:,-1].float().cpu()
        torch.testing.assert_close(expected,actual,rtol=.002,atol=.002)
        self.model=restored


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='outputs')
    parser.add_argument('--preflight-only',action='store_true')
    args=parser.parse_args()
    if Path(args.output).name!=args.output:raise ValueError('Output must be a new direct child directory')
    lock=json.loads((ROOT/'DATA_LOCK.json').read_text(encoding='utf8'))
    for name,digest in lock['sha256'].items():
        if sha(ROOT/name)!=digest:raise RuntimeError('Locked file changed: '+name)
    required={'train_distributed.py','distributed_engine.py','distributed_update.py','answer_loss.py','train.py','config.json','train.jsonl','dev.jsonl','launch_guard.py'}
    if not required<=set(lock['sha256']):raise RuntimeError('Distributed runtime must be fully locked')
    from launch_guard import require_launch
    permit=require_launch(ROOT,lock,mode='preflight' if args.preflight_only else 'train')
    if os.environ.get('RUNPOD_POD_ID')!=permit['pod_id']:raise RuntimeError('Provider identity mismatch')
    world=int(os.environ.get('WORLD_SIZE','1'));rank=int(os.environ.get('RANK','0'));local=int(os.environ.get('LOCAL_RANK','0'))
    if world!=permit.get('gpu_count') or not 0<=rank<world or local!=rank or int(os.environ.get('LOCAL_WORLD_SIZE',str(world)))!=world:
        raise RuntimeError('Expected one process per approved GPU on one node')
    import torch
    import torch.distributed as dist
    if not torch.cuda.is_available() or local>=torch.cuda.device_count():raise RuntimeError('Approved CUDA device unavailable')
    torch.cuda.set_device(local);device=torch.device('cuda',local)
    if world>1:dist.init_process_group('nccl',timeout=timedelta(seconds=180))
    try:
        from distributed_engine import Coordinator,TrainingEngine
        comm=Coordinator(device)
        from train import tokenize_row,read_rows
        cfg=json.loads((ROOT/'config.json').read_text(encoding='utf8'))
        if not cfg.get('answer_logits_only') or cfg['retention_kl_weight']!=0:raise ValueError('Expected existing selective-logit gold retention configuration')
        from transformers import AutoTokenizer,AutoModelForCausalLM,BitsAndBytesConfig,set_seed
        from peft import LoraConfig,get_peft_model,prepare_model_for_kbit_training
        def load():
            set_seed(cfg['seed'])
            tokenizer=AutoTokenizer.from_pretrained(cfg['base'],revision=cfg['revision'],trust_remote_code=False)
            train=[tokenize_row(tokenizer,r,cfg['max_length']) for r in read_rows('train.jsonl')]
            dev=[tokenize_row(tokenizer,r,cfg['max_length']) for r in read_rows('dev.jsonl')]
            quant=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=torch.bfloat16)
            base=AutoModelForCausalLM.from_pretrained(cfg['base'],revision=cfg['revision'],quantization_config=quant,
                torch_dtype=torch.bfloat16,device_map={'':local},trust_remote_code=False,attn_implementation='sdpa')
            base=prepare_model_for_kbit_training(base,use_gradient_checkpointing=True);base.config.use_cache=False
            model=get_peft_model(base,LoraConfig(r=cfg['rank'],lora_alpha=cfg['alpha'],lora_dropout=0.,target_modules=cfg['target_modules'],bias='none',task_type='CAUSAL_LM'))
            return tokenizer,train,dev,model
        tokenizer,train,dev,model=comm.call(load,'Load model and data')
        operations=AdapterOperations(model,tokenizer,device,cfg,train[0])
        engine=TrainingEngine(model=model,train=train,dev=dev,config=cfg,coordinator=comm,loss_fn=operations.loss,
            save_fn=operations.save,reload_fn=operations.reload,output=ROOT/args.output)
        if args.preflight_only:
            longest=max(range(len(train)),key=lambda i:len(train[i]['ids']))
            # Intentionally stress every GPU with the longest sequence. These
            # repeated probes never enter a formal epoch or a saved adapter.
            torch.cuda.synchronize();began=time.monotonic()
            stress=engine.update([longest]*world)
            torch.cuda.synchronize();stress_seconds=time.monotonic()-began
            ordered=sorted(range(len(train)),key=lambda i:len(train[i]['ids']))
            sample_count=min(engine.batch,len(ordered))
            representative=[ordered[round(i*(len(ordered)-1)/max(1,sample_count-1))] for i in range(sample_count)]
            torch.cuda.synchronize();began=time.monotonic()
            measured=engine.update(representative)
            torch.cuda.synchronize();seconds=time.monotonic()-began
            engine.comm.verify_parameters(engine.named)
            local_report={'rank':rank,'gpu':torch.cuda.get_device_name(local),'peak_allocated_gib':torch.cuda.max_memory_allocated(local)/2**30,
                'peak_reserved_gib':torch.cuda.max_memory_reserved(local)/2**30,'longest_tokens':len(train[longest]['ids']),
                'longest_probe_seconds':stress_seconds,'global_batch_probe_seconds':seconds,'global_batch':len(representative)}
            reports=[None]*world
            if world>1:dist.all_gather_object(reports,local_report)
            else:reports=[local_report]
            report={'forward_backward_optimizer_passed':True,'optimizer_step_called':True,'adapter_saved':False,
                'training_candidate_produced':False,'world_size':world,'ranks':reports,'config':cfg,'stress_update':stress,
                'representative_update':measured,'representative_global_tokens':sum(len(train[i]['ids']) for i in representative),
                'training_tokens_per_epoch':sum(len(s['ids']) for s in train),'planned_optimizer_steps':engine.total,
                'bundle_lock_sha256':sha(ROOT/'DATA_LOCK.json'),'release_approved':False}
            engine.write('memory-time-preflight.json',report)
            if rank==0:print('MULTIGPU_PREFLIGHT '+json.dumps(report),flush=True)
        else:
            report=engine.run()
            report.update(data_lock_sha256=sha(ROOT/'DATA_LOCK.json'),trainer_sha256=sha(Path(__file__)),
                engine_sha256=sha(ROOT/'distributed_engine.py'),reducer_sha256=sha(ROOT/'distributed_update.py'))
            engine.write('manifest.json',report)
            def environment():
                (engine.out/'environment.txt').write_text(subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True),encoding='utf8')
            comm.call(environment,'Record environment',rank_zero=True)
            if rank==0:print('TRAINING_COMPLETE_RELOAD_VERIFIED',flush=True)
    finally:
        if dist.is_initialized():dist.destroy_process_group()


if __name__=='__main__':main()

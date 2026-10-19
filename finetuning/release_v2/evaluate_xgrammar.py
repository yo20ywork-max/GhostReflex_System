"""Fresh-process generation. Never execute tool plans; raw outputs preserved."""
import argparse
import contextlib
import hashlib
import json
from pathlib import Path
import time
from train import ROOT,verify_lock

def file_sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''):digest.update(block)
    return digest.hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--data',choices=['dev','test','regression'],required=True);p.add_argument('--adapter',required=True);p.add_argument('--output',required=True);p.add_argument('--base',action='store_true');p.add_argument('--batch-size',type=int,default=1);p.add_argument('--categories',nargs='+');args=p.parse_args()
    verify_lock();verify_lock('GRAMMAR_EVAL_LOCK.json');cfg=json.loads((ROOT/'config.json').read_text())
    rows=[json.loads(l) for l in (ROOT/(args.data+'.jsonl')).read_text(encoding='utf8').splitlines()]
    if args.data=='integration-dev':
        manifest=json.loads((ROOT/'INTEGRATION_MANIFEST.json').read_text(encoding='utf8'))
        if file_sha256(ROOT/'integration-dev.jsonl')!=manifest['data_sha256']:raise ValueError('Integration input changed')
    if args.data=='transfer-audit':
        manifest=json.loads((ROOT/'TRANSFER_AUDIT_LOCK.json').read_text(encoding='utf8'))
        if file_sha256(ROOT/'transfer-audit.jsonl')!=manifest['data_sha256']:raise ValueError('Transfer audit changed')
    if args.categories:
        if args.data!='dev':raise ValueError('Subset screening is restricted to development data')
        rows=[r for r in rows if r['category'] in args.categories]
        if not rows:raise ValueError('Empty screen')
    import torch
    from transformers import AutoTokenizer,AutoModelForCausalLM,BitsAndBytesConfig
    from peft import PeftModel
    tokenizer=AutoTokenizer.from_pretrained(cfg['base'],revision=cfg['revision'],padding_side='left')
    tokenizer.pad_token=tokenizer.eos_token
    quant=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=torch.bfloat16)
    base=AutoModelForCausalLM.from_pretrained(cfg['base'],revision=cfg['revision'],quantization_config=quant,torch_dtype=torch.bfloat16,device_map={'':0},trust_remote_code=False,attn_implementation='sdpa')
    model=PeftModel.from_pretrained(base,args.adapter,is_trainable=False);model.eval();model.config.use_cache=True
    adapter_hash=file_sha256(Path(args.adapter)/'adapter_model.safetensors')
    receipt={'base':cfg['base'],'base_revision':cfg['revision'],'adapter_path':args.adapter,'adapter_sha256':adapter_hash,'data':args.data,'data_sha256':file_sha256(ROOT/(args.data+'.jsonl')),'categories':args.categories,'rows_per_candidate':len(rows),'include_base':args.base,'batch_size':args.batch_size,'max_new_tokens':1024,'do_sample':False,'evaluation_script_sha256':file_sha256(__file__),'torch':torch.__version__,'complete':False}
    receipt_path=Path(args.output+'.provenance.json')
    with receipt_path.open('x',encoding='utf8') as stream:json.dump(receipt,stream,ensure_ascii=False,indent=2)
    eos_ids=model.generation_config.eos_token_id
    eos_ids=[eos_ids] if isinstance(eos_ids,int) else (eos_ids or [tokenizer.eos_token_id])
    import xgrammar as xgr
    import xgrammar.contrib.hf
    from importlib.metadata import version
    schema=json.loads((ROOT/'contract.json').read_text(encoding='utf8'))['schema']
    info=xgr.TokenizerInfo.from_huggingface(tokenizer,vocab_size=model.config.vocab_size,stop_token_ids=eos_ids)
    compiler=xgr.GrammarCompiler(info,max_threads=2)
    compiled=compiler.compile_json_schema(schema,strict_mode=False)
    receipt.update(grammar_engine='xgrammar',xgrammar_version=version('xgrammar'),strict_mode=False)
    ordered=sorted(rows,key=lambda r:len(r['system'])+len(r['prompt']))
    start=time.monotonic()
    with Path(args.output).open('x',encoding='utf8') as out:
        for mode in (['base','adapter'] if args.base else ['adapter']):
            for i in range(0,len(ordered),args.batch_size):
                batch=ordered[i:i+args.batch_size]
                texts=[tokenizer.apply_chat_template([{'role':'system','content':r['system']},{'role':'user','content':r['prompt']}],tokenize=False,add_generation_prompt=True) for r in batch]
                inputs=tokenizer(texts,return_tensors='pt',padding=True,add_special_tokens=False).to('cuda')
                if len(batch)!=1:raise ValueError('Use batch size 1 for auditable per-row grammar')
                plan=batch[0]['oracle']['type']=='plan'
                grammar={}
                if plan:grammar['logits_processor']=[xgr.contrib.hf.LogitsProcessor(compiled)]
                began=time.monotonic()
                with model.disable_adapter() if mode=='base' else contextlib.nullcontext(),torch.inference_mode():
                    generated=model.generate(**inputs,max_new_tokens=1024,max_time=120,do_sample=False,pad_token_id=tokenizer.pad_token_id,**grammar)
                elapsed=time.monotonic()-began
                for j,r in enumerate(batch):
                    suffix=generated[j,inputs['input_ids'].shape[1]:]
                    answer=tokenizer.decode(suffix,skip_special_tokens=True)
                    result={'id':r['id'],'category':r['category'],'group':r['group'],'candidate':mode,'text':answer,'completed':any(bool((suffix==eos).any()) for eos in eos_ids),'generated_tokens':int((suffix!=tokenizer.pad_token_id).sum()),'batch_seconds':elapsed,'prompt_sha256':hashlib.sha256((r['system']+'\n'+r['prompt']).encode()).hexdigest()}
                    result['schema_constrained']=plan
                    result['grammar_engine']='xgrammar' if plan else None
                    if plan:
                        try:json.loads(answer);result['json_parseable']=True
                        except ValueError:result['json_parseable']=False;result['completed']=False
                    result['base_revision']=cfg['revision']
                    result['adapter_sha256']=adapter_hash if mode=='adapter' else None
                    out.write(json.dumps(result,ensure_ascii=False)+'\n');out.flush()
                print(json.dumps({'mode':mode,'done':min(i+len(batch),len(rows)),'total':len(rows),'seconds':time.monotonic()-start}),flush=True)
    receipt.update(complete=True,output_sha256=file_sha256(args.output),seconds=time.monotonic()-start)
    receipt_path.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8')
    print('EVALUATION_COMPLETE',flush=True)

if __name__=='__main__':main()

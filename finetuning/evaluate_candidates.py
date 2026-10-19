"""Compare base and saved adapters using the same inputs and decoding settings."""
import argparse
import contextlib
import json
from pathlib import Path
import time
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel
from train_pilot import BASE, REVISION


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data',required=True)
    parser.add_argument('--adapters',nargs='+',required=True,help='name=path')
    parser.add_argument('--output',required=True)
    parser.add_argument('--max-seconds',type=int,default=900)
    parser.add_argument('--split',choices=['dev','test'],default='dev')
    args=parser.parse_args()
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA required')
    data=json.loads(Path(args.data).read_text(encoding='utf-8'))
    tokenizer=AutoTokenizer.from_pretrained(BASE,revision=REVISION)
    quant=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',
        bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=torch.bfloat16)
    base=AutoModelForCausalLM.from_pretrained(BASE,revision=REVISION,
        quantization_config=quant,torch_dtype=torch.bfloat16,device_map={'':0})
    adapters=[entry.split('=',1) for entry in args.adapters]
    model=PeftModel.from_pretrained(base,adapters[0][1],adapter_name=adapters[0][0])
    for name,path in adapters[1:]:
        model.load_adapter(path,adapter_name=name,is_trainable=False)
    model.eval()
    start=time.monotonic()
    with Path(args.output).open('x',encoding='utf-8') as out:
        for row in data['records']:
            # Training history questions are explicitly labelled diagnostics, not held-out scores.
            if row['split']!=args.split and not (args.split=='dev' and row['id'].startswith('history-')):
                continue
            messages=[{'role':'system','content':row.get('system',data['system'])},
                      {'role':'user','content':row['prompt']}]
            tokens=tokenizer.apply_chat_template(messages,tokenize=True,
                add_generation_prompt=True,return_tensors='pt').to('cuda')
            for name in ['base']+[a[0] for a in adapters]:
                if time.monotonic()-start>args.max_seconds:
                    print('EVAL_TIME_LIMIT',flush=True)
                    return
                if name!='base':
                    model.set_adapter(name)
                scope=model.disable_adapter() if name=='base' else contextlib.nullcontext()
                with scope,torch.inference_mode():
                    answer=model.generate(tokens,attention_mask=torch.ones_like(tokens),
                        max_new_tokens=512,max_time=40,do_sample=False,pad_token_id=tokenizer.eos_token_id)
                text=tokenizer.decode(answer[0,tokens.shape[1]:],skip_special_tokens=True)
                record={'id':row['id'],'split':row['split'],'candidate':name,'text':text,
                        'base_revision':REVISION,'prompt':row['prompt'],'system':messages[0]['content'],
                        'train_diagnostic':row['split']=='train'}
                out.write(json.dumps(record,ensure_ascii=False)+'\n')
                out.flush()
                print(json.dumps({'id':row['id'],'candidate':name,'text':text},ensure_ascii=False),flush=True)
    print('EVAL_DONE',flush=True)


if __name__=='__main__':
    main()

"""Bounded CUDA QLoRA pilot; saves and reload-verifies a real PEFT adapter.

Run on a provisioned CUDA host only, after budget/storage approval.
No cloud provisioning, code execution from model answers, or product installation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import time

BASE = 'Qwen/Qwen2.5-Coder-7B-Instruct'
REVISION = 'c03e6d358207e414f1eca0bb1891e29f1db0e242'


def validate(data):
    ids, groups, prompts, sources = set(), {}, set(), {}
    for row in data['records']:
        if row['id'] in ids or row['prompt'].strip() in prompts:
            raise ValueError('Duplicate id or prompt')
        ids.add(row['id'])
        prompts.add(row['prompt'].strip())
        if row['split'] not in ('train', 'dev', 'test'):
            raise ValueError('Invalid split')
        previous = groups.setdefault(row['group'], row['split'])
        if previous != row['split']:
            raise ValueError('Group leakage')
        if row.get('source_id'):
            previous_source_split = sources.setdefault(row['source_id'], row['split'])
            if previous_source_split != row['split']:
                raise ValueError('Source leakage')
        if row['split'] == 'train' and (not row.get('chosen') or not row.get('rejected')
                                       or row['chosen'] == row['rejected']):
            raise ValueError('Invalid training pair')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', default=str(Path(__file__).with_name('pilot_data.json')))
    parser.add_argument('--output', required=True)
    parser.add_argument('--side', choices=['chosen', 'rejected'], default='chosen')
    parser.add_argument('--steps', type=int, default=12)
    parser.add_argument('--max-seconds', type=int, default=900)
    parser.add_argument('--validate-only', action='store_true')
    parser.add_argument('--tokenize-only', action='store_true', help='Downloads tokenizer only, never model weights')
    parser.add_argument('--learning-rate', type=float, default=5e-5)
    parser.add_argument('--target-modules', choices=['qv','all-linear'], default='qv')
    parser.add_argument('--skip-generation', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.steps <= 160 or not 60 <= args.max_seconds <= 1800 or not 0 < args.learning_rate <= 2e-4:
        raise ValueError('Pilot limit exceeded')
    data_bytes = Path(args.data).read_bytes()
    data = json.loads(data_bytes)
    validate(data)
    if args.validate_only:
        print('DATA_VALID: engineering pilot only; historical efficacy not tested')
        return
    out = Path(args.output)
    if out.exists():
        raise FileExistsError('Use a new output path to preserve previous runs')
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(BASE, revision=REVISION, trust_remote_code=False)
    samples = []
    for row in data['records']:
        if row['split'] != 'train':
            continue
        messages = [{'role':'system','content':row.get('system', data['system'])}, {'role':'user','content':row['prompt']}]
        prefix = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True)
        full = tokenizer.apply_chat_template(messages + [{'role':'assistant','content':row[args.side]}],
                                             tokenize=True, add_generation_prompt=False)
        if full[:len(prefix)] != prefix or len(full) > 3072 or len(full) <= len(prefix):
            raise ValueError(f"Unexpected chat boundary or token length for {row['id']}: {len(full)}; do not truncate")
        labels = [-100] * len(prefix) + full[len(prefix):]
        samples.append((full, labels))
    if not samples:
        raise ValueError('No training records')
    if args.tokenize_only:
        print(json.dumps({'tokenized_train_rows':len(samples), 'max_tokens':max(len(s[0]) for s in samples),
                          'assistant_boundaries_verified':True,'base_revision':REVISION}))
        return
    import torch
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig, set_seed
    from peft import LoraConfig, PeftModel, get_peft_model, prepare_model_for_kbit_training
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA GPU required; no CPU training fallback')
    set_seed(42)
    start = time.monotonic()
    out.mkdir(parents=True)
    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type='nf4',
                              bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=dtype)
    base = AutoModelForCausalLM.from_pretrained(BASE, revision=REVISION,
        quantization_config=quant, torch_dtype=dtype, device_map={'': 0}, trust_remote_code=False)
    base = prepare_model_for_kbit_training(base, use_gradient_checkpointing=True)
    base.config.use_cache = False
    model = get_peft_model(base, LoraConfig(r=8, lora_alpha=16, lora_dropout=0.0,
        target_modules=['q_proj', 'v_proj'] if args.target_modules=='qv' else 'all-linear', bias='none', task_type='CAUSAL_LM'))
    samples = [(torch.tensor([ids], device='cuda'), torch.tensor([labels], device='cuda'))
               for ids, labels in samples]
    trainable = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(trainable, lr=args.learning_rate)
    logs = []
    model.train()
    order = []
    for step in range(args.steps):
        if time.monotonic() - start > args.max_seconds:
            break
        optimizer.zero_grad(set_to_none=True)
        losses = []
        for _ in range(2):
            if not order:
                order = list(range(len(samples)))
                random.shuffle(order)
            tokens, labels = samples[order.pop()]
            loss = model(input_ids=tokens, attention_mask=torch.ones_like(tokens), labels=labels).loss
            if not torch.isfinite(loss):
                raise RuntimeError('Non-finite training loss')
            (loss / 2).backward()
            losses.append(float(loss.detach()))
        torch.nn.utils.clip_grad_norm_(trainable, 1.0)
        optimizer.step()
        entry = {'step':step+1, 'loss':sum(losses)/len(losses), 'seconds':time.monotonic()-start}
        logs.append(entry)
        print(json.dumps(entry), flush=True)
    if not logs:
        raise RuntimeError('No optimizer step completed before deadline')
    changed = any(torch.count_nonzero(p.detach()).item() > 0
                  for name, p in model.named_parameters() if 'lora_B' in name)
    if not changed:
        raise RuntimeError('Adapter did not change from zero initialization')
    adapter = out / 'adapter'
    model.save_pretrained(adapter, safe_serialization=True)
    tokenizer.save_pretrained(adapter)
    probe = samples[0][0][:, :min(32, samples[0][0].shape[1])]
    model.eval()
    with torch.no_grad():
        expected = model(input_ids=probe).logits[:, -1].float().cpu()
    # Unload without merging, then read the adapter from disk into the same base.
    # This checks serialization; a fresh-process reload remains a release gate.
    del optimizer, trainable
    original_base = model.unload()
    del model
    reloaded = PeftModel.from_pretrained(original_base, adapter, is_trainable=False)
    reloaded.eval()
    with torch.no_grad():
        actual = reloaded(input_ids=probe).logits[:, -1].float().cpu()
    torch.testing.assert_close(actual, expected, rtol=0.002, atol=0.002)
    generations = []
    reloaded.config.use_cache = True
    reloaded.gradient_checkpointing_disable()
    for row in data['records']:
        if args.skip_generation or row['split'] != 'dev' or time.monotonic() - start > args.max_seconds:
            continue
        tokens = tokenizer.apply_chat_template([{'role':'system','content':row.get('system', data['system'])},
            {'role':'user','content':row['prompt']}], add_generation_prompt=True,
            tokenize=True, return_tensors='pt').to('cuda')
        for mode in ('base', 'adapter'):
            import contextlib
            scope = reloaded.disable_adapter() if mode == 'base' else contextlib.nullcontext()
            with scope, torch.no_grad():
                answer = reloaded.generate(tokens, attention_mask=torch.ones_like(tokens),
                    max_new_tokens=512, max_time=45, do_sample=False, pad_token_id=tokenizer.eos_token_id)
            generations.append({'id':row['id'], 'mode':mode,
                'text':tokenizer.decode(answer[0, tokens.shape[1]:], skip_special_tokens=True)})
    manifest = {'base':BASE,'revision':REVISION,'side':args.side,
        'data_sha256':hashlib.sha256(data_bytes).hexdigest(), 'steps':logs,
        'adapter_changed':changed,'disk_reload_logits_verified':True,
        'learning_rate':args.learning_rate,'target_modules':args.target_modules,
        'generations':generations,'release_approved':False,
        'limitations':'Tiny mixed pilot. No claim of political-bias removal or unseen-task reliability.'}
    (out/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    import subprocess, sys
    (out/'environment.txt').write_text(subprocess.check_output([sys.executable,'-m','pip','freeze'], text=True), encoding='utf-8')
    print('TRAIN_SAVED_AND_RELOADED', flush=True)


if __name__ == '__main__':
    main()

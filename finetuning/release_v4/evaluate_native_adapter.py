"""Bounded post-training NF4 generation diagnostic, using already-cached weights.

Same visible dev messages as Ollama, not an assertion of backend/token parity.
No grammar-constrained categories, final holdouts, tool execution or model upload.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import time


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def preflight(root, epoch):
    root = root.resolve()
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            cwd = (proc / 'cwd').resolve()
            args = (proc / 'cmdline').read_bytes().split(b'\0')
        except (OSError, RuntimeError):
            continue
        if cwd == root and any(arg in (b'train.py', b'cloud_run.sh') for arg in args):
            raise RuntimeError('Original training is live; do not compete for its GPU')
    lock = json.loads((root / 'DATA_LOCK.json').read_text())
    for name, digest in lock['sha256'].items():
        if sha(root / name) != digest:
            raise ValueError('Locked source changed: ' + name)
    manifest = json.loads((root / 'outputs/manifest.json').read_text())
    if not manifest.get('training_completed') or not manifest.get('disk_reload_logits_verified'):
        raise ValueError('Verified terminal training required')
    entries = json.loads((root / 'outputs/checkpoints.json').read_text())
    if not any(row['epoch'] == epoch and row['full_epoch'] for row in entries):
        raise ValueError('Full checkpoint required')
    rows = [json.loads(line) for line in (root / 'dev.jsonl').read_text().splitlines()]
    rows = [row for row in rows if row['category'] in {'identity', 'grounded'}]
    if len(rows) != 16 or sum(row['category'] == 'identity' for row in rows) != 4:
        raise ValueError('Expected original 4 identity and 12 grounded development cases')
    if any(row['oracle']['type'] in {'plan', 'completion'} for row in rows):
        raise ValueError('Only unconstrained text categories are supported')
    checkpoint = root / 'outputs' / f'epoch-{epoch}'
    return lock, rows, checkpoint


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--epoch', type=int, choices=(1, 2, 3), required=True)
    parser.add_argument('--deadline-utc', required=True)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    deadline = datetime.fromisoformat(args.deadline_utc)
    if deadline.tzinfo is None or (deadline - datetime.now(timezone.utc)).total_seconds() < 720:
        raise ValueError('At least 12 minutes before the provider deadline required')
    root = args.root.resolve()
    lock, rows, checkpoint = preflight(root, args.epoch)
    if args.validate_only:
        print(json.dumps({'rows': len(rows), 'training_terminal': True, 'locked_sources_valid': True}))
        return
    destination = root / 'outputs' / f'backend-e{args.epoch}'
    destination.mkdir(exist_ok=False)
    (destination / 'evaluate.py').write_bytes(Path(__file__).read_bytes())
    watched = [root / 'DATA_LOCK.json', root / 'dev.jsonl', root / 'config.json',
               checkpoint / 'adapter_model.safetensors', checkpoint / 'adapter_config.json', Path(__file__)]
    before = {str(path): sha(path) for path in watched}
    cfg = json.loads((root / 'config.json').read_text())
    # Forbid accidental downloads or additional persistent weight copies.
    cache = root / 'hf-cache'
    if not cache.is_dir():
        raise ValueError('The original training cache is missing')
    os.environ['HF_HOME'] = str(cache)
    os.environ['HF_HUB_CACHE'] = str(cache / 'hub')
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    os.environ['OMP_NUM_THREADS'] = '4'
    def expired(*_):
        raise TimeoutError('Ten-minute native-backend diagnostic limit reached')
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(600)
    started = time.monotonic()
    import torch
    import transformers
    import peft
    from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
    from peft import PeftModel, prepare_model_for_kbit_training
    tokenizer = AutoTokenizer.from_pretrained(cfg['base'], revision=cfg['revision'], local_files_only=True, trust_remote_code=False)
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type='nf4', bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16)
    base = AutoModelForCausalLM.from_pretrained(cfg['base'], revision=cfg['revision'], local_files_only=True,
        trust_remote_code=False, quantization_config=quant, torch_dtype=torch.bfloat16, device_map={'': 0}, attn_implementation='sdpa')
    # Match the training base's nonquantized parameter casts, without enabling
    # gradient checkpointing or creating an optimizer for this inference run.
    base = prepare_model_for_kbit_training(base, use_gradient_checkpointing=False)
    model = PeftModel.from_pretrained(base, str(checkpoint), is_trainable=False, local_files_only=True)
    model.eval()
    options = {'do_sample': False, 'max_new_tokens': 1024, 'repetition_penalty': 1.0, 'use_cache': True}
    metadata = {'epoch': args.epoch, 'source_hashes': before, 'base': cfg['base'], 'revision': cfg['revision'],
        'quantization': quant.to_dict(), 'training_base_parameter_casts_reused': True,
        'generate_options': options, 'chat_template': tokenizer.chat_template,
        'generation_config': model.generation_config.to_dict(), 'torch': torch.__version__, 'transformers': transformers.__version__,
        'peft': peft.__version__, 'gpu': torch.cuda.get_device_name(), 'cache_dir': str(cache), 'cases': [row['id'] for row in rows],
        'scope': 'Original known development text cases, native NF4+PEFT backend. Visible messages match local development; quantization/runtime may produce different tokens. No native app or semantic pass claim.',
        'release_approved': False}
    (destination / 'manifest.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
    records = []
    with (destination / 'results.jsonl').open('x', encoding='utf8') as stream:
        for row in rows:
            messages = [{'role': 'system', 'content': row['system']}, {'role': 'user', 'content': row['prompt']}]
            tokens = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True)
            if len(tokens) + options['max_new_tokens'] > 12288:
                raise ValueError('Would exceed the local comparison context; no truncation allowed')
            ids = torch.tensor([tokens], device='cuda')
            began = time.monotonic()
            with torch.inference_mode(), torch.autocast('cuda', dtype=torch.bfloat16):
                output = model.generate(input_ids=ids, attention_mask=torch.ones_like(ids), **options)
            generated = output[0, len(tokens):].tolist()
            eos = model.generation_config.eos_token_id
            eos = [eos] if isinstance(eos, int) else eos
            record = {'id': row['id'], 'category': row['category'], 'messages': messages, 'input_ids': tokens,
                'output_ids': generated, 'text': tokenizer.decode(generated, skip_special_tokens=True),
                'completed': bool(generated and generated[-1] in (eos or [])), 'seconds': time.monotonic() - began,
                'prompt_sha256': hashlib.sha256((row['system'] + '\n' + row['prompt']).encode()).hexdigest()}
            stream.write(json.dumps(record, ensure_ascii=False) + '\n')
            stream.flush()
            records.append(record)
            print(json.dumps({key: record[key] for key in ('id', 'completed', 'seconds')}), flush=True)
    stable = all(sha(Path(path)) == digest for path, digest in before.items())
    summary = {'rows': len(records), 'complete_generations': sum(row['completed'] for row in records),
        'source_hashes_unchanged': stable, 'results_sha256': sha(destination / 'results.jsonl'),
        'seconds': time.monotonic() - started, 'max_allocated_vram_gib': torch.cuda.max_memory_allocated() / 2**30,
        'semantic_review_required': True, 'release_approved': False}
    (destination / 'generation-complete.json').write_text(json.dumps(summary, indent=2))
    signal.alarm(0)
    print(json.dumps(summary), flush=True)
    if not stable or len(records) != 16:
        raise RuntimeError('Native diagnostic incomplete or mixed sources')


if __name__ == '__main__':
    main()

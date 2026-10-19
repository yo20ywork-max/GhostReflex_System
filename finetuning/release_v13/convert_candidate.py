"""Offline, bounded conversion of one verified v13 checkpoint; never installs a model."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

R = Path(__file__).resolve().parent
CONVERTER = R.parent / 'release_v2/llama.cpp'
PIN = '6a1a922d269908a29cbd4b49c27e6a8e7fd10fae'


def sha(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--epoch', type=int, choices=(1, 2, 3), required=True)
    args = parser.parse_args()
    receipt = json.loads((R / f'EPOCH-{args.epoch}_TRANSFER_VERIFIED.json').read_text(encoding='utf8'))
    if not receipt['transfer_verified'] or receipt['epoch'] != args.epoch:
        raise ValueError('Missing matching transfer verification')
    rows = {row['path']: row for row in receipt['files']}
    source = R / 'artifacts/outputs' / f'epoch-{args.epoch}'
    for name in ('adapter_config.json', 'adapter_model.safetensors'):
        expected = rows[f'outputs/epoch-{args.epoch}/{name}']
        if (source / name).stat().st_size != expected['bytes'] or sha(source / name) != expected['sha256']:
            raise ValueError('Verified adapter changed')
    cfg = json.loads((R / 'config.json').read_text(encoding='utf8'))
    adapter = json.loads((source / 'adapter_config.json').read_text(encoding='utf8'))
    if adapter['r'] != cfg['rank'] or adapter['lora_alpha'] != cfg['alpha'] or adapter['base_model_name_or_path'] != cfg['base']:
        raise ValueError('Unexpected adapter configuration')
    revision = subprocess.check_output(['git', '-C', str(CONVERTER), 'rev-parse', 'HEAD'], text=True).strip()
    changes = subprocess.check_output(['git', '-C', str(CONVERTER), 'status', '--porcelain', '--untracked-files=no'], text=True)
    if revision != PIN or changes.strip():
        raise ValueError('Converter checkout differs from verified version')
    folder = R / 'local-adapters'
    folder.mkdir(exist_ok=True)
    if shutil.disk_usage(folder).free < 1_000_000_000:
        raise ValueError('Insufficient conversion disk headroom')
    target = folder / f'epoch-{args.epoch}.gguf'
    if target.exists():
        raise FileExistsError(target)
    environment = dict(os.environ, HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    command = [sys.executable, str(CONVERTER / 'convert_lora_to_gguf.py'), '--base', str(R.parent / 'release_v2/tokenizer'),
               '--outtype', 'f32', '--outfile', str(target), str(source)]
    with target.with_suffix('.convert.log').open('x', encoding='utf8') as log:
        subprocess.run(command, env=environment, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
    if not 0 < target.stat().st_size < 400_000_000:
        raise ValueError('Unexpected converted size')
    subprocess.run([sys.executable, str(R / 'verify_local_adapter.py'), '--epoch', str(args.epoch)], check=True, timeout=90)
    record = {'epoch': args.epoch, 'source_receipt_sha256': sha(R / f'EPOCH-{args.epoch}_TRANSFER_VERIFIED.json'),
              'converter_commit': PIN, 'converter_file_sha256': sha(CONVERTER / 'convert_lora_to_gguf.py'),
              'base_config_sha256': sha(R.parent / 'release_v2/tokenizer/config.json'), 'gguf_sha256': sha(target),
              'conversion_verified': True, 'model_installed': False, 'release_approved': False}
    with target.with_suffix('.conversion-provenance.json').open('x', encoding='utf8') as stream:
        json.dump(record, stream, indent=2)
    print(json.dumps(record), flush=True)


if __name__ == '__main__':
    main()

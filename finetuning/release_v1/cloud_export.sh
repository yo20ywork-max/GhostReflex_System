#!/usr/bin/env bash
set -euo pipefail
cd /workspace/crossgen-release-v1
export HF_HOME=/workspace/crossgen-release-v1/hf-cache
export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=8
python -c 'import json; assert json.load(open("RELEASE_GATE.json"))["release_approved"]'
mkdir -p export
selected=$(cat selected.txt)
timeout 30m python export_gguf.py --llama-dir llama.cpp --adapter "$selected" --output export/crossgen-agi-mu-f16.gguf
timeout 20m quantizer/llama-b10819/llama-quantize export/crossgen-agi-mu-f16.gguf export/crossgen-agi-mu-q4_k_m.gguf Q4_K_M 8
python -c 'from pathlib import Path; import hashlib,json; p=Path("export/crossgen-agi-mu-q4_k_m.gguf"); h=hashlib.sha256(); f=p.open("rb"); [h.update(b) for b in iter(lambda:f.read(4*1024*1024),b"")]; d={"file":p.name,"bytes":p.stat().st_size,"sha256":h.hexdigest(),"format":"Q4_K_M","quantized_from":"F16 full-precision base merged with selected LoRA","runtime_release_approved":False}; Path("q4-receipt.json").write_text(json.dumps(d,indent=2)); print(json.dumps(d))'
echo GGUF_EXPORT_DONE

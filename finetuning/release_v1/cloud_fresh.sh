#!/usr/bin/env bash
set -euo pipefail
cd /workspace/crossgen-release-v1
export HF_HOME=/workspace/crossgen-release-v1/hf-cache
export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=4
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
test ! -e outputs/fresh-r1
timeout 50m python train.py --output outputs/fresh-r1 --config fresh-config.json --train-data grounding-train.jsonl --lock FRESH_LOCK.json
python -c 'import json; print(json.load(open("outputs/fresh-r1/manifest.json"))["selected"]["path"])' > fresh-selected.txt
cp outputs/fresh-r1/manifest.json fresh-manifest.json
selected=$(cat fresh-selected.txt)
timeout 20m python evaluate.py --data dev --adapter "$selected" --output outputs/dev-fresh.jsonl
timeout 10m python evaluate.py --data regression --adapter "$selected" --output outputs/regression-fresh.jsonl
echo FRESH_TRAIN_AND_DEV_DONE

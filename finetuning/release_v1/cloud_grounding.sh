#!/usr/bin/env bash
set -euo pipefail
cd /workspace/crossgen-release-v1
export HF_HOME=/workspace/crossgen-release-v1/hf-cache
export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=4
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
test ! -e outputs/grounding-r1
python -m unittest test_answer_loss -v
python train.py --tokenize-only --config grounding-bf16-config.json --train-data grounding-train.jsonl --lock GROUNDING_BF16_LOCK.json
timeout 55m python train.py --output outputs/grounding-r1 --config grounding-bf16-config.json --train-data grounding-train.jsonl --lock GROUNDING_BF16_LOCK.json --init-adapter outputs/repair-r1/epoch-1
python -c 'import json; print(json.load(open("outputs/grounding-r1/manifest.json"))["selected"]["path"])' > grounding-selected.txt
selected=$(cat grounding-selected.txt)
timeout 20m python evaluate.py --data dev --adapter "$selected" --output outputs/dev-grounding.jsonl
timeout 10m python evaluate.py --data regression --adapter "$selected" --output outputs/regression-grounding.jsonl
echo GROUNDING_TRAIN_AND_DEV_DONE

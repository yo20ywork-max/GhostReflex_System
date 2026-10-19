#!/usr/bin/env bash
set -euo pipefail
cd /workspace/crossgen-release-v1
export HF_HOME=/workspace/crossgen-release-v1/hf-cache
export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=4
test ! -e outputs/repair-r1
timeout 100m python train.py --output outputs/repair-r1 --config repair-config.json --train-data repair-train.jsonl --lock REPAIR_LOCK.json --init-adapter outputs/epoch-3
python -c 'import json; print(json.load(open("outputs/repair-r1/manifest.json"))["selected"]["path"])' > repair-selected.txt
selected=$(cat repair-selected.txt)
timeout 20m python evaluate.py --data dev --adapter "$selected" --output outputs/dev-repair.jsonl
timeout 10m python evaluate.py --data regression --adapter "$selected" --output outputs/regression-repair.jsonl
echo REPAIR_TRAIN_AND_DEV_DONE

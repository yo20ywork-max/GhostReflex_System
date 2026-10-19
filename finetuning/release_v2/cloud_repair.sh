#!/usr/bin/env bash
set -euo pipefail
cd /workspace/crossgen-release-v2
export HF_HOME=/workspace/crossgen-release-v2/hf-cache
export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=4
python -c 'import json; from train import verify_lock; verify_lock("REPAIR_HISTORY_LOCK.json"); m=json.load(open("outputs/manifest.json")); assert m["disk_reload_logits_verified"] and m["training_completed"]'
timeout 45m python train.py --output outputs-repair --config repair-config.json --train-data repair-history-train.jsonl --lock REPAIR_HISTORY_LOCK.json --init-adapter outputs/epoch-2
timeout 25m python evaluate.py --data dev --adapter outputs-repair/epoch-1 --output outputs-repair/dev-repair.jsonl
timeout 25m python evaluate.py --data dev --adapter comparison-v1-fusion --output outputs/dev-prior-fusion.jsonl
echo REPAIR_AND_COMPARISON_DONE

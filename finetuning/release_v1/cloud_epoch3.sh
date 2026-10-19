#!/usr/bin/env bash
set -euo pipefail
cd /workspace/crossgen-release-v1
export HF_HOME=/workspace/crossgen-release-v1/hf-cache
export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=4
timeout 20m python evaluate.py --data dev --adapter outputs/epoch-3 --output outputs/dev-epoch3.jsonl
timeout 10m python evaluate.py --data regression --adapter outputs/epoch-3 --output outputs/regression-epoch3.jsonl
echo EPOCH3_REVIEW_DONE

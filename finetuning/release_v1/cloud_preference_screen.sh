#!/usr/bin/env bash
set -euo pipefail
cd /workspace/crossgen-release-v1
export HF_HOME=/workspace/crossgen-release-v1/hf-cache
export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=4
timeout 20m python evaluate.py --data dev --adapter outputs/preferences-r1/epoch-2 --output outputs/dev-preferences-e2.jsonl
timeout 10m python evaluate.py --data regression --adapter outputs/preferences-r1/epoch-2 --output outputs/regression-preferences-e2.jsonl
echo PREFERENCE_EPOCH_TWO_GENERATION_DONE

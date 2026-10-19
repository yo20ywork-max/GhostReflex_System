#!/usr/bin/env bash
set -euo pipefail
cd /workspace/crossgen-release-v1
export HF_HOME=/workspace/crossgen-release-v1/hf-cache
export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=4
timeout 20m python evaluate.py --data dev --adapter outputs/grounding-r1/epoch-2 --output outputs/dev-grounding-e2.jsonl
timeout 10m python evaluate.py --data regression --adapter outputs/grounding-r1/epoch-2 --output outputs/regression-grounding-e2.jsonl
echo GROUNDING_EPOCH_TWO_EVALUATED

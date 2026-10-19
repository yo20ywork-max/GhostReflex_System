#!/usr/bin/env bash
set -euo pipefail
cd /workspace/crossgen-release-v1
export HF_HOME=/workspace/crossgen-release-v1/hf-cache
export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=4
for epoch in 2 3; do
  timeout 10m python evaluate.py --data dev --adapter "outputs/repair-r1/epoch-$epoch" --output "outputs/dev-repair-e$epoch-screen.jsonl" --categories identity code asr locale grounded calibration literal
  timeout 10m python evaluate.py --data regression --adapter "outputs/repair-r1/epoch-$epoch" --output "outputs/regression-repair-e$epoch-screen.jsonl"
done
echo REPAIR_SCREEN_DONE

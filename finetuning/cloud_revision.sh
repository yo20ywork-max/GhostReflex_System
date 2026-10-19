#!/usr/bin/env bash
set -euo pipefail
cd /workspace/crossgen-pilot
export HF_HOME=/workspace/crossgen-pilot/hf-cache
export HF_HUB_DISABLE_XET=0
export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=4
timeout 20m python train_pilot.py --data revision_pilot_data.json --output outputs/revision --side chosen --steps 80 --max-seconds 900 --target-modules all-linear --learning-rate 0.0002 --skip-generation
timeout 15m python evaluate_candidates.py --data product_pilot_data.json --adapters revision=outputs/revision/adapter --output outputs/revision-comparison.jsonl --max-seconds 800
echo REVISION_DONE

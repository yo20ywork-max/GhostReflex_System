#!/usr/bin/env bash
set -euo pipefail
cd /workspace/crossgen-pilot
export HF_HOME=/workspace/crossgen-pilot/hf-cache
export HF_HUB_DISABLE_XET=0
export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=4
timeout 10m python train_pilot.py --data error_direction_data.json --output outputs/error-all-linear --side rejected --steps 8 --max-seconds 300 --target-modules all-linear --skip-generation
python export_counter.py --chosen outputs/revision/adapter --error outputs/error-all-linear/adapter --alpha 0.1 --output outputs/revision-counter-010
timeout 15m python evaluate_candidates.py --data product_pilot_data.json --adapters revision=outputs/revision/adapter counter=outputs/revision-counter-010 --output outputs/revision-counter-comparison.jsonl --max-seconds 800
echo REVISION_COUNTER_DONE

#!/usr/bin/env bash
set -euo pipefail
cd /workspace/crossgen-pilot
export HF_HOME=/workspace/crossgen-pilot/hf-cache
export HF_HUB_DISABLE_XET=0
export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=4
python export_counter.py --chosen outputs/chosen/adapter --error outputs/error/adapter --alpha 0.1 --output outputs/counter-010
timeout 20m python evaluate_candidates.py --data product_pilot_data.json --adapters chosen=outputs/chosen/adapter counter=outputs/counter-010 --output outputs/comparison.jsonl --max-seconds 900
echo COUNTER_COMPARISON_DONE

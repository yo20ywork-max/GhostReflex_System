#!/usr/bin/env bash
set -euo pipefail
cd /workspace/crossgen-pilot
export HF_HOME=/workspace/crossgen-pilot/hf-cache
export HF_HUB_DISABLE_XET=0
export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=4
timeout 12m python evaluate_candidates.py --data product_pilot_data.json --split test --adapters revision=outputs/revision/adapter --output outputs/heldout.jsonl --max-seconds 600
timeout 12m python evaluate_candidates.py --data transfer_probes.json --split test --adapters revision=outputs/revision/adapter --output outputs/transfer.jsonl --max-seconds 600
echo HOLDOUT_DONE

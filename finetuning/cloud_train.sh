#!/usr/bin/env bash
set -euo pipefail
cd /workspace/crossgen-pilot
export HF_HOME=/workspace/crossgen-pilot/hf-cache
export HF_HUB_DISABLE_XET=0
export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=4
timeout 25m python train_pilot.py --data product_pilot_data.json --output outputs/chosen --side chosen --steps 40 --max-seconds 900
echo CHOSEN_RUN_DONE

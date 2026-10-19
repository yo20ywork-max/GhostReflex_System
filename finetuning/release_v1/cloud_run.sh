#!/usr/bin/env bash
set -euo pipefail
cd /workspace/crossgen-release-v1
export HF_HOME=/workspace/crossgen-release-v1/hf-cache
export HF_HUB_DISABLE_XET=0
export HF_XET_NUM_CONCURRENT_RANGE_GETS=8
export PIP_NO_CACHE_DIR=1
export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=4
python -m pip install --break-system-packages --no-cache-dir -r requirements-cloud.txt
python -c 'import torch; assert torch.cuda.is_available(); print(torch.__version__,torch.cuda.get_device_name(0))'
timeout 160m python train.py --output outputs
python -c 'import json; print(json.load(open("outputs/manifest.json"))["selected"]["path"])' > selected.txt
selected=$(cat selected.txt)
timeout 30m python evaluate.py --data dev --adapter "$selected" --base --output outputs/dev.jsonl
timeout 10m python evaluate.py --data regression --adapter "$selected" --base --output outputs/regression.jsonl
echo TRAIN_AND_DEV_DONE

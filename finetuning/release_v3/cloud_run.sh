#!/usr/bin/env bash
set -euo pipefail
cd /workspace/crossgen-release-v3
export HF_HOME=/workspace/crossgen-release-v3/hf-cache
export HF_HUB_DISABLE_XET=0
export HF_XET_NUM_CONCURRENT_RANGE_GETS=8
export PIP_NO_CACHE_DIR=1
export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=4
python -m pip install --break-system-packages --no-cache-dir -r requirements-cloud.txt
python -c 'import torch; assert torch.cuda.is_available(); print(torch.__version__,torch.cuda.get_device_name(0))'
timeout 190m python train.py --output outputs
echo TRAINING_AND_RELOAD_COMPLETE

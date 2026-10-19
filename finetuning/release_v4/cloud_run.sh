#!/usr/bin/env bash
set -euo pipefail
cd /workspace/crossgen-release-v4
export HF_HOME=/workspace/crossgen-release-v4/hf-cache
export HF_XET_NUM_CONCURRENT_RANGE_GETS=8
export PIP_NO_CACHE_DIR=1
export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=4
mode="${1:-preflight}"
case "$mode" in
  preflight|train) ;;
  *) echo "Expected preflight or train" >&2; exit 2 ;;
esac
# Keep the template's CUDA torch. No second torch or model cache installation.
python -m pip install --break-system-packages --no-cache-dir -r requirements-cloud.txt
python -c 'import torch; assert torch.cuda.is_available(); print(torch.__version__,torch.cuda.get_device_name(0))'
if [ "$mode" = preflight ]; then
  timeout 45m python train.py --preflight-only --output preflight
  echo MEMORY_PREFLIGHT_COMPLETE
else
  python -c 'import json; p=json.load(open("preflight/memory-time-preflight.json")); assert p["forward_backward_optimizer_passed"] and not p["adapter_saved"]'
  timeout 190m python train.py --output outputs
  echo TRAINING_AND_RELOAD_COMPLETE
fi

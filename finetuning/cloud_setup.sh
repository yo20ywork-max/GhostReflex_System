#!/usr/bin/env bash
set -euo pipefail
cd /workspace/crossgen-pilot
export HF_HOME=/workspace/crossgen-pilot/hf-cache
export PIP_NO_CACHE_DIR=1
export HF_HUB_DISABLE_XET=1
python -m pip install --break-system-packages --no-cache-dir -r requirements-cloud.txt
python -c 'import torch, transformers, peft, bitsandbytes; assert torch.cuda.is_available(); print(torch.__version__, torch.cuda.get_device_name(0), transformers.__version__, peft.__version__, bitsandbytes.__version__)'
echo SETUP_READY

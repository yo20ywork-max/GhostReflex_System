#!/usr/bin/env bash
set -euo pipefail
cd /workspace/crossgen-release-v1
export HF_HOME=/workspace/crossgen-release-v1/hf-cache
export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=4
python -m unittest test_fusion_delta -v
timeout 10m python fuse_adapters.py
timeout 20m python evaluate.py --data dev --adapter outputs/fusion-r1/fusion --output outputs/dev-fusion.jsonl
timeout 10m python evaluate.py --data regression --adapter outputs/fusion-r1/fusion --output outputs/regression-fusion.jsonl
echo FUSION_EVALUATED

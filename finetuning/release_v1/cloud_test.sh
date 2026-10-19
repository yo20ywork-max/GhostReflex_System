#!/usr/bin/env bash
set -euo pipefail
cd /workspace/crossgen-release-v1
export HF_HOME=/workspace/crossgen-release-v1/hf-cache
export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=4
test ! -e outputs/test.jsonl
selected=$(cat selected.txt)
timeout 30m python evaluate.py --data test --adapter "$selected" --base --output outputs/test.jsonl
echo HELDOUT_TEST_DONE

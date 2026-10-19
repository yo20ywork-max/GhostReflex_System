#!/usr/bin/env bash
set -euo pipefail
cd /workspace/crossgen-release-v1
export HF_HOME=/workspace/crossgen-release-v1/hf-cache
export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=4
test ! -e outputs/preferences-r1
selected=$(cat preference-init.txt)
timeout 65m python train_preferences.py --adapter "$selected" --output outputs/preferences-r1
python -c 'import json; print(json.load(open("outputs/preferences-r1/manifest.json"))["selected"]["path"])' > preference-selected.txt
selected=$(cat preference-selected.txt)
timeout 20m python evaluate.py --data dev --adapter "$selected" --output outputs/dev-preferences.jsonl
timeout 10m python evaluate.py --data regression --adapter "$selected" --output outputs/regression-preferences.jsonl
echo PREFERENCE_TRAIN_AND_DEV_DONE

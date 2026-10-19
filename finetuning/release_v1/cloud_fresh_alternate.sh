#!/usr/bin/env bash
set -euo pipefail
cd /workspace/crossgen-release-v1
export HF_HOME=/workspace/crossgen-release-v1/hf-cache
export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=4
python - <<'PY'
import json
from pathlib import Path
m=json.loads(Path('outputs/fresh-r1/manifest.json').read_text())
assert m['training_completed'] and m['disk_reload_logits_verified']
other=[e['path'] for e in m['epochs'] if e['epoch']!=m['selected']['epoch']]
assert len(other)==1
Path('fresh-alternate.txt').write_text(other[0]+'\n')
PY
alternate=$(cat fresh-alternate.txt)
timeout 20m python evaluate.py --data dev --adapter "$alternate" --output outputs/dev-fresh-alternate.jsonl
timeout 10m python evaluate.py --data regression --adapter "$alternate" --output outputs/regression-fresh-alternate.jsonl
echo FRESH_ALTERNATE_EVALUATED

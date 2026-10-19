#!/usr/bin/env bash
set -euo pipefail
cd /workspace/crossgen-release-v1
export HF_HOME=/workspace/crossgen-release-v1/hf-cache
export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=4
test -s FINAL_SELECTION.json
test ! -e outputs/test.jsonl
python - <<'PY'
import hashlib,json
from pathlib import Path
s=json.loads(Path('FINAL_SELECTION.json').read_text())
p=Path(s['adapter_path'])/'adapter_model.safetensors'
assert hashlib.sha256(p.read_bytes()).hexdigest()==s['adapter_sha256']
assert Path('selected.txt').read_text().strip()==s['adapter_path']
assert s['frozen_before_test_generation'] is True
PY
selected=$(cat selected.txt)
timeout 25m python evaluate.py --data test --adapter "$selected" --base --output outputs/test.jsonl
timeout 10m python evaluate.py --data regression --adapter "$selected" --base --output outputs/regression-final.jsonl
timeout 15m python evaluate.py --data transfer-audit --adapter "$selected" --base --output outputs/transfer-final.jsonl
timeout 15m python evaluate.py --data integration-dev --adapter "$selected" --base --output outputs/integration-final.jsonl
echo FINAL_AUDIT_COMPLETE

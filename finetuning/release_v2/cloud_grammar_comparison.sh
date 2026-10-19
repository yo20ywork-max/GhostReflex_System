#!/usr/bin/env bash
set -euo pipefail
cd /workspace/crossgen-release-v2
export HF_HOME=/workspace/crossgen-release-v2/hf-cache
export PYTHONPATH=/workspace/crossgen-release-v2/eval-deps
export OMP_NUM_THREADS=4
export PYTHONUNBUFFERED=1
python verify_xgrammar.py
timeout 20m python evaluate_xgrammar.py --data dev --categories recovery negation tools --adapter outputs/epoch-2 --base --output outputs/xgrammar-epoch2-plans.jsonl
timeout 15m python evaluate_xgrammar.py --data dev --categories recovery negation tools --adapter outputs/epoch-1 --output outputs/xgrammar-epoch1-plans.jsonl
timeout 15m python evaluate_xgrammar.py --data dev --categories recovery negation tools --adapter comparison-v1-fusion --output outputs/xgrammar-prior-plans.jsonl
timeout 15m python evaluate_xgrammar.py --data dev --categories recovery negation tools --adapter outputs-repair/epoch-1 --output outputs-repair/xgrammar-repair-plans.jsonl
timeout 10m python evaluate.py --data regression --adapter outputs/epoch-2 --base --output outputs/regression-epoch2-nf4.jsonl
timeout 10m python evaluate.py --data regression --adapter outputs-repair/epoch-1 --output outputs-repair/regression-repair-nf4.jsonl
echo BYTE_GRAMMAR_COMPARISON_DONE

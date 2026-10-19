#!/usr/bin/env bash
set -euo pipefail
cd /workspace/crossgen-release-v1
bash cloud_fresh_alternate.sh
bash cloud_fusion.sh

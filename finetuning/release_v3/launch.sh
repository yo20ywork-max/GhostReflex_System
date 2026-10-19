#!/usr/bin/env bash
set -euo pipefail
cd /workspace/crossgen-release-v3
mkdir .launch_claim
date -u > .launch_claim/started_at
nohup bash cloud_run.sh > cloud_run.log 2>&1 < /dev/null &
pid=$!
printf '%s\n' "$pid" > cloud.pid
cat cloud.pid

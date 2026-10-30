#!/usr/bin/env bash
# A short run of the challenge's own load generator: 20k users, gzip, think-scale 2.5 (as scored).
set -uo pipefail
cd "$(dirname "$0")/.." && . ci/common.sh
( cd bench/mload && go build -o /tmp/mload . ) || exit 1
ulimit -n "$(ulimit -Hn)"; echo "nofile $(ulimit -n)"
start_server 3000
/tmp/mload -target 127.0.0.1 -ports 3000,3001 -users ${USERS:-20000} -ramp 30s -hold 60s -tokens seed/tokens.json \
  -gzip -think-scale 2.5 -out /tmp/run.json 2>&1 | tail -25
rc=${PIPESTATUS[0]}
grep -E "VmRSS|Threads" /proc/$SRV/status
stop_server
exit $rc

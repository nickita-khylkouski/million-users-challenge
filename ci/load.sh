#!/usr/bin/env bash
# A short run of the challenge's own load generator: 20k users, gzip, think-scale 2.5 (as scored).
set -uo pipefail
cd "$(dirname "$0")/.." && . ci/common.sh
( cd bench/mload && go build -o /tmp/mload . ) || exit 1
ulimit -n "$(ulimit -Hn)"; echo "nofile $(ulimit -n)"
start_server 3000
cpu() { awk '{ print $14 + $15 }' /proc/$SRV/stat; }   # utime + stime of all threads, clock ticks
t0=$(cpu)
/tmp/mload -target 127.0.0.1 -ports 3000,3001 -users ${USERS:-20000} -ramp 30s -hold 60s -tokens seed/tokens.json \
  -gzip -think-scale ${THINK:-2.5} -out /tmp/run.json 2>&1 | tail -25
rc=${PIPESTATUS[0]}
t1=$(cpu)
grep -E "VmRSS|Threads" /proc/$SRV/status
python3 -c "import json, os; r = json.load(open('/tmp/run.json')); s = ($t1 - $t0) / os.sysconf('SC_CLK_TCK'); \
print(f'server cpu {s:.2f} s for {r[\"reqs\"]} requests ({r[\"req_per_s\"]:.0f}/s): {s * 1e6 / max(r[\"reqs\"], 1):.1f} us per request')"
stop_server
exit $rc

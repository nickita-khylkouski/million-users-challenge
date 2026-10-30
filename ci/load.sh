#!/usr/bin/env bash
# A short run of the challenge's own load generator: 20k users, gzip, think-scale 2.5 (as scored).
set -uo pipefail
cd "$(dirname "$0")/.." && . ci/common.sh
( cd bench/mload && go build -o /tmp/mload . ) || exit 1
ulimit -n "$(ulimit -Hn)"; echo "nofile $(ulimit -n)"
start_server 3000
cpu() { awk '{ print $14 + $15 }' /proc/$SRV/stat; }   # utime + stime of all threads, clock ticks
t0=$(cpu)
python3 ci/sample.py 92 > /tmp/sample.txt &
SAMPLER=$!
T=/sys/kernel/tracing; [ -d $T/events/tcp ] || T=/sys/kernel/debug/tracing
sudo sh -c "echo > $T/trace; echo 1 > $T/events/tcp/tcp_retransmit_skb/enable; echo mload-start > $T/trace_marker"
echo "mload start: $(date -u +%T.%3N) UTC"
GODEBUG=gctrace=1 /tmp/mload -target 127.0.0.1 -ports 3000,3001 -users ${USERS:-20000} -ramp 30s -hold 60s -tokens seed/tokens.json \
  -gzip -think-scale ${THINK:-2.5} -out /tmp/run.json 2>/tmp/mload.err | tail -25
rc=${PIPESTATUS[0]}
t1=$(cpu)
wait $SAMPLER
sudo sh -c "echo 0 > $T/events/tcp/tcp_retransmit_skb/enable; cat $T/trace" > /tmp/retrans.trace
grep -v '^gc ' /tmp/mload.err | tail -5
grep -E "VmRSS|Threads" /proc/$SRV/status
python3 - "$t0" "$t1" <<'PY'
import json, os, sys
r = json.load(open('/tmp/run.json'))
s = (int(sys.argv[2]) - int(sys.argv[1])) / os.sysconf('SC_CLK_TCK')
for e in r['endpoints']:
    print(f"  {e['name']:22s} ok {e['ok']:8d} fail {e['fail']:4d} p95 {e['p95_ms']:7.1f} ms p99 {e['p99_ms']:7.1f} ms")
print(f"server cpu {s:.2f} s for {r['reqs']} requests ({r['req_per_s']:.0f}/s): {s * 1e6 / max(r['reqs'], 1):.1f} us per request")
PY
echo "-- kernel counters per second (t from the start of mload)"; cat /tmp/sample.txt
echo "-- retransmissions by connection (tcp_retransmit_skb), per second from the start of mload"
python3 ci/retrans.py /tmp/retrans.trace 3000
echo "-- the load generator's garbage collections from t = 20 s to 50 s (GODEBUG=gctrace=1)"
grep '^gc ' /tmp/mload.err | awk '{ t = substr($3, 2) + 0 } t >= 20 && t <= 50 { print "  " $1, $2, $3, $4, $5, "ms,", $11, "MB, goal", $13, "MB" }'
stop_server
exit $rc

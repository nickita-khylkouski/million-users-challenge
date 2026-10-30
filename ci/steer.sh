#!/usr/bin/env bash
# The steering program on a real x86 kernel (Rosetta refuses SO_ATTACH_REUSEPORT_CBPF), and the guard that
# detaches it when one worker gets far more than its share of new connections.
set -uo pipefail
cd "$(dirname "$0")/.." && . ci/common.sh
rc=0
echo "== defaults (what the box runs)"
start_server 3000
stop_server
echo; echo "== every worker, one client CPU at a time"
start_server 3000 SKIP_IRQ_CPU=0
python3 ci/steer.py $SRV 3000 percpu 200 || rc=1
stop_server
echo; echo "== guard: all connections from one CPU"
start_server 3000 SKIP_IRQ_CPU=0
python3 ci/steer.py $SRV 3000 guard 400 || rc=1
grep -q "cpu steering detached" /tmp/srv.log || { echo "FAIL: no detach logged"; rc=1; }
stop_server
echo; echo "== STEER=0 control: kernel hash"
start_server 3000 SKIP_IRQ_CPU=0 STEER=0
python3 ci/steer.py $SRV 3000 guard 400; true
stop_server
exit $rc

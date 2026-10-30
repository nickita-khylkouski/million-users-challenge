#!/usr/bin/env bash
# Retransmission timing of responses (ci/rto.py) for this submission and, if built, the PR's first commit
# (in /tmp/pr61, before TCP_THIN_LINEAR_TIMEOUTS) as the control.
set -uo pipefail
cd "$(dirname "$0")/.." && . ci/common.sh
rc=0
for run in "$SUB thin" "/tmp/pr61/submissions/asm-epoll-nickita-khylkouski exp"; do
  set -- $run
  [ -x "$1/build/server" ] || continue
  SUB=$1; echo "== $1"
  start_server 3000
  sudo python3 ci/rto.py 3000 "$2" 300 500 700 900 || rc=1
  stop_server
done
sudo iptables -S INPUT | grep -c DROP | xargs echo "leftover DROP rules:"
exit $rc

#!/usr/bin/env bash
# TCP_THIN_LINEAR_TIMEOUTS read back from the server's own sockets on a real kernel: set on the listeners,
# inherited by accepted sockets, set on the Postgres connections.
set -uo pipefail
cd "$(dirname "$0")/.." && . ci/common.sh
start_server 3000
sudo python3 ci/thin.py $SRV 3000; rc=$?
stop_server
exit $rc

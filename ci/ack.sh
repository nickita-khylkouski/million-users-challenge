#!/usr/bin/env bash
# Delayed-ACK behaviour with tcpdump on lo (port 80): see ci/acktest_srv.py for the request sequence. Expected:
# defaults: the server's only pure ACKs are the two the kernel's 40 ms timer sends while a response is held
# up (B1 Postgres stalled, C1 the server stalled); QUICKACK_MS=0: B2 and C2 also draw one each.
set -uo pipefail
cd "$(dirname "$0")/.." && . ci/common.sh
sudo sysctl -q net.ipv4.ip_unprivileged_port_start=0
for label in defaults QUICKACK_MS=0 QUICKACK=1; do
  echo "== $label"
  if [ $label = defaults ]; then start_server 80; else start_server 80 $label; fi
  sudo tcpdump -i lo -n -tt -l 'tcp port 80' > /tmp/cap.txt 2>/tmp/cap.err &
  TD=$!
  sleep 1
  sudo python3 ci/acktest_srv.py > /tmp/ev.txt 2>&1 || cat /tmp/ev.txt
  sleep 0.5
  sudo pkill -INT tcpdump; wait $TD 2>/dev/null
  stop_server
  python3 ci/parse_ack.py /tmp/cap.txt /tmp/ev.txt
  echo
done
echo "== TCP_INFO size on this kernel"
python3 ci/tcpinfo_check.py

#!/usr/bin/env python3
# Summarizes the tcp:tcp_retransmit_skb tracepoint over a load run: which connections retransmitted (client to
# server, server to client, server to Postgres, Postgres to server) and when, in seconds from the
# "mload-start" marker. usage: python3 ci/retrans.py TRACE_FILE PORT
import collections, re, sys

port = int(sys.argv[2]); ports = {port, port + 1}
t0, rows = None, []
for line in open(sys.argv[1]):
    m = re.search(r" (\d+\.\d+): (\w+): (.*)", line)
    if not m:
        continue
    ts, ev, rest = float(m[1]), m[2], m[3]
    if ev == "tracing_mark_write" and "mload-start" in rest:
        t0 = ts
    elif ev == "tcp_retransmit_skb":
        f = dict(kv.split("=", 1) for kv in rest.split() if "=" in kv)
        sp, dp = int(f["sport"]), int(f["dport"])
        who = ("server -> client" if sp in ports else "client -> server" if dp in ports else
               "server -> postgres" if dp == 5432 else "postgres -> server" if sp == 5432 else f"{sp} -> {dp}")
        rows.append((ts, who, f.get("state", "?")))
if not rows:
    print("no retransmissions"); sys.exit()
t0 = t0 or rows[0][0]
by = collections.defaultdict(collections.Counter)
for ts, who, _ in rows:
    by[who][int(ts - t0)] += 1
for who, c in sorted(by.items()):
    print(f"  {who:20s} {sum(c.values()):5d}: " + " ".join(f"t={t}:{n}" for t, n in sorted(c.items())))
print("  states:", dict(collections.Counter(st for *_, st in rows)))

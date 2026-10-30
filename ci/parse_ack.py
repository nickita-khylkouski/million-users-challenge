"""Merge a tcpdump -tt text capture with the acktest_srv.py event log into one timeline, limited to the test
connection's port. Marks pure ACKs; a pure ACK from the server (port 80) is the packet the design avoids."""
import re
import sys

cap, ev = sys.argv[1], sys.argv[2]
LINE = re.compile(r"^(\d+\.\d+) IP 127\.0\.0\.1\.(\d+) > 127\.0\.0\.1\.(\d+): Flags \[([^\]]+)\].*length (\d+)")

events = []
port = None
for line in open(ev):
    parts = line.split()
    if len(parts) >= 3 and parts[1] == "PORT":
        port = parts[2]
    try:
        t = float(parts[0])
    except (ValueError, IndexError):
        continue
    events.append((t, "EV   " + " ".join(parts[1:])))

server_pure = 0
for line in open(cap):
    m = LINE.match(line)
    if not m:
        continue
    t, sp, dp, fl, ln = m.groups()
    if port and sp != port and dp != port:
        continue
    who = "S>C" if sp == "80" else "C>S"
    kind = f"{who} [{fl}] len {ln}"
    if fl == "." and ln == "0":
        kind += "   <- pure ACK"
        if who == "S>C":
            kind += " FROM SERVER"
            server_pure += 1
    events.append((float(t), kind))

events.sort()
t0 = events[0][0] if events else 0
for t, s in events:
    print(f"{t - t0:9.4f}  {s}")
print(f"server pure ACKs on the test connection: {server_pure}")

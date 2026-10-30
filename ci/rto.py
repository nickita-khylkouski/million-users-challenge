#!/usr/bin/env python3
# Retransmission timing of the server's responses: on a warm keep-alive connection, drop every data packet the
# server sends to this connection (PSH set) for a fixed window, send a request, lift the rule when the window
# ends and time the response. The drop is in INPUT, after the packet has left the server's TCP stack, so it is
# a loss to the server (a drop in OUTPUT is a local send error, which TCP retries on another timer). The first
# transmission after the window gets through, so the latency shows when the kernel retransmitted: about 200 ms
# (tail-loss probe), 400 ms, then 600, 800, 1000 ms with TCP_THIN_LINEAR_TIMEOUTS and 800, 1600 ms with
# exponential backoff.
# usage: sudo python3 ci/rto.py PORT thin|exp WINDOW_MS...   (exits 1 if the timing doesn't match thin|exp)
import socket, subprocess, sys, time

port = int(sys.argv[1])
mode = sys.argv[2]
windows = [int(w) for w in sys.argv[3:]]
req = b"GET /health HTTP/1.1\r\nHost: x\r\n\r\n"

def read_response(s):
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = s.recv(4096)
        if not chunk:
            raise SystemExit("connection closed")
        buf += chunk
    head, _, body = buf.partition(b"\r\n\r\n")
    n = int([l.split(b":")[1] for l in head.split(b"\r\n") if l.lower().startswith(b"content-length")][0])
    while len(body) < n:
        body += s.recv(4096)

def rule(op, cport):
    subprocess.run(["iptables", op, "INPUT", "-i", "lo", "-p", "tcp", "--sport", str(port), "--dport", str(cport),
                    "--tcp-flags", "PSH", "PSH", "-j", "DROP"], check=True)

out = []
for w in windows:
    s = socket.create_connection(("127.0.0.1", port), timeout=10)
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    for _ in range(5):                       # warm up: an RTT estimate, delayed-ACK mode settled
        s.sendall(req); read_response(s); time.sleep(0.05)
    time.sleep(0.3)
    cport = s.getsockname()[1]
    rule("-I", cport)
    t0 = time.monotonic()
    s.sendall(req)
    time.sleep(max(0.0, w / 1000 - (time.monotonic() - t0)))
    rule("-D", cport)
    read_response(s)
    ms = (time.monotonic() - t0) * 1000
    out.append(ms)
    print(f"  responses dropped for {w:4d} ms: arrived after {ms:6.0f} ms", flush=True)
    s.close()

def expected(w):                             # when the first transmission after the window goes out
    times = [200, 400, 600, 800, 1000, 1200] if mode == "thin" else [200, 400, 800, 1600, 3200]
    return next(t for t in times if t > w)

bad = [(w, ms) for w, ms in zip(windows, out) if not expected(w) <= ms < expected(w) + 100]
print(("PASS" if not bad else "FAIL") + f": {mode} timeouts, expected at "
      + ", ".join(str(expected(w)) for w in windows) + " ms")
sys.exit(1 if bad else 0)

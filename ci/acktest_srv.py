"""Runs inside the server container, which shares the PID and network namespaces of the Postgres container.
Drives one keep-alive connection through:
  A1 first request on a new connection          A2 warm request
  B1 request answered late: Postgres SIGSTOPped 300 ms     B2 request after it
  C1 request answered late: the server itself SIGSTOPped 300 ms (request waits in the kernel)   C2 after it
  C3 warm request
tcpdump on lo (separate container) records the packets; parse_ack.py merges both logs."""
import os
import signal
import socket
import time

HOST, PORT = "127.0.0.1", 80


def procs():
    out = []
    for p in os.listdir("/proc"):
        if not p.isdigit() or int(p) == os.getpid():
            continue
        try:
            with open(f"/proc/{p}/cmdline", "rb") as f:
                argv = f.read().split(b"\0")
            with open(f"/proc/{p}/comm", "rb") as f:
                comm = f.read().strip()
        except OSError:
            continue
        out.append((int(p), argv, comm))
    return out


def server_pid():
    # under Rosetta argv[0] is the emulator; docker-init's cmdline also names the binary, so exclude it
    cands = [pid for pid, argv, comm in procs()
             if any(a.endswith(b"build/server") for a in argv) and pid != 1 and comm != b"docker-init"]
    if not cands:
        raise SystemExit("no server process found: " + repr([(p, a, c) for p, a, c in procs()][:30]))
    return max(cands)


def postgres_pids():
    return [pid for pid, _, comm in procs() if comm == b"postgres" and pid != 1]


def log(*a):
    print(f"{time.time():.6f}", *a, flush=True)


def send(s, path, mark):
    log("SEND", mark, path)
    s.sendall(f"GET {path} HTTP/1.1\r\nHost: x\r\n\r\n".encode())


def read_response(s, mark):
    buf = b""
    while b"\r\n\r\n" not in buf:
        c = s.recv(65536)
        if not c:
            raise EOFError
        buf += c
    head, _, rest = buf.partition(b"\r\n\r\n")
    cl = 0
    for line in head.split(b"\r\n"):
        if line.lower().startswith(b"content-length:"):
            cl = int(line.split(b":")[1])
    while len(rest) < cl:
        c = s.recv(65536)
        if not c:
            raise EOFError
        rest += c
    log("RECV", mark, head.split(b"\r\n")[0].decode(), f"{len(rest)}B")


def stalled(pids, what, s, path, mark):
    for p in pids:
        os.kill(p, signal.SIGSTOP)
    log("STOP", what, len(pids), "processes")
    send(s, path, mark)
    time.sleep(0.3)
    for p in pids:
        os.kill(p, signal.SIGCONT)
    log("CONT", what)
    read_response(s, mark)


srv = server_pid()
pgs = postgres_pids()
s = socket.socket()
s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
s.connect((HOST, PORT))
log("PORT", s.getsockname()[1], "serverpid", srv, "postgres", len(pgs))

send(s, "/posts/1", "A1-first")
read_response(s, "A1-first")
time.sleep(1.5)
send(s, "/posts/2", "A2-warm")
read_response(s, "A2-warm")
time.sleep(1.5)

stalled(pgs, "postgres", s, "/posts/3", "B1-pg-slow")
time.sleep(1.5)
send(s, "/posts/4", "B2-after-pg-slow")
read_response(s, "B2-after-pg-slow")
time.sleep(1.5)

stalled([srv], "server", s, "/posts/5", "C1-srv-slow")
time.sleep(1.5)
send(s, "/posts/6", "C2-after-srv-slow")
read_response(s, "C2-after-srv-slow")
time.sleep(1.5)
send(s, "/posts/7", "C3-warm")
read_response(s, "C3-warm")
time.sleep(0.3)
s.close()
log("CLOSE")

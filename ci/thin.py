"""TCP_THIN_LINEAR_TIMEOUTS on the server's own sockets, read back through pidfd_getfd (needs CAP_SYS_PTRACE, so
run it with sudo). The listeners set it, accepted sockets must have inherited it, the Postgres connections set it.
The script's own client sockets are the control: they never set it and must read 0.

  thin.py PID PORT
"""
import ctypes
import os
import socket
import sys

TCP_THIN_LINEAR_TIMEOUTS = 16
SYS_pidfd_getfd = 438                   # x86-64
pid, port = int(sys.argv[1]), int(sys.argv[2])
libc = ctypes.CDLL(None, use_errno=True)

clients = []
for _ in range(8):
    c = socket.create_connection(("127.0.0.1", port))
    c.sendall(b"GET /health HTTP/1.1\r\nHost: x\r\n\r\n")
    c.settimeout(10)
    if not c.recv(4096).startswith(b"HTTP/1.1 200"):
        raise SystemExit("health request failed")
    clients.append(c)
mine = {c.getsockname()[1] for c in clients}

pidfd = os.pidfd_open(pid)
seen = {"listener": [], "accepted": [], "postgres": [], "other": []}
for fd in sorted(os.listdir(f"/proc/{pid}/fd"), key=int):
    try:
        if not os.readlink(f"/proc/{pid}/fd/{fd}").startswith("socket:"):
            continue
    except OSError:
        continue
    dup = libc.syscall(SYS_pidfd_getfd, pidfd, int(fd), 0)
    if dup < 0:
        raise SystemExit(f"pidfd_getfd({fd}): {os.strerror(ctypes.get_errno())}")
    s = socket.socket(fileno=dup)       # default timeout: the shared O_NONBLOCK flag is left alone
    try:
        thin = s.getsockopt(socket.IPPROTO_TCP, TCP_THIN_LINEAR_TIMEOUTS)
        nodelay = s.getsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY)
        try:
            peer = s.getpeername()[1]
        except OSError:
            peer = None
    finally:
        s.close()                       # our duplicate only
    kind = ("listener" if peer is None else "postgres" if peer == 5432 else
            "accepted" if peer in mine else "other")
    seen[kind].append((thin, nodelay))

ok = True
for kind, v in seen.items():
    print(f"{kind:9s} {len(v):3d} sockets, thin_lto=1 on {sum(t for t, _ in v):3d}, nodelay=1 on {sum(n for _, n in v):3d}")
    if kind != "other" and (not v or any(t != 1 for t, _ in v)):
        ok = False
ctl = [c.getsockopt(socket.IPPROTO_TCP, TCP_THIN_LINEAR_TIMEOUTS) for c in clients]
print("control: the script's own client sockets read", ctl)
if len(seen["accepted"]) != len(clients):
    print(f"FAIL: found {len(seen['accepted'])} accepted sockets for {len(clients)} clients")
    ok = False
if any(ctl):
    print("FAIL: the control sockets read 1")
    ok = False
print("PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)

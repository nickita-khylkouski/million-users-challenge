"""CPU steering check on a real kernel. Loopback SYNs are processed on the CPU the client sends from, so a client
pinned to CPU c should see every connection land on the worker pinned to c while the steering program is
attached. Workers are told apart by their epoll sets (/proc/PID/fdinfo of every eventpoll fd).

  steer.py PID PORT percpu N     every CPU in turn opens N connections; each CPU's go to one worker, all different
  steer.py PID PORT guard N      CPU 1 opens N, then (after the guard's 1 s check) N more: the second lot spreads
"""
import os
import socket
import sys
import time

pid, port, mode, n = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3], int(sys.argv[4])


def sets():
    out = []
    for fd in sorted(os.listdir(f"/proc/{pid}/fd"), key=int):
        try:
            if os.readlink(f"/proc/{pid}/fd/{fd}") != "anon_inode:[eventpoll]":
                continue
            out.append(sum(1 for l in open(f"/proc/{pid}/fdinfo/{fd}") if l.startswith("tfd:")))
        except OSError:
            pass
    return out


def batch(cpu, k):
    os.sched_setaffinity(0, {cpu})
    socks = []
    for _ in range(k):
        s = socket.create_connection(("127.0.0.1", port))
        s.sendall(b"GET /health HTTP/1.1\r\nHost: x\r\n\r\n")
        socks.append(s)
    for s in socks:
        s.settimeout(10)
        if not s.recv(4096).startswith(b"HTTP/1.1 200"):
            raise SystemExit("health request failed")
    time.sleep(0.3)
    return socks


def diff(a, b):
    return [x - y for x, y in zip(a, b)]


cpus = sorted(os.sched_getaffinity(0))
print("cpus", cpus, "server", pid, "epoll sets before (listeners + postgres):", sets())
ok = True
if mode == "percpu":
    # rounds of n connections per CPU, CPUs interleaved, so the guard's window sees an even spread
    owners = {}
    held = []
    for r in range(5):
        for cpu in cpus:
            base = sets()
            held += batch(cpu, n)
            d = diff(sets(), base)
            w = d.index(max(d))
            print(f"round {r} client on cpu {cpu}: new connections per worker: {d}")
            ok &= max(d) >= 0.95 * n and owners.setdefault(cpu, w) == w
    ok &= len(set(owners.values())) == len(owners)
    print("cpu -> worker epoll set:", owners)
elif mode == "guard":
    base = sets()
    first = batch(cpus[1], n)
    mid = sets()
    d1 = diff(mid, base)
    print(f"first {n} from cpu {cpus[1]}: per worker {d1}")
    time.sleep(2.5)
    second = batch(cpus[1], n)
    d2 = diff(sets(), mid)
    print(f"next {n} from cpu {cpus[1]} after the guard's check: per worker {d2}")
    ok &= max(d1) >= 0.95 * n and max(d2) <= 0.6 * n
print("PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)

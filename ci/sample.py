#!/usr/bin/env python3
# Kernel counters once a second during a load run, to tell lost packets from stalls: TCP retransmissions,
# loss probes, retransmission timeouts, listen-queue overflows, softnet backlog drops and squeezes, and where
# the machine's CPU time went. usage: python3 ci/sample.py SECONDS
import sys, time

NET = [("TcpRetransSegs", "retrans"), ("TcpExtTCPLossProbes", "probes"), ("TcpExtTCPTimeouts", "rtos"),
       ("TcpExtListenOverflows", "ovfl"), ("TcpExtTCPBacklogDrop", "bdrop"), ("TcpExtTCPSynRetrans", "synrt")]

def net():
    v = {}
    for path in ("/proc/net/snmp", "/proc/net/netstat"):
        lines = open(path).read().split("\n")
        for names, vals in zip(lines[::2], lines[1::2]):
            n, x = names.split(), vals.split()
            if n:
                v.update((n[0].rstrip(":") + k, int(val)) for k, val in zip(n[1:], x[1:]))
    return v

def softnet():
    f = [line.split() for line in open("/proc/net/softnet_stat")]
    return sum(int(x[1], 16) for x in f), sum(int(x[2], 16) for x in f)

def cpu():   # user, system + irq, softirq, steal, idle + iowait (clock ticks, all CPUs)
    u, ni, sy, idle, io, irq, soft, steal = (int(x) for x in open("/proc/stat").readline().split()[1:9])
    return u + ni, sy + irq, soft, steal, idle + io

t0 = time.time()
pn, ps, pc = net(), softnet(), cpu()
print("    t " + " ".join(f"{h:>7s}" for _, h in NET) + " | softnet drop squeeze | cpu % user  sys soft steal idle")
while time.time() - t0 < float(sys.argv[1]):
    time.sleep(1)
    n, s, c = net(), softnet(), cpu()
    tot = max(sum(c) - sum(pc), 1)
    print(f"{time.time() - t0:5.0f} " + " ".join(f"{n[k] - pn[k]:7d}" for k, _ in NET)
          + f" |      {s[0] - ps[0]:7d} {s[1] - ps[1]:7d} |      "
          + " ".join(f"{100 * (a - b) / tot:4.0f}" for a, b in zip(c, pc)), flush=True)
    pn, ps, pc = n, s, c

#!/usr/bin/env python3
# Kernel counters once a second during a load run, to tell lost packets from stalls: TCP retransmissions,
# loss probes, retransmission timeouts, listen-queue overflows, softnet backlog drops and squeezes, where the
# machine's CPU time went, dirty and writeback memory, and the disks' writes, busy time and write latency.
# usage: python3 ci/sample.py SECONDS
import re, sys, time

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

def mem():   # dirty and writeback, MB
    m = dict(line.split(":") for line in open("/proc/meminfo"))
    return int(m["Dirty"].split()[0]) >> 10, int(m["Writeback"].split()[0]) >> 10

def disk():  # whole disks summed: writes, sectors written, ms writing; busiest disk's ms doing I/O
    w = sec = wms = busy = 0
    for line in open("/proc/diskstats"):
        f = line.split()
        if re.fullmatch(r"(sd[a-z]+|vd[a-z]+|xvd[a-z]+|nvme\d+n\d+)", f[2]):
            w += int(f[7]); sec += int(f[9]); wms += int(f[10])
            busy = max(busy, int(f[12]))
    return w, sec, wms, busy

t0 = time.time()
pn, ps, pc, pd = net(), softnet(), cpu(), disk()
print("    t " + " ".join(f"{h:>7s}" for _, h in NET) + " | softnet drop squeeze | cpu % user  sys soft steal idle"
      + " | MB dirty wback | disk MB/s busy% wlat ms")
while time.time() - t0 < float(sys.argv[1]):
    time.sleep(1)
    n, s, c, d, m = net(), softnet(), cpu(), disk(), mem()
    tot = max(sum(c) - sum(pc), 1)
    dw = d[0] - pd[0]
    print(f"{time.time() - t0:5.0f} " + " ".join(f"{n[k] - pn[k]:7d}" for k, _ in NET)
          + f" |      {s[0] - ps[0]:7d} {s[1] - ps[1]:7d} |      "
          + " ".join(f"{100 * (a - b) / tot:4.0f}" for a, b in zip(c, pc))
          + f" |    {m[0]:5d} {m[1]:5d} |     {(d[1] - pd[1]) * 512 / 1e6:6.1f} {(d[3] - pd[3]) / 10:5.0f}"
          + f" {(d[2] - pd[2]) / dw if dw else 0:7.1f}", flush=True)
    pn, ps, pc, pd = n, s, c, d

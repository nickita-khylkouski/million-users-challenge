# asm-epoll — x86-64 assembly, no libc

A static binary written in GNU assembler (Intel syntax). No libc, no runtime, no driver library: raw
syscalls, one epoll loop per core, a Postgres wire-protocol v3 client (SCRAM-SHA-256, extended query,
pipelined), HTTP/1.1, JSON, HMAC-SHA256 and gzip are all in `src/`. Build dependency: `binutils` 2.42
(Ubuntu 24.04's package, which `install.sh` installs). Runtime dependencies: none.

```
bash install.sh      # apt-get install binutils
bash build.sh        # as + ld  ->  build/server
bash start.sh        # reads DATABASE_URL, JWT_SECRET, HOST, PORT, EXTRA_PORT
```

Behaviour (status codes, error texts, validation order, JSON byte layout, SQL text) follows the challenge
spec and the reference `c-epoll` entry exactly, so the golden files match byte for byte. `test/run.sh`
passes 42/42.

## Architecture

Everything is built around one question: how many idle-but-live keep-alive connections can one 16-vCPU
box with a single-queue virtio NIC keep answering within the latency budget. Around a million connections
the box is not CPU-bound on HTTP or JSON; it is bound by packets per second on the one core that takes the
NIC interrupt, and by anything that makes a connection cost more than a few hundred bytes.

**Workers.** One thread per CPU, pinned, with its own `epoll` set, its own `SO_REUSEPORT` listening sockets
on both ports, and its own Postgres connections. Nothing is shared between workers after start: no locks,
no atomics, no cross-thread queues. The only process-wide table is the connection slot array (32 bytes per
fd, indexed by fd), which a worker only touches for its own fds.

**The interrupt core is skipped.** With a single-queue NIC every packet first lands on one CPU (NAPI, GRO,
the RPS dispatch), which then also carries its share of the TCP work and a worker. Reading
`/proc/softirqs` at start finds the column whose `NET_RX` count dominates; that CPU gets no worker when the
box has 4 or more CPUs. (`SKIP_IRQ_CPU=0` turns this off.)

**Flow steering.** Each listener group gets a classic BPF program attached with
`SO_ATTACH_REUSEPORT_CBPF` that returns the index of the worker pinned to the CPU on which the SYN was
processed (`SKF_AD_CPU`). With RPS spreading flows over all CPUs by hash, the TCP softirq work of a flow
and the worker that reads and writes its socket are then on the same core: the socket's data stays in
one cache, and no cross-CPU wakeups are needed. (`STEER=0` turns it off.)

**One packet in, one packet out.** Every response is one contiguous buffer (head + body) handed to a
single `sendto`, so it is one skb (one or two frames) and carries the ACK of the request with it. For
that the socket has to be in the kernel's delayed-ACK ("pingpong") mode; otherwise a request that comes
after a pause longer than the RTO, which is every request at these think times, is ACKed at once in a
packet of its own. Three things keep the socket in that mode (all checked with tcpdump on Linux 6.8):

- `TCP_QUICKACK` is cleared on the listeners *after* `listen()`. `inet_csk_listen_start()` resets the
  listener's ACK state, so set before `listen()` the option never reaches the accepted sockets: the first
  request of every connection then draws a pure ACK. Set after, its ACK rides on the response.
- Responses go out within a few milliseconds. The delayed-ACK timer is 40 ms at any HZ
  (`TCP_DELACK_MIN`), and when it fires the socket leaves pingpong mode.
- When a response was late anyway (`QUICKACK_MS`, default 25 ms, counted from when the request reached the
  kernel, which `TCP_INFO`'s `tcpi_last_data_recv` tells for the oldest request of each epoll batch), the
  server sets `TCP_QUICKACK=0` on that socket again. One slow response then costs one extra packet
  instead of one per request from there on, which is what stops overload from feeding on itself.

(A request that arrives in two segments, or is larger than one MSS, is ACKed at once whatever the mode;
the benchmark's requests are single writes under 1 KB, so that does not come up.)
`TCP_DEFER_ACCEPT` means accept only returns when the first request has arrived, so there is no idle
wakeup per connection (it changes no packets). The feed body is gzipped when the client accepts it
(bodies of 1 KB or more): 5.1 KB becomes 1.9 KB, from four segments to two in one skb, and the client's
GRO sees one packet and answers with one ACK. A single-segment feed is out of reach (gzip's floor on the
feed is 1881 bytes against about 1290 bytes of room), so that is as low as it goes. What is left per
request on a warm connection is the request, the response and the client's one ACK of it, plus what the
client adds on its own (the Go dialer's 15 s keepalive probes and their answers, about one pair per
request at the scoring think times).

**Postgres.** Every worker owns a few pipelined connections (`PG_CONNS` in total, default 64, divided over
the workers). Statements are appended to a connection's output buffer as `Bind`/`Execute` and sent once
per event-loop iteration behind a single `Sync`, so one round trip and one pair of packets carry a whole
batch of feed and post reads. Writes (`POST /posts`, likes) get their own `Sync` and are answered only
when the `ReadyForQuery` after it arrives, which is when the transaction is committed. Results are read
back in order through a small op ring per connection; a late result for a connection that has since been
closed and reused is detected with a generation counter and dropped. A connection that dies answers its
pending ops with 500 and is reconnected once per second. Health is a real `SELECT 1` through the same
path; without a working connection it is answered 503 immediately.

**Memory per connection.** Idle connections own nothing but their 32-byte slot. A read buffer is borrowed
from the worker while a request is parsed and only kept (allocated from a per-worker size-class
allocator) when a request arrives in pieces or when output has to wait for `EPOLLOUT`. A million
connections therefore cost the process about 32 MB plus the kernel's socket buffers.

**Batching.** When an iteration woke up for only a handful of events (`BATCH_MIN`, default 32) the loop
sleeps `BATCH_US` (default 2000 µs) before parsing them, so that more requests share one Postgres round
trip and one `sendto`. Both are environment knobs for A/B runs; `BATCH_US=0` disables it.

**Robustness under overload.** `accept` backs off for a second on `EMFILE`/`ENFILE` instead of spinning;
requests larger than 64 KB and chunked bodies drop the connection; the op ring and output buffers have
hard caps; nothing allocates per request on the fast path; no request ever gets a 5xx because of load
alone (only a failed database round trip).

## Environment

| variable | default | meaning |
|---|---|---|
| `DATABASE_URL`, `JWT_SECRET`, `HOST`, `PORT`, `EXTRA_PORT` | challenge values | as in the spec |
| `WORKERS` | CPUs (minus the interrupt core) | fewer workers |
| `PG_CONNS` | 64 | Postgres connections, total (at least 2 per worker) |
| `SKIP_IRQ_CPU` | 1 | leave the NET_RX core without a worker |
| `STEER` | 1 | CBPF reuseport steering by CPU |
| `DEFER_ACCEPT` | 1 | `TCP_DEFER_ACCEPT` seconds on the listeners (0 = off) |
| `QUICKACK` | 0 | 1 keeps the kernel default quick-ACK behaviour |
| `QUICKACK_MS` | 25 | re-arm delayed ACKs on a socket after a response this late (0 = off) |
| `BATCH_US` / `BATCH_MIN` | 2000 / 32 | event-loop batching, see above |

The server logs its choices at start (`workers`, `net_rx cpu`, `postgres connections per worker`).

## Testing

`bash test/run.sh submissions/asm-epoll-nickita-khylkouski` passes all 42 checks on a fresh seed copy. On
top of that the server was exercised with a protocol probe (pipelined requests, gzip round trip,
`Expect: 100-continue`, requests split across packets, `Connection: close`, HTTP/1.0, oversize requests,
hundreds of concurrent pipelined connections) and with the challenge's own `bench/mload` generator.

The ACK behaviour was checked with tcpdump on Linux 6.8.0 (one keep-alive connection, requests 1.5 s
apart): no pure ACK from the server on a fresh connection's first request, none on warm requests, and
after a response held up 300 ms by a stalled Postgres (where the kernel's timer ACK is unavoidable) the
next request again rides its ACK on the response, while with `QUICKACK_MS=0` it draws a pure ACK and
with `QUICKACK=1` the first request does too.

## Credits

- `rt.s`, `cpu.s`, `crypto.s`, `pg.s`, `http.s`, `json.s` and `gzip.s` come from the author's
  `asm-epoll-nickita-khylkouski` entry in the multicore-server-challenge (MIT). `main.s`, `server.s`,
  `pgio.s`, `api.s`, `render.s` and `sql.s` are new for this challenge.
- The exact response and validation semantics follow unorig-username's `c-epoll` reference entry, as the
  golden files do.
- `gzip.s`: deflate design and parameters follow libdeflate (Copyright 2016 Eric Biggers, 2024 Google LLC;
  MIT). The PCLMULQDQ CRC32 is translated from Chromium zlib's `crc32_sse42_simd_` (Copyright 2017 The
  Chromium Authors; BSD-3-Clause). Full notices are in `src/gzip.s` and `LICENSE`.

## Layout

```
src/
  main.s    entry, env, IRQ-core detection, listeners + CBPF steering, worker spawn
  server.s  epoll loop, accept, client read/parse/send, parked output, close
  api.s     routing, JWT verification, body validation
  pgio.s    pipelined Postgres I/O, op ring, Sync discipline, reconnects
  render.s  JSON bodies, static error responses, gzip + head in one send
  sql.s     the five prepared statements
  rt.s      allocator, threads, memcpy, time        http.s    HTTP/1.1 parser and head writer
  cpu.s     CPU feature detection                   json.s    JSON reader and writer
  crypto.s  SHA-256, HMAC, base64url                pg.s      Postgres protocol v3 (SCRAM, binary params)
  gzip.s    deflate + CRC32                         defs.inc / app.inc  constants and struct layouts
```

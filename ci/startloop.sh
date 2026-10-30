#!/usr/bin/env bash
# The interrupt-core detector's edge cases on a real kernel: fake /proc/interrupts, /proc/softirqs and
# /proc/irq/N/effective_affinity_list bind-mounted in a private mount namespace, the server started N times per case
# (start-up only: the database URL points at a closed port), every start's "net_rx cpu" line checked, core dumps kept.
set -uo pipefail
cd "$(dirname "$0")/.."
SUB=$PWD/submissions/asm-epoll-nickita-khylkouski
F=/tmp/fake
IRQ=$(for n in $(ls /proc/irq | grep -E '^[0-9]+$' | sort -n); do [ -f /proc/irq/$n/effective_affinity_list ] && { echo $n; break; }; done)
echo "using /proc/irq/$IRQ/effective_affinity_list for the affinity file"
python3 ci/fake.py $F $IRQ
sudo sysctl -q kernel.core_pattern=/tmp/core.%p
N=${N:-100}
rc=0
# interrupts softirqs affinity(for IRQ) expected-net_rx-cpu  ("real" / "-" = the machine's own file; "any" = just consistent)
while read -r int soft aff want; do
  out=$(sudo unshare -m bash -c "
    set -e
    if [ $int != real ]; then mount --bind $F/$int /proc/interrupts; fi
    if [ $soft != - ]; then mount --bind $F/$soft /proc/softirqs; fi
    if [ $aff != - ]; then mount --bind $F/$aff /proc/irq/$IRQ/effective_affinity_list; fi
    set +e
    ulimit -c unlimited
    cd $SUB
    for i in \$(seq $N); do
      env DATABASE_URL=postgres://x:y@127.0.0.1:1/db JWT_SECRET=s PORT=3900 EXTRA_PORT=3901 timeout 0.3 build/server 2>&1 \
        | grep -E '^net_rx cpu|^nic rx|dumped|rror|egm|ault' | tr '\n' ' '; echo
    done | sort | uniq -c")
  distinct=$(printf '%s\n' "$out" | wc -l)
  verdict=ok
  if [ "$distinct" != 1 ]; then verdict=FAIL
  elif [ "$want" != any ] && ! printf '%s\n' "$out" | grep -q "^ *$N net_rx cpu: $want "; then verdict=FAIL
  elif ! printf '%s\n' "$out" | grep -q "^ *$N net_rx cpu: "; then verdict=FAIL
  fi
  [ $verdict = FAIL ] && rc=1
  printf '%-4s %-36s want %-4s got:%s\n' $verdict "$int $soft $aff" "$want" "$(printf '%s' "$out" | tr '\n' '|')"
done <<'CASES'
real - - any
int_two - - -1
int_none soft_cpu2 - 2
int_none soft_flat - -1
int_none soft_ci - -1
int_none - - any
int_one - aff_1 1
int_one - aff_range 3
int_one - aff_list 3
int_one - aff_empty 3
int_one - aff_nonl 2
int_missing - - 2
int_zero soft_cpu1 aff_range 1
int_empty soft_cpu2 - 2
int_hdronly soft_cpu1 - 1
int_long soft_cpu1 aff_range 1
CASES
cores=$(ls /tmp/core.* 2>/dev/null)
if [ -n "$cores" ]; then
  echo "== core dumps: $(echo $cores | wc -w)"
  for c in $(echo $cores | tr ' ' '\n' | head -3); do
    sudo gdb -q -batch -ex bt -ex 'info registers' -ex 'x/8i $pc' $SUB/build/server $c 2>&1 | head -60
  done
  rc=1
fi
echo "core dumps: ${cores:-none}"
exit $rc

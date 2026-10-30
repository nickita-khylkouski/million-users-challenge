"""Writes fake /proc/interrupts, /proc/softirqs and effective_affinity_list files for the start-up loop.
fake.py DIR IRQ  (IRQ = an interrupt number that has a /proc/irq/IRQ directory on this machine)"""
import os, sys
d, irq = sys.argv[1], int(sys.argv[2])
os.makedirs(d, exist_ok=True)
hdr = "           CPU0       CPU1       CPU2       CPU3       \n"
def line(n, counts, name):
    return f" {n:>3}:" + "".join(f" {c:>10}" for c in counts) + f"       MSI 16385 Edge      {name}\n"
tail = "NMI:          0          0          0          0   Non-maskable interrupts\nLOC:      28425      28002      27260      29570   Local timer interrupts\nERR:          0\n"
files = {
    "int_two": hdr + line(irq, [500, 9000, 0, 0], "virtio0-input.0") + line(irq + 1, [1, 2, 3, 4], "virtio0-output.0") + line(irq + 2, [0, 0, 7000, 0], "virtio0-input.1") + tail,
    "int_none": hdr + line(irq, [10, 0, 0, 0], "ens5-Tx-Rx-0") + line(irq + 1, [5, 0, 0, 0], "virtio1-input") + tail,
    "int_one": hdr + line(irq - 1, [0, 0, 0, 0], "virtio1-input") + line(irq, [10, 20, 30, 9000], "virtio0-input.0") + line(irq + 1, [1, 2, 3, 4], "virtio0-output.0") + tail,
    "int_missing": hdr + line(999, [10, 20, 9000, 30], "virtio0-input.0") + tail,
    "int_zero": hdr + line(irq, [0, 0, 0, 0], "virtio0-input.0") + tail,
    "int_empty": "",
    "int_hdronly": hdr,
    "int_long": hdr + "".join(line(1000 + i, [i, i, i, i], f"dev{i}-q") for i in range(1500)) + line(irq, [1, 2, 3, 9000], "virtio0-input.0") + tail,
    "aff_1": "1\n", "aff_range": "0-3\n", "aff_list": "1,3\n", "aff_empty": "", "aff_nonl": "2",
    "soft_cpu2": "                    CPU0       CPU1       CPU2       CPU3       \n      NET_TX:          5          5          5          5\n      NET_RX:       1000       1200      90000        800\n",
    "soft_ci": "                    CPU0       CPU1       CPU2       CPU3       \n      NET_RX:       4207       1730       1202       1789\n",
    "soft_cpu1": "                    CPU0       CPU1       CPU2       CPU3       \n      NET_RX:       1000      50000       1100        800\n",
    "soft_flat": "                    CPU0       CPU1       CPU2       CPU3       \n      NET_RX:       1000       1100       1200        900\n",
}
for k, v in files.items():
    open(os.path.join(d, k), "w").write(v)

#!/bin/sh
# §1401: append per-window edge-per-$ (grpcap.py, x3 / x1 / UID 46 rows, pooled per arm) to ab_read_<name>.txt — the deciding read for book-group tests (§1400).
N=$1; cd /opt/mvtrx; L=liveswitch_${N}_log.txt; O=ab_read_${N}.txt
TP=$(sh tape_ab.sh)
{ echo "-- edge per \$ per window (grpcap.py; x1 = test subject):"
  python3 - "$L" <<'P' | while read a z lab; do echo "== window $lab sim $a-$z"; (ulimit -v 3500000; nice -n 10 python3 grpcap.py $a $z $TP | grep -E " (x1|46) ") ; done
import sys
W = [l.split() for l in open(sys.argv[1]) if " sim " in l]; W = [(int(w[2]), w[3]) for w in W]
for i in range(len(W) - 1):
    if W[i][1] in ("A", "B"): print(W[i][0], W[i + 1][0], W[i][1])
P
} >> $O 2>&1
rm -f /opt/mvtrx/tape_ab.jsonl
echo "ALERT $(date +%s) test $N edge-per-\$ read appended: $O" >> alerts.txt

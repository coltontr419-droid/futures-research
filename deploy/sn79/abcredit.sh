#!/bin/sh
# §1373: whole-miner validator-exact A/B — pool all A windows and all B windows from a switch log into two tapes, run making_exact on each (x3 + fleet 216
# as drift reference). Also counts large $300 moves per window (flash-event exposure).   sh abcredit.sh <switch log> <out file>
LOG=$1; OUT=$2; cd /opt/mvtrx
python3 - "$LOG" <<'PY'
import json, sys, os
W = [l.split() for l in open(sys.argv[1]) if " sim " in l]; W = [(int(w[2]), w[3]) for w in W]
wins = [(W[i][0], W[i + 1][0], W[i][1]) for i in range(len(W) - 1) if W[i][1] in ("A", "B")]
fa, fb = open("/tmp/abc_A.jsonl", "w"), open("/tmp/abc_B.jsonl", "w"); big = {"A": 0, "B": 0}; last = {}
for l in open(os.environ.get("TAPE", "/opt/mvtrx/live_tape_x3.jsonl")):
    i = l.find('"ts": ')
    if i < 0: continue
    t = int(l[i + 6:l.index(",", i)]) / 1e9
    if t >= 90000: continue
    for a, z, lab in wins:
        if a - 60 <= t < z:
            (fa if lab == "A" else fb).write(l)
            if a <= t and '"bids"' in l:
                r = json.loads(l)
                if r["book"] < 63 and r["bids"] and r["asks"]:
                    m = (r["bid"] + r["ask"]) / 2; p = last.get((r["book"], lab))
                    if p and abs(m - p) / p > 0.01: big[lab] += 1
                    last[(r["book"], lab)] = m
            break
print("1%+ one-second $300 mid jumps (flash exposure): A", big["A"], "| B", big["B"], "| windows A", sum(1 for w in wins if w[2] == "A"), "B", sum(1 for w in wins if w[2] == "B"))
PY
cd repo
for lab in A B; do for u in 64 46 216; do (ulimit -v 2000000; timeout 1500 nice -n 10 /opt/mvtrx/venv/bin/python /opt/mvtrx/making_exact.py /tmp/abc_$lab.jsonl $u 1 --since 0 2>&1 | grep -E "^ours" | head -1 | sed "s/^ours/[$lab] UID $u/" | sed "s/ → rank.*//") & done; wait; done
rm -f /tmp/abc_A.jsonl /tmp/abc_B.jsonl

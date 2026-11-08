#!/bin/sh
# §1302 read: validator-exact making by book group since T0 (default 24,435 = 1:50 PM CT): x4 (58) per arm (book mod 3: 0 base, 1 sticky 2, 2 sticky 5;
# all with the thin rule on the $300 books and 4-dec skipped) vs x2 (212, thin off everywhere, 4-dec skipped) vs fleet 216.   sh qread.sh [T0]
T0=${1:-24435}; SM=$(( T0 / 60 ))
cd /opt/mvtrx && T0=$T0 python3 - <<'PY'
import os
T0 = int(os.environ["T0"]) - 600
outs = {g: open(f"/tmp/qr_{g}.jsonl", "w") for g in ("vol", "calm")}
for l in open("/opt/mvtrx/live_tape_x3.jsonl"):
    i = l.find('"ts": ')
    if i < 0: continue
    t = int(l[i + 6:l.index(",", i)])
    if t >= 60000 * 10**9 or t < T0 * 10**9: continue
    j = l.find('"book": ')
    if j < 0: continue
    b = int(l[j + 8:l.index(",", j)])
    if b < 63: outs["vol"].write(l)
    elif b < 102: outs["calm"].write(l)
PY
cd repo
for g in vol calm; do
  (ulimit -v 2200000; timeout 1500 nice -n 10 /opt/mvtrx/venv/bin/python /opt/mvtrx/making_exact.py /tmp/qr_$g.jsonl 58 3 --since $SM 2>&1 | grep -E "^ours" | sed "s/^ours/[$g] x4/") &
  (ulimit -v 1800000; timeout 1500 nice -n 10 /opt/mvtrx/venv/bin/python /opt/mvtrx/making_exact.py /tmp/qr_$g.jsonl 212 1 --since $SM 2>&1 | grep -E "^ours" | head -1 | sed "s/^ours/[$g] x2/") &
  (ulimit -v 1800000; timeout 1500 nice -n 10 /opt/mvtrx/venv/bin/python /opt/mvtrx/making_exact.py /tmp/qr_$g.jsonl 216 1 --since $SM 2>&1 | grep -E "^ours" | head -1 | sed "s/^ours/[$g] fleet 216/") &
  wait
done
rm -f /tmp/qr_*.jsonl

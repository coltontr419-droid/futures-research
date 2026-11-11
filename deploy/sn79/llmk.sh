cd /opt/mvtrx
E=$(python3 -c "import json; f=open('live_tape_x3.jsonl','rb'); f.seek(-4000,2); print(int(json.loads(f.read().split(b'\n')[-2])['ts']/1e9))")
python3 - $E <<'PY'
import sys
E = int(sys.argv[1]); S = E - 10800
o = open("/tmp/w_top.jsonl", "w")
for l in open("/opt/mvtrx/live_tape_x3.jsonl"):
    i = l.find('"ts": ')
    if i < 0: continue
    t = int(l[i + 6:l.index(",", i)]) / 1e9
    if S <= t < E: o.write(l)
print("window sim", S, E)
PY
cd repo
for grp in "64 132 3" "46 17 193" "21 216"; do for u in $grp; do (ulimit -v 2000000; timeout 1500 nice -n 10 /opt/mvtrx/venv/bin/python /opt/mvtrx/making_exact.py /tmp/w_top.jsonl $u 1 2>&1 | grep -E "^ours" | sed "s/^ours/UID $u/") & done; wait; done
rm -f /tmp/w_top.jsonl

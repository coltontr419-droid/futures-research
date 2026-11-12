cd /opt/mvtrx
python3 - <<'PY'
o = open("/tmp/w_x2.jsonl", "w")
for l in open("/opt/mvtrx/live_tape_x3.jsonl"):
    i = l.find('"ts": ')
    if i < 0: continue
    t = int(l[i + 6:l.index(",", i)]) / 1e9
    if 5000 <= t < 30000: o.write(l)
PY
cd repo; (ulimit -v 2500000; timeout 1500 nice -n 10 /opt/mvtrx/venv/bin/python /opt/mvtrx/making_grp.py /tmp/w_x2.jsonl 191 1 --books 2>&1 | grep -E "^ours|GROUP|two-sided" | cut -c1-250)
rm -f /tmp/w_x2.jsonl

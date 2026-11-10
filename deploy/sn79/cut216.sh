cd /opt/mvtrx
python3 - <<'PY'
f1, f2 = open("/tmp/w_morn.jsonl", "w"), open("/tmp/w_now.jsonl", "w")
for l in open("/opt/mvtrx/live_tape_x3.jsonl"):
    i = l.find('"ts": ')
    if i < 0: continue
    t = int(l[i + 6:l.index(",", i)]) / 1e9
    if 44800 <= t < 55600: f1.write(l)
    if 52500 <= t < 63300: f2.write(l)
PY
cd repo
for w in morn now; do for u in 64 216; do (ulimit -v 2000000; timeout 1500 nice -n 10 /opt/mvtrx/venv/bin/python /opt/mvtrx/making_exact.py /tmp/w_$w.jsonl $u 1 2>&1 | grep -E "^ours|^field" | sed "s/^/[$w] UID $u: /") & done; wait; done
rm -f /tmp/w_morn.jsonl /tmp/w_now.jsonl

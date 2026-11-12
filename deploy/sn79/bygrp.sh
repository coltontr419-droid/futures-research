cd /opt/mvtrx
python3 - <<'PY'
o = open("/tmp/w_new.jsonl", "w")
for l in open("/opt/mvtrx/live_tape_x3.jsonl"):
    i = l.find('"ts": ')
    if i < 0: continue
    t = int(l[i + 6:l.index(",", i)]) / 1e9
    if t < 30000: o.write(l)
PY
cd repo
for u in 64 27; do
  (ulimit -v 2500000; timeout 1500 nice -n 10 /opt/mvtrx/venv/bin/python /opt/mvtrx/making_grp.py /tmp/w_new.jsonl $u 1 --books 2>&1 > /tmp/mx_$u.txt) &
done; wait
for u in 64 27; do grep -E "our books|GROUP" /tmp/mx_$u.txt | sed "s/^/UID $u: /" | cut -c1-400; done
rm -f /tmp/w_new.jsonl

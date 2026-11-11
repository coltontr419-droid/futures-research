cd /opt/mvtrx
E=$(python3 -c "import json; f=open('live_tape_x3.jsonl','rb'); f.seek(-4000,2); print(int(json.loads(f.read().split(b'\n')[-2])['ts']/1e9))")
for W in "$((E - 10800)) $E now" "$((E - 18000)) $((E - 7200)) earlier"; do set -- $W
  cat live_tape_x3.jsonl.prev live_tape_x3.jsonl | python3 -c "
import sys
S, E = int(sys.argv[1]), int(sys.argv[2])
for l in sys.stdin:
    i = l.find('\"ts\": ')
    if i < 0: continue
    t = int(l[i + 6:l.index(',', i)]) / 1e9
    if S <= t < E: sys.stdout.write(l)" $1 $2 > /tmp/w_$3.jsonl
  echo "== $3 window sim $1-$2"
  cd repo; for u in 64 216; do (ulimit -v 2000000; timeout 1500 nice -n 10 /opt/mvtrx/venv/bin/python /opt/mvtrx/making_exact.py /tmp/w_$3.jsonl $u 1 2>&1 | grep -E "^ours" | sed "s/^ours/UID $u/") & done; wait; cd ..
  rm -f /tmp/w_$3.jsonl
done

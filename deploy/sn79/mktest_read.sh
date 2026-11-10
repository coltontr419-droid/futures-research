#!/bin/sh
# §1290 morning read: validator-exact making credit (making_exact.py) for x2 (thin rule off) and x4 (fleet-size orders) vs the long-lived fleet and x3,
# over the SAME window since the test start (sim min 260). Output → /opt/mvtrx/mktest_read_<HHMM>.txt
OUT=/opt/mvtrx/mktest_read_$(TZ=America/Chicago date +%H%M).txt
{
echo "§1290 making-credit test read at $(TZ=America/Chicago date '+%a %I:%M %p') CT | window: sim min 260 → now ($(journalctl -u mvtrx-x3 --since -2min --no-pager | grep -o 'SIMULATION TIME : [0-9:]*' | tail -1))"
python3 - <<'PY'
o = open("/tmp/mkt_cur.jsonl", "w")
for l in open("/opt/mvtrx/live_tape_x3.jsonl"):
    i = l.find('"ts": ')
    if i >= 0 and int(l[i + 6:l.index(",", i)]) < 90000 * 10 ** 9: o.write(l)
PY
cd /opt/mvtrx/repo
for pair in "212 58" "216 252" "201 87"; do
  for u in $pair; do (ulimit -v 2800000; timeout 2400 nice -n 10 /opt/mvtrx/venv/bin/python /opt/mvtrx/making_exact.py /tmp/mkt_cur.jsonl $u 1 --since 260 2>&1 | grep -E "^ours" | head -1 | sed "s/^ours/uid $u/") & done; wait
done
echo "labels: 212 = x2 (thin rule OFF), 58 = x4 (orders \$3.6k), 216/252/87 = long-lived fleet 5F1F2JMu (14-27 d), 201 = x3 (frozen, its third of the books)"
for u in 212 58 201 216 252 87; do printf "gauge uid %s: " $u; UIDQ=$u /opt/mvtrx/x1_gauge.sh; done
rm -f /tmp/mkt_cur.jsonl
} > $OUT 2>&1
echo "ALERT §1290 making-credit test read ready: $OUT" >> /opt/mvtrx/alerts.txt

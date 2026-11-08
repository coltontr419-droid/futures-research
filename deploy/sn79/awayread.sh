#!/bin/sh
# §1320: server-side reads while the laptop is closed (session crons stop). Writes /opt/mvtrx/away_<tag>.txt; never changes a miner.
TAG=$1; OUT=/opt/mvtrx/away_$TAG.txt; cd /opt/mvtrx
{
echo "== $(TZ=America/Chicago date) ($TAG)"
cd /tmp && timeout 150 /opt/mvtrx/venv/bin/python /opt/mvtrx/regcheck.py x4=58 x2=212 2>&1 | tail -2; cd /opt/mvtrx
NOW=$(python3 -c "import json; f=open('live_tape_x3.jsonl','rb'); f.seek(-4000,2); print(int(json.loads(f.read().split(b'\n')[-2])['ts']/1e9))")
echo "now sim s $NOW | tape last write $(( $(date +%s) - $(stat -c %Y live_tape_x3.jsonl) )) s ago"
if [ "$TAG" = "read" ]; then
  echo "-- CALM (hold + soft gate + 1:2:3) since 26565, per-fill:"; (ulimit -v 3000000; nice -n 10 python3 abtest.py live_tape_x3.jsonl 26565 $NOW x4=58 x2=212) 2>&1 | grep -E "^calm|^\\\$300"
  echo "-- vfill since 26565:"; (ulimit -v 3000000; nice -n 10 python3 vfill.py live_tape_x3.jsonl 26565 $NOW x4=58 x2=212) 2>&1 | tail -2
  echo "-- \$300 fleet copy 2 h (since 25844), per-fill:"; (ulimit -v 3000000; nice -n 10 python3 abtest.py live_tape_x3.jsonl 25844 $NOW x4=58 x2=212) 2>&1 | grep "^\\\$300"
  echo "-- vfill \$300 since 25844:"; (ulimit -v 3000000; nice -n 10 python3 vfill.py live_tape_x3.jsonl 25844 $NOW x4=58 x2=212) 2>&1 | grep "^\\\$300"
  echo "-- fleet sanity since 26565:"; (ulimit -v 3000000; nice -n 10 python3 abtest.py live_tape_x3.jsonl 26565 $NOW fleet=216 x2=212) 2>&1 | grep -E "^calm|^\\\$300"
  echo "-- order life / placement since 26565:"; (ulimit -v 3500000; nice -n 10 python3 repricestudy.py live_tape_x3.jsonl 26565 $NOW fleet=7,31,40,52,59,87,102,111,133,134,147,156,210,216,241,252,255 x4=58 x2=212) 2>&1 | tail -18
  echo "-- x4 errors since 4:55 PM:"; journalctl -u mvtrx-x4 --since "22:55:56" --no-pager | grep -iE "error|traceback" | grep -viE "proxy|NOT READY|settle|=====" | head -3
  journalctl -u mvtrx-x4 --since "-15min" --no-pager | grep "PACE STATUS" | tail -1 | cut -c60-200
fi
echo "-- prune / wallet:"; cd /tmp && timeout 280 /opt/mvtrx/venv/bin/python /opt/mvtrx/prep.py 2>&1 | grep -v "^$" | tail -4
for u in 212 58 216; do UIDQ=$u /opt/mvtrx/x1_gauge.sh 2>/dev/null; done
systemctl is-active mvtrx-x2 mvtrx-x4
} > $OUT 2>&1
echo "ALERT $(date +%s) away read $TAG done: /opt/mvtrx/away_$TAG.txt" >> /opt/mvtrx/alerts.txt

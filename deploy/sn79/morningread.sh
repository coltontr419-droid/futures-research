#!/bin/sh
# §1339: server-side morning read while the laptop is closed (session crons stop). Writes /opt/mvtrx/morning_read.txt + an ALERT line. Never changes a miner.
OUT=/opt/mvtrx/morning_read.txt; cd /opt/mvtrx; F=7,31,40,52,59,87,102,111,133,134,147,156,210,216,241,252,255
{
echo "== $(TZ=America/Chicago date) morning read (x3 unchanged since 2:44:57 AM CT; reading from sim 34,155 = after the 3:07 AM tape rotation, past the 20-min restart skip)"
cd /tmp && /opt/mvtrx/venv/bin/python /opt/mvtrx/regcheck.py x3=64 2>&1 | tail -1; cd /opt/mvtrx
NOW=$(python3 -c "import json; f=open('live_tape_x3.jsonl','rb'); f.seek(-4000,2); print(int(json.loads(f.read().split(b'\n')[-2])['ts']/1e9))"); echo "now sim s $NOW"
echo "-- gaps to the fleet (kept bp/fill):"; (ulimit -v 3000000; nice -n 10 python3 abtest.py live_tape_x3.jsonl 34155 $NOW fleet=$F x3=64) 2>&1 | grep -E "^calm|^\\\$300|^4-dec"
echo "-- calm order life / placement:"; (ulimit -v 3500000; nice -n 10 python3 repricestudy.py live_tape_x3.jsonl 34155 $NOW fleet=$F x3=64) 2>&1 | grep -A4 "== x3" | head -5
echo "-- \$300 after-move placements:"; (ulimit -v 4500000; nice -n 10 python3 why300b.py live_tape_x3.jsonl x3=64@34155-$NOW) 2>&1 | grep -E "^==|before placing|moved away 1-2 ticks   |best flat / came toward   "
echo "-- survival:"; cd /tmp && timeout 280 /opt/mvtrx/venv/bin/python /opt/mvtrx/survive.py 64 2>&1 | tail -1; cd /opt/mvtrx
echo "-- gauges:"; for u in 64 216; do UIDQ=$u /opt/mvtrx/x1_gauge.sh 2>/dev/null | head -1; done
echo "-- health:"; systemctl is-active mvtrx-x3; python3 selftrade.py; echo "errors since 2:44 AM: $(journalctl -u mvtrx-x3 --since "08:44:57" --no-pager | grep -iE "error|traceback" | grep -viE "proxy|NOT READY|settle|=====|UnknownSynapse" | wc -l) | INS OVER: $(journalctl -u mvtrx-x3 --since "08:44:57" --no-pager | grep -c "INS OVER")"
} > $OUT 2>&1
echo "ALERT $(date +%s) morning read done: /opt/mvtrx/morning_read.txt" >> /opt/mvtrx/alerts.txt

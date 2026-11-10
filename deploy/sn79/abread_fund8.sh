#!/bin/sh
cd /opt/mvtrx; { echo "== $(TZ=America/Chicago date) test fund8: fundamental lean 0.3 (A) vs 0 (B) on base pull 0 / skew 5 / ladder 2:5:10:20 / inside 5"; cat liveswitch_fund8_log.txt; (ulimit -v 3000000; nice -n 10 python3 abwin.py live_tape_x3.jsonl liveswitch_fund8_log.txt fleet=7,31,40,52,59,87,102,111,133,134,147,156,210,216,241,252,255 us=64 --clip=20) 2>&1; } > /opt/mvtrx/ab_read_fund8.txt 2>&1
echo "ALERT $(date +%s) test fund8 read done: /opt/mvtrx/ab_read_fund8.txt" >> /opt/mvtrx/alerts.txt

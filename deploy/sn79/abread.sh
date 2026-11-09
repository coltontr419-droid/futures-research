#!/bin/sh
cd /opt/mvtrx; { echo "== $(TZ=America/Chicago date) \$300 pull on/off ABAB read (A = pull OFF, B = pull ON)"; cat liveswitch_log.txt; (ulimit -v 3000000; nice -n 10 python3 abwin.py live_tape_x3.jsonl liveswitch_log.txt fleet=7,31,40,52,59,87,102,111,133,134,147,156,210,216,241,252,255 us=64) 2>&1; } > /opt/mvtrx/ab_read.txt 2>&1
echo "ALERT $(date +%s) \$300 pull ABAB read done: /opt/mvtrx/ab_read.txt" >> /opt/mvtrx/alerts.txt

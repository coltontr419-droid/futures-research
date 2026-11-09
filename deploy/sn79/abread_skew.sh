#!/bin/sh
cd /opt/mvtrx; { echo "== $(TZ=America/Chicago date) \skew A=5 vs B=10 ABAB read (pull on)"; cat liveswitch_skew_log.txt; (ulimit -v 3000000; nice -n 10 python3 abwin.py live_tape_x3.jsonl liveswitch_skew_log.txt fleet=7,31,40,52,59,87,102,111,133,134,147,156,210,216,241,252,255 us=64) 2>&1; } > /opt/mvtrx/ab_read_skew.txt 2>&1
echo "ALERT $(date +%s) \skew ABAB read done: /opt/mvtrx/ab_read_skew.txt" >> /opt/mvtrx/alerts.txt

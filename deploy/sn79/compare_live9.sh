#!/bin/sh
# Comparison 9 (decisions.md §1207): fast path vs the same + flow_pull=0.3.
R=/opt/mvtrx/live_compare9.txt; P=/opt/mvtrx/venv/bin/python
echo "comparison 9 $(date -u +%H:%M) UTC" > $R
for t in live_tape_x1_fast live_tape_x1_flowpull; do
  cp /opt/mvtrx/$t.jsonl /tmp/c9_$t.jsonl; echo "== $t" >> $R
  for s in markouts.py takers.py invloss.py; do nice -n 10 $P /opt/mvtrx/$s /tmp/c9_$t.jsonl 93 >> $R 2>&1; done; rm -f /tmp/c9_$t.jsonl
done

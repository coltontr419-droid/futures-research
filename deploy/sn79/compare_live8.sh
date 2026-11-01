#!/bin/sh
# Comparison 8 (decisions.md §1207): pull 1.0 vs the same + fast path (speed only).
R=/opt/mvtrx/live_compare8.txt; P=/opt/mvtrx/venv/bin/python
echo "comparison 8 $(date -u +%H:%M) UTC" > $R
for t in live_tape_x1_pull1 live_tape_x1_fast; do
  cp /opt/mvtrx/$t.jsonl /tmp/c8_$t.jsonl; echo "== $t" >> $R
  for s in markouts.py takers.py invloss.py; do nice -n 10 $P /opt/mvtrx/$s /tmp/c8_$t.jsonl 93 >> $R 2>&1; done; rm -f /tmp/c8_$t.jsonl
done

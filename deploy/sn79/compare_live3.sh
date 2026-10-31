#!/bin/sh
# Comparison 3 (decisions.md §1199): pull vs pull + inventory cap, with loss-by-inventory and taker breakdowns.
R=/opt/mvtrx/live_compare3.txt; P=/opt/mvtrx/venv/bin/python
echo "comparison 3 $(date -u +%H:%M) UTC" > $R
for t in live_tape_x1_pull live_tape_x1_invcap; do
  cp /opt/mvtrx/$t.jsonl /tmp/c3_$t.jsonl; echo "== $t" >> $R
  for s in markouts.py takers.py invloss.py; do nice -n 10 $P /opt/mvtrx/$s /tmp/c3_$t.jsonl 93 >> $R 2>&1; done; rm -f /tmp/c3_$t.jsonl
done

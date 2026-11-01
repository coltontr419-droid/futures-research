#!/bin/sh
# Comparison 10 (decisions.md §1207): fast path vs the same + sticky=1 (queue position).
R=/opt/mvtrx/live_compare10.txt; P=/opt/mvtrx/venv/bin/python
echo "comparison 10 $(date -u +%H:%M) UTC" > $R
for t in live_tape_x1_fast live_tape_x1_sticky; do
  cp /opt/mvtrx/$t.jsonl /tmp/c10_$t.jsonl; echo "== $t" >> $R
  for s in markouts.py takers.py invloss.py swept.py; do nice -n 10 $P /opt/mvtrx/$s /tmp/c10_$t.jsonl 93 >> $R 2>&1; done; rm -f /tmp/c10_$t.jsonl
done

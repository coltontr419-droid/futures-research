#!/bin/sh
# Second comparison (decisions.md §1199): the pull setting with ~1.5 h of data, plus who takes our quotes under it.
R=/opt/mvtrx/live_compare2.txt; P=/opt/mvtrx/venv/bin/python
echo "comparison 2 $(date -u +%H:%M) UTC" > $R
for t in live_tape_x1_nopred live_tape_x1_pull; do
  cp /opt/mvtrx/$t.jsonl /tmp/c2_$t.jsonl; echo "== $t" >> $R
  nice -n 10 $P /opt/mvtrx/markouts.py /tmp/c2_$t.jsonl 93 >> $R 2>&1; nice -n 10 $P /opt/mvtrx/takers.py /tmp/c2_$t.jsonl 93 >> $R 2>&1; rm -f /tmp/c2_$t.jsonl
done

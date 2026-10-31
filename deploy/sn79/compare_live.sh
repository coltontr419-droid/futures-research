#!/bin/sh
# Live markout comparison (decisions.md §1199): old lab model (no join) vs no predictor (join) vs live-fitted 30 s model (join).
R=/opt/mvtrx/live_compare.txt; P=/opt/mvtrx/venv/bin/python
echo "live comparison $(date -u +%H:%M) UTC" > $R
for t in live_tape_x1 live_tape_x1_nopred live_tape_x1_livemodel; do
  cp /opt/mvtrx/$t.jsonl /tmp/cmp_$t.jsonl 2>/dev/null || continue
  echo "== $t" >> $R; nice -n 10 $P /opt/mvtrx/markouts.py /tmp/cmp_$t.jsonl 93 >> $R 2>&1; rm -f /tmp/cmp_$t.jsonl
done

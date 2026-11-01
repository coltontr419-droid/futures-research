#!/bin/sh
# Generic live comparison (decisions.md §1207): markouts, takers, inventory loss and sweep share for two tapes.
# usage: compare_pair.sh <tape A name> <tape B name> <result file>
R=$3; P=/opt/mvtrx/venv/bin/python
echo "comparison $1 vs $2 $(date -u +%H:%M) UTC" > $R
for t in $1 $2; do
  cp /opt/mvtrx/$t.jsonl /tmp/cp_$t.jsonl; echo "== $t" >> $R
  for s in markouts.py takers.py invloss.py swept.py; do nice -n 10 $P /opt/mvtrx/$s /tmp/cp_$t.jsonl 93 >> $R 2>&1; done; rm -f /tmp/cp_$t.jsonl
done

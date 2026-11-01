#!/bin/sh
# Readout of a per-book A/B run: markouts per arm + EXACT making credit per arm. usage: read_arms.sh <tape name> <n arms> "<labels>" <out file>
cp /opt/mvtrx/$1.jsonl /tmp/rarm.jsonl
echo "=== readout $(date -u +%H:%M) UTC" >> $4
nice -n 10 /opt/mvtrx/venv/bin/python /opt/mvtrx/compare_arms.py /tmp/rarm.jsonl ${UID_X:-41} $2 "$3" >> $4 2>&1
echo "--- making credit per arm, EXACT (making_exact.py)" >> $4
cd /opt/mvtrx/repo && nice -n 10 /opt/mvtrx/venv/bin/python /opt/mvtrx/making_exact.py /tmp/rarm.jsonl ${UID_X:-41} $2 >> $4 2>&1
rm -f /tmp/rarm.jsonl

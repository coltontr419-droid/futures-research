#!/bin/sh
cp /opt/mvtrx/live_tape_x1_arms1.jsonl /tmp/ra1.jsonl
echo "=== readout $(date -u +%H:%M) UTC" >> /opt/mvtrx/arms1_readouts.txt
nice -n 10 /opt/mvtrx/venv/bin/python /opt/mvtrx/compare_arms.py /tmp/ra1.jsonl 41 4 "base (fast+cancel_first),edge=2,edge=3,flow pull 10s/3s/0.3" >> /opt/mvtrx/arms1_readouts.txt 2>&1
rm -f /tmp/ra1.jsonl

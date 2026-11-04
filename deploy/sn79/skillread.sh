#!/bin/sh
cd /opt/mvtrx
for L in 30 45; do
  echo "== x2 (tilt) last $L sim min"; nice venv/bin/python skill_val.py live_tape_x2.jsonl 247 $L skip_x2.txt 2>&1 | grep -v Warn
  echo "== x1 (sleeve on skipped books) last $L sim min"; nice venv/bin/python skill_val.py live_tape_x1_size6.jsonl 213 $L skip_x1.txt 2>&1 | grep -v Warn
done

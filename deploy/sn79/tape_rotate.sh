#!/bin/sh
# Nightly (decisions.md §1236): a live tape over 2 GB keeps its last 1 GB as <tape>.prev, then is truncated in place (the agent appends with
# O_APPEND to the same inode, so it keeps writing). Readers that need history read <tape>.prev then <tape>.
for f in /opt/mvtrx/live_tape_x1.jsonl /opt/mvtrx/live_tape_x2c.jsonl; do
  [ -f "$f" ] || continue
  sz=$(stat -c %s "$f")
  if [ "$sz" -gt 2000000000 ]; then
    tail -c 1000000000 "$f" | tail -n +2 > "$f.prev.tmp" && mv "$f.prev.tmp" "$f.prev" && truncate -s 0 "$f"
    echo "$(date -u +%FT%TZ) rotated $f ($sz bytes)" >> /opt/mvtrx/tape_rotate.log
  fi
done

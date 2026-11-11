#!/bin/sh
# build /opt/mvtrx/tape_ab.jsonl (= rotated .prev + live tape) for A/B reads; prints its path
cd /opt/mvtrx
if [ -f live_tape_x3.jsonl.prev ]; then cat live_tape_x3.jsonl.prev live_tape_x3.jsonl > tape_ab.jsonl; else cp live_tape_x3.jsonl tape_ab.jsonl; fi
echo /opt/mvtrx/tape_ab.jsonl

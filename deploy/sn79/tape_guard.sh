#!/bin/sh
# §1412: unattended guard — if x3 (tape recorder) is no longer registered, move the tape to x1 once (tape_to_x1.sh checks registration itself).
cd /opt/mvtrx
[ -f tape_moved_to_x1.flag ] && exit 0
cd /tmp && /opt/mvtrx/venv/bin/python /opt/mvtrx/regcheck.py x3=64 > /dev/null 2>&1 && exit 0
cd /opt/mvtrx; sh tape_to_x1.sh >> tape_guard.log 2>&1 && touch tape_moved_to_x1.flag

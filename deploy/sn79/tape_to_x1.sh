#!/bin/sh
# §1409: if x3 (the only tape recorder) is pruned, move tape= to x1 at once (gated restart of x1). Run ONLY after regcheck says x3 is NOT registered.
cd /opt/mvtrx
cd /tmp && /opt/mvtrx/venv/bin/python /opt/mvtrx/regcheck.py x3=64 > /dev/null 2>&1 && { echo "x3 still registered - not moving the tape"; exit 1; }
cd /opt/mvtrx; U=/etc/systemd/system/mvtrx-x1.service; cp $U mvtrx-x1.service.pre-tape
grep -q "tape=/opt/mvtrx/live_tape_x3.jsonl" $U || sed -i "s| lock_dir=/opt/mvtrx/locks | lock_dir=/opt/mvtrx/locks tape=/opt/mvtrx/live_tape_x3.jsonl |" $U
grep -c "tape=/opt/mvtrx/live_tape_x3.jsonl" $U
systemctl stop mvtrx-x3 2>/dev/null; systemctl disable mvtrx-x3 2>/dev/null
sh /opt/mvtrx/restart_x1.sh; tail -2 /opt/mvtrx/restart_x1.log
echo "ALERT $(date +%s) x3 pruned: tape moved to x1 (x1 restarted)" >> /opt/mvtrx/alerts.txt

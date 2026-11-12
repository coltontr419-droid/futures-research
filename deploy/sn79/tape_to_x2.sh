#!/bin/sh
# §1409: if x1 (the tape recorder) is pruned, move tape= to x1 at once (gated restart of x1). Run ONLY after regcheck says x3 is NOT registered.
cd /opt/mvtrx
cd /tmp && /opt/mvtrx/venv/bin/python /opt/mvtrx/regcheck.py x1=27 > /dev/null 2>&1 && { echo "x3 still registered - not moving the tape"; exit 1; }
cd /opt/mvtrx; U=/etc/systemd/system/mvtrx-x2.service; cp $U mvtrx-x2.service.pre-tape
grep -q "tape=/opt/mvtrx/live_tape_x3.jsonl" $U || sed -i "s| lock_dir=/opt/mvtrx/locks | lock_dir=/opt/mvtrx/locks tape=/opt/mvtrx/live_tape_x3.jsonl |" $U
grep -c "tape=/opt/mvtrx/live_tape_x3.jsonl" $U
systemctl stop mvtrx-x1 2>/dev/null; systemctl disable mvtrx-x1 2>/dev/null; cp our_uids.txt our_uids.txt.pre-x1prune; sed -i "/^27 /d" our_uids.txt
B=$(systemctl show -p ActiveEnterTimestamp --value mvtrx-x2); systemctl daemon-reload; systemctl restart mvtrx-x2; sleep 5; echo "x2 restarted: $B -> $(systemctl show -p ActiveEnterTimestamp --value mvtrx-x2)"
echo "ALERT $(date +%s) x1 pruned: tape moved to x2 (x2 restarted)" >> /opt/mvtrx/alerts.txt

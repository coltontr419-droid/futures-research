#!/bin/sh
# §1399: after the sim day resets (86,400 → 0), our_uids.txt start sims (old-sim values) would make selftrade.py / the watchdog ignore every new fill.
# Once the live tape's last ts is in the NEW sim (< 20,000 s), set every start to 0 (prior owners' fills are from the old sim and long out of the 200 MB window).
cd /opt/mvtrx
T=$(python3 -c "import json; f=open('live_tape_x3.jsonl','rb'); f.seek(-4000,2); print(int(json.loads(f.read().split(b'\n')[-2])['ts']/1e9))")
if [ "$T" -lt 20000 ]; then
  cp our_uids.txt our_uids.txt.pre-simreset
  awk '{ if (NF >= 4) $4 = 0; print }' our_uids.txt.pre-simreset > our_uids.txt
  echo "ALERT $(date +%s) sim reset seen (tape ts $T): our_uids start sims set to 0" >> alerts.txt
  python3 selftrade.py >> alerts_simreset.txt 2>&1
else
  echo "ALERT $(date +%s) sim reset NOT seen yet (tape ts $T) - our_uids unchanged, check again" >> alerts.txt
fi

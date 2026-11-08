#!/bin/sh
# Launch a newly registered maker safely (decisions.md §1298, §1315), in the new-UID checklist order:
#   1. the hotkey must hold a UID on SN79 (fresh chain check)   2. our_uids.txt gets "<uid> maker <name> <start sim s>" BEFORE the miner starts
#   3. no stale heartbeat/ledger under that UID                  4. tape: if nobody wrote the tape in the last 2 min, this miner records it
#   5. enable + start the unit   6. verify: running, heartbeat, quoting, no errors
#   usage: sh launch_maker.sh <name e.g. x3>        (the unit /etc/systemd/system/mvtrx-<name>.service must already exist)
set -e
N=$1; [ -n "$N" ] || { echo "usage: launch_maker.sh <name>"; exit 1; }
U=/etc/systemd/system/mvtrx-$N.service; [ -f "$U" ] || { echo "no unit $U"; exit 1; }
grep -q -- "--wallet.hotkey $N " $U || { echo "unit hotkey is not $N"; exit 1; }
cd /opt/mvtrx
TAPE=/opt/mvtrx/live_tape_x3.jsonl
UID_=$(cd /tmp && timeout 150 /opt/mvtrx/venv/bin/python -c "
import json, bittensor as bt
hk = json.load(open('/root/.bittensor/wallets/main/hotkeys/$N'))['ss58Address']
m = bt.Subtensor(network='finney').metagraph(79, lite=True)
u = [i for i, h in enumerate(m.hotkeys) if h == hk]
print(u[0] if u else 'NONE')" 2>/dev/null | tail -1)
[ "$UID_" != "NONE" ] && [ -n "$UID_" ] || { echo "$N is NOT registered on SN79 - stop"; exit 1; }
echo "1. $N holds UID $UID_"
# start sim s: (a) a running maker's log, (b) the tape's last line if the tape is fresh, (c) none -> read it from this miner right after start (§1315)
SIM=$(for s in $(awk '$2=="maker"{print $3}' our_uids.txt); do [ "$s" = "$N" ] && continue; journalctl -u mvtrx-$s --since "-3min" --no-pager | grep -o "T=[0-9]*" | tail -1; done | head -1 | cut -c3-)
SIMS=$(( ${SIM:-0} / 1000000000 ))
AGE=$(( $(date +%s) - $(stat -c %Y $TAPE 2>/dev/null || echo 0) ))
if [ "$SIMS" -le 0 ] && [ "$AGE" -lt 120 ]; then
  SIMS=$(python3 -c "import json; f=open('$TAPE','rb'); f.seek(-4000,2); print(int(json.loads(f.read().split(b'\n')[-2])['ts']/1e9))")
  echo "   (sim time from the fresh tape: $SIMS)"
fi
cp our_uids.txt our_uids.txt.bak-launch-$N
sed -i "/ $N /d; /^$UID_ /d" our_uids.txt
if [ "$SIMS" -gt 0 ]; then echo "$UID_ maker $N $SIMS" >> our_uids.txt; echo "2. our_uids.txt: $UID_ maker $N $SIMS"
else echo "2. no running maker and no fresh tape: the start sim s is written right after this miner starts (no takers -> no self-trade risk)"; fi
[ -f pace_$UID_.ledger ] && mv pace_$UID_.ledger pace_$UID_.ledger.old-$(date +%s) && echo "3. moved an old ledger for UID $UID_ aside" || echo "3. no old ledger for UID $UID_"
rm -f locks/maker_$UID_.hb
if [ "$AGE" -ge 120 ] && ! grep -q "tape=" $U; then
  cp $U /opt/mvtrx/mvtrx-$N.service.pre-tape-$(date +%s)
  sed -i "s| lock_dir=/opt/mvtrx/locks | lock_dir=/opt/mvtrx/locks tape=$TAPE |" $U
  grep -q "tape=" $U && echo "4. tape was idle ${AGE}s -> $N now records it" || { echo "4. could not add tape= to $U - stop"; exit 1; }
else echo "4. tape is being recorded (last write ${AGE}s ago) or $N already records it"; fi
systemctl daemon-reload; systemctl enable mvtrx-$N 2>/dev/null; systemctl restart mvtrx-$N
T0=$(systemctl show mvtrx-$N -p ActiveEnterTimestamp --value); echo "5. started $T0"
i=0; while [ $i -lt 120 ]; do journalctl -u mvtrx-$N --since "$T0" --no-pager | grep -qE "MK QUALITY|PACE STATUS" && break; sleep 5; i=$((i+1)); done
if [ "$SIMS" -le 0 ]; then
  SIM=$(journalctl -u mvtrx-$N --since "$T0" --no-pager | grep -o "T=[0-9]*" | head -1 | cut -c3-); SIMS=$(( ${SIM:-0} / 1000000000 ))
  [ "$SIMS" -gt 0 ] && echo "$UID_ maker $N $SIMS" >> our_uids.txt && echo "   our_uids.txt: $UID_ maker $N $SIMS (from this miner)" || echo "   WARNING: could not read the sim time - add the our_uids line by hand"
fi
cat our_uids.txt
E=$(journalctl -u mvtrx-$N --since "$T0" --no-pager | grep -cE "Traceback|QUOTE ERROR" || true)
echo "6. active: $(systemctl is-active mvtrx-$N) | heartbeat: $(ls locks/maker_$UID_.hb 2>/dev/null || echo MISSING) | errors: $E | $(journalctl -u mvtrx-$N --since "$T0" --no-pager | grep "PACE STATUS" | tail -1 | grep -o "[0-9]* of [0-9]* traded books blocked")"
echo "Remember: copy <name>pub.txt to the futures droplet if it is not there (earnings + push-out alerts)."

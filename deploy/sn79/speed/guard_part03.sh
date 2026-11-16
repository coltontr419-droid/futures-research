#!/bin/sh
# §1536 auto-revert guard for the mk_gate_part 0.3 tweak on 255 (user rule: tweaks to a winner get an automatic revert).
# Every 10 min for 100 min: if >= 360 sim s since the switch and the validator-exact $300 alpha per sim min < 3.0 (proven 4.5) or $300 bp/$ < +0.8 -> set mk_gate_part back to 0.5.
cd /opt/mvtrx; SW=$1; L=/opt/mvtrx/guard_part03.log
for i in $(seq 1 10); do
  sleep 600
  /opt/mvtrx/venv/bin/python regcheck.py x2=255 >/dev/null 2>&1 || { echo "$(date -u +%H:%M) not registered - guard stops" >> $L; exit 0; }
  grep -q '"mk_gate_part": 0.3' live_params_255.json || { echo "$(date -u +%H:%M) gate_part no longer 0.3 - guard stops" >> $L; exit 0; }
  S=$(journalctl -u mvtrx-x2 --since "-1min" --no-pager | grep -o "T=[0-9]*" | tail -1 | cut -c3- | awk '{print int($1/1e9)}')
  [ -n "$S" ] || continue; D=$((S - SW)); [ $D -ge 360 ] || { echo "$(date -u +%H:%M) sim +$D s - waiting" >> $L; continue; }
  M=$(echo "$D" | awk '{printf "%.2f", $1/60}')
  R=$( (ulimit -v 7000000; nice -n 10 timeout 300 venv/bin/python speed/skill_cls2.py live_tape_x3.jsonl $M 255) 2>&1 | grep "uid 255" | head -1)
  A=$(echo "$R" | grep -o "Σα *[-+][0-9.]*" | grep -o "[-+][0-9.]*"); B=$(echo "$R" | grep -o "= *[-+][0-9.]* bp" | grep -o "[-+][0-9.]*")
  [ -n "$A" ] || { echo "$(date -u +%H:%M) no read" >> $L; continue; }
  PM=$(echo "$A $M" | awk '{printf "%.2f", $1/$2}')
  echo "$(date -u +%H:%M) sim +$D s: \$300 Σα $A over $M min = $PM/min, $B bp/\$" >> $L
  if [ $(echo "$PM $B" | awk '{print ($1 < 3.0 || $2 < 0.8) ? 1 : 0}') = 1 ]; then
    cp live_params_255.json live_params_255.guard-reverted.json
    /opt/mvtrx/venv/bin/python -c "
import json,os
p='live_params_255.json'; d=json.load(open(p)); d['mk_gate_part']=0.5
open(p+'.tmp','w').write(json.dumps(d)); os.replace(p+'.tmp',p)"
    echo "$(date -u +%H:%M) REVERTED mk_gate_part 0.3 -> 0.5 ($PM/min, $B bp)" >> $L
    echo "$(TZ=America/Chicago date +%H:%M:%S) sim $S GUARD-REVERT {\"mk_gate_part\": 0.5}" >> liveswitch_redo255_log.txt
    echo "ALERT $(date +%s) 255 gate_part 0.3 auto-reverted to 0.5 ($PM alpha/min, $B bp)" >> alerts.txt
    exit 0
  fi
done
echo "$(date -u +%H:%M) guard finished (no revert)" >> $L

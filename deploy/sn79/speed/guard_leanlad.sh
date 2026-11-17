#!/bin/sh
# §1571 auto-revert guard for mk_lean_lad 3 on UID 47 (x1); control = UID 85 (x2, frozen). Every 10 min for 150 min, once ≥ 600 sim s after the warm-up (sim 78645):
# validator-exact $300 Σα per sim min of 47 vs 85 over the same window; revert to 0 if 47 < 0.75 × 85, or 47's $300 bp/$ < +0.8.
cd /opt/mvtrx; W0=78645; L=/opt/mvtrx/guard_leanlad.log
for i in $(seq 1 15); do
  sleep 600
  /opt/mvtrx/venv/bin/python regcheck.py x1=47 >/dev/null 2>&1 || { echo "$(date -u +%H:%M) 47 not registered - guard stops" >> $L; exit 0; }
  grep -q '"mk_lean_lad": 3' live_params_47.json || { echo "$(date -u +%H:%M) mk_lean_lad no longer 3 - guard stops" >> $L; exit 0; }
  S=$(journalctl -u mvtrx-x1 --since "-2min" --no-pager | grep -o "T=[0-9]*" | tail -1 | cut -c3- | awk '{print int($1/1e9)}')
  [ -n "$S" ] || continue; D=$((S - W0)); [ $D -ge 600 ] || { echo "$(date -u +%H:%M) sim +$D s after warm-up - waiting" >> $L; continue; }
  M=$(echo "$D" | awk '{printf "%.2f", $1/60}')
  R=$( (ulimit -v 6000000; nice -n 10 timeout 300 venv/bin/python speed/skill_cls2.py live_tape_x3.jsonl $M 47 85) 2>&1 | grep -E "uid +(47|85):" | head -2)
  A47=$(echo "$R" | grep "uid  47" | grep -o "Σα *[-+][0-9.]*" | grep -o "[-+][0-9.]*"); B47=$(echo "$R" | grep "uid  47" | grep -o "= *[-+][0-9.]* bp" | grep -o "[-+][0-9.]*")
  A85=$(echo "$R" | grep "uid  85" | grep -o "Σα *[-+][0-9.]*" | grep -o "[-+][0-9.]*")
  [ -n "$A47" ] && [ -n "$A85" ] || { echo "$(date -u +%H:%M) no read" >> $L; continue; }
  echo "$(date -u +%H:%M) +$D s ($M min): \$300 47 $A47 ($B47 bp) vs 85 $A85" >> $L
  if [ $(echo "$A47 $A85 $B47" | awk '{print ($1 < 0.75 * $2 || $3 < 0.8) ? 1 : 0}') = 1 ]; then
    cp live_params_47.json live_params_47.guard-reverted.json
    /opt/mvtrx/venv/bin/python -c "
import json,os
p='live_params_47.json'; d=json.load(open(p)); d['mk_lean_lad']=0
open(p+'.tmp','w').write(json.dumps(d)); os.replace(p+'.tmp',p)"
    echo "$(date -u +%H:%M) REVERTED mk_lean_lad 3 -> 0 (47 $A47 / $B47 bp vs 85 $A85)" >> $L
    echo "ALERT $(date +%s) UID 47 lean ladder auto-reverted (47 $A47 vs 85 $A85, $B47 bp)" >> alerts.txt
    exit 0
  fi
done
echo "$(date -u +%H:%M) guard finished (no revert)" >> $L

#!/bin/sh
# 11-15: bring a freshly registered x2 UID live on the CURRENT best settings in minutes:  sh newminer.sh <new uid> [old uid=179]
#   1 regcheck (stop if not registered)  2 START settings → live_params_<uid>.json + .START.json  3 UID copies of the A/B scripts
#   4 our_uids.txt with the start sim second  5 gated restart of mvtrx-x2 (the unit finds live_params/ledger by UIDN) + verify
set -e
N=$1; O=${2:-255}; HK=${HK:-x2}; cd /opt/mvtrx   # HK=x1 sh newminer.sh <uid> for a second miner (11-16)
[ -n "$N" ] || { echo "usage: newminer.sh <uid> [old uid]"; exit 1; }
venv/bin/python regcheck.py $HK=$N || { echo "STOP: $HK is not UID $N"; exit 1; }
[ -f live_params_$N.json ] && cp live_params_$N.json live_params_$N.json.pre-newminer
# 11-16 (§1533): start on the FROZEN proven settings (live_params_NEXT.json) with the frozen agent 683f430c
M=$(md5sum agents/QuoteAgent.py | cut -c1-8); [ "$M" = "16708680" ] || { echo "STOP: agent md5 $M is not the frozen 16708680"; exit 1; }
PF=${PARAMS:-live_params_NEXT.json}   # 11-17 §1581: PARAMS=live_params_NEXT_B1.json for the band (diversified) miner
if [ -f $PF ]; then cp $PF live_params_$N.START.json; cp $PF live_params_$N.json; echo "settings: $PF"
else cp live_params_$O.START.json live_params_$N.START.json; cp live_params_$O.START.json live_params_$N.json; fi
for s in abtest_sched abgrp skillread makingread readchain; do sed "s/live_params_$O\.json/live_params_$N.json/g; s/UIDS_EXTRA=$O:x2/UIDS_EXTRA=$N:x2/; s/ $O 252 216 / $N 252 216 /; s/_$O\.sh/_$N.sh/g" ${s}_$O.sh > ${s}_$N.sh; done
[ -f pace_$N.ledger ] && mv pace_$N.ledger pace_$N.ledger.old.$(date +%s)
B=$(systemctl show -p ActiveEnterTimestamp --value mvtrx-$HK)
systemctl enable mvtrx-$HK >/dev/null 2>&1 || true; systemctl restart mvtrx-$HK; sleep 5
A=$(systemctl show -p ActiveEnterTimestamp --value mvtrx-$HK); [ "$A" != "$B" ] && echo "RESTARTED $A" || { echo "RESTART NOT CONFIRMED"; exit 1; }
for i in $(seq 1 24); do SIM=$(journalctl -u mvtrx-$HK --since "-2min" --no-pager | grep -o "T=[0-9]*" | tail -1 | cut -c3- | awk '{print int($1/1e9)}'); [ -n "$SIM" ] && break; sleep 10; done
[ -n "$SIM" ] || { echo "no state yet — set our_uids.txt by hand"; exit 1; }
cp our_uids.txt our_uids.txt.bak-$N; if [ "$HK" = "x2" ]; then echo "$N maker x2 $SIM" > our_uids.txt; else echo "$N maker $HK $SIM" >> our_uids.txt; fi; echo "our_uids: $(cat our_uids.txt)"
grep -h "live_params_\|UIDS_EXTRA\| $N 252" abtest_sched_$N.sh abgrp_$N.sh skillread_$N.sh makingread_$N.sh | grep -o "live_params_[0-9]*.json\|UIDS_EXTRA=[0-9]*:x2\| $N 252 216" | sort -u
journalctl -u mvtrx-$HK --since "-2min" --no-pager | grep -E "PACE ledger|REPLIES|QUOTE ERROR|Traceback" | cut -c60-200 | tail -4

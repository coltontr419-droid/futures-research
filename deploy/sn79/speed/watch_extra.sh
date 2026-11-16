#!/bin/sh
# §1541 extra standing checks, called by overnight.sh every 10 min, one ALERT line per problem (forwarded like the others):
#  hung miner (no validator state for > 6 min), slow replies (call time > 1.0 s), coverage < 170, skill net alpha < 0 for 2 checks in a row,
#  scoring-validator gauges missing for our UID.
cd /opt/mvtrx; S=/opt/mvtrx/ov_state
for u in $(awk '{print $1":"$3}' our_uids.txt); do
  U=${u%%:*}; H=${u##*:}
  systemctl is-active -q mvtrx-$H || continue
  LAST=$(journalctl -u mvtrx-$H --since "-6min" --no-pager | grep -c "T=[0-9]")
  [ "$LAST" -eq 0 ] && echo "ALERT $H UID $U: no validator state for > 6 min (hung or not queried)"
  CT=$(UIDS="$U" sh speed/ct.sh 2>/dev/null | grep -o "\[[0-9.]*\]" | tr -d "[]" | head -1)
  [ -n "$CT" ] && [ $(echo "$CT" | awk '{print ($1 > 1.0)}') = 1 ] && echo "ALERT $H UID $U: slow replies, call time $CT s (> 1.0)"
  G=$(UIDS="$U" GAUGES="debeta_coverage_books debeta_skill_net_alpha" sh speed/gauges.sh 2>/dev/null | awk 'NR>1{print $2}' | tr "\n" " ")
  COV=$(echo $G | cut -d" " -f1); NA=$(echo $G | cut -d" " -f2)
  if [ -z "$COV" ] || [ "$COV" = "NA" ]; then echo "ALERT $H UID $U: scoring validator 5EWwdZB7 shows no gauges for us"; continue; fi
  [ $(echo "$COV" | awk '{print ($1 < 170)}') = 1 ] && echo "ALERT $H UID $U: coverage $COV books (< 170; skill is cut below 160)"
  if [ $(echo "$NA" | awk '{print ($1 < 0)}') = 1 ]; then
    [ -f $S/neg_$U ] && echo "ALERT $H UID $U: skill net alpha negative two checks in a row ($NA)"; touch $S/neg_$U
  else rm -f $S/neg_$U; fi
  echo "  extra $H UID $U: states(6 min) $LAST | call ${CT:-?} s | coverage $COV | net alpha $NA"
done

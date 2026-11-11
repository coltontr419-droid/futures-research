#!/bin/sh
# §1378: fc10 = capped fund lean (fund 0.3, fund_cap 0.5 spread) (A) vs base fund 0 (B), ABAB half-hours from 00:35 UTC (6:35 PM CT, 21 min after the restart).
cd /opt/mvtrx
sed 's/liveswitch_skip8_log.txt/liveswitch_fc10_log.txt/' liveswitch_skip8.sh > liveswitch_fc10.sh
BASE='"flow_pull": 0, "skew": 5, "mk_vol_touch_min": 0, "mk_nochase_bp": 1, "mk_vol_lad": "2:5:10:20", "mk_vol_inside": 5, "mk_skip_vol": 0'
i=0
for L in A B A B; do
  T=$(date -u -d "2026-11-11 00:35:00 UTC + $((i * 30)) min" "+%Y-%m-%d %H:%M:%S")
  if [ $L = A ]; then X='"fund": 0.3, "fund_cap": 0.5'; else X='"fund": 0, "fund_cap": 0'; fi
  systemd-run --quiet --unit mvtrx-fc10-$i --on-calendar "$T UTC" /bin/sh /opt/mvtrx/liveswitch_fc10.sh $L "{$BASE, $X}"; i=$((i + 1))
done
systemd-run --quiet --unit mvtrx-fc10-end --on-calendar "2026-11-11 02:35:00 UTC" /bin/sh /opt/mvtrx/liveswitch_fc10.sh END "{$BASE, \"fund\": 0, \"fund_cap\": 0}"
cat > abread_fc10.sh <<'R'
#!/bin/sh
cd /opt/mvtrx
{ echo "== $(TZ=America/Chicago date) test fc10: capped fund lean (fund 0.3, cap 0.5 spread) (A) vs fund 0 (B) — judge on WHOLE-MINER credit vs UID 216 drift; per fill second"
  cat liveswitch_fc10_log.txt; echo "-- whole-miner credit:"; sh abcredit.sh liveswitch_fc10_log.txt /dev/null 2>&1
  echo "-- per fill (capped):"; (ulimit -v 3000000; nice -n 10 python3 abwin.py live_tape_x3.jsonl liveswitch_fc10_log.txt fleet=7,31,40,52,59,87,102,111,133,134,147,156,210,216,241,252,255 us=64 --clip=20) 2>&1 | grep "^=="; } > /opt/mvtrx/ab_read_fc10.txt 2>&1
echo "ALERT $(date +%s) test fc10 read done: /opt/mvtrx/ab_read_fc10.txt" >> /opt/mvtrx/alerts.txt
R
systemd-run --quiet --unit mvtrx-fc10-read --on-calendar "2026-11-11 02:38:00 UTC" /bin/sh /opt/mvtrx/abread_fc10.sh
systemctl list-timers --all | grep fc10 | awk '{print $2, $3, $NF}'

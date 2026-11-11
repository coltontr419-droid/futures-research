#!/bin/sh
# §1379: fm11 = fundamental MOVE lean on $300 books (fund_mv 0.5 × Δf over 10 s, clipped ±1 spread) (A) vs off (B), ABAB half-hours from 03:10 UTC (9:10 PM CT, 23 min after the restart).
cd /opt/mvtrx
sed 's/liveswitch_skip8_log.txt/liveswitch_fm11_log.txt/' liveswitch_skip8.sh > liveswitch_fm11.sh
BASE='"flow_pull": 0, "skew": 5, "mk_vol_touch_min": 0, "mk_nochase_bp": 1, "mk_vol_lad": "2:5:10:20", "mk_vol_inside": 5, "mk_skip_vol": 0, "fund": 0, "fund_cap": 0'
i=0
for L in A B A B; do
  T=$(date -u -d "2026-11-11 03:10:00 UTC + $((i * 30)) min" "+%Y-%m-%d %H:%M:%S")
  if [ $L = A ]; then X='"fund_mv": 0.5, "fund_mv_cap": 1.0'; else X='"fund_mv": 0, "fund_mv_cap": 1.0'; fi
  systemd-run --quiet --unit mvtrx-fm11-$i --on-calendar "$T UTC" /bin/sh /opt/mvtrx/liveswitch_fm11.sh $L "{$BASE, $X}"; i=$((i + 1))
done
systemd-run --quiet --unit mvtrx-fm11-end --on-calendar "2026-11-11 05:10:00 UTC" /bin/sh /opt/mvtrx/liveswitch_fm11.sh END "{$BASE, \"fund_mv\": 0, \"fund_mv_cap\": 1.0}"
cat > abread_fm11.sh <<'R'
#!/bin/sh
cd /opt/mvtrx
{ echo "== $(TZ=America/Chicago date) test fm11: fundamental MOVE lean on \$300 (fund_mv 0.5, 10 s, cap 1 spread) (A) vs off (B) — WHOLE-MINER credit vs UID 216 first; per fill second"
  cat liveswitch_fm11_log.txt; echo "-- whole-miner credit:"; sh abcredit.sh liveswitch_fm11_log.txt /dev/null 2>&1
  echo "-- per fill (capped):"; (ulimit -v 3000000; nice -n 10 python3 abwin.py live_tape_x3.jsonl liveswitch_fm11_log.txt fleet=7,31,40,52,59,87,102,111,133,134,147,156,210,216,241,252,255 us=64 --clip=20) 2>&1 | grep "^=="; } > /opt/mvtrx/ab_read_fm11.txt 2>&1
echo "ALERT $(date +%s) test fm11 read done: /opt/mvtrx/ab_read_fm11.txt" >> /opt/mvtrx/alerts.txt
R
systemd-run --quiet --unit mvtrx-fm11-read --on-calendar "2026-11-11 05:13:00 UTC" /bin/sh /opt/mvtrx/abread_fm11.sh
systemctl list-timers --all | grep fm11 | awk '{print $2, $3, $NF}'

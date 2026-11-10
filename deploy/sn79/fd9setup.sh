#!/bin/sh
# §1377: fund 0.3 (A) vs 0 (B) re-test, 4 half-hours BABA from 22:05 UTC (4:05 PM CT), pooled with fund8 (ABAB 11:20-1:20) for the read.
cd /opt/mvtrx
sed 's/liveswitch_skip8_log.txt/liveswitch_fd9_log.txt/' liveswitch_skip8.sh > liveswitch_fd9.sh
BASE='"flow_pull": 0, "skew": 5, "mk_vol_touch_min": 0, "mk_nochase_bp": 1, "mk_vol_lad": "2:5:10:20", "mk_vol_inside": 5, "mk_skip_vol": 0'
i=0
for L in B A B A; do
  T=$(date -u -d "2026-11-10 22:05:00 UTC + $((i * 30)) min" "+%Y-%m-%d %H:%M:%S")
  if [ $L = A ]; then F=0.3; else F=0; fi
  systemd-run --quiet --unit mvtrx-fd9-$i --on-calendar "$T UTC" /bin/sh /opt/mvtrx/liveswitch_fd9.sh $L "{$BASE, \"fund\": $F}"; i=$((i + 1))
done
systemd-run --quiet --unit mvtrx-fd9-end --on-calendar "2026-11-10 00:05:00 UTC" /bin/true 2>/dev/null; systemctl stop mvtrx-fd9-end.timer 2>/dev/null
systemd-run --quiet --unit mvtrx-fd9-end2 --on-calendar "2026-11-11 00:05:00 UTC" /bin/sh /opt/mvtrx/liveswitch_fd9.sh END "{$BASE, \"fund\": 0}"
cat > abread_fd9.sh <<'R'
#!/bin/sh
cd /opt/mvtrx; cat liveswitch_fund8_log.txt liveswitch_fd9_log.txt > liveswitch_fdpool_log.txt
{ echo "== $(TZ=America/Chicago date) test fd9 (+fund8 pooled, 8 half-hours): fund 0.3 (A) vs 0 (B) — judge on WHOLE-MINER credit vs UID 216 drift; per fill second"
  cat liveswitch_fdpool_log.txt; echo "-- whole-miner credit, fd9 alone:"; sh abcredit.sh liveswitch_fd9_log.txt /dev/null 2>&1
  echo "-- whole-miner credit, pooled fund8+fd9:"; sh abcredit.sh liveswitch_fdpool_log.txt /dev/null 2>&1
  echo "-- per fill (capped), pooled:"; (ulimit -v 3000000; nice -n 10 python3 abwin.py live_tape_x3.jsonl liveswitch_fdpool_log.txt fleet=7,31,40,52,59,87,102,111,133,134,147,156,210,216,241,252,255 us=64 --clip=20) 2>&1 | grep "^=="; } > /opt/mvtrx/ab_read_fd9.txt 2>&1
echo "ALERT $(date +%s) test fd9 read done: /opt/mvtrx/ab_read_fd9.txt" >> /opt/mvtrx/alerts.txt
R
systemd-run --quiet --unit mvtrx-fd9-read --on-calendar "2026-11-11 00:08:00 UTC" /bin/sh /opt/mvtrx/abread_fd9.sh
systemctl list-timers --all | grep fd9

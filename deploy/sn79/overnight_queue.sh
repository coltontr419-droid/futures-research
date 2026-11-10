#!/bin/sh
# §1361: overnight ABAB test queue for x3 (UID 64) — schedules server-side timers ONLY when run with the user's approval.
#   sh /opt/mvtrx/overnight_queue.sh <start UTC "YYYY-MM-DD HH:MM">   (each test = 4 × 30-min windows A/B/A/B + END, read 3 min after END)
# Base settings (winners so far): pull 0.3, skew 5, touch_min 0, no-chase 1, $300 ladder = winner of test 5 (set LAD below before running).
set -e; cd /opt/mvtrx
LAD=${LAD:-"2:5:10"}; START="$1"; [ -n "$START" ] || { echo "usage: overnight_queue.sh 'YYYY-MM-DD HH:MM' (UTC)"; exit 1; }
BASE="\"flow_pull\": 0.3, \"skew\": 5, \"mk_vol_touch_min\": 0, \"mk_nochase_bp\": 1, \"mk_vol_lad\": \"$LAD\""
t0=$(date -u -d "$START" +%s)
mk() {  # name, A-json-extra, B-json-extra, windows (4 or 8)
  N=$1; A=$2; B=$3; W=${4:-4}
  sed "s|/opt/mvtrx/liveswitch_log.txt|/opt/mvtrx/liveswitch_${N}_log.txt|" liveswitch.sh > liveswitch_$N.sh; : > liveswitch_${N}_log.txt
  i=0; while [ $i -lt $W ]; do
    L=A; X="$A"; [ $((i % 2)) -eq 1 ] && { L=B; X="$B"; }
    T=$(date -u -d @$((t0 + i * 1800)) "+%Y-%m-%d %H:%M:%S")
    systemd-run --quiet --unit mvtrx-on-$N-$i --on-calendar "$T UTC" /bin/sh /opt/mvtrx/liveswitch_$N.sh $L "{$BASE$X}"; i=$((i + 1)); done
  T=$(date -u -d @$((t0 + W * 1800)) "+%Y-%m-%d %H:%M:%S"); systemd-run --quiet --unit mvtrx-on-$N-end --on-calendar "$T UTC" /bin/sh /opt/mvtrx/liveswitch_$N.sh END "{$BASE}"
  cat > abread_$N.sh <<R
#!/bin/sh
cd /opt/mvtrx; { echo "== \$(TZ=America/Chicago date) overnight test $N (A: $A | B: $B)"; cat liveswitch_${N}_log.txt; (ulimit -v 3000000; nice -n 10 python3 abwin.py live_tape_x3.jsonl liveswitch_${N}_log.txt fleet=7,31,40,52,59,87,102,111,133,134,147,156,210,216,241,252,255 us=64 --clip=20) 2>&1; } > /opt/mvtrx/ab_read_$N.txt 2>&1
echo "ALERT \$(date +%s) overnight test $N read done: /opt/mvtrx/ab_read_$N.txt" >> /opt/mvtrx/alerts.txt
R
  T=$(date -u -d @$((t0 + W * 1800 + 180)) "+%Y-%m-%d %H:%M:%S"); systemd-run --quiet --unit mvtrx-on-$N-read --on-calendar "$T UTC" /bin/sh /opt/mvtrx/abread_$N.sh
  t0=$((t0 + W * 1800 + 600))
}
mk calm4 ', "mk_calm_touch_min": 4' ', "mk_calm_touch_min": 3'
mk size300 ', "mk_vol_size": 0.07' ', "mk_vol_size": 0.034'
mk dec2 ', "mk_dec_inside": 2' ', "mk_dec_inside": 1'
mk pull8 ', "flow_pull": 0' ', "flow_pull": 0.3' 8
systemctl list-timers --all --no-pager | grep mvtrx-on- | cut -c1-28,60-100

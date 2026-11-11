#!/bin/sh
# §1380: schedule a live-reload A/B test: 4 half-hours (ORDER e.g. ABAB), END back to the base, whole-miner + per-fill read 3 min after the end.
#   sh abtest_sched.sh <name> "<start UTC YYYY-mm-dd HH:MM:SS>" <ORDER> '<base json body, no braces>' '<A extra>' '<B extra>' "<description>"
N=$1; T0=$2; ORD=$3; BASE=$4; XA=$5; XB=$6; DESC=$7
cd /opt/mvtrx
sed "s/liveswitch_skip8_log.txt/liveswitch_${N}_log.txt/" liveswitch_skip8.sh > liveswitch_$N.sh
i=0
for L in $(echo $ORD | sed 's/./& /g'); do
  T=$(date -u -d "$T0 UTC + $((i * 30)) min" "+%Y-%m-%d %H:%M:%S")
  if [ $L = A ]; then X=$XA; else X=$XB; fi
  systemd-run --quiet --unit mvtrx-$N-$i --on-calendar "$T UTC" /bin/sh /opt/mvtrx/liveswitch_$N.sh $L "{$BASE, $X}"; i=$((i + 1))
done
TE=$(date -u -d "$T0 UTC + $((i * 30)) min" "+%Y-%m-%d %H:%M:%S"); TR=$(date -u -d "$T0 UTC + $((i * 30 + 3)) min" "+%Y-%m-%d %H:%M:%S")
systemd-run --quiet --unit mvtrx-$N-end --on-calendar "$TE UTC" /bin/sh /opt/mvtrx/liveswitch_$N.sh END "{$BASE, $XB}"
cat > abread_$N.sh <<R
#!/bin/sh
cd /opt/mvtrx; TP=\$(sh tape_ab.sh); export TAPE=\$TP
{ echo "== \$(TZ=America/Chicago date) test $N: $DESC — WHOLE-MINER credit (x3 vs reference UID 46; 216 = drift check) first; per fill vs UID 46 second"
  cat liveswitch_${N}_log.txt; echo "-- whole-miner credit:"; sh abcredit.sh liveswitch_${N}_log.txt /dev/null 2>&1
  echo "-- per fill (capped):"; (ulimit -v 3000000; nice -n 10 python3 abwin.py \$TP liveswitch_${N}_log.txt fleet=46 us=64 --clip=20) 2>&1 | grep "^=="; } > /opt/mvtrx/ab_read_$N.txt 2>&1
echo "ALERT \$(date +%s) test $N read done: /opt/mvtrx/ab_read_$N.txt" >> /opt/mvtrx/alerts.txt
rm -f /opt/mvtrx/tape_ab.jsonl
R
systemd-run --quiet --unit mvtrx-$N-read --on-calendar "$TR UTC" /bin/sh /opt/mvtrx/abread_$N.sh
systemctl list-timers --all | grep "mvtrx-$N-" | awk '{print $2, $3, $NF}'

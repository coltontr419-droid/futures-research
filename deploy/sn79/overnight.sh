#!/bin/sh
# Standing watchdog (decisions.md §1248, §1255, §1256), every 10 min via mvtrx-overnight.timer, laptop open or closed.
#  1. status line → /opt/mvtrx/overnight_log.txt (gauges x1/x3, errors, flow, memory, lab progress)
#  2. self-trade guard: any self-trade → stop mvtrx-x1 (the taker)
#  3. every UID registered; validator volume sync + alerts (pace_sync.py); heartbeat line, so a dead watchdog is noticed from outside
# State: /opt/mvtrx/ov_state/. Never kills by pattern.
exec 9>/tmp/overnight.lock; flock -n 9 || exit 0
S=/opt/mvtrx/ov_state; L=/opt/mvtrx/overnight_log.txt; mkdir -p $S
now() { echo "$(date -u +%H:%MZ) / $(TZ=America/Chicago date +%I:%M%p) CT"; }
simmin() { journalctl -u mvtrx-x1 --since "-15min" --no-pager | grep -o "SIMULATION TIME : [0-9:]*" | tail -1 | awk -F'[ :]+' '{print $3*60+$4+$5/60}'; }
SM=$(simmin)
N0=$(wc -l < $L)

# 1. status
{
  echo "== $(now) | sim min ${SM:-?}"
  for u in $(awk '{print $1":"$3}' /opt/mvtrx/our_uids.txt); do
    systemctl is-active -q mvtrx-${u##*:} || { echo "ALERT ${u##*:} UID ${u%%:*}: service is DOWN"; continue; }
    printf "  %s " "${u##*:}"; UIDQ=${u%%:*} /opt/mvtrx/x1_gauge.sh
    st=$(systemctl show mvtrx-${u##*:} -p ActiveEnterTimestamp --value)
    ne=$(journalctl -u mvtrx-${u##*:} --since "$st" --no-pager | grep -c "QUOTE ERROR\|Traceback")
    [ "$ne" -gt 0 ] && echo "ALERT ${u##*:} UID ${u%%:*}: $ne errors since its last start"
    echo "    errors since start $ne | $(journalctl -u mvtrx-${u##*:} --since "-15min" --no-pager | grep -E "IOC FLOW|MK QUALITY" | tail -1 | cut -c60-200)"
  done
  echo "  mem $(free -m | awk '/Mem:/{print $7}') MB free | load $(cut -d' ' -f1-3 /proc/loadavg) | lab $(cat /opt/mvtrx/labrand_done 2>/dev/null || echo running)"
} >> $L 2>&1

# 2. self-trade guard (only while our taker runs)
if systemctl is-active -q mvtrx-x1; then
  ST=$(/opt/mvtrx/selftrade.sh 2>/dev/null | grep -o "taking them): [0-9]*" | grep -o "[0-9]*$")
  echo "  self-trades ${ST:-?}" >> $L
  if [ "${ST:-0}" -gt 0 ]; then systemctl stop mvtrx-x1; echo "ALERT SELF-TRADE: $ST fills between our own UIDs; mvtrx-x1 was stopped" >> $L; fi
fi

# 3. standing checks (§1255): every UID still registered; validator volume sync; alerts also go to alerts.txt
timeout 90 /opt/mvtrx/venv/bin/python - <<'PY' >> $L 2>/dev/null
import json, bittensor as bt
m = bt.Subtensor(network="finney").metagraph(79, lite=True)
for l in open("/opt/mvtrx/our_uids.txt"):
    p = l.split()
    if p:
        hk = json.load(open("/root/.bittensor/wallets/main/hotkeys/" + p[2]))["ss58Address"]
        print(f"  {p[2]} UID {p[0]} registered" if m.hotkeys[int(p[0])] == hk else f"ALERT {p[2]} UID {p[0]}: NOT REGISTERED (pruned)")
PY
python3 /opt/mvtrx/pace_sync.py >> $L 2>&1
tail -n +$((N0 + 1)) $L | grep "^ALERT" | sort -u >> /opt/mvtrx/alerts.txt
echo "HEARTBEAT $(date +%s)" >> /opt/mvtrx/alerts.txt

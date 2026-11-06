#!/bin/sh
# Overnight watchdog 2026-11-06 (decisions.md §1248), every 10 min via mvtrx-overnight.timer, while the laptop is closed.
#  1. status line → /opt/mvtrx/overnight_log.txt (gauges x1/x3, errors, flow, memory, lab progress)
#  2. self-trade guard: any self-trade → stop mvtrx-x1 (the taker)
#  3. x1 (UID 114) pruned → final §1245 read saved to /opt/mvtrx/x1scale_final.txt, then stop mvtrx-x1, drop 114 from our_uids.txt
#  4. x3 A/B (§1242, since sim min 1067.4) once ≥ 45 sim min: verdict by a fixed rule, apply the winner, start the §1247 volatile-books A/B
# State: /opt/mvtrx/ov_state/. Never kills by pattern.
exec 9>/tmp/overnight.lock; flock -n 9 || exit 0
S=/opt/mvtrx/ov_state; L=/opt/mvtrx/overnight_log.txt; mkdir -p $S
now() { echo "$(date -u +%H:%MZ) / $(TZ=America/Chicago date +%I:%M%p) CT"; }
simmin() { journalctl -u mvtrx-x3 --since "-15min" --no-pager | grep -o "SIMULATION TIME : [0-9:]*" | tail -1 | awk -F'[ :]+' '{print $3*60+$4+$5/60}'; }
SM=$(simmin)

# 1. status
{
  echo "== $(now) | sim min ${SM:-?}"
  for u in 22:x1 58:x3; do
    systemctl is-active -q mvtrx-${u##*:} || { echo "  ${u##*:}: service not active"; continue; }
    printf "  %s " "${u##*:}"; UIDQ=${u%%:*} /opt/mvtrx/x1_gauge.sh
    st=$(systemctl show mvtrx-${u##*:} -p ActiveEnterTimestamp --value)
    echo "    errors since start $(journalctl -u mvtrx-${u##*:} --since "$st" --no-pager | grep -c "QUOTE ERROR\|Traceback") | $(journalctl -u mvtrx-${u##*:} --since "-15min" --no-pager | grep -E "IOC FLOW|MK QUALITY" | tail -1 | cut -c60-200)"
  done
  echo "  mem $(free -m | awk '/Mem:/{print $7}') MB free | load $(cut -d' ' -f1-3 /proc/loadavg) | lab $(cat /opt/mvtrx/labrand_done 2>/dev/null || echo running)"
} >> $L 2>&1

# 2. self-trade guard (only while our taker runs)
if systemctl is-active -q mvtrx-x1; then
  ST=$(/opt/mvtrx/selftrade.sh 2>/dev/null | grep -o "taking them): [0-9]*" | grep -o "[0-9]*$")
  echo "  self-trades ${ST:-?}" >> $L
  if [ "${ST:-0}" -gt 0 ]; then systemctl stop mvtrx-x1; echo "  !! SELF-TRADE $ST → stopped mvtrx-x1" >> $L; fi
fi

# 3. x1 pruned?
if [ ! -f $S/x1_done ] && systemctl is-active -q mvtrx-x1; then
  OWN=$(cd /tmp && timeout 90 /opt/mvtrx/venv/bin/python -c "
import json, bittensor as bt
hk = json.load(open('/root/.bittensor/wallets/main/hotkeys/x1'))['ss58Address']
m = bt.Subtensor(network='finney').metagraph(79, lite=True)
print('yes' if m.hotkeys[114] == hk else 'no')" 2>/dev/null | tail -1)
  if [ "$OWN" = "no" ]; then
    echo "  x1 PRUNED (UID 114 no longer our hotkey) at $(now): final read" >> $L
    { echo "§1245 final read, x1 pruned at $(now)"; sh /opt/mvtrx/x1scale_read.sh; UIDQ=114 /opt/mvtrx/x1_gauge.sh; } > /opt/mvtrx/x1scale_final.txt 2>&1
    systemctl stop mvtrx-x1; sed -i '/^114 /d' /opt/mvtrx/our_uids.txt
    touch $S/x1_done; echo "  x1 stopped, 114 removed from our_uids.txt; result in x1scale_final.txt" >> $L
  fi
fi

# 4. x3 A/B verdict once ≥ 45 sim min since 1067.4 (sim day resets at 1440: a smaller sim min also means the window is long past)
if [ ! -f $S/ab_done ] && [ -n "$SM" ]; then
  if awk "BEGIN{exit !($SM >= 1112.4 || $SM < 1000)}"; then
    echo "  x3 A/B: ≥ 45 sim min → verdict" >> $L
    T=/tmp/t_ov.jsonl
    { tail -c 500000000 /opt/mvtrx/live_tape_x1.jsonl | tail -n +2; cat /opt/mvtrx/live_tape_x3.jsonl; } > $T
    (cd /opt/mvtrx/repo && timeout 2400 nice -n 10 /opt/mvtrx/venv/bin/python /opt/mvtrx/making_exact.py $T 58 3 --since 1067.4) > $S/ab_final.txt 2>&1
    rm -f $T
    W=$(python3 - "$S/ab_final.txt" <<'EOF'
import re, sys
arms = {}
for l in open(sys.argv[1]):
    m = re.match(r"ours arm (\d): .*R/C ([+-][\d.]+|nan) .*credit\s+([\d.+-]+)", l)
    if m: arms[int(m.group(1))] = (float(m.group(2)) if m.group(2) != "nan" else 0.0, float(m.group(3)))
names = {1: "mk_min_spread_bp=1.05", 2: "mk_thin_ratio=0.77"}
if 0 not in arms or arms[0][1] <= 0:
    print("NONE no-control"); sys.exit()
q0, c0 = arms[0]; best = None
for k in (1, 2):                      # rule: credit ≥ 1.15 × control AND R/C ≥ control's
    if k in arms and arms[k][1] >= 1.15 * c0 and arms[k][0] >= q0 and (best is None or arms[k][1] > arms[best][1]):
        best = k
print((names[best] if best else "NONE") + " " + " ".join(f"arm{k}:credit={v[1]:.1f},rc={v[0]:+.3f}" for k, v in sorted(arms.items())))
EOF
)
    echo "  x3 A/B verdict: $W" >> $L
    P=${W%% *}; [ "$P" = "NONE" ] && P=""
    case "$W" in NONE\ no-control*) echo "  x3 A/B read failed (no control arm) → no change, will retry" >> $L; rm -f $S/ab_final.txt;;
    *)
      U=/etc/systemd/system/mvtrx-x3.service; cp $U $U.pre-ab2
      sed -i "s| arms=[^ ]*| ${P:+$P }arms=mk_skip_vol:1|" $U
      grep -o "pace_win.*" $U >> $L
      systemctl daemon-reload; systemctl restart mvtrx-x3
      echo "$SM" > $S/ab2_since; touch $S/ab_done
      echo "  x3 restarted: winner '${P:-control}' on all books + §1247 A/B arms=mk_skip_vol:1 (odd volatile books skipped) from sim min $SM" >> $L;;
    esac
  fi
fi

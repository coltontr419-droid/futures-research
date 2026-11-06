#!/bin/sh
# Add a skill-only reversal UID on SN79 (decisions.md §1228): ./add_skill_uid.sh <hotkey> <port> <variant>  [START=1 to enable]
#   Template = the working x2 unit (lean=1 raw=1 lazy_load=1, no making: every book skipped + sleeve on all books, own tape).
#   Needs /root/.bittensor/wallets/main/hotkeys/<hotkey> and a REGISTERED UID on netuid 79 (refuses to start otherwise).
#   ALSO copy hotkeys/<hotkey>pub.txt to futures-droplet:/root/.bittensor/wallets/main/hotkeys/ for the earnings check.
#   Our skill UIDs are all takers (IOC only), so they can never trade with each other; variants keep their entries apart (§1228 overlap table).
set -e
HK=$1; PORT=$2; VAR=$3
[ -n "$HK" ] && [ -n "$PORT" ] && [ -n "$VAR" ] || { echo "usage: $0 <hotkey> <port> <variant: M1S (scaled, §1245) M1 V0 V4 V1 V3 V6 N3 N4 N9 N8 V5 | 2nd tier N10 N5 N2 N1 | model M1>"; exit 1; }
case $VAR in              # sleeve_bp (trigger bp) rev_look (s) rev_hold (s) sleeve_step (one bet per book per s)
  V0) P="sleeve_bp=12 rev_look=600 rev_hold=2400 sleeve_step=3600";;
  V1) P="sleeve_bp=8 rev_look=600 rev_hold=2400 sleeve_step=3600";;
  V3) P="sleeve_bp=12 rev_look=300 rev_hold=1200 sleeve_step=2400";;
  V4) P="sleeve_bp=12 rev_look=900 rev_hold=3600 sleeve_step=3600";;
  V5) P="sleeve_bp=10 rev_look=1200 rev_hold=3600 sleeve_step=5400";;
  V6) P="sleeve_bp=8 rev_look=300 rev_hold=1200 sleeve_step=1200";;
  N3) P="sleeve_bp=14 rev_look=1500 rev_hold=4800 sleeve_step=5400";;
  N4) P="sleeve_bp=10 rev_look=1800 rev_hold=5400 sleeve_step=7200";;
  N8) P="sleeve_bp=13 rev_look=1200 rev_hold=2400 sleeve_step=4800";;
  N9) P="sleeve_bp=8 rev_look=900 rev_hold=3600 sleeve_step=5400";;
  N10) P="sleeve_bp=10 rev_look=600 rev_hold=4800 sleeve_step=5400";;
  N5) P="sleeve_bp=9 rev_look=450 rev_hold=1200 sleeve_step=1800";;
  N2) P="sleeve_bp=12 rev_look=750 rev_hold=3000 sleeve_step=3600";;
  N1) P="sleeve_bp=10 rev_look=450 rev_hold=1800 sleeve_step=2700";;
  M1) P="sleeve_bp=12 rev_model=/opt/mvtrx/agents/rev_model.json rev_preload=/opt/mvtrx/live_tape_x1.jsonl rev_hold=900 sleeve_step=3600 lock_dir=/opt/mvtrx/locks lock_max=120";;   # §1233 fitted predictor, top 2% forecasts
  M1S) P="sleeve_bp=12 rev_model=/opt/mvtrx/agents/rev_model.json rev_preload=/opt/mvtrx/live_tape_x1.jsonl rev_hold=900 sleeve_step=3600 lock_dir=/opt/mvtrx/locks lock_max=120 rev_th_k=0.7 pace_cap=450000 pace_win=5400 pace_ledger=/opt/mvtrx/pace_UIDN.ledger"; TS=60; RU=5000;;   # §1245/§1246 scaled taker, paced, ledger per UID
  *) echo "unknown variant $VAR"; exit 1;;
esac
[ -f /root/.bittensor/wallets/main/hotkeys/$HK ] || { echo "hotkey file missing: copy hotkeys/$HK from the laptop first"; exit 1; }
U=/etc/systemd/system/mvtrx-$HK.service
[ -f $U ] && { echo "$U exists"; exit 1; }
TP=""; [ "${TAPE:-0}" = 1 ] && TP="tape=/opt/mvtrx/live_tape_$HK.jsonl "   # tapes grow GBs/day: one UID (x2) keeps one; TAPE=1 to add
PARAMS="size=0.06 edge=1 lean=1 ${TP}model=/opt/mvtrx/agents/model30_of.json raw=1 lazy_load=1 own_ex=1 skip_file=/opt/mvtrx/books_all.txt sleeve_file=/opt/mvtrx/books_all.txt skip_flat=1 take_size=${TS:-25} sleeve_cool=5 rev_usd=${RU:-1000} $P"
sed -e "s/--wallet.hotkey x2/--wallet.hotkey $HK/" -e "s/8102/$PORT/g" -e "s|hotkeys/x2$|hotkeys/$HK|" \
    -e "s|--agent.params .*|--agent.params $PARAMS|" -e "s|^Description=.*|Description=Bittensor SN79 (MVTRX) miner $HK, skill-only reversal $VAR (decisions.md 1228)|" \
    /etc/systemd/system/mvtrx-x2.service > $U
UID_=$(/opt/mvtrx/venv/bin/python -c "
import json, bittensor as bt
hk = json.load(open('/root/.bittensor/wallets/main/hotkeys/$HK'))['ss58Address']
m = bt.Subtensor(network='finney').metagraph(79, lite=True)
print(m.hotkeys.index(hk) if hk in m.hotkeys else -1)" 2>/dev/null | tail -1)
echo "unit $U | variant $VAR | uid $UID_"
grep -o "agent.params.*" $U
[ "$UID_" -ge 0 ] || { echo "hotkey not registered on 79 yet: unit written, NOT started"; exit 0; }
if [ "${START:-0}" = 1 ]; then systemctl daemon-reload && systemctl enable --now mvtrx-$HK && echo "started mvtrx-$HK (first bets ≈ 10 sim min after start; check: UIDQ=$UID_ /opt/mvtrx/x1_gauge.sh)"; fi

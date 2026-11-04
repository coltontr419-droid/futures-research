#!/bin/sh
# Add an MVTRX miner UID on this box (decisions.md §1211 add. 25): ./add_uid.sh <hotkey> <port> [skip_file]
#   needs /root/.bittensor/wallets/main/hotkeys/<hotkey> (copied from the laptop) and a registered UID on netuid 79.
#   ALSO copy hotkeys/<hotkey>pub.txt to futures-droplet:/root/.bittensor/wallets/main/hotkeys/ so the earnings check and Discord report see it.
#   Creates mvtrx-<hotkey>.service from mvtrx-x2.service — the template (§1211 add. 28): paced making on x2s books + the calm-book sleeve on the SHARED
#   sleeve-only books (sleeve_books_x2.txt; immediate-fill orders from two UIDs never match each other, so sharing is safe; no UID rests orders there),
#   its own tape, and an hourly readout at :<RO_MIN> (default 30). Does NOT start anything unless START=1.
set -e
HK=$1; PORT=$2; SKIP=${3:-/opt/mvtrx/skip_x2.txt}; RO=${RO_MIN:-30}
[ -n "$HK" ] && [ -n "$PORT" ] || { echo "usage: $0 <hotkey> <port> [skip_file]"; exit 1; }
[ -f /root/.bittensor/wallets/main/hotkeys/$HK ] || { echo "hotkey file missing: copy hotkeys/$HK from the laptop first"; exit 1; }
U=/etc/systemd/system/mvtrx-$HK.service
[ -f $U ] && { echo "$U exists"; exit 1; }
sed -e "s/--wallet.hotkey x2/--wallet.hotkey $HK/" -e "s/8102/$PORT/g" -e "s|live_tape_x2.jsonl|live_tape_$HK.jsonl|" \
    -e "s|skip_file=[^ ]*|skip_file=$SKIP|" -e "s| arms=[^ ]*||" -e "s/miner x2/miner $HK/" /etc/systemd/system/mvtrx-x2.service > $U
UID_=$(/opt/mvtrx/venv/bin/python -c "
import json, bittensor as bt
hk = json.load(open(\"/root/.bittensor/wallets/main/hotkeys/$HK\"))[\"ss58Address\"]
m = bt.Subtensor(network=\"finney\").metagraph(79, lite=True)
print(m.hotkeys.index(hk) if hk in m.hotkeys else -1)" 2>/dev/null | tail -1)
sed -e "s|live_tape_x2|live_tape_$HK|; s|window_readouts_x2|window_readouts_$HK|; s|(x2, UID|($HK, UID|" /opt/mvtrx/window_est_x2.sh > /opt/mvtrx/window_est_$HK.sh
echo "unit $U | uid $UID_ | readout /opt/mvtrx/window_est_$HK.sh"
[ "$UID_" -ge 0 ] || { echo "hotkey not registered on 79 yet; unit created, not started"; exit 0; }
if [ "${START:-0}" = 1 ]; then
  systemctl daemon-reload && systemctl enable --now mvtrx-$HK
  systemd-run --unit=mvtrx-window-est-$HK --setenv=UID2=$UID_ --on-calendar="*:$RO" /bin/sh /opt/mvtrx/window_est_$HK.sh
  echo started
fi

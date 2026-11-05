#!/bin/sh
# Add a MAKER-ONLY MVTRX UID on all 128 books (decisions.md §1235): ./add_maker_uid.sh <hotkey> <port>   [START=1 to enable]
#   Template = the working x3 unit (old-x1 all-book making params, volume pacing, no taking, lock_dir maker side with the §1235 add. 2 ack fix).
#   Needs /root/.bittensor/wallets/main/hotkeys/<hotkey> and a REGISTERED UID on netuid 79 (refuses to start otherwise).
#   ALSO copy hotkeys/<hotkey>pub.txt to futures-droplet:/root/.bittensor/wallets/main/hotkeys/ for the earnings check.
#   Several makers may share books (post-only quotes cannot cross each other; each UID has its own per-book volume cap); takers of ours
#   must run lock_dir so they never fill against any of our makers.
set -e
HK=$1; PORT=$2
[ -n "$HK" ] && [ -n "$PORT" ] || { echo "usage: $0 <hotkey> <port>"; exit 1; }
[ -f /root/.bittensor/wallets/main/hotkeys/$HK ] || { echo "hotkey file missing: copy hotkeys/$HK from the laptop first"; exit 1; }
U=/etc/systemd/system/mvtrx-$HK.service
[ -f $U ] && { echo "$U exists"; exit 1; }
sed -e "s/--wallet.hotkey x3/--wallet.hotkey $HK/" -e "s/8103/$PORT/g" -e "s|hotkeys/x3$|hotkeys/$HK|" \
    -e "s|^Description=.*|Description=Bittensor SN79 (MVTRX) miner $HK, MAKER-ONLY on all books, lock-handshake maker side (decisions.md 1235)|" \
    /etc/systemd/system/mvtrx-x3.service > $U
UID_=$(/opt/mvtrx/venv/bin/python -c "
import json, bittensor as bt
hk = json.load(open('/root/.bittensor/wallets/main/hotkeys/$HK'))['ss58Address']
m = bt.Subtensor(network='finney').metagraph(79, lite=True)
print(m.hotkeys.index(hk) if hk in m.hotkeys else -1)" 2>/dev/null | tail -1)
echo "unit $U | maker | uid $UID_"; grep -o "agent.params.*" $U
[ "$UID_" -ge 0 ] || { echo "hotkey not registered on 79 yet: unit written, NOT started"; exit 0; }
if [ "${START:-0}" = 1 ]; then systemctl daemon-reload && systemctl enable --now mvtrx-$HK && echo "started mvtrx-$HK"; fi

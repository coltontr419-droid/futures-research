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
# no test arms and no shared tape: arms stay on the UID under test; each maker writes its own tape only with TAPE=1 (tapes grow GBs/day)
TP=""; [ "${TAPE:-0}" = 1 ] && TP=" tape=/opt/mvtrx/live_tape_$HK.jsonl"
sed -e "s/--wallet.hotkey x3/--wallet.hotkey $HK/" -e "s/8103/$PORT/g" -e "s|hotkeys/x3$|hotkeys/$HK|" \
    -e "s| arms=[^ ]*||" -e "s| tape=/opt/mvtrx/live_tape_x3.jsonl|$TP|" -e "s| pace_win=[^ ]*||" -e "s| pace_k=[^ ]*||" -e "s| pace_since=[^ ]*||" \
    -e "s|^Description=.*|Description=Bittensor SN79 (MVTRX) miner $HK, MAKER-ONLY on all books, lock-handshake maker side (decisions.md 1235)|" \
    /etc/systemd/system/mvtrx-x3.service > $U
UID_=$(/opt/mvtrx/venv/bin/python -c "
import json, bittensor as bt
hk = json.load(open('/root/.bittensor/wallets/main/hotkeys/$HK'))['ss58Address']
m = bt.Subtensor(network='finney').metagraph(79, lite=True)
print(m.hotkeys.index(hk) if hk in m.hotkeys else -1)" 2>/dev/null | tail -1)
sim_now() { for j in x3 x1; do journalctl -u mvtrx-$j --since "-10min" --no-pager | grep -o "T=[0-9]*" | tail -1 | cut -c3- | awk '{print int($1/1000000000)}' | grep . && return; done; }
if [ "$UID_" -ge 0 ]; then                    # §1250: ignore the previous owner's fills on a re-used UID
  SIM=$(sim_now); [ -n "$SIM" ] || { echo "no live sim time found: set pace_since and our_uids.txt by hand"; exit 1; }
  [ -f /opt/mvtrx/pace_$UID_.ledger ] && mv /opt/mvtrx/pace_$UID_.ledger /opt/mvtrx/pace_$UID_.ledger.old.$SIM   # the cap resets on a new registration
  sed -i "s|--agent.params \\(.*\\)|--agent.params \\1 pace_since=$SIM|" $U
  sed -i "/^$UID_ /d" /opt/mvtrx/our_uids.txt; echo "$UID_ maker $HK $SIM" >> /opt/mvtrx/our_uids.txt
fi
echo "unit $U | maker | uid $UID_"; grep -o "agent.params.*" $U
[ "$UID_" -ge 0 ] || { echo "hotkey not registered on 79 yet: unit written, NOT started"; exit 0; }
if [ "${START:-0}" = 1 ]; then systemctl daemon-reload && systemctl enable --now mvtrx-$HK && echo "started mvtrx-$HK"; fi

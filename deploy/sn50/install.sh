#!/usr/bin/env bash
# Synth (SN50) miner install for one server (decisions.md §1189). Run as root on the target box from a copy of futures-research/deploy/sn50/:
#   bash install.sh <public_ip>
# Then copy the hotkey(s) s1, s2, ... to /root/.bittensor/wallets/main/hotkeys/ and: systemctl enable --now synth-cache synth-s1
set -euo pipefail
IP="${1:?public ip}"
HERE="$(cd "$(dirname "$0")" && pwd)"
apt-get install -y -qq git python3-venv >/dev/null
mkdir -p /opt/synth/ours/src/futuresres/synth /opt/synth/ours/data/synth
[ -d /opt/synth/repo ] || git clone -q https://github.com/synthdataco/synth-subnet.git /opt/synth/repo
python3 -m venv /opt/synth/venv
/opt/synth/venv/bin/pip install -q --upgrade pip
/opt/synth/venv/bin/pip install -q -e /opt/synth/repo
/opt/synth/venv/bin/pip install -q curl_cffi numpy pandas xxhash
cp "$HERE"/src/futuresres/__init__.py /opt/synth/ours/src/futuresres/
touch /opt/synth/ours/src/futuresres/synth/__init__.py
cp "$HERE"/src/futuresres/synth/{miner_model,s50_backtest,s50_1h,fast_crps,competition_config_upstream}.py /opt/synth/ours/src/futuresres/synth/
cp "$HERE"/run_miner.py "$HERE"/cache_warmer.py /opt/synth/
cat > /etc/systemd/system/synth-cache.service <<UNIT
[Unit]
Description=Synth forecast cache warmer (decisions.md 1189)
After=network-online.target
[Service]
ExecStart=/opt/synth/venv/bin/python /opt/synth/cache_warmer.py
Restart=always
RestartSec=30
MemoryMax=500M
[Install]
WantedBy=multi-user.target
UNIT
for i in 1 2 3 4 5; do port=$((8100 + i)); cat > /etc/systemd/system/synth-s$i.service <<UNIT
[Unit]
Description=Bittensor SN50 (Synth) miner s$i (decisions.md 1189)
After=network-online.target synth-cache.service
ConditionPathExists=/root/.bittensor/wallets/main/hotkeys/s$i
[Service]
WorkingDirectory=/opt/synth/repo
ExecStart=/opt/synth/venv/bin/python /opt/synth/run_miner.py --netuid 50 --subtensor.network finney --wallet.name main --wallet.hotkey s$i --wallet.path /root/.bittensor/wallets --axon.ip $IP --axon.port $port --axon.external_ip $IP --axon.external_port $port --logging.info
Restart=always
RestartSec=30
MemoryMax=900M
[Install]
WantedBy=multi-user.target
UNIT
done
systemctl daemon-reload
echo "installed; next: copy hotkeys s<N>, then systemctl enable --now synth-cache synth-s1"

#!/bin/sh
# §1414: start x2 (user registered hotkey x2) on agent 7d4dd4f5 (low-group knobs) and the proven base; schedule its 24-h test day.  sh start_x2.sh <uid>
U=$1; cd /opt/mvtrx
[ -n "$U" ] || { echo "usage: start_x2.sh <uid>"; exit 1; }
cd /tmp && /opt/mvtrx/venv/bin/python /opt/mvtrx/regcheck.py x2=$U || { echo "x2 not registered as $U"; exit 1; }
cd /opt/mvtrx
[ "$(md5sum agents/QuoteAgent.lowgrp.py | cut -c1-8)" = "7d4dd4f5" ] || { echo "lowgrp agent md5 wrong"; exit 1; }
cp agents/QuoteAgent.py agents/QuoteAgent.pre-lowgrp.py; cp agents/QuoteAgent.lowgrp.py agents/QuoteAgent.py
sed -i "s/12372763/7d4dd4f5/g" restart_x1.sh restart_x3.sh       # future gated restarts expect the superset agent (identical defaults)
SIM=$(python3 -c "import json; f=open('live_tape_x3.jsonl','rb'); f.seek(-4000,2); print(int(json.loads(f.read().split(b'\n')[-2])['ts']/1e9))")
grep -q "^$U " our_uids.txt || echo "$U maker x2 $SIM" >> our_uids.txt
T0=$(date -u -d "+30 min" "+%Y-%m-%d %H:%M:00")
sh x2_day.sh $U "$T0"
grep -q "tape=" /etc/systemd/system/mvtrx-x2.service && echo "WARNING: x2 unit has tape=" ; grep -o "wallet.hotkey [^ ]*\|axon.port [0-9]*" /etc/systemd/system/mvtrx-x2.service
systemctl daemon-reload; systemctl enable mvtrx-x2 2>&1 | tail -1; systemctl start mvtrx-x2; sleep 8; systemctl is-active mvtrx-x2
cat our_uids.txt; python3 selftrade.py
echo "ALERT $(date +%s) x2 UID $U started; test day from $T0 UTC" >> alerts.txt

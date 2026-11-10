#!/bin/sh
# §1358: gated restart of x3 to load the live agent (52798500: live ladders + fund) with live_params_s=5. Refuses unless registered. Logs to restart_x3.log.
cd /opt/mvtrx; L=/opt/mvtrx/restart_x3.log; echo "== $(TZ=America/Chicago date)" >> $L
cd /tmp && /opt/mvtrx/venv/bin/python /opt/mvtrx/regcheck.py x3=64 >> $L 2>&1 || { echo "NOT REGISTERED - no restart" >> $L; echo "ALERT $(date +%s) x3 restart skipped: not registered" >> /opt/mvtrx/alerts.txt; exit 1; }
cd /opt/mvtrx; M=$(md5sum agents/QuoteAgent.py | cut -c1-8); [ "$M" = "52798500" ] || { echo "agent md5 $M != 52798500 - no restart" >> $L; exit 1; }
U=/etc/systemd/system/mvtrx-x3.service; cp $U mvtrx-x3.service.pre-lps5
grep -q "live_params_s=" $U || sed -i "s| live_params=/opt/mvtrx/live_params_UIDN.json | live_params=/opt/mvtrx/live_params_UIDN.json live_params_s=5 |" $U
grep -o "live_params_s=[0-9]*" $U >> $L
B=$(systemctl show -p ActiveEnterTimestamp --value mvtrx-x3); systemctl daemon-reload; systemctl restart mvtrx-x3; sleep 5
A=$(systemctl show -p ActiveEnterTimestamp --value mvtrx-x3); echo "before $B | after $A | $(systemctl is-active mvtrx-x3)" >> $L
[ "$A" != "$B" ] && echo "ALERT $(date +%s) x3 restarted (live ladders, live_params_s 5)" >> /opt/mvtrx/alerts.txt || echo "ALERT $(date +%s) x3 RESTART DID NOT HAPPEN" >> /opt/mvtrx/alerts.txt

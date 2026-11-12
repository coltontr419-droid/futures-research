#!/bin/sh
# §1358: gated restart of x3 to load the live agent (12372763: fund move §1379) with live_params_s=5. Refuses unless registered. Logs to restart_x1.log.
cd /opt/mvtrx; L=/opt/mvtrx/restart_x1.log; echo "== $(TZ=America/Chicago date)" >> $L
cd /tmp && /opt/mvtrx/venv/bin/python /opt/mvtrx/regcheck.py x1=27 >> $L 2>&1 || { echo "NOT REGISTERED - no restart" >> $L; echo "ALERT $(date +%s) x1 restart skipped: not registered" >> /opt/mvtrx/alerts.txt; exit 1; }
cd /opt/mvtrx; M=$(md5sum agents/QuoteAgent.py | cut -c1-8); [ "$M" = "12372763" ] || { echo "agent md5 $M != 12372763 - no restart" >> $L; exit 1; }
U=/etc/systemd/system/mvtrx-x1.service; cp $U mvtrx-x1.service.pre-bookmap
grep -q "live_params_s=" $U || sed -i "s| live_params=/opt/mvtrx/live_params_UIDN.json | live_params=/opt/mvtrx/live_params_UIDN.json live_params_s=5 |" $U
grep -o "live_params_s=[0-9]*" $U >> $L
B=$(systemctl show -p ActiveEnterTimestamp --value mvtrx-x1); systemctl daemon-reload; systemctl restart mvtrx-x1; sleep 5
A=$(systemctl show -p ActiveEnterTimestamp --value mvtrx-x1); echo "before $B | after $A | $(systemctl is-active mvtrx-x1)" >> $L
[ "$A" != "$B" ] && echo "ALERT $(date +%s) x1 restarted (book_map agent)" >> /opt/mvtrx/alerts.txt || echo "ALERT $(date +%s) x1 RESTART DID NOT HAPPEN" >> /opt/mvtrx/alerts.txt

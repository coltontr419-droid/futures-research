#!/bin/sh
# Every 8 wall h (mvtrx-autorefit.timer, decisions.md §1256). Shadow unless /opt/mvtrx/autorefit_on exists: then a passing model replaces x1's, with rollback if x1 does not come back.
exec 9>/tmp/autorefit.lock; flock -n 9 || exit 0
L=/opt/mvtrx/autorefit_log.txt; A=/opt/mvtrx/alerts.txt; U=/etc/systemd/system/mvtrx-x1.service; cd /opt/mvtrx
now() { echo "$(date -u +%F\ %H:%MZ)"; }
T=/tmp/ar.jsonl; { cat live_tape_x1.jsonl.prev 2>/dev/null; cat live_tape_x1.jsonl; } | tail -c 950000000 | tail -n +2 > $T
SZ=$(stat -c %s $T); if [ "$SZ" -lt 800000000 ]; then echo "$(now) too little tape ($SZ bytes), skipped" >> $L; rm -f $T; exit 0; fi
for k in 1 2 3; do OFF=$(( (3 - k) * 300 )); (ulimit -v 2500000; nice -n 15 /opt/mvtrx/venv/bin/python predfeat5.py 300 $OFF /tmp/ar$k.npz $T) > /dev/null 2>&1; done
rm -f $T
RUN=$(grep -o "rev_model=[^ ]*" $U | cut -d= -f2); OUT=/opt/mvtrx/agents/rev_model_auto_$(date -u +%m%d%H).json
R=$( (ulimit -v 2500000; nice -n 15 /opt/mvtrx/venv/bin/python -I autorefit.py $RUN /tmp/ar1.npz /tmp/ar2.npz /tmp/ar3.npz $OUT) 2>&1 | tail -1); rm -f /tmp/ar1.npz /tmp/ar2.npz /tmp/ar3.npz
echo "$(now) running $(basename $RUN) | $R" >> $L
case "$R" in *'"pass": true'*) ;; *'"pass": false'*) rm -f $OUT; exit 0;; *) echo "ALERT autorefit failed: $(echo "$R" | cut -c1-120)" >> $A; rm -f $OUT; exit 0;; esac
if [ ! -f /opt/mvtrx/autorefit_on ]; then echo "$(now) shadow: candidate passed, not deployed" >> $L; rm -f $OUT; exit 0; fi
cp $U $U.pre-auto; sed -i "s|rev_model=[^ ]*|rev_model=$OUT|" $U; systemctl daemon-reload; systemctl restart mvtrx-x1; sleep 240
if systemctl is-active -q mvtrx-x1 && ! journalctl -u mvtrx-x1 --since "-4min" --no-pager | grep -q "Traceback\|QUOTE ERROR"; then echo "$(now) deployed $(basename $OUT)" >> $L
else cp $U.pre-auto $U; systemctl daemon-reload; systemctl restart mvtrx-x1; echo "ALERT autorefit: new model failed at start, rolled back to $(basename $RUN)" >> $A; fi

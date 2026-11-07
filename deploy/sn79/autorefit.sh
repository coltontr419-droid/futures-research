#!/bin/sh
# Every 8 wall h (mvtrx-autorefit.timer, decisions.md §1256, §1268): needs two passes in a row; a deployed model is watched live by livecheck.py. Shadow unless /opt/mvtrx/autorefit_on exists: then a passing model replaces x1's, with rollback if x1 does not come back.
exec 9>/tmp/autorefit.lock; flock -n 9 || exit 0
L=/opt/mvtrx/autorefit_log.txt; A=/opt/mvtrx/alerts.txt; U=/etc/systemd/system/mvtrx-x1.service; cd /opt/mvtrx
now() { echo "$(date -u +%F\ %H:%MZ)"; }
T=/tmp/ar.jsonl
python3 - <<'PY'                                            # §1268: x3's tape (x1 has none), current simulation only (a reset sends ts backwards)
out = open("/tmp/ar.jsonl", "w"); buf = []; last = 0
for l in open("/opt/mvtrx/live_tape_x3.jsonl"):
    i = l.find('"ts": ')
    if i < 0: continue
    t = int(l[i + 6:l.index(",", i)])
    if t < last - 3_600_000_000_000: buf = []
    last = t; buf.append(l)
    if len(buf) > 4_000_000: out.writelines(buf[:2_000_000]); buf = buf[2_000_000:]
out.writelines(buf)
PY
SZ=$(stat -c %s $T); if [ "$SZ" -lt 800000000 ]; then echo "$(now) too little tape ($SZ bytes), skipped" >> $L; rm -f $T; exit 0; fi
for k in 1 2 3; do OFF=$(( (3 - k) * 300 )); (ulimit -v 2500000; nice -n 15 /opt/mvtrx/venv/bin/python predfeat5.py 300 $OFF /tmp/ar$k.npz $T) > /dev/null 2>&1; done
rm -f $T
RUN=$(grep -o "rev_model=[^ ]*" $U | cut -d= -f2); OUT=/opt/mvtrx/agents/rev_model_auto_$(date -u +%m%d%H).json
R=$( (ulimit -v 2500000; nice -n 15 /opt/mvtrx/venv/bin/python -I autorefit.py $RUN /tmp/ar1.npz /tmp/ar2.npz /tmp/ar3.npz $OUT) 2>&1 | tail -1); rm -f /tmp/ar1.npz /tmp/ar2.npz /tmp/ar3.npz
echo "$(now) running $(basename $RUN) | $R" >> $L
case "$R" in *'"pass": true'*) ;; *'"pass": false'*) rm -f $OUT /opt/mvtrx/autorefit_pass; exit 0;; *) echo "ALERT autorefit failed: $(echo "$R" | cut -c1-120)" >> $A; rm -f $OUT; exit 0;; esac
if [ ! -f /opt/mvtrx/autorefit_pass ]; then touch /opt/mvtrx/autorefit_pass; echo "$(now) passed once: needs a second pass in a row before any swap" >> $L; rm -f $OUT; exit 0; fi   # §1268
rm -f /opt/mvtrx/autorefit_pass
if [ ! -f /opt/mvtrx/autorefit_on ]; then echo "$(now) shadow: candidate passed, not deployed" >> $L; rm -f $OUT; exit 0; fi
cp $U $U.pre-auto; sed -i "s|rev_model=[^ ]*|rev_model=$OUT|" $U; systemctl daemon-reload; systemctl restart mvtrx-x1; sleep 240
if systemctl is-active -q mvtrx-x1 && ! journalctl -u mvtrx-x1 --since "-4min" --no-pager | grep -q "Traceback\|QUOTE ERROR"; then echo "$(now) deployed $(basename $OUT)" >> $L
  SIM=$(journalctl -u mvtrx-x1 --since "-2min" --no-pager | grep -o "T=[0-9]*" | tail -1 | cut -c3- | awk '{print int($1/1000000000)}')
  printf '{"model": "%s", "previous": "%s", "since_s": %s}' "$OUT" "$RUN" "${SIM:-0}" > /opt/mvtrx/autorefit_deployed.json   # §1268: watched live by livecheck.py
else cp $U.pre-auto $U; systemctl daemon-reload; systemctl restart mvtrx-x1; echo "ALERT autorefit: new model failed at start, rolled back to $(basename $RUN)" >> $A; fi

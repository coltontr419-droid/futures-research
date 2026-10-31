set -e
cd /opt/mvtrx/repo
F=taos/im/protocol/events.py
cp -n $F $F.orig
python3 - <<'PY'
p="taos/im/protocol/events.py"; s=open(p).read()
old="""            # Pop from the left until within threshold
            while self.events:
                first_ts = next(iter(self.events))
                if first_ts >= retention_threshold:
                    break
                self.events.pop(first_ts)
"""
new="""            # One linear pass: popping from the left of a dict is quadratic (CPython rescans the deleted slots each time),
            # which stalled the miner for 10+ minutes after every restart once the CSV history held ~1.5M events
            if next(iter(self.events)) < retention_threshold:
                self.events = {ts: e for ts, e in self.events.items() if ts >= retention_threshold}
"""
assert s.count(old)==1; open(p,"w").write(s.replace(old,new)); print("patched")
PY
systemctl stop mvtrx-x1
D=/opt/mvtrx/repo/agents/data/93/5EWwdZB7qCCMaAso5Mzcks4UUcPxKYvpAj32t5Mg1v6HSxoF
mkdir -p /opt/mvtrx/csv_archive
mv $D/20261029_0111 /opt/mvtrx/csv_archive/20261029_0111_upto_2026-10-31_2320
systemctl start mvtrx-x1
echo restarted $(date -u +%H:%M:%S)

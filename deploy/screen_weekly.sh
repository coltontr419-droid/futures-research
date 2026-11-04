#!/bin/sh
# Weekly subnet screen (decisions.md §1219): re-run subnet_scan.py, keep a dated copy, and list subnets that newly pass
# (median miner > $100/month, top wallet < 50% of miners) or whose median moved > 50% vs the previous scan.
cd /opt/mvtrx && D=$(date -u +%F)
nice venv/bin/python subnet_scan.py > /dev/null 2>&1 && cp subnet_scan.json screens/scan_$D.json
venv/bin/python - <<PY >> screens/changes.txt
import json, glob
f = sorted(glob.glob("/opt/mvtrx/screens/scan_*.json")); cur = {x["net"]: x for x in json.load(open(f[-1]))}
prev = {x["net"]: x for x in json.load(open(f[-2]))} if len(f) > 1 else {}
ok = lambda x: x["med"] > 100 and x["topck"] < 0.5
print("=== " + f[-1].split("_")[-1][:10])
for n, x in sorted(cur.items(), key=lambda kv: -kv[1]["med"]):
    p = prev.get(n)
    if ok(x) and (p is None or not ok(p)): print(f"  NEW PASS  SN{n} {x['name'][:20]}: median \${x['med']:.0f} p90 \${x['p90']:.0f} line \${x['line']:.0f} burn {x['burn']:.3f} top wallet {x['topck']:.0%}")
    elif p and p["med"] > 30 and abs(x["med"] / p["med"] - 1) > 0.5: print(f"  MOVED     SN{n} {x['name'][:20]}: median \${p['med']:.0f} -> \${x['med']:.0f}")
PY
# SN61 RedTeam: which challenges are active and their reward weights (decisions.md §1219 add. 2) — watch for FlowRadar going live
curl -sL https://raw.githubusercontent.com/RedTeamSubnet/RedTeam/main/src/redteam_core/challenge_pool/active_challenges.yaml \
  | grep -E "^[a-z_0-9]+:$|challenge_incentive_weight" | paste - - | sed "s/^/  SN61 active: /" >> screens/changes.txt

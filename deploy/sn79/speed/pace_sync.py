"""Every watchdog tick (decisions.md §1255): for each UID in our_uids.txt, pull the validator's public per-book daily_volume and write it next to the ledger,
then print any condition that needs a human, one ALERT per line: not registered, near the cap, orders dropped, no fills lately.
    python pace_sync.py     (run from the watchdog; the agent reads pace_sync_<uid>.json once per sim minute)"""
# 11-15: queries filtered to the LIVE validator 5EWwdZB7 — the stale old-sim 5E7RbxVy series charged UID 255 $500k/book (§1491)
import json, os, subprocess, time
P = "https://taos.simulate.trading/api/datasources/proxy/uid/c7665619-8b04-4227-9882-a44e8dad57a6/api/v1/query"
CAP = 500000.0
def q(expr):
    out = subprocess.run(["curl", "-s", "--max-time", "30", "-G", P, "--data-urlencode", "query=" + expr], capture_output=True, text=True, check=True).stdout
    return json.loads(out)["data"]["result"]
for line in open("/opt/mvtrx/our_uids.txt"):
    p = line.split()
    if not p: continue
    uid, role, name = int(p[0]), p[1], p[2]; L = f"/opt/mvtrx/pace_{uid}.ledger"
    try:
        v = {}
        for r in q(f'agent_gauges{{agent_gauge_name="daily_volume",agent_id="{uid}",wallet=~"5EWwdZB7.*"}}'):
            b = r["metric"]["book_id"]; v[b] = max(v.get(b, 0.0), float(r["value"][1]))
        # 11-16 §1544: plausibility guard — at 21:49 UTC the live validator briefly reported ≈ $500k on 187 of our books (real max $92k). A book cannot gain more than
        # ≈ $60k between two 10-min ticks (refill $5.2/sim s); if > 5 books jumped by more than that, keep the previous file (the agent would charge the gap into the bucket).
        prev_f = f"/opt/mvtrx/pace_sync_{uid}.json"
        try: prev = json.load(open(prev_f))
        except Exception: prev = {}
        jumps = [b for b, x in v.items() if x - float(prev.get(b, 0.0)) > 60000.0]
        if prev and len(jumps) > 5:
            print(f"ALERT {name} UID {uid}: validator volume IMPLAUSIBLE ({len(jumps)} books jumped > $60k in one tick, max ${max(v.values()):,.0f}) — ignored, previous sync kept")
            continue
        tmp = f"/opt/mvtrx/pace_sync_{uid}.json.tmp"; json.dump(v, open(tmp, "w")); os.replace(tmp, f"/opt/mvtrx/pace_sync_{uid}.json")
        top = max(v.values(), default=0.0)
        print(f"  pace {name}: validator max book ${top:,.0f} of ${CAP:,.0f}, books over $400k {sum(x >= 400000 for x in v.values())}")
        if top >= 0.9 * CAP: print(f"ALERT {name} UID {uid}: a book is at ${top:,.0f}, within 10% of the hard cap")
        d = q(f'max(miner_gauges{{miner_gauge_name="dropped",agent_id="{uid}",wallet=~"5EWwdZB7.*"}})')
        if d and float(d[0]["value"][1]) > 0: print(f"  {name} UID {uid}: the validator dropped {d[0]['value'][1]} instructions (log only, user 11-08)")
    except Exception as e:
        print(f"  {name} UID {uid}: volume check failed (log only, user 11-08): {str(e)[:120]}")
    if os.path.exists(L):
        age = (time.time() - os.path.getmtime(L)) / 60
        lim = 45 if role == "maker" else 180
        if age > lim: print(f"ALERT {name} UID {uid}: no fills for {age:.0f} wall min")

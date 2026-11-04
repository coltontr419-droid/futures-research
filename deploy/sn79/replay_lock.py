import json, os, shutil, sys
exec(open("/opt/mvtrx/replay_own.py").read().split("live, _ = run")[0])
SK = "/opt/mvtrx/skip_books.txt"; skip = set(map(int, open(SK).read().split()))
kw = dict(own_ex=1, skip_file=SK, skip_flat=1)
cur, _ = run("/opt/mvtrx/agents/QuoteAgent.py", **kw); off, _ = run("/tmp/QA_lock.py", **kw)
print("1. lock off: identical to the live agent:", cur == off, "| instructions", sum(map(len, cur)))
# 2. maker with locks on the SELL side of 5 making books
D = "/tmp/locktest"; shutil.rmtree(D, ignore_errors=True); os.makedirs(D)
mk = [b for b in range(128) if b not in skip][:5]
for b in mk: open(f"{D}/lock_{b}_1", "w").write("0")
on, _ = run("/tmp/QA_lock.py", lock_dir=D, **kw)
pl = [json.loads(x) for st in on for x in st if "PLACE" in x]
bad = [i for i in pl if int(i["bookId"]) in mk and int(i["direction"]) == 1]
print("2. maker: SELL placements on locked books", len(bad), "| BUY placements there", sum(int(i["bookId"]) in mk and int(i["direction"]) == 0 for i in pl),
      "| acks written", sorted(f for f in os.listdir(D) if f.startswith("ack")))
# 3. taker (reversal) with no maker: locks requested, no IOC; then with acks pre-written: IOCs flow
shutil.rmtree(D); os.makedirs(D)
rk = dict(kw, rev_look=60, rev_hold=180, rev_usd=1000, sleeve_bp=4.0, sleeve_step=20, sleeve_cool=5)
t0, _ = run("/tmp/QA_lock.py", **rk)
t1, _ = run("/tmp/QA_lock.py", lock_dir=D, **rk)
ioc = lambda r: sum(1 for st in r for x in st if "PLACE" in x and json.loads(x)["timeInForce"] == 2)
print("3. taker without acks: IOCs", ioc(t1), "(vs", ioc(t0), "unlocked) | lock files", len([f for f in os.listdir(D) if f.startswith("lock")]))
shutil.rmtree(D); os.makedirs(D)
for b in range(128):
    for sd in (0, 1): open(f"{D}/ack_{b}_{sd}", "w").write("1e18")
t2, _ = run("/tmp/QA_lock.py", lock_dir=D, **rk)
print("   taker with acks: IOCs", ioc(t2), "(fires once acked; first request per bet waits one step)")

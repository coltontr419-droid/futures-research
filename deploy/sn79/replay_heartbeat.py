import json, os, shutil
exec(open("/opt/mvtrx/replay_own.py").read().split("live, _ = run")[0])
SK = "/opt/mvtrx/skip_books.txt"; skip = set(map(int, open(SK).read().split()))
kw = dict(own_ex=1, skip_file=SK, skip_flat=1)
cur, _ = run("/opt/mvtrx/agents/QuoteAgent.py", **kw); off, _ = run("/tmp/QA_hb.py", **kw)
print("1. lock off: identical to the live agent:", cur == off, "| instructions", sum(map(len, cur)))
D = "/tmp/lock_hb"; shutil.rmtree(D, ignore_errors=True); os.makedirs(D)
mk = [b for b in range(128) if b not in skip][:5]
for b in mk: open(f"{D}/lock_{b}_1", "w").write("0")
on, a = run("/tmp/QA_hb.py", lock_dir=D, **kw)
pl = [json.loads(x) for st in on for x in st if "PLACE" in x]
print("2. maker: SELL placements on locked books %d | acks %s | heartbeat files %s" % (
    sum(1 for i in pl if int(i["bookId"]) in mk and int(i["direction"]) == 1), sorted(f for f in os.listdir(D) if f.startswith("ack"))[:3], [f for f in os.listdir(D) if f.endswith(".hb")]))
rk = dict(kw, rev_look=60, rev_hold=180, rev_usd=1000, sleeve_bp=4.0, sleeve_step=20, sleeve_cool=5)
ioc = lambda r: sum(1 for st in r for x in st if "PLACE" in x and json.loads(x)["timeInForce"] == 2)
t0, _ = run("/tmp/QA_hb.py", **rk); base = ioc(t0)
shutil.rmtree(D); os.makedirs(D)
t1, _ = run("/tmp/QA_hb.py", lock_dir=D, **rk)
print("3a. taker, NO live maker heartbeat: IOCs %d (unlocked %d) → trades freely" % (ioc(t1), base))
shutil.rmtree(D); os.makedirs(D); open(f"{D}/maker_999.hb", "w").write("1e18")
t2, _ = run("/tmp/QA_hb.py", lock_dir=D, **rk)
print("3b. taker, live maker 999, no acks: IOCs %d → waits" % ioc(t2))
for b in range(128):
    for sd in (0, 1): open(f"{D}/ack_{b}_{sd}_999", "w").write("1e18")
t3, _ = run("/tmp/QA_hb.py", lock_dir=D, **rk)
print("3c. taker, live maker 999, acks from 999: IOCs %d → fires" % ioc(t3))
open(f"{D}/maker_998.hb", "w").write("1e18")
t4, _ = run("/tmp/QA_hb.py", lock_dir=D, **rk)
print("3d. taker, live makers 999 + 998, acks only from 999: IOCs %d → waits for both" % ioc(t4))

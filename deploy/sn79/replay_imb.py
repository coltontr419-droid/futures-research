import json
exec(open("/opt/mvtrx/replay_own.py").read().split("live, _ = run")[0])
open("/tmp/books_all.txt", "w").write(" ".join(map(str, range(128))))
kw = dict(own_ex=1, skip_file="/tmp/books_all.txt", sleeve_file="/tmp/books_all.txt", skip_flat=1, take_size=25, sleeve_cool=5, rev_usd=1000,
          sleeve_bp=4, rev_look=300, rev_hold=600, sleeve_step=3600)
cur, _ = run("/opt/mvtrx/agents/QuoteAgent.py", **kw); off, _ = run("/tmp/QA_imb.py", **kw)
print("rev_imb off: identical to the live agent:", cur == off, "| placements", sum(1 for st in cur for x in st if "PLACE" in x))
on, a = run("/tmp/QA_imb.py", rev_imb=0.17, **kw)
pl_on = sum(1 for st in on for x in st if "PLACE" in x); pl_off = sum(1 for st in off for x in st if "PLACE" in x)
print("rev_imb 0.17: placements %d vs %d without the filter | all IOC: %s" % (pl_on, pl_off, all(json.loads(x)["timeInForce"] == 2 for st in on for x in st if "PLACE" in x)))

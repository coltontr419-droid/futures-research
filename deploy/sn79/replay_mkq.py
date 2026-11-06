import json
exec(open("/opt/mvtrx/replay_own.py").read().split("live, _ = run")[0])
open("/tmp/books_none.txt", "w").write("")
kw = dict(own_ex=1, skip_file="/tmp/books_none.txt", fit_qty=1, pace_cap=450000, pace_win=5400)
cur, _ = run("/opt/mvtrx/agents/QuoteAgent.py", **kw); off, _ = run("/tmp/QA_mkq.py", **kw)
print("1. rules off: identical to the live agent:", cur == off, "| instructions", sum(map(len, cur)))
on, a = run("/tmp/QA_mkq.py", arms="mk_min_spread_bp:1.05/mk_thin_ratio:0.77", **kw)
pl = lambda r: sum(1 for st in r for x in st if "PLACE" in x)
print("2. arms on: errors %d | decisions %d, books skipped tight %d, thin sides pulled %d | placements %d vs %d off" % (
    getattr(a, "_qerr", 0), a._mkq_n[0], a._mkq_n[1], a._mkq_n[2], pl(on), pl(off)))

import json
exec(open("/opt/mvtrx/replay_own.py").read().split("live, _ = run")[0])
open("/tmp/books_none.txt", "w").write("")
kw = dict(own_ex=1, skip_file="/tmp/books_none.txt", fit_qty=1, pace_cap=450000, pace_win=5400, lock_dir="/tmp/locktest_mk")
import os; os.makedirs("/tmp/locktest_mk", exist_ok=True)
cur, _ = run("/opt/mvtrx/agents/QuoteAgent.py", **kw); off, _ = run("/tmp/QA_mk.py", **kw)
print("1. mk_model off: identical to the live agent:", cur == off, "| instructions", sum(map(len, cur)))
on, a = run("/tmp/QA_mk.py", mk_model="/opt/mvtrx/agents/rev_model.json", mk_pull_bp=2.0, arms="mk_pull_bp:0", **kw)
print("2. mk_model on (arm 0 guard 2 bp, arm 1 guard off): errors %d | books fed %d | guard decisions %d, sides pulled %d | placements %d vs %d off" % (
    getattr(a, "_qerr", 0), len(a._rf.books), a._mk_n[1], a._mk_n[0], sum(1 for st in on for x in st if "PLACE" in x), sum(1 for st in off for x in st if "PLACE" in x)))

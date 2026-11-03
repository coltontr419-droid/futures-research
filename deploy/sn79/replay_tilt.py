import json
exec(open("/opt/mvtrx/replay_own.py").read().split("live, _ = run")[0])
kw = dict(own_ex=1, skip_file="/opt/mvtrx/skip_x2.txt", skip_flat=1, fit_qty=1, pace_cap=450000.0, pace_win=5400, arms="edge:4/edge:8")
a, _ = run("/opt/mvtrx/agents/QuoteAgent.py", **kw); b, _ = run("/tmp/QA_tilt.py", **kw); c, ag = run("/tmp/QA_tilt.py", tilt_bp=5.0, **kw)
print("tilt off = live agent:", a == b, "| instructions", sum(map(len, a)))
pl = lambda x: [json.loads(s) for st in x for s in st if "PLACE" in s]
pa, pc = pl(a), pl(c)
buy = lambda L: sum(i["quantity"] * i["price"] for i in L if i["direction"] == 0); sell = lambda L: sum(i["quantity"] * i["price"] for i in L if i["direction"] == 1)
print("tilt on: targets", len(ag._tilt), "(+", sum(v > 0 for v in ag._tilt.values()), "/ -", sum(v < 0 for v in ag._tilt.values()), ") | placements", len(pa), "->", len(pc), "| buy-minus-sell notional off", round(buy(pa) - sell(pa)), "on", round(buy(pc) - sell(pc)))

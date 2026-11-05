import json
exec(open("/opt/mvtrx/replay_own.py").read().split("live, _ = run")[0])
open("/tmp/books_all.txt", "w").write(" ".join(map(str, range(128))))
kw = dict(own_ex=1, skip_file="/tmp/books_all.txt", sleeve_file="/tmp/books_all.txt", skip_flat=1, take_size=25, sleeve_cool=5,
          rev_usd=1000, sleeve_bp=12, rev_look=600, rev_hold=2400, sleeve_step=3600)
cur, _ = run("/opt/mvtrx/agents/QuoteAgent.py", **kw); off, _ = run("/tmp/QA_model.py", **kw)
print("1. rev_model off: identical to the live agent:", cur == off, "| placements", sum(1 for st in cur for x in st if "PLACE" in x))
mk = dict(kw); mk.pop("rev_look"); mk.update(rev_model="/opt/mvtrx/agents/rev_model.json", rev_hold=600)
on, a = run("/tmp/QA_model.py", **mk)
rf = a._rf; nb = len(rf.books); sec = a._sec
hist = max((len(s["mid"].d) for s in rf.books.values()), default=0)
print("2. rev_model on: swallowed _quote errors %d | books tracked %d | longest mid history %d s | model entries %d | all IOC: %s" % (
    getattr(a, "_qerr", 0), nb, hist, getattr(a, "_model_n", 0), all(json.loads(x)["timeInForce"] == 2 for st in on for x in st if "PLACE" in x)))
b0 = next(iter(rf.books)); s0 = rf.books[b0]
print("   sample book %s: flow seconds folded %d, trades sizes seen %d, last fund %s" % (b0, s0["flow"].n, len(s0["sizes"]), s0["fund"].at(sec)))

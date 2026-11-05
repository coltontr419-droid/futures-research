exec(open("/opt/mvtrx/replay_own.py").read().split("live, _ = run")[0])
open("/tmp/books_all.txt", "w").write(" ".join(map(str, range(128))))
kw = dict(own_ex=1, skip_file="/tmp/books_all.txt", sleeve_file="/tmp/books_all.txt", skip_flat=1, take_size=25, sleeve_cool=5, rev_usd=1000,
          sleeve_bp=12, rev_hold=600, sleeve_step=3600, rev_model="/opt/mvtrx/agents/rev_model.json", rev_preload="/opt/mvtrx/live_tape_x1.jsonl", rev_preload_mb=150)
on, a = run("/tmp/QA_model.py", **kw)
rf = a._rf; ready = sum(1 for b in rf.books if rf.features(b, max(s["mid"].d[-1][0] for s in rf.books.values())) is not None)
print("preload on: errors %d | books tracked %d | books with features ready right after start %d | model entries in the replay %d" % (
    getattr(a, "_qerr", 0), len(rf.books), ready, getattr(a, "_model_n", 0)))

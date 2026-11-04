import json, sys
exec(open("/opt/mvtrx/replay_own.py").read().split("live, _ = run")[0])
SK = "/opt/mvtrx/skip_books.txt"; skip = set(map(int, open(SK).read().split()))
kw = dict(own_ex=1, skip_file=SK, skip_flat=1)
cur, _ = run("/opt/mvtrx/agents/QuoteAgent.py", **kw); off, _ = run("/tmp/QA_rev.py", **kw)
print("rev off: identical to the live agent:", cur == off, "| instructions", sum(map(len, cur)))
on, a = run("/tmp/QA_rev.py", rev_look=60, rev_hold=180, rev_usd=1000, sleeve_bp=4.0, sleeve_step=20, sleeve_cool=5, **kw)
ns = [json.loads(s) for st in on for s in st if "PLACE" in s]
sk = [i for i in ns if int(i["bookId"]) in skip]
print("rev on: orders on skipped books", len(sk), "all IOC:", all(i["timeInForce"] == 2 for i in sk),
      "| other-book orders identical to off:", [s for st in on for s in st if "PLACE" in s and int(json.loads(s)["bookId"]) not in skip] == [s for st in off for s in st if "PLACE" in s and int(json.loads(s)["bookId"]) not in skip])
print("rev targets set:", sum(t != 0 for t, _ in a._rev.values()), "of", len(a._rev), "books")

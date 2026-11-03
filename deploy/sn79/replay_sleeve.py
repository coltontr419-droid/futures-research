import json, sys
exec(open("/opt/mvtrx/replay_own.py").read().split("live, _ = run")[0])
SK = "/opt/mvtrx/skip_books.txt"; skip = set(map(int, open(SK).read().split()))
kw = dict(own_ex=1, skip_file=SK, skip_flat=1)
cur, _ = run("/opt/mvtrx/agents/QuoteAgent.py", **kw); off, _ = run("/tmp/QA_sleeve.py", **kw)
print("sleeve off: identical to the live agent:", cur == off, "| instructions", sum(map(len, cur)))
on, a = run("/tmp/QA_sleeve.py", sleeve_bp=5.0, sleeve_q=10.0, **kw)
ns = [json.loads(s) for st in on for s in st if "PLACE" in s]
sk = [i for i in ns if int(i["bookId"]) in skip]; calm = [i for i in ns if int(i["bookId"]) not in skip]
print("sleeve on: orders on skipped books", len(sk), "all IOC:", all(i["timeInForce"] == 2 for i in sk), "| max qty", max((i["quantity"] for i in sk), default=0),
      "| calm-book orders identical to sleeve off:", [s for st in on for s in st if "PLACE" in s and int(json.loads(s)["bookId"]) not in skip] == [s for st in off for s in st if "PLACE" in s and int(json.loads(s)["bookId"]) not in skip])
print("targets set:", len(a._sleeve), "| +:", sum(v > 0 for v in a._sleeve.values()), "-:", sum(v < 0 for v in a._sleeve.values()))

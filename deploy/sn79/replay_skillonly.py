import json
exec(open("/opt/mvtrx/replay_own.py").read().split("live, _ = run")[0])
open("/tmp/books_all.txt", "w").write(" ".join(map(str, range(128))))
r, a = run("/opt/mvtrx/QuoteAgent.lock.py", own_ex=1, skip_file="/tmp/books_all.txt", sleeve_file="/tmp/books_all.txt", skip_flat=1, take_size=25,
           sleeve_bp=12, sleeve_step=3600, sleeve_cool=5, rev_look=600, rev_hold=2400, rev_usd=1000)
pl = [json.loads(x) for st in r for x in st if "PLACE" in x]
print("skill-only replay: placements", len(pl), "| all IOC:", all(i["timeInForce"] == 2 for i in pl), "| any post-only:", any(i.get("postOnly") for i in pl),
      "| books", len({i["bookId"] for i in pl}), "| max notional $%.0f" % max((i["quantity"] * (i.get("price") or 0) for i in pl), default=0))

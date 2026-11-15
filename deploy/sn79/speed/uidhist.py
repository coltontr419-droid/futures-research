"""Per sim-hour behaviour of one uid in a tape (stdin = only lines with that uid as Ma or Ta): maker fills, taker trades, $, median fill $, books, $ per book, buy share.
New segment when sim time jumps backwards (new simulation)."""
import sys, json, collections, statistics as st
U = int(sys.argv[1]); label = sys.argv[2]
H = collections.OrderedDict(); seg = 0; last = None; seen = set()
for l in sys.stdin:
    try: r = json.loads(l)
    except ValueError: continue
    ts = r.get("ts"); bk = r.get("book")
    if ts is None: continue
    k = (bk, r.get("id"), ts)
    if k in seen: continue
    seen.add(k)
    if last is not None and ts < last - 3600e9: seg += 1
    last = ts; h = (seg, int(ts // 3600e9))
    x = H.setdefault(h, {"mk": [], "tk": 0, "tkusd": 0.0, "books": set(), "buy": 0})
    usd = r["p"] * r["q"]
    if r.get("Ma") == U: x["mk"].append(usd); x["books"].add(bk); x["buy"] += r["s"] == 1
    if r.get("Ta") == U: x["tk"] += 1; x["tkusd"] += usd
for (seg, h), x in H.items():
    n = len(x["mk"])
    if n + x["tk"] < 5: continue
    med = st.median(x["mk"]) if n else 0
    print(f"{label:22} seg{seg} simh {h:2d} | maker fills {n:5d} ${sum(x['mk']) / 1e3:6.0f}k median fill ${med:6,.0f} books {len(x['books']):3d} | taker {x['tk']:4d} ${x['tkusd'] / 1e3:5.0f}k | maker buy share {x['buy'] / max(n, 1):4.0%}")

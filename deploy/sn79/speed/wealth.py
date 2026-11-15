import sys, json, glob, collections
sys.path.insert(0, "/opt/mvtrx/repo")
from taos.im.protocol import MarketSimulationStateUpdate
b = open(sorted(glob.glob("/opt/mvtrx/cap14/req_*.json"))[0]).read()
s = MarketSimulationStateUpdate(**json.loads(b)); s.decompress(lazy=True)
ra = s.accounts._raw_accounts; u = next(iter(ra)); acc = ra[u]; rb = s.books._raw_books
W = collections.defaultdict(list)
for bk, d in acc.items():
    bk = int(bk); book = rb.get(bk) or rb.get(str(bk))
    if not book or not book.get("b") or not book.get("a"): continue
    mid = (book["b"][0]["p"] + book["a"][0]["p"]) / 2
    qi = (d.get("qb") or {}).get("i"); bi = (d.get("bb") or {}).get("i")
    if qi is None or bi is None: continue
    g = "$300" if bk < 128 else ("$30" if bk < 192 else "4dec")
    W[g].append((qi + bi * mid, qi, bi, mid))
for g, v in W.items():
    v.sort(); m = v[len(v) // 2]
    print(f"{g}: initial wealth per book median ${m[0]:,.0f} (quote {m[1]:,.0f} + base {m[2]:.3f} × mid {m[3]:.2f}); range ${v[0][0]:,.0f}–${v[-1][0]:,.0f}")
cfg = s.config if isinstance(s.config, dict) else getattr(s.config, "__dict__", {})
txt = json.dumps(cfg, default=str)
for k in ("capital_turnover", "turnover", "volume_cap", "max_volume", "wealth", "miner_wealth"):
    i = txt.find(k)
    if i >= 0: print("config:", txt[max(0, i - 60): i + 120])

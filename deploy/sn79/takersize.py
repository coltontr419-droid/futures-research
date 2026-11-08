"""§1306: how big is the incoming trade that fills each maker fill? A taker "event" = all prints from the same taker at the same ts on a book: total $ and price levels
swept. x2 vs fleet, $300 and calm books. Outcome per bucket: share of $, edge, kept 20 s later, kept÷edge.   python takersize.py <tape> <since> <name=uids> ..."""
import json, sys, collections, bisect
tape, LO = sys.argv[1], float(sys.argv[2]); G = {a.split("=")[0]: {int(u) for u in a.split("=")[1].split(",")} for a in sys.argv[3:]}
who = {u: g for g, us in G.items() for u in us}
M = collections.defaultdict(lambda: ([], [])); EV = collections.defaultdict(lambda: [0.0, set()]); F = []; seen = set()
for l in open(tape, "rb"):
    i = l.find(b'"ts": '); t = int(l[i + 6:l.index(b",", i)])
    if t >= 60000 * 10**9 or t < (LO - 120) * 10**9: continue
    if b'"bid": ' in l[:80]:
        j = l.find(b'"bids"'); r = json.loads(l[:j].rstrip(b', ') + b"}")
        if r["book"] < 102 and r.get("bid") and r.get("ask"): M[r["book"]][0].append(t / 1e9); M[r["book"]][1].append((r["bid"] + r["ask"]) / 2)
    elif b'"Ta": ' in l:
        r = json.loads(l); k = (r["book"], r.get("id"), r["ts"])
        if k in seen or r["book"] >= 102: continue
        seen.add(k); e = EV[(r["book"], r["ts"], r.get("Ta"))]; e[0] += r["q"] * r["p"]; e[1].add(r["p"])
        if r.get("Ma") in who and t / 1e9 >= LO: F.append((who[r["Ma"]], r["book"], r["ts"], r.get("Ta"), r["s"], r["q"], r["p"]))
R = collections.defaultdict(list)
for g, b, ts, ta, s, q, p in F:
    t = ts / 1e9; a = M[b]; i = bisect.bisect_left(a[0], t) - 1; j = bisect.bisect_left(a[0], t + 20)
    if i < 0 or j >= len(a[0]): continue
    m0, m1 = a[1][i], a[1][j]; mk = -1 if s == 0 else 1
    edge = mk * (m0 - p) / m0 * 1e4; kept = edge + mk * (m1 - m0) / m0 * 1e4; usd = q * p
    ev_usd, ev_lv = EV[(b, ts, ta)]; nl = len(ev_lv); grp = "$300" if b < 63 else "calm"
    sz = "<$1k" if ev_usd < 1000 else "$1-3k" if ev_usd < 3000 else "$3-10k" if ev_usd < 10000 else "$10k+"
    R[(g, grp, "size", sz)].append((usd, edge, kept)); R[(g, grp, "levels", "1 level" if nl == 1 else "2-3 levels" if nl <= 3 else "4+ levels")].append((usd, edge, kept))
    R[(g, grp, "all", "")].append((usd, edge, kept))
def row(v, tot):
    w = sum(x[0] for x in v); e = sum(x[0] * x[1] for x in v) / w; k = sum(x[0] * x[2] for x in v) / w
    return f"{w / tot:4.0%} $ | edge {e:+5.2f} kept {k:+5.2f} | k÷e {k / e if e else 0:+5.2f}"
for grp in ("$300", "calm"):
    print(f"######## {grp}")
    for g in G:
        allv = R.get((g, grp, "all", ""), [])
        if not allv: continue
        tot = sum(x[0] for x in allv); print(f"== {g}: {len(allv)} fills | {row(allv, tot)}")
        print("   incoming trade size: " + " || ".join(f"{v}: {row(R[(g, grp, 'size', v)], tot)}" for v in ("<$1k", "$1-3k", "$3-10k", "$10k+") if R.get((g, grp, "size", v))))
        print("   levels it swept:     " + " || ".join(f"{v}: {row(R[(g, grp, 'levels', v)], tot)}" for v in ("1 level", "2-3 levels", "4+ levels") if R.get((g, grp, "levels", v))))

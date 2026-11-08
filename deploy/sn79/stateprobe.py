"""§1305: the BOOK STATE right before each $300-book maker fill, x2 vs fleet — queue balance at the touch (our side's size ÷ other side's), top-5 depth balance,
signed trade flow in the 10 s before (+ = flow toward our side, i.e. trades hitting our side), seconds since the last trade. Outcome: share of $, edge, kept 20 s
later, kept÷edge.   python stateprobe.py <tape> <since> <name=uids> ...   (current sim only)"""
import json, sys, collections, bisect
tape, LO = sys.argv[1], float(sys.argv[2]); G = {a.split("=")[0]: {int(u) for u in a.split("=")[1].split(",")} for a in sys.argv[3:]}
who = {u: g for g, us in G.items() for u in us}
S = collections.defaultdict(lambda: ([], [])); TR = collections.defaultdict(list); F = []; seen = set()
for l in open(tape, "rb"):
    i = l.find(b'"ts": '); t = int(l[i + 6:l.index(b",", i)]) / 1e9
    if t >= 60000 or t < LO - 120: continue
    if b'"bid": ' in l[:80]:
        r = json.loads(l)
        if r["book"] < 63 and r.get("bids") and r.get("asks"): S[r["book"]][0].append(t); S[r["book"]][1].append((r["bids"], r["asks"]))
    elif b'"Ta": ' in l:
        r = json.loads(l); k = (r["book"], r.get("id"), r["ts"])
        if k in seen or r["book"] >= 63: continue
        seen.add(k); TR[r["book"]].append((t, 1 if r["s"] == 0 else -1, r["q"] * r["p"]))   # +1 = taker bought (hit the asks)
        if r.get("Ma") in who and t >= LO: F.append((who[r["Ma"]], r["book"], t, r["s"], r["q"], r["p"]))
R = collections.defaultdict(list)
for g, b, t, s, q, p in F:
    a = S[b]; i = bisect.bisect_left(a[0], t) - 1; j = bisect.bisect_left(a[0], t + 20)
    if i < 0 or j >= len(a[0]): continue
    bids, asks = a[1][i]; bids2, asks2 = a[1][j]
    m0 = (bids[0][0] + asks[0][0]) / 2; m1 = (bids2[0][0] + asks2[0][0]) / 2; mk = -1 if s == 0 else 1          # mk +1: the maker bought (its bid was hit)
    ours, other = (bids, asks) if mk > 0 else (asks, bids)
    qb = ours[0][1] / max(other[0][1], 1e-9); d5 = sum(x[1] for x in ours[:5]) / max(sum(x[1] for x in other[:5]), 1e-9)
    tr = TR[b]; k0 = bisect.bisect_left(tr, (t - 10, -9, 0)); k1 = bisect.bisect_left(tr, (t, -9, 0))
    flow = sum(-x[1] * x[2] for x in tr[k0:k1]) * mk                          # + = recent trades hit OUR side (sellers into our bid / buyers into our ask)
    gap = t - tr[k1 - 1][0] if k1 > 0 else 99
    edge = mk * (m0 - p) / m0 * 1e4; kept = edge + mk * (m1 - m0) / m0 * 1e4; usd = q * p
    feats = {"touch queue ours÷other": "<0.5" if qb < 0.5 else "0.5-1" if qb < 1 else "1-2" if qb < 2 else ">2",
             "top-5 depth ours÷other": "<0.7" if d5 < 0.7 else "0.7-1.4" if d5 < 1.4 else ">1.4",
             "10 s flow": "hitting OUR side" if flow > 1000 else "hitting the OTHER side" if flow < -1000 else "quiet/mixed",
             "since last trade": "<1 s" if gap < 1 else "1-5 s" if gap < 5 else "5 s+"}
    for f, v in feats.items(): R[(g, f, v)].append((usd, edge, kept))
    R[(g, "all", "")].append((usd, edge, kept))
order = {"touch queue ours÷other": ["<0.5", "0.5-1", "1-2", ">2"], "top-5 depth ours÷other": ["<0.7", "0.7-1.4", ">1.4"],
         "10 s flow": ["hitting OUR side", "quiet/mixed", "hitting the OTHER side"], "since last trade": ["<1 s", "1-5 s", "5 s+"]}
def row(v, tot):
    w = sum(x[0] for x in v); e = sum(x[0] * x[1] for x in v) / w; k = sum(x[0] * x[2] for x in v) / w
    return f"{w / tot:4.0%} $ | edge {e:+5.2f} kept {k:+5.2f} | k÷e {k / e if e else 0:+5.2f}"
for g in G:
    allv = R[(g, "all", "")]; tot = sum(x[0] for x in allv); print(f"== {g}: {len(allv)} $300 fills | {row(allv, tot)}")
    for f, vals in order.items(): print(f"   {f}: " + " || ".join(f"{v}: {row(R[(g, f, v)], tot)}" for v in vals if R.get((g, f, v))))

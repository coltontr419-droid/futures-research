"""What do the top skill miners do that x1 does not? (decisions.md §1243) One pass over a tape: for each uid, its fills as maker and as taker
(count, notional, median size), books touched, inventory behaviour (mean |inventory| in notional, round-trip time ≈ 2·mean|inv| / volume rate),
and the mid markout in the trader's favour at 30 s / 120 s / 600 s, split maker vs taker (bp, + = good). Pairs with skill_val.py (the score).

    python skillcmp.py <tape.jsonl> <uid,uid,...>
"""
import bisect, json, statistics as st, sys
from collections import defaultdict

tape, uids = sys.argv[1], {int(u) for u in sys.argv[2].split(",")}
mids = defaultdict(lambda: ([], []))          # book -> (ts list, mid list)
fills = []                                     # (ts, book, uid, signed qty for that uid, price, role)
t0 = t1 = None
for line in open(tape):
    r = json.loads(line)
    ts = r.get("ts")
    if ts is None: continue
    t0 = ts if t0 is None else min(t0, ts); t1 = ts if t1 is None else max(t1, ts)
    if "p" in r:
        buy_maker = r.get("s") == 1                     # s == 1: the resting (maker) order was the buy
        for who, role in ((r.get("Ma"), "mk"), (r.get("Ta"), "tk")):
            if who in uids:
                sgn = (1 if buy_maker else -1) * (1 if role == "mk" else -1)
                fills.append((ts / 1e9, r["book"], who, sgn * r["q"], r["p"], role))
    elif r.get("bid") and r.get("ask"):
        m = mids[r["book"]]; m[0].append(ts / 1e9); m[1].append((r["bid"] + r["ask"]) / 2)

span = (t1 - t0) / 1e9
print(f"tape span {span / 60:.0f} sim min, {len(fills)} fills of the chosen uids")
def mid_at(book, t):
    ts, ms = mids[book]; i = bisect.bisect_left(ts, t)
    return ms[i] if i < len(ts) else None

by = defaultdict(list)
for f in sorted(fills): by[f[2]].append(f)
print("uid  | maker fills  taker fills | notional/h | med size | books | mean|inv| $ | round trip s | markout bp 30/120/600 s  maker || taker")
for u in sorted(uids):
    F = by.get(u, [])
    if not F: print(f"{u:4d} | no fills"); continue
    inv = defaultdict(float); last = {}; area = 0.0; vol = 0.0
    mo = {"mk": defaultdict(list), "tk": defaultdict(list)}
    for ts, b, _, q, p, role in F:
        if b in last: area += abs(inv[b]) * p * (ts - last[b])
        inv[b] += q; last[b] = ts; vol += abs(q) * p
        for h in (30, 120, 600):
            m = mid_at(b, ts + h)
            if m is not None: mo[role][h].append((1 if q > 0 else -1) * (m - p) / p * 1e4)
    mean_inv = area / span
    rt = 2 * mean_inv / (vol / span) if vol else float("nan")
    nm = sum(f[5] == "mk" for f in F); nt = len(F) - nm
    fmt = lambda d: "/".join(f"{st.mean(d[h]):+5.1f}" if d[h] else "  n/a" for h in (30, 120, 600))
    print(f"{u:4d} | {nm:11d} {nt:12d} | {vol / span * 3600:10.0f} | {st.median(abs(f[3]) * f[4] for f in F):8.0f} | "
          f"{len({f[1] for f in F}):5d} | {mean_inv:11.0f} | {rt:12.0f} | {fmt(mo['mk'])} || {fmt(mo['tk'])}")

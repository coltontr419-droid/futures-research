"""§1312: every remaining observable difference between the long-lived fleet and our makers, per book group ($300 0-62, calm 63-101, 4-dec 102-127).
Read-only tape study.  python3 fleetgap.py <tape> <T0 sim s> <T1 sim s> fleet=<uids> x2=212 x4=58
Per group & maker: fills and $ per UID per book-active sim hour, filled size per order id (≈ order size floor), depth of the fill vs the prior touch in ticks
(0 touch, <0 inside, >0 behind), edge / kept (book mid, 20 s), inventory behaviour (share of fills that cut the UID's running position on that book when |pos| is
above its own median), and two-sidedness (books where the UID filled both sides)."""
import json, sys, collections, statistics as stt
tape, T0, T1 = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
G = {a.split("=")[0]: {int(u) for u in a.split("=")[1].split(",")} for a in sys.argv[4:]}
who = {u: g for g, us in G.items() for u in us}
SN = collections.defaultdict(dict); F = []
for l in open(tape, "rb"):
    i = l.find(b'"ts": ')
    if i < 0: continue
    t = int(l[i + 6:l.index(b",", i)]) / 1e9
    if t >= 90000 or t < T0 - 30 or t > T1 + 30: continue
    if b'"Mi"' in l:
        r = json.loads(l)
        if r["Ma"] in who and r["Ma"] != r["Ta"] and T0 <= t < T1: F.append((t, r["book"], r["p"], r["q"], r["s"], r["Ma"], r["Mi"]))
    elif b'"bids"' in l:
        r = json.loads(l)
        if r["bids"] and r["asks"]: SN[r["book"]][int(t)] = (r["bid"], r["ask"])
grp = lambda b: "$300" if b < 63 else "calm" if b < 102 else "4-dec"
tick = lambda b: 0.0001 if b >= 102 else 0.01
F.sort(); pos = collections.defaultdict(float); rows = []
for t, b, p, q, s, u, mi in F:
    sec = int(t); sn = SN[b].get(sec - 1) or SN[b].get(sec - 2); later = SN[b].get(sec + 20)
    buy = (s == 1); sg = 1 if buy else -1
    before = pos[(u, b)]; pos[(u, b)] += sg * q
    if not sn or not later: continue
    mid = (sn[0] + sn[1]) / 2; mid2 = (later[0] + later[1]) / 2
    depth = round(((sn[0] - p) if buy else (p - sn[1])) / tick(b))
    rows.append(dict(g=who[u], grp=grp(b), u=u, b=b, t=t, usd=p * q, q=q, mi=(b, mi), depth=depth, edge=sg * (mid - p) / mid * 1e4,
                     kept=sg * (mid2 - p) / mid * 1e4, absb=abs(before) * p, cut=(before != 0 and (before > 0) != buy), side=s))
hrs = (T1 - T0) / 3600
for gname in ("$300", "calm", "4-dec"):
    print(f"\n== {gname} books, sim {T0:.0f}-{T1:.0f} ({hrs:.2f} sim h)")
    for g in G:
        v = [x for x in rows if x["g"] == g and x["grp"] == gname]
        if not v: print(f"{g:6s} no fills"); continue
        D = sum(x["usd"] for x in v); nu = len({x["u"] for x in v}); nb = len({(x["u"], x["b"]) for x in v})
        per_o = collections.defaultdict(float)
        for x in v: per_o[(x["u"], x["mi"])] += x["usd"]
        os_ = sorted(per_o.values())
        dd = collections.Counter(min(max(x["depth"], -1), 5) for x in v); dsum = sum(x["usd"] for x in v)
        dep = " ".join(f"{('in' if k < 0 else k)}:{sum(x['usd'] for x in v if min(max(x['depth'], -1), 5) == k) / dsum:.0%}" for k in sorted(dd))
        med = stt.median([x["absb"] for x in v]); big = [x for x in v if x["absb"] > med and x["absb"] > 0]
        cut = sum(1 for x in big if x["cut"]) / len(big) if big else float("nan")
        both = collections.defaultdict(set)
        for x in v: both[(x["u"], x["b"])].add(x["side"])
        two = sum(1 for k in both.values() if len(k) == 2) / len(both)
        print(f"{g:6s} UIDs {nu:2d} | fills/UID/sim h {len(v) / nu / hrs:6.1f} | $/UID/book/sim h {D / nb / hrs:8,.0f} | books/UID {nb / nu:5.1f} | two-sided {two:.0%}"
              f"\n       filled $ per order: median {stt.median(os_):,.0f} p90 {os_[int(len(os_) * .9)]:,.0f} | fill depth ($): {dep}"
              f"\n       edge {sum(x['edge'] * x['usd'] for x in v) / D:+.2f} kept {sum(x['kept'] * x['usd'] for x in v) / D:+.2f} bp | "
              f"when |pos| > its median (${med:,.0f}): {cut:.0%} of fills cut the position")

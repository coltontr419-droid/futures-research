"""§1272 part 2: entry clip spacing, exit slice size and level, first-exit level, and OPEN positions' marks at tape end (survivor check).
    python legs2.py <tape> <uids>"""
import json, sys, collections, statistics as st, bisect
tape, uids = sys.argv[1], {int(u) for u in sys.argv[2].split(",")}
M = collections.defaultdict(lambda: ([], [])); F = collections.defaultdict(list); seen = set(); T = 0
for l in open(tape, "rb"):
    i = l.find(b'"ts": '); t = int(l[i + 6:l.index(b",", i)]) / 1e9; T = max(T, t)
    if b'"bid"' in l[:60]:
        j = l.find(b'"bids"'); r = json.loads(l[:j].rstrip(b', ') + b"}")
        if r.get("bid") and r.get("ask"): m = M[r["book"]]; m[0].append(t); m[1].append((r["bid"] + r["ask"]) / 2)
    elif b'"Ta": ' in l:
        r = json.loads(l); k = (r["book"], r.get("id"))
        if r.get("Ta") in uids and k not in seen:
            seen.add(k); F[(r["Ta"], r["book"])].append((t, (1 if r["s"] == 0 else -1) * r["q"], r["p"]))
mid = lambda b, t: (lambda a: a[1][max(0, bisect.bisect_right(a[0], t) - 1)] if a[0] else None)(M[b])
for u in sorted(uids):
    gap, clipusd, exit_frac, first_exit, held_open, opens, peak_usd, nlegs_open = [], [], [], [], [], [], [], []
    books = [b for (uu, b) in F if uu == u]
    for b in books:
        fs = sorted(F[(u, b)]); inv = 0.0; cost = 0.0; q = 0.0; lastt = None; exited = False; peak = 0.0; n = 0; t0 = None
        for t, d, p in fs:
            m0 = mid(b, t) or p
            if abs(inv) * p < 1 or (d > 0) == (inv > 0):
                if abs(inv) * p < 1: cost = q = 0.0; exited = False; peak = 0.0; n = 0; t0 = t; lastt = None
                if lastt is not None: gap.append(t - lastt)
                lastt = t; clipusd.append(abs(d) * p); cost += abs(d) * m0; q += abs(d); inv += d; n += 1; peak = max(peak, abs(inv) * p)
            else:
                avg = cost / q; sg = 1 if inv > 0 else -1; pnl = sg * (m0 - avg) / avg * 1e4
                exit_frac.append(min(1, abs(d) / abs(inv)))
                if not exited: first_exit.append(pnl); exited = True
                cost -= avg * min(abs(d), abs(inv)); q -= min(abs(d), abs(inv)); inv += d
                if abs(inv) * p >= 1 and (inv > 0) != (sg > 0): cost = abs(inv) * m0; q = abs(inv); n = 1; peak = abs(inv) * p
        if abs(inv) * (fs[-1][2]) >= 1 and q > 0:
            avg = cost / q; sg = 1 if inv > 0 else -1; me = mid(b, T) or fs[-1][2]
            opens.append(sg * (me - avg) / avg * 1e4); held_open.append(T - t0); peak_usd.append(peak); nlegs_open.append(n)
    if not gap: print(f"{u}: too few"); continue
    pc = lambda a, x: sorted(a)[int(x * (len(a) - 1))]
    print(f"== uid {u}: books {len(books)} | entry clip ${st.median(clipusd):,.0f} (p90 ${pc(clipusd, .9):,.0f}), gap between clips median {st.median(gap):.0f} s (p25 {pc(gap, .25):.0f}, p75 {pc(gap, .75):.0f})")
    print(f"   exits: slice = {st.median(exit_frac):.0%} of position (p75 {pc(exit_frac, .75):.0%}); FIRST exit at median {st.median(first_exit):+.1f} bp vs avg (p25 {pc(first_exit, .25):+.1f}, p75 {pc(first_exit, .75):+.1f}); first exits in profit {sum(v > 0 for v in first_exit) / len(first_exit):.0%}")
    if opens: print(f"   OPEN at tape end: {len(opens)} positions, mark median {st.median(opens):+.1f} bp (mean clipped {st.mean(max(-100, min(100, v)) for v in opens):+.1f}), underwater {sum(v < 0 for v in opens) / len(opens):.0%}, open for median {st.median(held_open):.0f} s, peak size median ${st.median(peak_usd):,.0f}, legs {st.median(nlegs_open):.0f}")

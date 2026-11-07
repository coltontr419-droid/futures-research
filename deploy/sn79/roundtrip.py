"""Why do the top skill UIDs score 4-7 bp from +1.5 bp entries? (decisions.md §1258) Rebuild each UID's position per book from its fills on a tape slice. A round trip runs from flat to flat (or a sign flip). For each: hold time,
peak notional, signed mid move from notional-weighted entry to notional-weighted exit, the same at fixed +300 / +900 s after the first entry, best favourable excursion and how much of it the exit kept. Book alpha and notional as in skill_val.
    python roundtrip.py <tape> <MB> <since sim s> <uid,uid,...>"""
import bisect, json, statistics as st, sys, collections
tape, MB, since, uids = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), {int(u) for u in sys.argv[4].split(",")}
M = collections.defaultdict(lambda: ([], [])); F = collections.defaultdict(list); seen = set()
with open(tape, "rb") as fh:
    fh.seek(0, 2); fh.seek(max(0, fh.tell() - MB * 1_000_000)); fh.readline()
    for l in fh:
        if b'"bid"' in l[:60]:
            i = l.find(b'"bids"'); r = json.loads(l[:i].rstrip(b', ') + b"}")
            if r.get("bid") and r.get("ask"):
                t = r["ts"] / 1e9; m = M[r["book"]]
                if t >= since - 60 and (not m[0] or t > m[0][-1]): m[0].append(t); m[1].append((r["bid"] + r["ask"]) / 2)
        elif b'"Ta": ' in l:
            r = json.loads(l); t = r["ts"] / 1e9; k = (r["book"], r.get("id"))
            if t >= since and r.get("Ta") in uids and k not in seen:
                seen.add(k); F[(r["Ta"], r["book"])].append((t, (1 if r["s"] == 0 else -1) * r["q"], r["p"]))
def mid(b, t):
    a, m = M[b]; i = bisect.bisect_left(a, t)
    return m[i] if i < len(a) else None
R = collections.defaultdict(list); O = collections.defaultdict(list); fills = collections.Counter()
for (u, b), fs in F.items():
    fs.sort(); inv = 0.0; cur = None; fills[u] += len(fs)
    for t, d, p in fs:
        m0 = mid(b, t)
        if m0 is None: continue
        if cur is None:
            cur = dict(t0=t, sg=1 if d > 0 else -1, en=0.0, eq=0.0, ex=0.0, xq=0.0, peak=0.0, n=0)
        same = (d > 0) == (cur["sg"] > 0); q = abs(d); cur["n"] += 1
        if same:
            cur["en"] += m0 * q; cur["eq"] += q
        else:
            cur["ex"] += m0 * min(q, abs(inv)); cur["xq"] += min(q, abs(inv))
        new = inv + d; cur["peak"] = max(cur["peak"], abs(new) * m0)
        if abs(new) < 1e-9 or new * inv < 0:
            if cur["xq"] > 0:
                e = cur["en"] / cur["eq"]; x = cur["ex"] / cur["xq"]; sg = cur["sg"]; a, mm = M[b]; i, j = bisect.bisect_left(a, cur["t0"]), bisect.bisect_left(a, t)
                fx = lambda s: (sg * (mid(b, cur["t0"] + s) - e) / e * 1e4) if mid(b, cur["t0"] + s) is not None else None
                ex = max((sg * (v - e) / e * 1e4 for v in mm[i:j + 1]), default=0)
                mae = min((sg * (v - e) / e * 1e4 for v in mm[i:j + 1]), default=0)
                R[u].append(dict(hold=t - cur["t0"], ret=sg * (x - e) / e * 1e4, peak=cur["peak"], n=cur["n"], f300=fx(300), f900=fx(900), mfe=ex, mae=mae))
            cur = None; inv = 0.0
            if new * inv != 0: pass
            if abs(new) > 1e-9:
                cur = dict(t0=t, sg=1 if new > 0 else -1, en=m0 * abs(new), eq=abs(new), ex=0.0, xq=0.0, peak=abs(new) * m0, n=1); inv = new
        else:
            inv = new
    if cur is not None and abs(inv) > 1e-9:
        e = cur['en'] / cur['eq']; a, mm = M[b]; lm = mm[-1] if mm else e
        i0 = bisect.bisect_left(a, cur['t0'])
        O[u].append(dict(age=a[-1] - cur['t0'] if a else 0, ret=cur['sg'] * (lm - e) / e * 1e4, val=abs(inv) * lm, mae=min((cur['sg'] * (v - e) / e * 1e4 for v in mm[i0:]), default=0)))
print("uid  fills  roundtrips | hold median s | $ peak median | legs | RT move bp: mean(±50) median hit | same at +300 s, +900 s from entry | best excursion mean | kept of best | $-wtd RT bp")
for u in sorted(R, key=lambda u: (u == 22, u)):
    X = R[u]; n = len(X)
    if n < 10: print(u, "few round trips", n, "fills", fills[u]); continue
    c = lambda v: max(-50, min(50, v)); w = sum(x["peak"] for x in X)
    f3 = [c(x["f300"]) for x in X if x["f300"] is not None]; f9 = [c(x["f900"]) for x in X if x["f900"] is not None]; ret = [c(x["ret"]) for x in X]; mf = [c(x["mfe"]) for x in X]
    print(f"{u:4d} {fills[u]:5d} {n:5d} | {st.median(x['hold'] for x in X):6.0f} | {st.median(x['peak'] for x in X):7.0f} | {st.mean(x['n'] for x in X):4.1f} | {st.mean(ret):+6.2f} {st.median(ret):+6.2f} {sum(r > 0 for r in ret) / n:4.0%} | {st.mean(f3):+6.2f} {st.mean(f9):+6.2f} | {st.mean(mf):+6.2f} | {st.mean(ret) / st.mean(mf):4.0%} | {sum(c(x['ret']) * x['peak'] for x in X) / w:+6.2f}")

print("open at the end of the slice, marked to the last mid: uid | open books | age median s | mark bp mean, share under water | closed + open combined mean bp, win rate")
for u in sorted(O, key=lambda u: (u == 22, u)):
    Y = O[u]; X = R.get(u, []); c = lambda v: max(-50, min(50, v)); A = [c(x["ret"]) for x in X] + [c(y["ret"]) for y in Y]
    print(f"{u:4d} | {len(Y):3d} | {st.median(y['age'] for y in Y):6.0f} | {st.mean(c(y['ret']) for y in Y):+6.2f} {sum(y['ret'] < 0 for y in Y) / len(Y):4.0%} | {st.mean(A):+6.2f} {sum(a > 0 for a in A) / len(A):4.0%}  (n {len(A)})")

print("STOPS? closed positions: uid | losers n, share | loser exit bp p50 p10 worst | hold s losers vs winners | worst dip of closed WINNERS p50 p10 worst | open positions: worst mark, dip p10 worst | positions past -10 / -20 / -50 bp at any time")
for u in sorted(R, key=lambda u: (u == 22, u)):
    X = R[u]; Y = O.get(u, [])
    if len(X) < 10: continue
    L = sorted(x["ret"] for x in X if x["ret"] <= 0); W = [x for x in X if x["ret"] > 0]; q = lambda v, p: sorted(v)[int(len(v) * p)] if v else 0
    allm = [x["mae"] for x in X] + [y["mae"] for y in Y]; n = len(allm)
    print(f"{u:4d} | {len(L):3d} {len(L) / len(X):4.0%} | {q(L, .5):+7.1f} {q(L, .1):+7.1f} {min(L, default=0):+7.1f} | {st.median([x['hold'] for x in X if x['ret'] <= 0] or [0]):5.0f} / {st.median(x['hold'] for x in W):5.0f} | {q([x['mae'] for x in W], .5):+6.1f} {q([x['mae'] for x in W], .1):+6.1f} {min((x['mae'] for x in W), default=0):+7.1f} | {min((y['ret'] for y in Y), default=0):+7.1f}, {q([y['mae'] for y in Y], .1):+6.1f} {min((y['mae'] for y in Y), default=0):+7.1f} | {sum(m < -10 for m in allm) / n:4.0%} {sum(m < -20 for m in allm) / n:4.0%} {sum(m < -50 for m in allm) / n:4.0%}")

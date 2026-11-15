"""MEASURED: when the mixed miners TAKE — is it unwinding their own inventory or new direction? Per book, running inventory (base units) from their own
maker + taker fills since the window start (relative; true starting inventory unknown → also report the share where the take crosses zero).
Per taker trade: unwind (reduces |inv|) vs add; class; size; spread then; 20 s / 120 s markout (+ = price moved its way); seconds since its last maker fill
on that book (taking right after being filled = hedging the fill)."""
import json, sys, collections
tape, LO, HI = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]); U = [int(u) for u in sys.argv[4:]]; US = set(U)
S = collections.defaultdict(dict); EV = []; seen = set()
for l in open(tape, "rb"):
    i = l.find(b'"ts": ')
    if i < 0 or b'"book": ' not in l: continue
    try: ts = int(l[i + 6:l.index(b",", i)]); s = ts // 10**9
    except ValueError: continue
    if s < LO - 5 or s > HI + 125: continue
    j = l.find(b'"book": '); bk = int(l[j + 8:l.index(b",", j)])
    if b'"bid": ' in l[:90]:
        r = json.loads(l)
        if r.get("bid") and r.get("ask"): S[bk][s] = (r["bid"], r["ask"])
    elif b'"Ta"' in l:
        r = json.loads(l); k = (bk, r.get("id"), ts)
        if k in seen or not (LO <= s < HI): continue
        seen.add(k)
        if r.get("Ma") in US or r.get("Ta") in US: EV.append((ts, s, bk, r))
EV.sort(key=lambda x: x[0])
inv = collections.defaultdict(float); lastfill = {}; R = collections.defaultdict(lambda: [0.0, 0.0, 0.0, 0, 0.0])
for ts, s, bk, r in EV:
    q = r["q"]; tb = r["s"] == 0                     # taker bought?
    if r.get("Ma") in US:
        u = r["Ma"]; inv[(u, bk)] += -q if tb else q; lastfill[(u, bk)] = s
    if r.get("Ta") in US:
        u = r["Ta"]; d = q if tb else -q; before = inv[(u, bk)]; after = before + d; inv[(u, bk)] = after
        kind = "UNWIND" if abs(after) < abs(before) - 1e-12 else "ADD"
        lf = lastfill.get((u, bk)); hedge = lf is not None and s - lf <= 2
        a = S[bk].get(s - 1); b20 = S[bk].get(s + 20); b120 = S[bk].get(s + 120)
        if not (a and b20 and b120): continue
        m0 = (a[0] + a[1]) / 2; sg = 1 if tb else -1; usd = r["p"] * q
        c = "$300" if bk < 128 else ("$30" if bk < 192 else "4dec")
        for key in ((u, "ALL"), (u, kind), (u, kind + (" ≤2 s after own maker fill" if hedge else " (no recent fill)")), (u, c)):
            x = R[key]; x[0] += usd; x[1] += usd * sg * ((b20[0] + b20[1]) / 2 - m0) / m0 * 1e4; x[2] += usd * sg * ((b120[0] + b120[1]) / 2 - m0) / m0 * 1e4; x[3] += 1
for u in U:
    tot = R[(u, "ALL")][0]
    if not tot: print(f"{u}: no taker trades"); continue
    print(f"== uid {u}: taker trades {R[(u, 'ALL')][3]}, ${tot / 1e3:.0f}k")
    for key in sorted([k for k in R if k[0] == u and k[1] != "ALL"], key=lambda k: -R[k][0]):
        x = R[key]; print(f"   {key[1]:42} {x[0] / tot:4.0%} n {x[3]:4d} | markout 20 s {x[1] / x[0]:+.2f}  120 s {x[2] / x[0]:+.2f} bp")

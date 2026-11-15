"""MEASURED: do $300/4-dec maker INSIDE and TOUCH fills line up with the fade signal (−dmid60 − dmid300 sign agrees with the maker's side)?
Markout 20/120 s for fills where fade agrees vs disagrees, per uid; share agreeing.  python fadecheck.py tape lo hi uids..."""
import json, sys, collections
tape, LO, HI = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]); U = [int(u) for u in sys.argv[4:]]; US = set(U)
B = collections.defaultdict(dict); F = []; seen = set()
for l in open(tape, "rb"):
    i = l.find(b'"ts": ')
    if i < 0 or b'"book": ' not in l: continue
    try: ts = int(l[i + 6:l.index(b",", i)]); s = ts // 10**9
    except ValueError: continue
    if s < LO - 320 or s > HI + 125: continue
    j = l.find(b'"book": '); bk = int(l[j + 8:l.index(b",", j)])
    if 128 <= bk < 192: continue
    if b'"bid": ' in l[:90]:
        r = json.loads(l)
        if r.get("bid") and r.get("ask"): B[bk][s] = (r["bid"], r["ask"])
    elif b'"Ma"' in l:
        r = json.loads(l); k = (bk, r.get("id"), ts)
        if k in seen: continue
        seen.add(k)
        if r.get("Ma") in US and LO <= s < HI: F.append((s, bk, r["Ma"], r["p"], r["q"], r["s"]))
R = collections.defaultdict(lambda: [0.0, 0.0, 0.0, 0])
for s, bk, u, p, q, side in F:
    d = B[bk]; a = d.get(s - 1); a60 = d.get(s - 61); a300 = d.get(s - 301); b20 = d.get(s + 20); b120 = d.get(s + 120)
    if not (a and a60 and a300 and b20 and b120): continue
    mid = lambda x: (x[0] + x[1]) / 2; m0 = mid(a); buy = side == 1; sg = 1 if buy else -1
    tk = 0.01 if bk < 128 else 0.0001
    dd = round(((a[0] - p) if buy else (p - a[1])) / tk); kind = "inside" if dd < 0 else ("touch" if dd == 0 else "behind")
    fade = -((m0 - mid(a60)) + (m0 - mid(a300)))       # + = price fell recently → fade says BUY
    agree = "fade agrees" if fade * sg > 0 else ("fade disagrees" if fade * sg < 0 else "flat")
    c = "$300" if bk < 128 else "4dec"; usd = p * q
    for key in ((u, c, kind, agree), (u, c, "all", agree)):
        x = R[key]; x[0] += usd; x[1] += usd * sg * (mid(b20) - m0) / m0 * 1e4; x[2] += usd * sg * (mid(b120) - m0) / m0 * 1e4; x[3] += 1
for c in ("$300", "4dec"):
    for kind in ("inside", "touch", "behind", "all"):
        print(f"== {c} {kind.upper()} maker fills: share agreeing with fade | markout 20 s / 120 s (agree vs disagree)")
        for u in U:
            ag, dg = R[(u, c, kind, "fade agrees")], R[(u, c, kind, "fade disagrees")]
            if ag[3] + dg[3] < 15: continue
            f = lambda x: f"{x[1] / x[0]:+.2f}/{x[2] / x[0]:+.2f}" if x[0] else "  n/a  "
            print(f"   {u:3d}: agree {ag[0] / (ag[0] + dg[0]):4.0%} (n {ag[3] + dg[3]:5d}) | agree {f(ag)} | disagree {f(dg)}")

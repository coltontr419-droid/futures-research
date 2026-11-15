"""MEASURED: who hits the $300 inside/touch fills of each uid — miner takers (0-255) vs simulator background agents (by negative id) — share of $ and 20-s markout."""
import json, sys, collections
tape, LO, HI = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]); U = [int(u) for u in sys.argv[4:]]; US = set(U)
S = collections.defaultdict(dict); F = []; seen = set()
for l in open(tape, "rb"):
    i = l.find(b'"ts": ')
    if i < 0: continue
    ts = int(l[i + 6:l.index(b",", i)]); s = ts // 10**9
    if s < LO - 5 or s > HI + 25: continue
    j = l.find(b'"book": '); bk = int(l[j + 8:l.index(b",", j)])
    if bk >= 128: continue
    if b'"bid": ' in l[:90]:
        r = json.loads(l)
        if r.get("bid") and r.get("ask"): S[bk][s] = (r["bid"], r["ask"])
    elif b'"Ta"' in l:
        r = json.loads(l); k = (bk, r.get("id"), ts)
        if k in seen: continue
        seen.add(k)
        if r.get("Ma") in US and LO <= s < HI: F.append((s, bk, r["Ma"], r["p"], r["q"], r["s"], r.get("Ta")))
R = collections.defaultdict(lambda: [0.0, 0.0, 0]); TOT = collections.defaultdict(float)
for s, bk, u, p, q, side, ta in F:
    a = S[bk].get(s - 1); b = S[bk].get(s + 20)
    if not (a and b): continue
    buy = side == 1; sg = 1 if buy else -1; m0 = (a[0] + a[1]) / 2
    d = round(((a[0] - p) if buy else (p - a[1])) / 0.01); kind = "inside" if d < 0 else ("touch" if d == 0 else "behind")
    if kind == "behind": continue
    mo = sg * ((b[0] + b[1]) / 2 - m0) / m0 * 1e4
    who = f"bg{ta}" if ta is not None and ta < 0 else ("miner" if ta is not None else "?")
    x = R[(u, kind, who)]; x[0] += p * q; x[1] += p * q * mo; x[2] += 1; TOT[(u, kind)] += p * q
for kind in ("inside", "touch"):
    print(f"== $300 {kind.upper()} fills by taker (share of $, n, 20-s markout bp)")
    for u in U:
        ks = sorted([k for k in R if k[0] == u and k[1] == kind], key=lambda k: -R[k][0])
        print(f"  {u}: " + " | ".join(f"{k[2]} {R[k][0] / TOT[(u, kind)]:3.0%} n{R[k][2]} {R[k][1] / R[k][0]:+.2f}" for k in ks[:7]))

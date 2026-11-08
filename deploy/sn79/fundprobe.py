"""§1306b: do the fleet's maker fills sit on the right side of the sim's FUNDAMENTAL? For each fill: gap = (fundamental − mid)/mid in bp, signed for the maker
(+ = the maker bought below / sold above fundamental, i.e. the fill leans toward fair value). Buckets of that signed gap → share of $, kept 20 s later, kept÷edge.
Also: share of each UID's fills on the 'toward fundamental' side.   python fundprobe.py <tape> <since> <name=uids> ..."""
import json, sys, collections, bisect
tape, LO = sys.argv[1], float(sys.argv[2]); G = {a.split("=")[0]: {int(u) for u in a.split("=")[1].split(",")} for a in sys.argv[3:]}
who = {u: g for g, us in G.items() for u in us}
M = collections.defaultdict(lambda: ([], [], [])); F = []; seen = set()
for l in open(tape, "rb"):
    i = l.find(b'"ts": '); t = int(l[i + 6:l.index(b",", i)]) / 1e9
    if t >= 60000 or t < LO - 120: continue
    if b'"bid": ' in l[:80]:
        r = json.loads(l)
        if r["book"] < 102 and r.get("bid") and r.get("ask") and r.get("fund"): a = M[r["book"]]; a[0].append(t); a[1].append((r["bid"] + r["ask"]) / 2); a[2].append(r["fund"])
    elif b'"Ma": ' in l:
        r = json.loads(l); k = (r["book"], r.get("id"), r["ts"])
        if k in seen or r["book"] >= 102: continue
        seen.add(k)
        if r.get("Ma") in who and t >= LO: F.append((who[r["Ma"]], r["book"], t, r["s"], r["q"], r["p"]))
R = collections.defaultdict(list); n_fund = 0
for g, b, t, s, q, p in F:
    a = M[b]; i = bisect.bisect_left(a[0], t) - 1; j = bisect.bisect_left(a[0], t + 20)
    if i < 0 or j >= len(a[0]): continue
    m0, f0, m1 = a[1][i], a[2][i], a[1][j]; mk = -1 if s == 0 else 1; n_fund += 1
    gap = mk * (f0 - m0) / m0 * 1e4                                   # + = fair value is on our side of the trade (we bought below fair / sold above)
    edge = mk * (m0 - p) / m0 * 1e4; kept = edge + mk * (m1 - m0) / m0 * 1e4
    gb = "toward fair >5bp" if gap > 5 else "toward fair 1-5bp" if gap > 1 else "near fair ±1bp" if gap >= -1 else "against fair 1-5bp" if gap >= -5 else "against fair >5bp"
    grp = "$300" if b < 63 else "calm"
    R[(g, grp, gb)].append((q * p, edge, kept)); R[(g, grp, "all")].append((q * p, edge, kept))
print(f"fills with a fundamental on the tape: {n_fund}")
order = ["toward fair >5bp", "toward fair 1-5bp", "near fair ±1bp", "against fair 1-5bp", "against fair >5bp"]
def row(v, tot):
    w = sum(x[0] for x in v); e = sum(x[0] * x[1] for x in v) / w; k = sum(x[0] * x[2] for x in v) / w
    return f"{w / tot:4.0%} $ | kept {k:+5.2f} | k÷e {k / e if e else 0:+5.2f}"
for grp in ("$300", "calm"):
    print(f"######## {grp}")
    for g in G:
        allv = R.get((g, grp, "all"), [])
        if not allv: continue
        tot = sum(x[0] for x in allv); print(f"== {g}: {row(allv, tot)}")
        print("   " + " || ".join(f"{v}: {row(R[(g, grp, v)], tot)}" for v in order if R.get((g, grp, v))))

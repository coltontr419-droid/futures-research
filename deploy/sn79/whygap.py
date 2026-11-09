"""§1322: why do our maker fills keep less than the long-lived fleet's? Every route visible on the tape, per book group, with a mix / within decomposition
(gap = Σ(s_us − s_fleet)·k_fleet [WHERE fills happen] + Σ s_us·(k_us − k_fleet) [HOW they do in the same bucket]).  Read-only.
python3 whygap.py <tape> <T0> <T1> fleet=<uids> us=<uid>"""
import json, sys, collections, bisect
tape, T0, T1 = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
G = {a.split("=")[0]: {int(u) for u in a.split("=")[1].split(",")} for a in sys.argv[4:6]}; who = {u: g for g, us in G.items() for u in us}
FLEET = G["fleet"]; SN = collections.defaultdict(dict); TR = []; QID = {}
for l in open(tape, "rb"):
    i = l.find(b'"ts": '); t = int(l[i + 6:l.index(b",", i)]) / 1e9
    if t >= 60000 or t < T0 - 700 or t > T1 + 30: continue
    j = l.find(b'"book": '); b = int(l[j + 8:l.index(b",", j)])
    if b >= 102: continue
    r = json.loads(l)
    if "Mi" in r:
        if T0 <= t < T1: TR.append((t, b, r["id"], r["p"], r["q"], r["s"], r["Ma"], r["Ta"], r["Mi"]))
    elif "bids" in r:
        if r["bids"] and r["asks"]: SN[b][int(t)] = (r["bid"], r["ask"], r["bids"], r["asks"])
    elif "queue" in r:
        for q in r["queue"]: QID.setdefault((b, q[4]), t)
PB = collections.defaultdict(list)
for (b, k), v in QID.items(): PB[b].append((k, v))
for b in PB: PB[b].sort()
def placed(b, mi):
    v = PB.get(b, []); ids = [x[0] for x in v]; j = bisect.bisect_left(ids, mi)
    if j == 0 or j >= len(v): return None
    (i0, t0), (i1, t1) = v[j - 1], v[j]; return t0 + (t1 - t0) * (mi - i0) / max(1, i1 - i0)
def snap(b, s):
    for k in (0, 1, 2):
        x = SN[b].get(int(s) - k)
        if x: return x
# taker sweeps: same taker, book, second, side
sweep = collections.defaultdict(list)
for x in TR: sweep[(x[1], int(x[0]), x[7], x[5])].append(x)
rows = []; lastfill = {}; pos = collections.defaultdict(float)
for t, b, tid, p, q, s, ma, ta, mi in sorted(TR):
    if ma not in who or ma == ta: continue
    g = who[ma]; a = snap(b, t - 1); z = SN[b].get(int(t) + 20) or SN[b].get(int(t) + 21); after = SN[b].get(int(t) + 1)
    if not a or not z: continue
    buy = s == 1; sg = 1 if buy else -1; tick = 0.01; mid = (a[0] + a[1]) / 2; mid2 = (z[0] + z[1]) / 2
    kept = sg * (mid2 - p) / mid * 1e4
    sw = sweep[(b, int(t), ta, s)]; sw_usd = sum(x[3] * x[4] for x in sw); px_lv = sorted({x[3] for x in sw}, reverse=not buy)
    at_px = sorted([x for x in sw if abs(x[3] - p) < 1e-9], key=lambda x: x[2])
    back = at_px[-1][2] == tid and len(px_lv) > 1 and abs(px_lv[-1] - p) > 1e-9      # last fill at our price and the sweep went beyond it = we were at the back
    swept = after is not None and ((after[0] < p - 1e-9) if buy else (after[1] > p + 1e-9))
    lv = (a[2] if buy else a[3]); lvl_q = next((x[1] for x in lv if abs(x[0] - p) < 1e-9), 0.0)
    pt = placed(b, mi); age = t - pt if pt is not None else None
    gap = t - lastfill.get((ma, b), -1e9); lastfill[(ma, b)] = t
    before = pos[(ma, b)]; pos[(ma, b)] += sg * q
    tk = "background" if ta < 0 else ("fleet taker" if ta in FLEET else "miner taker")
    rows.append(dict(g=g, grp="$300" if b < 63 else "calm", usd=p * q, kept=kept, edge=sg * (mid - p) / mid * 1e4,
        taker=tk, queue="back of a swept level" if back else ("level swept (front/mid)" if swept else "level held"),
        size=("< $2k" if sw_usd < 2000 else "$2-10k" if sw_usd < 10000 else "$10k+"),
        age=("n/a" if age is None else "< 5 s" if age < 5 else "5-30 s" if age < 30 else "30-120 s" if age < 120 else "120 s+"),
        spread=str(min(round((a[1] - a[0]) / tick), 4)) + (" ticks" if round((a[1] - a[0]) / tick) < 4 else "+ ticks"),
        cluster=("< 2 s after our last fill" if gap < 2 else "2-60 s" if gap < 60 else "60 s+"),
        inv=("adds to position" if before == 0 or (before > 0) == buy else "cuts position"),
        depth=str(min(max(round(((a[0] - p) if buy else (p - a[1])) / tick), -1), 3)) + (" (inside)" if round(((a[0] - p) if buy else (p - a[1])) / tick) < 0 else " behind" if round(((a[0] - p) if buy else (p - a[1])) / tick) < 3 else "+ behind"),
        move=sg * (mid2 - mid) / mid * 1e4,
        level_q=("our level < $2k deep" if lvl_q * p < 2000 else "$2-10k deep" if lvl_q * p < 10000 else "$10k+ deep")))
dims = ["depth", "level_q", "age", "queue", "taker", "size", "spread", "cluster", "inv"]
for grp in ("calm", "$300"):
    F = [x for x in rows if x["g"] == "fleet" and x["grp"] == grp]; U = [x for x in rows if x["g"] == "us" and x["grp"] == grp]
    if not F or not U: continue
    DF, DU = sum(x["usd"] for x in F), sum(x["usd"] for x in U)
    kf, ku = sum(x["kept"] * x["usd"] for x in F) / DF, sum(x["kept"] * x["usd"] for x in U) / DU
    print(f"\n######## {grp}: fleet {len(F)} fills kept {kf:+.2f} bp | us {len(U)} fills kept {ku:+.2f} bp | gap {kf - ku:+.2f} bp")
    summary = []
    for d in dims:
        keys = sorted({x[d] for x in F + U}); mix = within = 0.0; lines = []
        for k in keys:
            f = [x for x in F if x[d] == k]; u = [x for x in U if x[d] == k]
            sf = sum(x["usd"] for x in f) / DF; su = sum(x["usd"] for x in u) / DU
            kkf = sum(x["kept"] * x["usd"] for x in f) / sum(x["usd"] for x in f) if f else 0.0
            kku = sum(x["kept"] * x["usd"] for x in u) / sum(x["usd"] for x in u) if u else kkf
            mix += (su - sf) * kkf; within += su * (kku - kkf)
            ef = sum(x["edge"] * x["usd"] for x in f) / sum(x["usd"] for x in f) if f else 0.0; eu = sum(x["edge"] * x["usd"] for x in u) / sum(x["usd"] for x in u) if u else 0.0
            lines.append(f"    {k:28s} fleet {sf:5.0%} kept {kkf:+6.2f} (edge {ef:+5.2f}) n {len(f):5d} | us {su:5.0%} kept {kku:+6.2f} (edge {eu:+5.2f}) n {len(u):4d}")
        summary.append((d, -mix, -within))
        print(f"  -- {d}: WHERE (mix) explains {-mix:+.2f} bp of the gap, HOW (within) {-within:+.2f}"); print("\n".join(lines))
    print("  -- depth x level crowding (kept bp, share of $):")
    for dk in sorted({x["depth"] for x in F + U}):
        for lq in ("our level < $2k deep", "$2-10k deep", "$10k+ deep"):
            f = [x for x in F if x["depth"] == dk and x["level_q"] == lq]; u = [x for x in U if x["depth"] == dk and x["level_q"] == lq]
            if len(f) + len(u) < 20: continue
            w = lambda v, k: sum(x[k] * x["usd"] for x in v) / sum(x["usd"] for x in v) if v else float("nan")
            print(f"    {dk:12s} {lq:22s} fleet {sum(x['usd'] for x in f) / DF:4.0%} kept {w(f, 'kept'):+6.2f} | us {sum(x['usd'] for x in u) / DU:4.0%} kept {w(u, 'kept'):+6.2f} (n {len(u)})")
    mf = sum(x["move"] * x["usd"] for x in F) / DF; mu = sum(x["move"] * x["usd"] for x in U) / DU
    ef_ = sum(x["edge"] * x["usd"] for x in F) / DF; eu_ = sum(x["edge"] * x["usd"] for x in U) / DU
    print(f"  == kept = edge at fill + mid move after: fleet {ef_:+.2f} + {mf:+.2f} | us {eu_:+.2f} + {mu:+.2f}")
    print("  == ranked by WHERE effect:", ", ".join(f"{d} {m:+.2f}" for d, m, w in sorted(summary, key=lambda x: -abs(x[1]))))

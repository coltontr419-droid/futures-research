"""Credit per dollar traded, x3 vs the field's makers (decisions.md §1251). Joins making_exact's per-UID C / R / quality / credit (from
/tmp/making_exact_field.json, same tape and window) with each maker's traded notional, fill count, median fill and books from the tape.
    python makereff.py <tape.jsonl> <since sim min> <our uid> [top n]"""
import json, statistics as st, sys
from collections import defaultdict
tape, since, me = sys.argv[1], float(sys.argv[2]) * 6e10, int(sys.argv[3]); top = int(sys.argv[4]) if len(sys.argv) > 4 else 12
F = json.load(open("/tmp/making_exact_field.json")); seen = set(); notl = defaultdict(float); sizes = defaultdict(list); books = defaultdict(set)
for l in open(tape):
    if '"Ma": ' not in l: continue
    r = json.loads(l); u = r.get("Ma")
    if u is None or u < 0 or r["ts"] < since: continue
    k = (r["book"], r.get("id"))
    if k in seen: continue
    seen.add(k); v = r["p"] * r["q"]; notl[u] += v; sizes[u].append(v); books[u].add(r["book"])
rows = []
for u, d in F.items():
    u = int(u)
    if notl[u] > 0: rows.append((d["credit"], u, notl[u], d["C"], d["q"], len(sizes[u]), st.median(sizes[u]), len(books[u])))
rows.sort(reverse=True)
def show(x):
    cr, u, n, C, q, nf, med, bk = x
    print(f"{u:4d}{' <- x3' if u == me else '':6} credit {cr:7.1f} | $M {n / 1e6:6.2f} | credit/$M {cr / (n / 1e6):7.1f} | captured bp {1e4 * C / n:6.2f} | quality {q:.3f} | two-sided share {cr / q / C if q and C else 0:.2f} | fills {nf:6d} median ${med:6.0f} | books {bk}")
print(f"makers with fills: {len(rows)}"); [show(x) for x in rows[:top]]
print("..."); [show(x) for x in rows if x[1] == me]
e = sorted(r[0] / (r[2] / 1e6) for r in rows if r[2] > 1e5); print(f"credit/$M across makers with > $0.1M: median {st.median(e):.1f}, p75 {e[3 * len(e) // 4]:.1f}, p90 {e[int(len(e) * .9)]:.1f}")

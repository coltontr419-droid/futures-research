"""The making pool's credit, computed with the validator's OWN code (decisions.md §1209): every book's full trade stream from a tape goes
through taos.im.validator.debeta.accumulate_book_capture with the live dials (centred window 15 trades, realized horizon 20 s, min order
size 0.25, maker fee weight 0.005, background votes off, taker legs tracked), then the pool's basis exactly as reward.making_basis_sums
reads it: maker-only captured pair, markout_quality = clamp(R / C, 0, 1), credit = Σ_book 2·min(buy, sell) of the quality-scaled pair.
Per arm (book_id mod N) for our uid; the field's makers for comparison.

    python making_exact.py <tape.jsonl> <our uid> [n arms]          (run with /opt/mvtrx/venv from /opt/mvtrx/repo)
"""
import json
import sys
from collections import defaultdict

sys.path.insert(0, "/opt/mvtrx/repo")
from taos.im.validator.debeta import accumulate_book_capture, balanced_reward_per_book, markout_quality  # noqa: E402

tape, me = sys.argv[1], int(sys.argv[2]); n = int(sys.argv[3]) if len(sys.argv) > 3 else 1
# optional 4th arg: keep only our fills of one class (others lose their maker id but still print into the mid): bot | bg | small | large
only = sys.argv[4] if len(sys.argv) > 4 and not sys.argv[4].startswith("--") else ""
def keep(r):
    if r.get("Ma") != me or not only:
        return True
    bot = r.get("Ta") is not None and r["Ta"] >= 0
    return {"bot": bot, "bg": not bot, "small": r["q"] <= 1.6, "large": r["q"] > 1.6}[only]
# --since <sim minutes>: our fills before that time lose their maker id (they still print into the mid) — scores one setup's period alone.
# Trades are de-duplicated by (book, id): each tape opens with the validator's backlog, so concatenated tapes overlap (§1209 addendum 8).
since = float(sys.argv[sys.argv.index("--since") + 1]) * 6e10 if "--since" in sys.argv else None
trades, seen = defaultdict(list), set()
for line in open(tape):
    r = json.loads(line)
    if "p" in r:
        key = (r["book"], r.get("id"), r["ts"])
        if key in seen:
            continue
        seen.add(key)
        if since is not None and r["ts"] < since and r.get("Ma") == me:
            r["Ma"] = -1
        trades[r["book"]].append({"p": r["p"], "q": r["q"], "s": r["s"], "Ma": r.get("Ma", -1) if keep(r) else -1, "Ta": r.get("Ta", -1),
                                  "Mf": r.get("Mf") or 0.0, "t": r["ts"], "i": r.get("id")})
cb, cs, rb, rs = (defaultdict(dict) for _ in range(4)); tb, ts = {}, {}   # the validator pre-creates every uid's entry
for book, tr in trades.items():
    tr.sort(key=lambda t: t["t"])
    accumulate_book_capture(cb, cs, book, tr, 15, buy_hist={}, sell_hist={}, ts=tr[-1]["t"], mid_state=None,
                            real_buy_sums=rb, real_sell_sums=rs, real_buy_hist={}, real_sell_hist={},
                            horizon_ns=20_000_000_000, now_ns=tr[-1]["t"], min_size=0.25, fee_weight=0.005,
                            market_votes=False, taker=(tb, ts, {}, {}))
less = lambda pair, legs: {u: {b: v - (legs.get(u) or {}).get(b, 0.0) for b, v in books.items()} for u, books in pair.items()}
mb, ms = less(cb, tb), less(cs, ts)


def group(u, k):
    """Our uid split into arm k (books with id mod n == k); every other uid whole."""
    if u != me:
        return mb.get(u, {}), ms.get(u, {}), rb.get(u, {}), rs.get(u, {})
    f = lambda d: {b: v for b, v in (d.get(u) or {}).items() if b % n == k}
    return f(mb), f(ms), f(rb), f(rs)


def credit(b_, s_, rb_, rs_):
    q = markout_quality({0: b_}, {0: s_}, {0: rb_}, {0: rs_}, [0])[0]
    C = sum(b_.values()) + sum(s_.values()); R = sum(rb_.values()) + sum(rs_.values())
    two = balanced_reward_per_book({0: b_}, {0: s_}, [0])[0]
    return C, R, q, two * q, two


field = {}
for u in set(mb) | set(ms):
    if u >= 0 and u != me:
        field[u] = credit(*group(u, 0))
for k in range(n):
    C, R, q, cr, two = credit(*group(me, k))
    tot = sum(v[3] for v in field.values())
    rank = sum(1 for v in field.values() if v[3] > cr) + 1
    print(f"ours{'' if n == 1 else f' arm {k}'}: captured C {C:9.1f} | realized R {R:9.1f} | R/C {R / C if C else float('nan'):+.3f} | "
          f"quality {q:.3f} | two-sided {two:8.1f} | credit {cr:7.1f} → rank {rank} of {len(field) + 1} ({cr / (tot + cr) if tot + cr else 0:.2%})")
Cs = sorted(v[0] for v in field.values())
print(f"field captured C median {Cs[len(Cs) // 2]:.1f}, p75 {Cs[3 * len(Cs) // 4]:.1f}, p90 {Cs[int(len(Cs) * .9)]:.1f}")
qs = sorted(v[2] for v in field.values() if v[0] > 0)
crs = sorted(v[3] for v in field.values())
print(f"field: {len(field)} makers | quality median {qs[len(qs) // 2]:.3f} (p25 {qs[len(qs) // 4]:.3f}, p75 {qs[3 * len(qs) // 4]:.3f}) | "
      f"credit median {crs[len(crs) // 2]:.1f}, p90 {crs[int(len(crs) * .9)]:.1f}")
json.dump({str(u): {"C": v[0], "R": v[1], "q": v[2], "credit": v[3]} for u, v in field.items()}, open("/tmp/making_exact_field.json", "w"))

if "--books" in sys.argv:                                   # per-book split of our captured / realized (exact), for book selection
    rows = []
    for b in sorted(set(mb.get(me, {})) | set(ms.get(me, {}))):
        c = mb.get(me, {}).get(b, 0.0) + ms.get(me, {}).get(b, 0.0); r = rb.get(me, {}).get(b, 0.0) + rs.get(me, {}).get(b, 0.0)
        rows.append((r, c, b))
    rows.sort()
    R = sum(x[0] for x in rows); C = sum(x[1] for x in rows)
    print(f"our books {len(rows)}: total C {C:.1f}, R {R:.1f}")
    for drop in (0, 5, 10, 20, 30, 40):
        kept = rows[drop:]; kR = sum(x[0] for x in kept); kC = sum(x[1] for x in kept)
        print(f"  drop the {drop:2d} worst-R books: C {kC:7.1f} R {kR:7.1f} quality {max(0.0, min(1.0, kR / kC)) if kC > 0 else 0:.3f}")
    print("  worst 10 books (R, C, book):", [(round(r, 1), round(c, 1), b) for r, c, b in rows[:10]])

# two-sided diagnostics (§1209): why Σ_book 2·min(buy, sell) is small — per arm, over our books: both sides positive / one side missing /
# one side negative, how much positive capture the min throws away, and how much the quality-scaled credit would be if each book's sides
# were equal (the ceiling from evening out the sides alone)
for k in range(n):
    b_, s_, _, _ = group(me, k)
    books = set(b_) | set(s_); both = miss = neg = 0; lost = 0.0; pos_tot = 0.0; mins = 0.0
    for bk in books:
        x, y = b_.get(bk), s_.get(bk)
        if x is None or y is None:
            miss += 1
        elif x > 0 and y > 0:
            both += 1
        else:
            neg += 1
        xv, yv = x or 0.0, y or 0.0
        pos_tot += max(xv, 0.0) + max(yv, 0.0); mins += 2 * min(xv, yv); lost += max(xv, 0.0) + max(yv, 0.0) - 2 * max(min(xv, yv), 0.0)
    print(f"  two-sided{'' if n == 1 else f' arm {k}'}: books {len(books)} | both sides positive {both} | one side missing {miss} | "
          f"one side ≤ 0 {neg} | positive capture {pos_tot:.1f}, kept by the per-book min {max(mins, 0.0):.1f} (Σ2·min {mins:+.1f})")

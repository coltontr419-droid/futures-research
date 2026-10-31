"""Offline MVTRX scorer for the lab (futures-research decisions.md §1194). Replays a QuoteAgent tape through the validator's own
de-beta code (taos.im.validator.debeta, offline paths): two-sided spread capture vs the centred mid (CAPTURE_W prints a side), making =
sum over books of 2·min(buy, sell) capture, and per-book alpha = MTM P&L − mean inventory × book drift, with kappa across books.
Every miner-side agent (id >= 0) in the tape is scored, so the example agents in the same run are the comparison.

    python score_tape.py /opt/mvtrx/tape.jsonl [--repo /opt/mvtrx/repo] [--min-size 0.25]

Not modelled: the counterparty (P11) discount, the fee-aware netting, the realized-spread basis, windowing/EMA, and other miners' share
of the pools (the local run has only the example agents), so the numbers rank strategies against each other, not dollars.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("tape")
    ap.add_argument("--repo", default="/opt/mvtrx/repo")
    ap.add_argument("--min-size", type=float, default=0.25)
    ap.add_argument("--min-books", type=int, default=4)
    a = ap.parse_args()
    sys.path.insert(0, a.repo)
    from taos.im.validator import debeta as db
    try:
        from taos.im.validator.trade import CAPTURE_W
    except ImportError:                                   # trade.py imports bittensor; the constant is 15 in 0.6.6
        CAPTURE_W = 15

    trades, seen, quotes = defaultdict(list), set(), defaultdict(list)
    for line in open(a.tape):
        r = json.loads(line)
        if "p" in r:
            key = (r["book"], r.get("id"), r["ts"])
            if key in seen:
                continue
            seen.add(key)
            trades[r["book"]].append(r)
        else:
            quotes[r["book"]].append(r)
    buy, sell = defaultdict(dict), defaultdict(dict)
    mtm, invsum, inv = defaultdict(dict), defaultdict(dict), defaultdict(dict)
    invn, p_first, p_last = {}, {}, {}
    for book, ts in trades.items():
        ts.sort(key=lambda t: (t["ts"], t.get("id") or 0))
        db.accumulate_book_capture(buy, sell, book, ts, CAPTURE_W, min_size=a.min_size)
        db.accumulate_book_mtm(mtm, invsum, invn, inv, p_first, p_last, book, ts)
    alphas = db.book_alphas_by_book(mtm, invsum, invn, {b: p_last[b] - p_first[b] for b in p_last})
    uids = sorted({u for u in list(buy) + list(sell) + list(alphas) if u is not None and u >= 0})
    making = db.balanced_reward_per_book(buy, sell, uids)
    fills = defaultdict(int)
    for ts in trades.values():
        for t in ts:
            for k in ("Ma", "Ta"):
                if t.get(k) is not None and t[k] >= 0:
                    fills[(t[k], k)] += 1
    n_trades = sum(len(v) for v in trades.values())
    print(f"books {len(trades)}, trades {n_trades}, sim span {(max(t['ts'] for v in trades.values() for t in v) - min(t['ts'] for v in trades.values() for t in v)) / 3.6e12:.2f} h")
    print(f"{'uid':>4} {'maker fills':>11} {'taker fills':>11} {'buy cap':>10} {'sell cap':>10} {'making':>10} {'alpha sum':>11} {'books +':>8} {'kappa':>7}")
    for u in uids:
        al = alphas.get(u, {})
        b, s = sum(buy.get(u, {}).values()), sum(sell.get(u, {}).values())
        k = db.kappa_floored(list(al.values()), 0.0, a.min_books)
        print(f"{u:>4} {fills[(u, 'Ma')]:>11} {fills[(u, 'Ta')]:>11} {b:>10.2f} {s:>10.2f} {making.get(u, 0.0):>10.2f} {sum(al.values()):>11.2f} "
              f"{sum(1 for x in al.values() if x > 0):>4}/{len(al):<3} {k:>7.3f}")


if __name__ == "__main__":
    main()

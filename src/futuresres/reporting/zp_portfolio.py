"""The edge portfolio so far - Z02 (MES, rebalancing) + Z05 (MGC, gold overnight/day) - in one Tradeify
account, replayed through REAL history in order. A COMPUTATION; descriptive (realised returns, partly a
second look at test data); no trial. decisions.md 101.

    python -m futuresres.reporting.zp_portfolio [--log]

Per trading day (dates both strategies have, 2013-2026): Z02's one-MES-by-sign P&L (today's contract value,
$3.07 when held, adverse excursion from ES's daily high/low) plus Z05's 1-MGC P&L (three round trips at
$3.32, adverse excursion from its own minute path). The day's worst point is the SUM of the two legs'
worst points (conservative - as if both lows coincided). A unit = 1 MES + 1 MGC.

Reported, against A03's zero-edge solved policy (P(>=1 payout in 84 days) 61%, mean net +$675):
  single   an account started on every date, walked forward (evaluation, then funded)
  seq84    back-to-back $80 attempts for 84 trading days from every 5th start date
for the portfolio and for each edge alone, at 1 and 2 units.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.z_firms as zf

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "zp_portfolio.json"
OUT_MD = ROOT / "reports" / "zp_portfolio.md"
SPEC = zf.SPECS["Tradeify Select Daily (user's terms)"]
START = 50_000.0


def legs():
    from futuresres.signals import z02_trial as z2
    from futuresres.signals import z05_trial as z5
    d2, r_sp, r_ty, price, lo, hi = z2._data()
    held = z2._held(d2, r_sp, r_ty)
    pre = d2 <= np.datetime64("2023-03-17")
    K = 1.0 / float(np.median(np.abs(held[pre & (held != 0)])))
    ct = z2._contracts(held, K, "sign_1")
    notional = float(price[np.isfinite(price)][-1]) * 5.0
    c2 = ct * notional * r_sp - np.abs(ct) * 3.07
    l2 = np.minimum(np.where(ct > 0, ct * notional * lo, -ct * notional * hi) - np.abs(ct) * 3.07, c2)
    d5, rn1, rd, rn2, pnl5, low5, _ = z5._data()
    c5 = pnl5 - 3 * 3.32
    l5 = np.minimum(low5 - 3 * 3.32, c5)
    dates = np.intersect1d(d2, d5)
    i2, i5 = np.searchsorted(d2, dates), np.searchsorted(d5, dates)
    return dates, {"Z02": (c2[i2], l2[i2]), "Z05": (c5[i5], l5[i5])}


def _single(c, l, room=300):
    """An account started on every date, in real order: evaluation then funded. Returns summary dict."""
    S = len(c); starts = np.arange(0, S - room); A = len(starts)
    eq = np.full(A, START); pk = eq.copy(); best = np.zeros(A); state = np.zeros(A, int); days = np.zeros(A, int)
    passday = np.full(A, -1)
    for k in range(S):
        act = np.flatnonzero(state == 0)
        if not len(act):
            break
        idx = starts[act] + k
        ok_i = idx < S
        state[act[~ok_i]] = 2
        act, idx = act[ok_i], idx[ok_i]
        if not len(act):
            break
        ne, pnl, br, npk = zf._day(eq[act], pk[act], l[idx, None], c[idx, None], SPEC["dd"], None, None, None,
                                   SPEC["eval_daily"], SPEC["breach"], 1.0)
        eq[act] = ne; pk[act] = npk; days[act] += 1; best[act] = np.maximum(best[act], pnl)
        prof = ne - START
        ok = (~br) & (prof >= SPEC["target"]) & (best[act] <= SPEC["eval_consistency"] * prof)
        state[act[br]] = -1; state[act[ok]] = 1; passday[act[ok]] = idx[ok]
    passed = np.flatnonzero(state == 1)
    feq = np.full(len(passed), START); fpk = feq.copy(); npay = np.zeros(len(passed), int)
    paid = np.zeros(len(passed)); first = np.full(len(passed), -1); alive = np.ones(len(passed), bool)
    for k in range(504):
        act = np.flatnonzero(alive)
        if not len(act):
            break
        idx = passday[passed[act]] + 1 + k
        ok_i = idx < S
        alive[act[~ok_i]] = False
        act, idx = act[ok_i], idx[ok_i]
        if not len(act):
            break
        ne, _, br, npk = zf._day(feq[act], fpk[act], l[idx, None], c[idx, None], SPEC["dd"], None,
                                 SPEC["f_lock_trigger"], SPEC["f_lock_level"], SPEC["f_daily"], SPEC["breach"], 1.0)
        feq[act] = ne; fpk[act] = npk; alive[act[br]] = False
        live = act[~br]
        amt = np.maximum(feq[live] - (START + 2000), 0.0)
        amt = np.where(npay[live] >= 3, amt, np.minimum(amt, 1250.0))
        got = amt > 0
        paid[live] += 0.9 * amt
        newly = live[got & (first[live] < 0)]
        first[newly] = (passday[passed[newly]] - starts[passed[newly]]) + 1 + k + 1
        feq[live] -= amt; npay[live] += got
    net = np.full(A, -80.0); net[passed] += paid
    pay84 = np.zeros(A, bool); pay84[passed] = (first > 0) & (first <= 84)
    return {"starts": int(A), "p_pass": float((state == 1).mean()), "p_payout_84": float(pay84.mean()),
            "ev_2y": float(net.mean()), "days_to_pass_median": float(np.median(days[state == 1])) if (state == 1).any() else None}


def _seq(c, l, window=84, step=5):
    S = len(c); starts = np.arange(0, S - window, step); A = len(starts)
    phase = np.zeros(A, int); eq = np.full(A, START); pk = eq.copy(); best = np.zeros(A); npay = np.zeros(A, int)
    fees = np.full(A, 80.0); paid = np.zeros(A); first = np.full(A, -1)
    for d in range(window):
        idx = starts + d
        lock_t = np.where(phase == 1, SPEC["f_lock_trigger"], 1e18)
        # evaluation and funded floors differ: compute both and pick per account
        ne_e, pnl_e, br_e, pk_e = zf._day(eq, pk, l[idx, None], c[idx, None], SPEC["dd"], None, None, None,
                                          SPEC["eval_daily"], SPEC["breach"], 1.0)
        ne_f, pnl_f, br_f, pk_f = zf._day(eq, pk, l[idx, None], c[idx, None], SPEC["dd"], None,
                                          SPEC["f_lock_trigger"], SPEC["f_lock_level"], SPEC["f_daily"], SPEC["breach"], 1.0)
        ev = phase == 0
        ne = np.where(ev, ne_e, ne_f); pnl = np.where(ev, pnl_e, pnl_f); br = np.where(ev, br_e, br_f)
        pk = np.where(ev, pk_e, pk_f); eq = ne
        best = np.where(ev, np.maximum(best, pnl), best)
        prof = eq - START
        ok = ev & ~br & (prof >= SPEC["target"]) & (best <= SPEC["eval_consistency"] * prof)
        amt = np.where(~ev & ~br, np.maximum(eq - (START + 2000), 0.0), 0.0)
        amt = np.where(npay >= 3, amt, np.minimum(amt, 1250.0))
        paid += 0.9 * amt; first = np.where((amt > 0) & (first < 0), d + 1, first)
        eq -= amt; npay += amt > 0
        reset = br | ok
        phase = np.where(ok, 1, np.where(br, 0, phase))
        eq = np.where(reset, START, eq); pk = np.where(reset, START, pk)
        best = np.where(reset, 0.0, best); npay = np.where(reset, 0, npay)
        fees += np.where(br & (d + 1 < window), 80.0, 0.0)
    net = paid - fees
    return {"windows": int(A), "p_any_payout": float((first > 0).mean()), "mean_net": float(net.mean()),
            "p_net_positive": float((net > 0).mean()), "mean_fees": float(fees.mean()),
            "net_p10_p50_p90": [float(x) for x in np.quantile(net, [0.1, 0.5, 0.9])]}


def run() -> dict:
    dates, L = legs()
    combos = {"Z02 alone": ["Z02"], "Z05 alone": ["Z05"], "Z02 + Z05": ["Z02", "Z05"]}
    out = {"dates": [str(dates[0]), str(dates[-1]), int(len(dates))], "rows": {}}
    for name, parts in combos.items():
        c1 = sum(L[p][0] for p in parts); l1 = sum(L[p][1] for p in parts)
        sh = float(c1.mean() / c1.std() * math.sqrt(252))
        for units in (1, 2):
            c, l = c1 * units, l1 * units
            r = {"realised_sharpe": sh, "daily_sigma": float(c.std()), "single": _single(c, l), "seq84": _seq(c, l)}
            out["rows"][f"{name} x{units}"] = r
            s, q = r["single"], r["seq84"]
            print(f"{name:10} x{units}: Sharpe {sh:+.2f} sigma ${c.std():.0f} | single P(pass) {s['p_pass']:.0%} "
                  f"EV {s['ev_2y']:+.0f} | 4-month: P(payout) {q['p_any_payout']:.0%} net {q['mean_net']:+.0f} "
                  f"P(net>0) {q['p_net_positive']:.0%}", flush=True)
    return out


def render(r: dict) -> str:
    w = ["# The edge portfolio (Z02 + Z05) in one Tradeify account — real history replayed", "",
         f"Generated by `python -m futuresres.reporting.zp_portfolio`. {r['dates'][2]} trading days, {r['dates'][0]} → "
         f"{r['dates'][1]}. Realised returns (descriptive). `decisions.md` §101.", "",
         "| strategy | realised Sharpe | daily $σ | one account: P(pass) | one account: EV per $80 | "
         "4 months back-to-back: P(≥1 payout) | mean net | P(net > 0) | net 10/50/90 |", "|---|---|---|---|---|---|---|---|---|"]
    for k, v in r["rows"].items():
        s, q = v["single"], v["seq84"]
        p = q["net_p10_p50_p90"]
        w.append(f"| {k} | {v['realised_sharpe']:+.2f} | {v['daily_sigma']:,.0f} | {s['p_pass']:.0%} | {s['ev_2y']:+,.0f} | "
                 f"{q['p_any_payout']:.0%} | {q['mean_net']:+,.0f} | {q['p_net_positive']:.0%} | "
                 f"{p[0]:+,.0f} / {p[1]:+,.0f} / {p[2]:+,.0f} |")
    w += ["", "Reference — A03, zero-edge solved staking on 2 MNQ, real history: P(≥1 payout in 4 months) 61%, "
          "mean net +$675, P(net > 0) 45%.", ""]
    return "\n".join(w)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--log", action="store_true")
    a = ap.parse_args(argv)
    r = json.loads(OUT.read_text()) if (a.log and OUT.exists()) else run()
    OUT.write_text(json.dumps(r, indent=1) + "\n"); OUT_MD.write_text(render(r))
    if a.log:
        from futuresres.stats.trials import Trial, TrialLog
        log = TrialLog(ROOT / "measurements.jsonl")
        rec = log.append(Trial(trial_id=log.next_id("m"), hypothesis_id="Z-portfolio", symbol="MES+MGC",
                               date_range=(r["dates"][0], r["dates"][1]), status="completed",
                               params={"kind": "edge_portfolio_replay", **r},
                               note="kind=computation; NOT a trial. Z02 + Z05 in one Tradeify account, real history. decisions.md 101."))
        print("logged", rec["trial_id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())

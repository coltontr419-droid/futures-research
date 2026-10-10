"""A04 - route 1: the solved staking policy run as a PORTFOLIO of parallel Tradeify accounts, payouts
reinvested, across lanes chosen to move independently. A COMPUTATION; zero edge; no trial. decisions.md 94.

    python -m futuresres.reporting.a04_portfolio --lanes        # each lane alone, real history in order
    python -m futuresres.reporting.a04_portfolio --portfolio    # budgets x account limits, 12 months
    python -m futuresres.reporting.a04_portfolio --log

LANES (one instrument-session each; contracts set so a lane's daily swing is close to 2 MNQ in New York,
the size A03 found best, so the solved $ brackets resolve inside the session):
  MNQ_NY   MNQ 09:30-16:00        MNQ_ASIA MNQ 19:00-03:00
  MGC_LON  MGC 03:00-11:30        MGC_PM   MGC 12:00-16:00
Sessions are PAIRED BY DATE (dates both instruments have complete) and walked IN REAL ORDER, so the
lanes' true co-movement - including stress days when everything moves - is kept. Drift removed per era.

THE PORTFOLIO: a bankroll starts at B; up to M accounts run at once, slot k on lane k mod 4; an empty
slot buys a new $80 evaluation when the bankroll covers it; payouts (90%) go to the bankroll. Each account
plays A01's solved policy (evaluation: max P(pass); funded: max expected dollars). Every start date
whose 12 months fit is replayed (every 5th date). Tradeify Select Daily as the user confirmed.
"""

from __future__ import annotations

import argparse
import gc
import io
import contextlib
import json
import math
import sys
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.a01_game as g
import futuresres.reporting.y01_structure_ev as y
import futuresres.reporting.y03_sessions as s3
from futuresres.reporting.a02_real import _bracket_day

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "a04_portfolio.json"
OUT_MD = ROOT / "reports" / "a04_portfolio.md"
START = 50_000.0
FEE = 80.0
LANES = {   # name: (product, window minutes after 18:00 ET)
    "MNQ_NY": ("MNQ", (930, 1320)), "MNQ_ASIA": ("MNQ", (60, 540)),
    "MGC_LON": ("MGC", (540, 1050)), "MGC_PM": ("MGC", (1080, 1320)),
}
TARGET_SIGMA = 1400.0          # ~ 2 MNQ in New York post-2021
_CACHE: dict = {}


def build_lanes() -> dict:
    """$ paths per lane on the dates BOTH products have complete, contracts fixed from the lane's own
    post-2021 daily swing. Costs are charged in the simulation, not in the paths."""
    if _CACHE:
        return _CACHE
    warnings.filterwarnings("ignore")
    per = {}
    for prod in ("MNQ", "MGC"):
        spec = s3.PRODUCTS[prod]
        y.SERIES = y.ROOT / "data" / "continuous" / f"{spec['series']}.parquet"
        y.MULT = spec["mult"]
        dates, H, L, C, notional = y.load_sessions()
        per[prod] = {"dates": dates, "notional": notional, "rt": spec["rt"], "lanes": {}}
        for name, (p, win) in LANES.items():
            if p != prod:
                continue
            y.WINDOWS[name] = win
            eras = []
            for m in (dates < y.ERA, dates >= y.ERA):
                h, l, c, _ = y.window_paths(H[m], L[m], C[m], name, None)
                eras.append((h * notional, l * notional, c * notional))
            h = np.concatenate([e[0] for e in eras]); l = np.concatenate([e[1] for e in eras])
            c = np.concatenate([e[2] for e in eras])
            post = dates >= y.ERA
            n = max(1, int(round(TARGET_SIGMA / float(c[post, -1].std()))))
            per[prod]["lanes"][name] = (h.astype(np.float32), l.astype(np.float32), c.astype(np.float32), n)
        del H, L, C
        gc.collect()
    common = np.intersect1d(per["MNQ"]["dates"], per["MGC"]["dates"])
    out = {"dates": common, "lanes": {}}
    for prod in ("MNQ", "MGC"):
        idx = np.searchsorted(per[prod]["dates"], common)
        for name, (h, l, c, n) in per[prod]["lanes"].items():
            out["lanes"][name] = {"h": h[idx] * n, "l": l[idx] * n, "c": c[idx] * n, "contracts": n,
                                  "cost": per[prod]["rt"] * n, "product": prod}
    _CACHE.update(out)
    return out


def _policies():
    if "eval" not in g.POLICY:
        warnings.filterwarnings("ignore")
        with contextlib.redirect_stdout(io.StringIO()):
            g.solve_all(21, keep_policy_at=21)
            g.solve_funded(21, "dollars", keep_policy_at=21)
    return g.POLICY["eval"], g.POLICY["funded"]


def _step(phase, eq, pk, best, npay, lane_path, day_idx, cost, pe, pf):
    """One day for a set of accounts on ONE lane. Returns pnl, breached, passed, payout amount."""
    h, l, c = lane_path
    ev = phase == 0
    b_e = np.clip(np.rint((eq - START) / 100).astype(int), g.B_MIN, g.B_MAX)
    pk_e = np.maximum(np.clip(np.rint((pk - START) / 100).astype(int), 0, g.B_MAX), np.maximum(b_e, 0))
    bd_e = np.clip(np.rint(best / 100).astype(int), 0, g.BD_MAX)
    b_f = np.clip(np.rint((eq - START) / 100).astype(int), g.F_BMIN, g.F_BMAX)
    pk_f = np.maximum(np.clip(np.rint((pk - START) / 100).astype(int), 0, g.BUFFER), np.clip(b_f, 0, g.BUFFER))
    a = np.where(ev, pe[b_e - g.B_MIN, pk_e, bd_e], pf[b_f - g.F_BMIN, pk_f, np.minimum(npay, g.LIVE_AFTER)])
    W = (a // 100) * 100.0; L = (a % 100) * 100.0
    floor = np.where(ev, pk - 2000, np.where(pk >= START + 2000, START, pk - 2000))
    L = np.minimum(L, np.maximum(eq - floor - 1, 1))
    trade = a > 0
    pnl, _, _ = _bracket_day(h[day_idx], l[day_idx], c[day_idx], np.where(trade, W + cost, 1e12),
                             np.where(trade, np.maximum(L - cost, 1.0), 1e12))
    pnl = np.where(trade, pnl - cost, 0.0)
    return pnl, floor


def lanes_alone(window: int = 84) -> dict:
    """Each lane alone, A03's back-to-back test: real history in order from every 5th start date."""
    pe, pf = _policies()
    lanes = build_lanes()
    D = len(lanes["dates"])
    starts = np.arange(0, D - window, 5)
    out = {}
    for name, ln in lanes["lanes"].items():
        A = len(starts)
        phase = np.zeros(A, int); eq = np.full(A, START); pk = eq.copy(); best = np.zeros(A)
        npay = np.zeros(A, int); fees = np.full(A, FEE); paid = np.zeros(A); first = np.full(A, -1)
        for d in range(window):
            pnl, floor = _step(phase, eq, pk, best, npay, (ln["h"], ln["l"], ln["c"]), starts + d,
                               ln["cost"], pe, pf)
            eq = eq + pnl; br = eq <= floor; pk = np.maximum(pk, eq)
            best = np.where(phase == 0, np.maximum(best, pnl), best)
            ok = (phase == 0) & ~br & (eq - START >= 3000) & (best <= 0.4 * (eq - START))
            amt = np.where((phase == 1) & ~br, np.maximum(eq - (START + 2000), 0.0), 0.0)
            amt = np.where(npay >= 3, amt, np.minimum(amt, 1250.0))
            paid += 0.9 * amt; first = np.where((amt > 0) & (first < 0), d + 1, first)
            eq -= amt; npay += amt > 0
            reset = br | ok
            phase = np.where(ok, 1, np.where(br, 0, phase))
            eq = np.where(reset, START, eq); pk = np.where(reset, START, pk)
            best = np.where(reset, 0.0, best); npay = np.where(reset, 0, npay)
            fees += np.where(br & (d + 1 < window), FEE, 0.0)
        net = paid - fees
        out[name] = {"contracts": ln["contracts"], "p_any_payout_84": float((first > 0).mean()),
                     "mean_net_84": float(net.mean()), "p_net_positive": float((net > 0).mean()),
                     "mean_fees": float(fees.mean())}
        print(name, out[name], flush=True)
    # daily P&L correlation between lanes for a held 1-contract-equivalent position (path closes)
    names = list(lanes["lanes"])
    C = np.corrcoef(np.vstack([lanes["lanes"][n]["c"][:, -1] for n in names]))
    out["_corr"] = {f"{a}~{b}": float(C[i, j]) for i, a in enumerate(names) for j, b in enumerate(names) if j > i}
    print("daily close correlations:", out["_corr"])
    return out


def portfolio(budget: float, max_slots: int, months: int = 12, step: int = 5) -> dict:
    """Replay real history from every `step`-th start date; bankroll and slots per trader, vectorised."""
    pe, pf = _policies()
    lanes = build_lanes()
    names = list(lanes["lanes"])
    D = len(lanes["dates"])
    T = months * 21
    starts = np.arange(0, D - T, step)
    A, K = len(starts), max_slots
    lane_of = np.arange(K) % len(names)
    active = np.zeros((A, K), bool); phase = np.zeros((A, K), int)
    eq = np.full((A, K), START); pk = eq.copy(); best = np.zeros((A, K)); npay = np.zeros((A, K), int)
    bank = np.full(A, float(budget)); paid_total = np.zeros(A); fees_total = np.zeros(A)
    monthly = []
    busted = np.zeros(A, bool)
    for d in range(T):
        # fill empty slots while the bankroll covers a fee
        for k in range(K):
            can = ~active[:, k] & (bank >= FEE)
            bank[can] -= FEE; fees_total[can] += FEE
            active[can, k] = True; phase[can, k] = 0
            eq[can, k] = START; pk[can, k] = START; best[can, k] = 0.0; npay[can, k] = 0
        for k in range(K):
            ln = lanes["lanes"][names[lane_of[k]]]
            on = active[:, k]
            if not on.any():
                continue
            ii = np.flatnonzero(on)
            pnl, floor = _step(phase[ii, k], eq[ii, k], pk[ii, k], best[ii, k], npay[ii, k],
                               (ln["h"], ln["l"], ln["c"]), starts[ii] + d, ln["cost"], pe, pf)
            e = eq[ii, k] + pnl; br = e <= floor; p = np.maximum(pk[ii, k], e)
            bst = np.where(phase[ii, k] == 0, np.maximum(best[ii, k], pnl), best[ii, k])
            ok = (phase[ii, k] == 0) & ~br & (e - START >= 3000) & (bst <= 0.4 * (e - START))
            amt = np.where((phase[ii, k] == 1) & ~br, np.maximum(e - (START + 2000), 0.0), 0.0)
            amt = np.where(npay[ii, k] >= 3, amt, np.minimum(amt, 1250.0))
            bank[ii] += 0.9 * amt; paid_total[ii] += 0.9 * amt
            e -= amt
            np_ = npay[ii, k] + (amt > 0)
            ph = np.where(ok, 1, phase[ii, k])
            # a pass opens a fresh funded account in the same slot (no new fee); a breach frees the slot
            e = np.where(ok, START, e); p = np.where(ok, START, p); bst = np.where(ok, 0.0, bst)
            np_ = np.where(ok, 0, np_)
            eq[ii, k], pk[ii, k], best[ii, k], npay[ii, k], phase[ii, k] = e, p, bst, np_, ph
            active[ii[br], k] = False
        busted |= (bank < FEE) & ~active.any(1)
        if (d + 1) % 21 == 0:
            net = bank + 0.0 - budget
            monthly.append({"month": (d + 1) // 21, "bank_p10_p50_p90": [float(x) for x in np.quantile(bank, [0.1, 0.5, 0.9])],
                            "net_mean": float(net.mean()), "p_bank_above_start": float((bank > budget).mean()),
                            "p_busted": float(busted.mean()), "paid_mean_cum": float(paid_total.mean()),
                            "active_accounts_mean": float(active.sum(1).mean())})
    return {"budget": budget, "max_slots": max_slots, "start_dates": int(A), "monthly": monthly,
            "fees_mean": float(fees_total.mean()), "paid_mean": float(paid_total.mean())}


def render(res: dict) -> str:
    w = ["# A04 — the solved policy as a portfolio of parallel Tradeify accounts", "",
         "Generated by `python -m futuresres.reporting.a04_portfolio`. Real history replayed in order, lanes "
         "paired by date, drift removed, payouts reinvested. Zero edge; a computation, no trial. `decisions.md` §94.", ""]
    if "lanes" in res:
        w += ["## Each lane alone (A03's test: back-to-back, 84 days)", "",
              "| lane | contracts | P(≥1 payout in 84 days) | mean net | P(net > 0) |", "|---|---|---|---|---|"]
        for k, v in res["lanes"].items():
            if k.startswith("_"):
                continue
            w.append(f"| {k} | {v['contracts']} | {v['p_any_payout_84']:.0%} | {v['mean_net_84']:+,.0f} | {v['p_net_positive']:.0%} |")
        w += ["", "Daily correlations between lanes: " + ", ".join(f"{k} {v:+.2f}" for k, v in res["lanes"]["_corr"].items()), ""]
    for key, r in res.get("portfolio", {}).items():
        w += [f"## Budget ${r['budget']:,.0f}, up to {r['max_slots']} accounts at once ({r['start_dates']} start dates)", "",
              "| month | bankroll 10th / median / 90th | mean net | P(bankroll > start) | P(busted) | accounts running |",
              "|---|---|---|---|---|---|"]
        for m in r["monthly"]:
            if m["month"] in (1, 2, 3, 4, 6, 9, 12):
                q = m["bank_p10_p50_p90"]
                w.append(f"| {m['month']} | ${q[0]:,.0f} / ${q[1]:,.0f} / ${q[2]:,.0f} | {m['net_mean']:+,.0f} | "
                         f"{m['p_bank_above_start']:.0%} | {m['p_busted']:.0%} | {m['active_accounts_mean']:.1f} |")
        w.append("")
    return "\n".join(w)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lanes", action="store_true"); ap.add_argument("--portfolio", action="store_true")
    ap.add_argument("--log", action="store_true")
    a = ap.parse_args(argv)
    res = json.loads(OUT.read_text()) if OUT.exists() else {}
    if a.lanes:
        res["lanes"] = lanes_alone()
    if a.portfolio:
        res["portfolio"] = {}
        for budget, slots in ((800, 4), (800, 8), (1600, 8), (1600, 12)):
            r = portfolio(budget, slots)
            res["portfolio"][f"{budget}_{slots}"] = r
            m4, m12 = r["monthly"][3], r["monthly"][-1]
            print(f"budget {budget} slots {slots}: month 4 median bank {m4['bank_p10_p50_p90'][1]:.0f} "
                  f"P>start {m4['p_bank_above_start']:.0%} busted {m4['p_busted']:.0%} | month 12 median "
                  f"{m12['bank_p10_p50_p90'][1]:.0f} P>start {m12['p_bank_above_start']:.0%} busted {m12['p_busted']:.0%}",
                  flush=True)
    OUT.write_text(json.dumps(res, indent=1, default=float) + "\n")
    OUT_MD.write_text(render(res))
    if a.log:
        from futuresres.stats.trials import Trial, TrialLog
        log = TrialLog(ROOT / "measurements.jsonl")
        rec = log.append(Trial(trial_id=log.next_id("m"), hypothesis_id="A-series", symbol="MNQ+MGC",
                               date_range=("2016-01-27", "2026-08-27"), status="completed",
                               params={"kind": "portfolio_route1", **res},
                               note="kind=computation; NOT a trial. A04 portfolio of parallel accounts, zero edge. decisions.md 94."))
        print("logged", rec["trial_id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())

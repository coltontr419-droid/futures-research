"""A02 - A01's solved staking policy executed on REAL MNQ minute paths (drift removed).

A COMPUTATION; no market claim, no trial. decisions.md 93.

    python -m futuresres.reporting.a02_real [--contracts 5] [--log]

Each day the policy table (A01: evaluation solved for P(pass within 21 days); funded solved for E[$ paid
within 21 days]) maps the account's state to a bracket +W / -L in dollars. Executed on a resampled real
09:30-16:00 MNQ session, drift removed, with N contracts: take profit when the running P&L reaches +W,
stop at -L (capped at the distance to the floor and at the $1,000 daily limit); a minute that touches
both counts as the STOP (conservative); neither by 16:00 -> exit at the close. Cost N x $2.32 per day
traded; stop fills at the bar's low if it gaps through. Tradeify Select Daily rules as the user confirmed.
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.a01_game as g
import futuresres.reporting.z_firms as zf

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "a02_real.json"
HORIZON, TOTAL = 84, 504
START = 50_000.0


def _bracket_day(h, l, c, W, L):
    """Per account: realised P&L of a bracket on one session's $ path (per-account W, L arrays)."""
    A, T = c.shape
    hitW = h >= W[:, None]
    hitL = l <= -L[:, None]
    big = T + 1
    tw = np.where(hitW.any(1), hitW.argmax(1), big)
    tl = np.where(hitL.any(1), hitL.argmax(1), big)
    rows = np.arange(A)
    out = c[:, -1].copy()
    stop = (tl < big) & (tl <= tw)
    take = (tw < big) & ~stop
    out[stop] = np.minimum(-L, l[rows, np.minimum(tl, T - 1)])[stop]   # gap-through fills at the bar low
    out[take] = W[take]
    return out, stop, take


_PATHS = {}


def run(contracts: int = 5, accounts: int = 8000, seed: int = 93) -> dict:
    warnings.filterwarnings("ignore")
    import io, contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        g.solve_all(21, keep_policy_at=21)
        g.solve_funded(21, "dollars", keep_policy_at=21)
    pe, pf = g.POLICY["eval"], g.POLICY["funded"]
    if not _PATHS:                                                   # loaded once (the 2.7 GB machine)
        _PATHS["p"] = zf.strategy_paths(("MNQ_RTH_0",))["MNQ_RTH_0"]
    h1, l1, c1 = _PATHS["p"]                                         # 1 MNQ, $; cost already in l, c
    rt1 = 2.32
    # rebuild per-contract $ paths without the per-contract cost, then scale to N contracts
    h = h1 * np.float32(contracts); l = (l1 + np.float32(rt1)) * np.float32(contracts)
    c = (c1 + np.float32(rt1)) * np.float32(contracts)
    cost = rt1 * contracts
    S = len(c)
    rng = np.random.default_rng(seed)
    A = accounts
    eq = np.full(A, START); pk = eq.copy(); best = np.zeros(A); state = np.zeros(A, int)
    pass_day = np.full(A, -1); days = np.zeros(A, int)
    feq = np.full(A, START); fpk = feq.copy(); npay = np.zeros(A, int); paid = np.zeros(A); paid84 = np.zeros(A)
    first = np.full(A, -1); outcomes = {"take": 0, "stop": 0, "time": 0}
    for d in range(TOTAL):
        ev_ = np.flatnonzero(state == 0)
        if len(ev_):
            b = np.clip(np.rint((eq[ev_] - START) / 100).astype(int), g.B_MIN, g.B_MAX)
            pkk = np.clip(np.rint((pk[ev_] - START) / 100).astype(int), 0, g.B_MAX)
            pkk = np.maximum(pkk, np.maximum(b, 0))                       # rounding can put pk below b
            bd = np.clip(np.rint(best[ev_] / 100).astype(int), 0, g.BD_MAX)
            a = pe[b - g.B_MIN, pkk, bd]
            W = (a // 100) * 100.0; L = (a % 100) * 100.0
            trade = a > 0
            floor = pk[ev_] - 2000
            L = np.minimum(L, np.maximum(eq[ev_] - floor - 1, 1))
            idx = rng.integers(0, S, len(ev_))
            # orders net of the day's cost, so the NET result lands on the solver's grid (decisions.md 93)
            pnl, st, tk = _bracket_day(h[idx], l[idx], c[idx], np.where(trade, W + cost, 1e12),
                                       np.where(trade, np.maximum(L - cost, 1.0), 1e12))
            pnl = np.where(trade, pnl - cost, 0.0)
            outcomes["take"] += int((tk & trade).sum()); outcomes["stop"] += int((st & trade).sum())
            outcomes["time"] += int((~tk & ~st & trade).sum())
            ne = eq[ev_] + pnl
            br = ne <= floor
            eq[ev_] = ne; days[ev_] += 1
            pk[ev_] = np.maximum(pk[ev_], ne)
            best[ev_] = np.maximum(best[ev_], pnl)
            prof = ne - START
            ok = (~br) & (prof >= 3000) & (best[ev_] <= 0.40 * prof)
            state[ev_[br]] = -1
            state[ev_[ok]] = 1; pass_day[ev_[ok]] = d + 1
        fu = np.flatnonzero((state == 1) & (pass_day <= d))
        if len(fu):
            b = np.clip(np.rint((feq[fu] - START) / 100).astype(int), g.F_BMIN, g.F_BMAX)
            pkk = np.clip(np.rint((fpk[fu] - START) / 100).astype(int), 0, g.BUFFER)
            pkk = np.maximum(pkk, np.clip(b, 0, g.BUFFER))
            n = np.minimum(npay[fu], g.LIVE_AFTER)
            a = pf[b - g.F_BMIN, pkk, n]
            W = (a // 100) * 100.0; L = (a % 100) * 100.0
            trade = a > 0
            floor = np.where(fpk[fu] >= START + 2000, START, fpk[fu] - 2000)
            L = np.minimum(L, np.maximum(feq[fu] - floor - 1, 1))
            idx = rng.integers(0, S, len(fu))
            pnl, st, tk = _bracket_day(h[idx], l[idx], c[idx], np.where(trade, W + cost, 1e12),
                                       np.where(trade, np.maximum(L - cost, 1.0), 1e12))
            pnl = np.where(trade, pnl - cost, 0.0)
            ne = feq[fu] + pnl
            br = ne <= floor
            feq[fu] = ne; fpk[fu] = np.maximum(fpk[fu], ne)
            state[fu[br]] = -1
            live = fu[~br]
            amt = np.maximum(feq[live] - (START + 2000), 0.0)
            amt = np.where(npay[live] >= 3, amt, np.minimum(amt, 1250.0))
            got = amt > 0
            w = live[got]
            paid[w] += 0.9 * amt[got]
            if d < HORIZON:
                paid84[w] += 0.9 * amt[got]
            first[w[first[w] < 0]] = d + 1
            feq[w] -= amt[got]; npay[w] += 1
        if not (state >= 0).any():
            break
    tot = sum(outcomes.values())
    return {"contracts": contracts, "p_pass": float((pass_day > 0).mean()),
            "days_to_pass_median": float(np.median(pass_day[pass_day > 0])) if (pass_day > 0).any() else None,
            "p_payout_84": float(((first > 0) & (first <= HORIZON)).mean()),
            "days_to_first_payout_median": float(np.median(first[first > 0])) if (first > 0).any() else None,
            "dollars_84": float(paid84.mean()), "ev_84": float(paid84.mean() - 80),
            "ev_2y": float(paid.mean() - 80),
            "bracket_outcomes": {k: v / max(tot, 1) for k, v in outcomes.items()}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--contracts", type=int, nargs="+", default=[3, 5, 8])
    ap.add_argument("--log", action="store_true")
    a = ap.parse_args(argv)
    res = {}
    for n in a.contracts:
        r = run(n)
        res[n] = r
        print(json.dumps(r), flush=True)
    OUT.write_text(json.dumps(res, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())


def sequential(contracts: int = 2, mode: str = "iid", traders: int = 6000, window: int = HORIZON,
               seed: int = 94, fee: float = 80.0, passive: bool = False) -> dict:
    """Back-to-back attempts within `window` trading days: one account at a time; a failed evaluation or
    funded account is replaced by a new $80 evaluation the next day. mode 'iid' resamples real sessions;
    'replay' walks real sessions IN ORDER from every start date (window must fit). Policy as in run()."""
    warnings.filterwarnings("ignore")
    import io, contextlib
    if "eval" not in g.POLICY:
        with contextlib.redirect_stdout(io.StringIO()):
            g.solve_all(21, keep_policy_at=21)
            g.solve_funded(21, "dollars", keep_policy_at=21)
    pe, pf = g.POLICY["eval"], g.POLICY["funded"]
    if not _PATHS:
        _PATHS["p"] = zf.strategy_paths(("MNQ_RTH_0",))["MNQ_RTH_0"]
    h1, l1, c1 = _PATHS["p"]
    rt1 = 2.32
    h = h1 * np.float32(contracts); l = (l1 + np.float32(rt1)) * np.float32(contracts)
    c = (c1 + np.float32(rt1)) * np.float32(contracts)
    cost = rt1 * contracts
    S = len(c)
    rng = np.random.default_rng(seed)
    if mode == "replay":
        starts = np.arange(0, S - window)
        A = len(starts)
    else:
        A = traders
    phase = np.zeros(A, int)                      # 0 eval, 1 funded
    eq = np.full(A, START); pk = eq.copy(); best = np.zeros(A); npay = np.zeros(A, int)
    fees = np.full(A, fee); paid = np.zeros(A); first = np.full(A, -1); attempts = np.ones(A, int)
    for d in range(window):
        idx = (starts + d) if mode == "replay" else rng.integers(0, S, A)
        ev = phase == 0
        fu = ~ev
        b_e = np.clip(np.rint((eq - START) / 100).astype(int), g.B_MIN, g.B_MAX)
        pk_e = np.maximum(np.clip(np.rint((pk - START) / 100).astype(int), 0, g.B_MAX), np.maximum(b_e, 0))
        bd_e = np.clip(np.rint(best / 100).astype(int), 0, g.BD_MAX)
        a_e = pe[b_e - g.B_MIN, pk_e, bd_e]
        b_f = np.clip(np.rint((eq - START) / 100).astype(int), g.F_BMIN, g.F_BMAX)
        pk_f = np.maximum(np.clip(np.rint((pk - START) / 100).astype(int), 0, g.BUFFER), np.clip(b_f, 0, g.BUFFER))
        a_f = pf[b_f - g.F_BMIN, pk_f, np.minimum(npay, g.LIVE_AFTER)]
        a = np.where(ev, a_e, a_f)
        W = (a // 100) * 100.0; L = (a % 100) * 100.0
        if passive:                     # the baseline: hold to 16:00, only the $1,000 soft daily stop
            a = np.ones_like(a); W = np.full(A, 1e9); L = np.full(A, 1000.0)
        floor = np.where(ev, pk - 2000, np.where(pk >= START + 2000, START, pk - 2000))
        L = np.minimum(L, np.maximum(eq - floor - 1, 1))
        trade = a > 0
        pnl, _, _ = _bracket_day(h[idx], l[idx], c[idx], np.where(trade, W + cost, 1e12),
                                 np.where(trade, np.maximum(L - cost, 1.0), 1e12))
        pnl = np.where(trade, pnl - cost, 0.0)
        ne = eq + pnl
        br = ne <= floor
        eq = ne; pk = np.maximum(pk, ne)
        best = np.where(ev, np.maximum(best, pnl), best)
        prof = eq - START
        ok = ev & ~br & (prof >= 3000) & (best <= 0.40 * prof)
        # funded payouts
        amt = np.where(fu & ~br, np.maximum(eq - (START + 2000), 0.0), 0.0)
        amt = np.where(npay >= 3, amt, np.minimum(amt, 1250.0))
        got = amt > 0
        paid += 0.9 * amt
        first = np.where(got & (first < 0), d + 1, first)
        eq -= amt; npay += got
        # transitions: pass -> fresh funded account; any breach -> a new $80 evaluation next day
        reset = br | ok
        new_phase = np.where(ok, 1, np.where(br, 0, phase))
        eq = np.where(reset, START, eq); pk = np.where(reset, START, pk)
        best = np.where(reset, 0.0, best); npay = np.where(reset, 0, npay)
        newly_eval = br & (d + 1 < window)
        fees += np.where(newly_eval, fee, 0.0); attempts += newly_eval
        phase = new_phase
    net = paid - fees
    return {"contracts": contracts, "mode": mode, "passive": passive, "traders": int(A), "window_days": window,
            "p_any_payout": float((first > 0).mean()),
            "median_day_first_payout": float(np.median(first[first > 0])) if (first > 0).any() else None,
            "mean_attempts": float(attempts.mean()), "mean_fees": float(fees.mean()),
            "mean_paid": float(paid.mean()), "mean_net": float(net.mean()),
            "p_net_positive": float((net > 0).mean()),
            "net_p10_p50_p90": [float(x) for x in np.quantile(net, [0.1, 0.5, 0.9])]}

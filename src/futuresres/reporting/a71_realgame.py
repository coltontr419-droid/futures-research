"""A71 - the bracket policy re-solved for the real game (decisions.md 649). No trial.

A23's policy maximises P(pass in 21 days) and E[$ in 21 days] in an endless funded stage. Here, per market (its 1-tick + Tradovate cost
priced into the odds), the RENEWAL game of one account slot: breach -> re-buy ($80) and start again; pass -> funded; funded payouts at
90%; the 3rd payout ends the slot (the move to live) with a terminal value R. And the LIVE game: $0 start, $2,000 trailing drawdown
locking at $0, 80% of withdrawals above $2,000. Both by backward induction over H days, the H-day policy used as a stationary rule.
Replayed in A63's joint simulation (5 x 50K, 3 NKD + 2 FDXM, live rules).

    python -m futuresres.reporting.a71_realgame
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import math
import sys
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.a23_account_sizes as a23
import futuresres.reporting.a63_firms as f
from futuresres.reporting.a60_live import data, summary
from futuresres.reporting.a67_cashpath import launch_paths

ROOT = Path(__file__).resolve().parents[3]
MIX = f.MIXES["5: 3NKD+2FDXM"]
F0 = dict(f.FIRMS["Tradeify Select Daily"], data_month=14.0)
NEG = -1e18


def solve_renewal(s: a23.Spec, c: float, H: int, R: float):
    """(eval policy, eval grid, funded policy (b, pk, N 0..3, 1), funded grid, value at the evaluation's start) for cost c ($ a trade)."""
    cu = c / 100.0
    # evaluation grid (as a23.solve_eval)
    B_MIN, B_MAX = -s.dd, int(s.target * 1.5); BD_MAX = int(math.ceil(s.cons * B_MAX)); nb = B_MAX - B_MIN + 1
    shp = (nb, B_MAX + 1, BD_MAX + 1)
    B, PK, BD = (np.broadcast_to(x, shp) for x in (np.arange(nb)[:, None, None] + B_MIN, np.arange(B_MAX + 1)[None, :, None],
                                                    np.arange(BD_MAX + 1)[None, None, :]))
    evalid = (PK >= np.maximum(B, 0)) & (B > PK - s.dd)
    # funded grid (as a23.solve_funded, withdraw all, no Flex); N = payouts so far 0..2
    BUF = s.f_dd; FMIN, FMAX = -s.f_dd, BUF + max(s.w_set) + 10; nf = FMAX - FMIN + 1
    fshp = (nf, BUF + 1, 3)
    FB = np.broadcast_to((np.arange(nf) + FMIN)[:, None, None], fshp); FP = np.broadcast_to(np.arange(BUF + 1)[None, :, None], fshp)
    FN = np.broadcast_to(np.arange(3)[None, None, :], fshp)
    ffloor = np.where(FP >= BUF, 0, FP - s.f_dd); fvalid = (FB > ffloor) & (FP >= np.minimum(np.maximum(FB, 0), BUF))
    VE = np.zeros(shp); VF = np.zeros(fshp); ae = np.zeros(shp, np.int32); af = np.zeros(fshp, np.int32)

    def f_eod(bb, VFn):
        pkk = np.minimum(np.maximum(FP, np.clip(bb, 0, None)), BUF)
        amt = np.minimum(np.clip(bb - BUF, 0, None), s.f_cap); n2 = FN + (amt > 0)
        cont = VFn[np.clip(bb - amt, FMIN, FMAX) - FMIN, pkk, np.minimum(n2, 2)]
        return amt * 90.0 + np.where(n2 >= 3, R, cont)

    for _ in range(H):
        E0 = VE[0 - B_MIN, 0, 0]; F0v = VF[0 - FMIN, 0, 0]; rebuy = E0 - s.fee
        nE = np.full(shp, NEG); nae = np.zeros(shp, np.int32)
        dist = B - (PK - s.dd)
        for W in s.w_set:
            bw = np.minimum(B + W, B_MAX); pkw = np.maximum(PK, bw); bdw = np.minimum(np.maximum(BD, W), BD_MAX)
            win_pass = (bw >= s.target) & (np.maximum(BD, W) <= s.cons * bw)
            vw = np.where(win_pass, F0v, VE[bw - B_MIN, pkw, bdw])
            for L in s.l_eval:
                Le = np.minimum(L, dist); p = np.clip(Le - cu, 0, None) / (W + Le)
                bl = B - Le; fail = bl <= PK - s.dd
                vl = np.where(fail, rebuy, VE[np.clip(bl, B_MIN, B_MAX) - B_MIN, PK, BD])
                v = p * vw + (1 - p) * vl
                bt = v > nE + 1e-9; nE = np.where(bt, v, nE); nae = np.where(bt, W * 100 + L, nae)
        nF = np.full(fshp, NEG); naf = np.zeros(fshp, np.int32)
        for W in s.w_set:
            rw = f_eod(np.minimum(FB + W, FMAX), VF)
            for L in s.l_funded:
                Le = np.minimum(L, np.maximum(FB - ffloor, 1)); p = np.clip(Le - cu, 0, None) / (W + Le)
                failL = (FB - Le) <= ffloor
                rl = np.where(failL, rebuy, f_eod(np.clip(FB - Le, FMIN, FMAX), VF))
                v = p * rw + (1 - p) * rl
                bt = v > nF + 1e-9; nF = np.where(bt, v, nF); naf = np.where(bt, W * 100 + L, naf)
        VE = np.where(evalid, nE, 0.0); ae = nae; VF = np.where(fvalid, nF, 0.0); af = naf
    pf = np.concatenate([af, af[:, :, 2:3]], axis=2)[..., None]          # N = 3 (never used) copies N = 2; one winning-day slot
    return ae, {"B_MIN": B_MIN, "B_MAX": B_MAX, "BD_MAX": BD_MAX}, pf, {"FMIN": FMIN, "FMAX": FMAX, "BUF": BUF, "WD": 0}, float(VE[0 - B_MIN, 0, 0])


def solve_live(s: a23.Spec, c: float, H: int, room: int = 20, lock: int = 20):
    """Live account: balance b ($100 units from $0), peak 0..lock; floor pk - room until the peak reaches lock, then 0; 80% of all above
    lock withdrawn each day; dead = 0. Returns (policy, grid, value at the start)."""
    cu = c / 100.0; LMIN, LMAX = -room, lock + max(s.w_set) + 10; nl = LMAX - LMIN + 1
    shp = (nl, lock + 1)
    B = np.broadcast_to((np.arange(nl) + LMIN)[:, None], shp); PK = np.broadcast_to(np.arange(lock + 1)[None, :], shp)
    floor = np.where(PK >= lock, 0, PK - room); valid = (B > floor) & (PK >= np.minimum(np.maximum(B, 0), lock))
    V = np.zeros(shp); act = np.zeros(shp, np.int32)

    def eod(bb, Vn):
        pkk = np.minimum(np.maximum(PK, np.clip(bb, 0, None)), lock)
        amt = np.where(pkk >= lock, np.clip(bb - lock, 0, None), 0)
        return amt * 80.0 + Vn[np.clip(bb - amt, LMIN, LMAX) - LMIN, pkk]

    for _ in range(H):
        nV = np.full(shp, NEG); na = np.zeros(shp, np.int32)
        for W in s.w_set:
            rw = eod(np.minimum(B + W, LMAX), V)
            for L in s.l_funded:
                Le = np.minimum(L, np.maximum(B - floor, 1)); p = np.clip(Le - cu, 0, None) / (W + Le)
                rl = np.where((B - Le) <= floor, 0.0, eod(np.clip(B - Le, LMIN, LMAX), V))
                v = p * rw + (1 - p) * rl
                bt = v > nV + 1e-9; nV = np.where(bt, v, nV); na = np.where(bt, W * 100 + L, na)
        V = np.where(valid, nV, 0.0); act = na
    return act, {"LMIN": LMIN, "LMAX": LMAX, "LOCK": lock}, float(V[0 - LMIN, 0])


_CACHE: dict = {}


def _cached(fn, *args):
    if (fn.__name__, args[1:]) not in _CACHE:
        _CACHE[(fn.__name__, args[1:])] = fn(*args)
    return _CACHE[(fn.__name__, args[1:])]


def policies(P, H: int, R, live_solved: bool):
    """Per-market policies for A63 (F['pol'], F['live_pol'])."""
    s = a23.specs()["50K Daily"]; pol, lpol, vals = {}, {}, {}
    for m in sorted(set(MIX)):
        c = float(P[m][3])
        la, lg, vl = _cached(solve_live, s, c, H)
        r = vl if R == "V_live" else float(R)
        pe, ge, pf, gf, v0 = _cached(solve_renewal, s, c, H, r)
        pol[m] = (pe, ge, pf, gf); vals[m] = {"V_live": vl, "R": r, "V_eval_start": v0}
        if live_solved:
            lpol[m] = (la, lg)
    return pol, lpol, vals


def main() -> int:
    warnings.filterwarnings("ignore"); out = {"candidates": {}}
    cp, Pp = data("post"); cq, Pq = data("pre"); P1, Q1 = launch_paths(Pp), launch_paths(Pq)
    st = np.array(cp[: len(cp) - 84]); m24 = np.array([x < dt.date(2025, 1, 1) for x in st]); mall = np.ones(len(st), bool)

    def read(F):
        r = f.simulate(cp, P1, 84, MIX, F); rq = f.simulate(cq, Q1, 84, MIX, F)
        return {"2021-24": summary(r, m24), "2025 starts": summary(r, ~m24), "2021-26": summary(r, mall), "2010-20": summary(rq, np.ones(len(rq["net"]), bool))}

    base = f.simulate(cp, P1, 84, MIX, F0); out["current_2021_24"] = float(base["net"][m24].mean())
    print(f"current policy: 2021-24 {out['current_2021_24']:+,.0f}", flush=True)
    grid = {}
    for H, R, ls in itertools.product((21, 42, 84), (0, 1000, 2000, "V_live"), (False, True)):
        pol, lpol, vals = policies(P1, H, R, ls)
        r = f.simulate(cp, P1, 84, MIX, dict(F0, pol=pol, live_pol=lpol or None))
        k = f"H{H}|R{R}|live {'solved' if ls else 'fixed'}"; grid[k] = (H, R, ls)
        out["candidates"][k] = {"2021-24": float(r["net"][m24].mean()), "values": vals}
        print(f"  {k:28}: 2021-24 {out['candidates'][k]['2021-24']:+8,.0f}  " + "  ".join(f"{m} V_live {v['V_live']:,.0f} V0 {v['V_eval_start']:,.0f}" for m, v in vals.items()), flush=True)
    best = max(out["candidates"], key=lambda k: out["candidates"][k]["2021-24"]); H, R, ls = grid[best]
    pol, lpol, _ = policies(P1, H, R, ls)
    out["chosen"] = {"key": best, **read(dict(F0, pol=pol, live_pol=lpol or None))}; out["current"] = read(F0)
    for lab in ("current", "chosen"):
        x = out[lab]
        print(f"{lab:8} {out['chosen']['key'] if lab == 'chosen' else '':28}: " + " | ".join(
            f"{per} {x[per]['net_mean']:+,.0f} ({x[per]['p_pos']:.0%}, p10 {x[per]['p10']:+,.0f})" for per in ("2021-24", "2025 starts", "2021-26", "2010-20")), flush=True)
    c_, b_ = out["current"], out["chosen"]
    out["adopt"] = bool(b_["2025 starts"]["net_mean"] > c_["2025 starts"]["net_mean"] and b_["2010-20"]["net_mean"] > c_["2010-20"]["net_mean"]
                        and b_["2025 starts"]["p10"] >= c_["2025 starts"]["p10"] - 1000)
    print(f"adopt (decisions.md 649): {out['adopt']}", flush=True)
    (ROOT / "reports" / "a71_realgame.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

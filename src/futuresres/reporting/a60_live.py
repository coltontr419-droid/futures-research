"""A60 - the five-account book under Tradeify's live-account rules (decisions.md 624). No trial.

A joint simulation of the five accounts on their common sessions: each account runs the plan's evaluation / funded game (A23's solved
50K Daily policy, the deployed rules' sides); the book moves to LIVE when one funded account has 3 payouts or the book has 10 payouts
since the last reset; funded accounts with a payout go live, every other account is closed; live accounts start at $0, trail $2,000
until +$2,000 then lock at $0, trade fixed brackets, withdraw above a cushion at 80%; no new evaluations while any live account is open;
when the last live account fails, 20 sessions of cool-off, then five new evaluations and the payout count resets.

    python -m futuresres.reporting.a60_live
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import sys
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.a23_account_sizes as a23
import futuresres.reporting.a27_standalone as a27
import futuresres.reporting.a43_scale as a43
import futuresres.reporting.d10_universe as d10
import futuresres.reporting.d24_shock as sh

ROOT = Path(__file__).resolve().parents[3]
MKTS = ("MNQ", "MGC", "MCL", "NKD", "FDXM")
LIVE_GRID = ((600, 600), (800, 800), (1_000, 1_000), (1_200, 1_000))
CUSHIONS = (2_000.0, 4_000.0)
COOL = 20
LIVE_DD, LIVE_LOCK = 2_000.0, 2_000.0


def data(era: str):
    """Common sessions; per market one-contract $ paths (h, l, c) on those sessions, contracts, round trip."""
    R = a43.masks()
    zs = sh.shocks(d10.series(), "ZN"); nxt = lambda d: d + dt.timedelta(days=1 if d.weekday() < 4 else 3)
    zn_short = {nxt(d) for d, q in zs.items() if q[1] and q[0] < 0}
    rule = {"MNQ": lambda v: v in zn_short, "NKD": R["NKD"], "FDXM": R["FDXM"], "MGC": None, "MCL": None}
    raw = {}
    for m in MKTS:
        (h, l, c), d = a23.market_paths(m, era); dd = [x.astype(object) for x in d]
        if rule[m] is not None:
            h, l, c = a27.flip(h, l, c, np.array([rule[m](v) for v in dd]))
        raw[m] = (h, l, c, {v: i for i, v in enumerate(dd)})
    common = sorted(set.union(*(set(raw[m][3]) for m in MKTS)))          # every session any market traded
    out = {}
    for m in MKTS:
        h, l, c, ix = raw[m]; T = c.shape[1]; n, rt = a23.MARKETS[m]
        H = np.zeros((len(common), T), np.float32); Lo = H.copy(); C = H.copy(); has = np.zeros(len(common), bool)
        for j, v in enumerate(common):
            i = ix.get(v)
            if i is not None:
                H[j], Lo[j], C[j] = h[i] * n, l[i] * n, c[i] * n; has[j] = True
        out[m] = (H, Lo, C, n * rt, has)                 # a market without a session that day sits it out (no trade, no cost)
    return common, out


def simulate(common, P, window: int, live_wl, cushion, live: bool = True) -> dict:
    s = a23.specs()["50K Daily"]; pe, ge, _, pf, gf, _ = a23.policy(s)
    S = len(common); starts = np.arange(0, S - window); A = len(starts)
    START, ddE, ddF = s.start, s.dd * 100.0, s.f_dd * 100.0
    st = {m: {"phase": np.zeros(A, int), "eq": np.full(A, START), "pk": np.full(A, START), "best": np.zeros(A), "npay": np.zeros(A, int),
              "live": np.zeros(A, bool), "leq": np.zeros(A), "lpk": np.zeros(A), "lalive": np.zeros(A, bool)} for m in MKTS}
    mode = np.zeros(A, int); cool = np.zeros(A, int); bookpay = np.zeros(A, int)
    fees = np.full(A, 5 * s.fee); paid_sim = np.zeros(A); paid_live = np.zeros(A); moves = np.zeros(A, int); first_live = np.full(A, -1)
    live_n_at_move = []; cool_days = np.zeros(A, int); closed_n = np.zeros(A, int)
    W_live, L_live = map(float, live_wl)
    for d in range(window):
        idx = starts + d
        # cool-off: count down; at the end, five new evaluations
        cl = mode == 2
        cool_days += cl; cool = np.where(cl, cool - 1, cool)
        restart = cl & (cool <= 0)
        if restart.any():
            mode = np.where(restart, 0, mode); bookpay = np.where(restart, 0, bookpay)
            fees += np.where(restart & (d + 1 < window), 5 * s.fee, 0.0)
            for m in MKTS:
                a_ = st[m]
                for k, v in (("phase", 0), ("eq", START), ("pk", START), ("best", 0.0), ("npay", 0)):
                    a_[k] = np.where(restart, v, a_[k])
        sim = mode == 0; liv = mode == 1
        for m in MKTS:
            h, l, c, cost, has = P[m]; a_ = st[m]; act = has[idx]
            # ---- sim accounts (A23's step, restricted to starts in sim mode)
            ev = a_["phase"] == 0; fu = ~ev; eq, pk, best, npay = a_["eq"], a_["pk"], a_["best"], a_["npay"]
            b_e = np.clip(np.rint((eq - START) / 100).astype(int), ge["B_MIN"], ge["B_MAX"])
            pk_e = np.maximum(np.clip(np.rint((pk - START) / 100).astype(int), 0, ge["B_MAX"]), np.maximum(b_e, 0))
            bd_e = np.clip(np.rint(best / 100).astype(int), 0, ge["BD_MAX"])
            a_e = pe[b_e - ge["B_MIN"], pk_e, bd_e]
            b_f = np.clip(np.rint((eq - START) / 100).astype(int), gf["FMIN"], gf["FMAX"])
            pk_f = np.maximum(np.clip(np.rint((pk - START) / 100).astype(int), 0, gf["BUF"]), np.clip(b_f, 0, gf["BUF"]))
            a_f = pf[b_f - gf["FMIN"], pk_f, np.minimum(npay, s.live_after), np.zeros(A, int)]
            a = np.where(ev, a_e, a_f); W = (a // 100) * 100.0; L = (a % 100) * 100.0
            floor = np.where(ev, pk - ddE, np.where(pk >= START + ddF, START, pk - ddF))
            L = np.minimum(L, np.maximum(eq - floor - 1, 1))
            trade = sim & act & (a > 0) & (eq - floor > cost + 10)
            # ---- live accounts: fixed brackets, stop capped at the floor distance
            lfloor = np.where(a_["lpk"] >= LIVE_LOCK, 0.0, a_["lpk"] - LIVE_DD)
            lact = liv & a_["lalive"]
            Wl = np.full(A, W_live); Ll = np.minimum(np.full(A, L_live), np.maximum(a_["leq"] - lfloor - 1, 1))
            ltrade = lact & act & (a_["leq"] - lfloor > cost + 10)
            WW = np.where(trade, W + cost, np.where(ltrade, Wl + cost, 1e12)); LL = np.where(trade, np.maximum(L - cost, 1.0), np.where(ltrade, np.maximum(Ll - cost, 1.0), 1e12))
            pnl = a23._bracket(h[idx], l[idx], c[idx], WW, LL)
            pnl = np.round(np.where(trade | ltrade, pnl.astype(np.float64) - cost, 0.0), 2)
            # sim bookkeeping
            ne = eq + np.where(trade, pnl, 0.0); br = sim & act & ((ne <= floor) | ~trade)
            eq = np.where(sim, ne, eq); pk = np.where(sim, np.maximum(pk, ne), pk)
            best = np.where(sim & ev, np.maximum(best, pnl), best); prof = eq - START
            ok = sim & ev & ~br & (prof >= s.target * 100 - 0.005) & (best <= s.cons * prof + 0.005)
            amt = np.where(sim & fu & ~br, np.maximum(eq - (START + ddF), 0.0), 0.0)
            amt = np.where(npay >= s.live_after, amt, np.minimum(amt, s.cap_usd))
            got = amt > 0
            paid_sim += 0.9 * amt; eq -= amt; npay = npay + got; bookpay = bookpay + got
            reset = br | ok
            a_["phase"] = np.where(ok, 1, np.where(br, 0, a_["phase"]))
            a_["eq"] = np.where(reset, START, eq); a_["pk"] = np.where(reset, START, pk)
            a_["best"] = np.where(reset, 0.0, best); a_["npay"] = np.where(reset, 0, npay)
            fees += np.where(br & (d + 1 < window), s.fee, 0.0)
            # live bookkeeping
            leq = a_["leq"] + np.where(ltrade, pnl, 0.0); lpk = np.maximum(a_["lpk"], leq)
            lfloor2 = np.where(lpk >= LIVE_LOCK, 0.0, lpk - LIVE_DD)
            dead = lact & act & ((leq <= lfloor2) | ~ltrade)
            a_["lalive"] = a_["lalive"] & ~dead
            wd = np.where(a_["lalive"] & (lpk >= LIVE_LOCK) & (leq > cushion), leq - cushion, 0.0)
            paid_live += 0.8 * wd; leq -= wd
            a_["leq"], a_["lpk"] = leq, lpk
        # ---- move to live at the end of the day
        three = np.zeros(A, bool)
        for m in MKTS:
            three |= (st[m]["phase"] == 1) & (st[m]["npay"] >= 3)
        trig = (mode == 0) & (three | (bookpay >= 10)) & live
        if trig.any():
            elig = {m: trig & (st[m]["phase"] == 1) & (st[m]["npay"] >= 1) for m in MKTS}
            anyone = np.zeros(A, bool)
            for m in MKTS:
                anyone |= elig[m]
            go = trig & anyone
            for m in MKTS:
                e = elig[m] & go
                st[m]["lalive"] = np.where(go, e, st[m]["lalive"]); st[m]["leq"] = np.where(go, 0.0, st[m]["leq"]); st[m]["lpk"] = np.where(go, 0.0, st[m]["lpk"])
                closed_n += go & ~e
            live_n_at_move += [int(sum(elig[m][i] for m in MKTS)) for i in np.where(go)[0]]
            mode = np.where(go, 1, mode); moves += go; first_live = np.where(go & (first_live < 0), d + 1, first_live)
        # ---- all live accounts failed: cool-off
        alive = np.zeros(A, bool)
        for m in MKTS:
            alive |= st[m]["lalive"]
        endl = (mode == 1) & ~alive
        mode = np.where(endl, 2, mode); cool = np.where(endl, COOL, cool)
    net = paid_sim + paid_live - fees
    return {"start": starts, "net": net, "paid_sim": paid_sim, "paid_live": paid_live, "fees": fees, "moves": moves, "first_live": first_live,
            "cool_days": cool_days, "closed": closed_n, "live_at_move": np.array(live_n_at_move), "evals": fees / s.fee}


def summary(r, mask) -> dict:
    x = r["net"][mask]
    return {"runs": int(mask.sum()), "net_mean": float(x.mean()), "net_median": float(np.median(x)), "p_pos": float((x > 0).mean()),
            "p10": float(np.percentile(x, 10)), "worst": float(x.min()), "paid_sim": float(r["paid_sim"][mask].mean()),
            "paid_live": float(r["paid_live"][mask].mean()), "fees": float(r["fees"][mask].mean()), "evals": float(r["evals"][mask].mean()),
            "p_reach_live": float((r["moves"][mask] > 0).mean()), "moves": float(r["moves"][mask].mean()),
            "first_live_day_median": float(np.median(r["first_live"][mask][r["first_live"][mask] > 0])) if (r["first_live"][mask] > 0).any() else None,
            "cool_days": float(r["cool_days"][mask].mean()), "closed_accounts": float(r["closed"][mask].mean())}


def main() -> int:
    warnings.filterwarnings("ignore"); out = {}
    common_p, Pp = data("post"); common_q, Pq = data("pre")
    for window in (84, 252):
        st = np.array(common_p[: len(common_p) - window]); m24 = np.array([x < dt.date(2025, 1, 1) for x in st]); m25 = ~m24; mall = np.ones(len(st), bool)
        res = {(wl, cu): simulate(common_p, Pp, window, wl, cu) for wl, cu in itertools.product(LIVE_GRID, CUSHIONS)}
        best = max(res, key=lambda k: res[k]["net"][m24].mean())
        rq = simulate(common_q, Pq, window, *best); mq = np.ones(len(rq["net"]), bool)
        base = simulate(common_p, Pp, window, *best, live=False); baseq = simulate(common_q, Pq, window, *best, live=False)
        out[window] = {"chosen": {"live_brackets": list(best[0]), "cushion": best[1]},
                       "2025 starts": summary(res[best], m25), "2021-26": summary(res[best], mall), "2010-20": summary(rq, mq),
                       "no_live_rules": {"2025 starts": summary(base, m25), "2021-26": summary(base, mall), "2010-20": summary(baseq, mq)},
                       "grid_2021_24": {f"{k[0]}|{k[1]}": float(v["net"][m24].mean()) for k, v in res.items()},
                       "live_accounts_at_move": {str(k): float(np.mean(res[best]["live_at_move"] == k)) for k in range(1, 6)} if len(res[best]["live_at_move"]) else {}}
        print(f"\n=== horizon {window} sessions; live brackets {best[0]}, cushion ${best[1]:,.0f} (chosen on 2021-24 starts) ===", flush=True)
        for per in ("2025 starts", "2021-26", "2010-20"):
            x = out[window][per]
            b = out[window]["no_live_rules"][per]
            print(f"{per:12}: WITHOUT live rules net {b['net_mean']:+8,.0f} (P>0 {b['p_pos']:.0%}, p10 {b['p10']:+,.0f}) | WITH:", flush=True)
            print(f"{per:12}: net {x['net_mean']:+8,.0f} (median {x['net_median']:+,.0f}, P>0 {x['p_pos']:.0%}, p10 {x['p10']:+,.0f}, worst {x['worst']:+,.0f}) | "
                  f"sim paid ${x['paid_sim']:,.0f}, live paid ${x['paid_live']:,.0f}, fees ${x['fees']:,.0f} ({x['evals']:.0f} evals) | reach live {x['p_reach_live']:.0%} "
                  f"(moves {x['moves']:.2f}, first at day {x['first_live_day_median']}), cool-off days {x['cool_days']:.0f}, accounts closed {x['closed_accounts']:.1f}", flush=True)
        print("live accounts at a move (share):", out[window]["live_accounts_at_move"], flush=True)
    (ROOT / "reports" / "a60_live.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

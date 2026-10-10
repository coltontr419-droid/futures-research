"""Prop-firm account types priced against the programme's strategies: P(first payout within 84 trading
days) and EV per attempt, net of every fee. A COMPUTATION; no market claim, no trial. decisions.md 92.

    python -m futuresres.reporting.z_firms --check     # must reproduce decisions.md 82 (Tradeify, user's terms)
    python -m futuresres.reporting.z_firms             # every account x every strategy
    python -m futuresres.reporting.z_firms --log

RULES were gathered 2026-10-09 from third-party summaries of each firm's 50K accounts (sources in
decisions.md 92; several conflict and none could be confirmed on the firms' own pages). Where a rule was
missing or contradictory, the assumption is written in the spec as `note`. Rules change often: treat every
figure as dated.

STRATEGIES (drift removed from real paths, then an edge imposed; post-2021 sessions):
  MNQ_RTH_0        1 MNQ, 09:30-16:00 ET, long, no edge                (minute paths)
  MNQ_RTH_S1       the same with an imposed annual Sharpe of 1 - about the best published effect found
  MGC_LON_0        1 MGC, 03:00-11:30 ET, long, no edge                (minute paths)
  Z02_MES_041      Z02: one MES by the rebalancing signal's sign, its own realised test Sharpe (0.41),
                   imposed on its demeaned daily P&L shape            (daily bars with lows)
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

import futuresres.reporting.y01_structure_ev as y
import futuresres.reporting.y03_sessions as s3

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "z_firms.json"
OUT_MD = ROOT / "reports" / "z_firms.md"
START = 50_000.0
HORIZON = 84            # trading days, ~4 months: the user's limit for a first payout
TOTAL = 504             # followed two years for the full EV
MONTH = 21
ACCOUNTS = 4000

# ------------------------------------------------------------------ the account types (50K)
SPECS: dict[str, dict] = {
    "Tradeify Select Daily (user's terms)": dict(
        fee=80, monthly=0, activation=0, target=3000, dd=2000, eval_cap=None, eval_daily=1000,
        eval_consistency=0.40, min_days=0, time_limit=None, breach="intraday",
        f_lock_trigger=52000, f_lock_level=50000, f_daily=1000, f_consistency=None,
        pay_mode="above", buffer=2000, require=0, frac=1.0, every="daily", q_days=0, q_min=0,
        caps=[1250, 1250, 1250], cap_after=10**9, min_pay=0, split=0.90,
        note="the user's confirmed terms (decisions.md 81-82); list price $165"),
    "Tradeify Select Flex": dict(
        fee=165, monthly=0, activation=0, target=3000, dd=2000, eval_cap=None, eval_daily=None,
        eval_consistency=0.40, min_days=3, time_limit=None, breach="intraday",
        f_lock_trigger=52000, f_lock_level=50000, f_daily=None, f_consistency=None,
        pay_mode="frac", buffer=0, require=0, frac=0.5, every="n_winning", q_days=5, q_min=1,
        caps=[3000], cap_after=3000, min_pay=0, split=0.90,
        note="every 5 winning days (ASSUMED: any day > $0), up to 50% of profit, cap $3,000; funded lock assumed as Select Daily"),
    "Tradeify Growth": dict(
        fee=145, monthly=0, activation=0, target=3000, dd=2000, eval_cap=None, eval_daily=1250,
        eval_consistency=None, min_days=0, time_limit=None, breach="intraday",
        f_lock_trigger=52000, f_lock_level=50000, f_daily=1250, f_consistency=0.35,
        pay_mode="above", buffer=2000, require=53000, frac=1.0, every="n_winning", q_days=5, q_min=150,
        caps=[1500, 2000, 2500], cap_after=3000, min_pay=0, split=0.90,
        note="balance >= $53,000 to request; withdrawable above $52,000 ASSUMED"),
    "Tradeify Lightning (no eval)": dict(
        fee=492, monthly=0, activation=0, target=None, dd=2000, eval_cap=None, eval_daily=None,
        eval_consistency=None, min_days=0, time_limit=None, breach="intraday",
        f_lock_trigger=52000, f_lock_level=50000, f_daily=None, f_consistency=0.20,
        pay_mode="frac", buffer=0, require=53000, frac=1.0, every="daily", q_days=0, q_min=0,
        caps=[2000, 2000, 2000], cap_after=2500, min_pay=1000, split=0.90,
        note="straight to funded; $3,000 profit goal for the first payout (then $2,000 ASSUMED as the same rule); drawdown ASSUMED $2,000 EOD locking at $50,000"),
    "Apex EOD": dict(
        fee=147, monthly=0, activation=129, target=3000, dd=2000, eval_cap=None, eval_daily=1000,
        eval_consistency=None, min_days=0, time_limit=21, breach="intraday",
        f_lock_trigger=52100, f_lock_level=50100, f_daily=1000, f_consistency=0.50,
        pay_mode="above", buffer=2100, require=52600, frac=1.0, every="n_winning", q_days=5, q_min=250,
        caps=[1500, 1750, 2000, 2250, 2500], cap_after=3000, min_pay=500, split=1.0,
        note="30 calendar days to pass (21 trading); eval fee ASSUMED $147 list; safety net $52,100; ladder ASSUMED linear to $3,000 at the 6th; account closes after 6 payouts NOT modelled"),
    "Topstep (standard path)": dict(
        fee=0, monthly=49, activation=149, target=3000, dd=2000, eval_cap=50000, eval_daily=None,
        eval_consistency=0.50, min_days=2, time_limit=None, breach="intraday",
        f_lock_trigger=52000, f_lock_level=50000, f_daily=None, f_consistency=None,
        pay_mode="frac", buffer=0, require=0, frac=0.5, every="n_winning", q_days=5, q_min=150,
        caps=[2000], cap_after=2000, min_pay=125, split=0.90,
        note="$49/month + $149 activation; MLL stops at the start balance; consistency raises the target; 5 winning days >= $150, 50% of balance up to $2,000"),
    "Lucid Flex": dict(
        fee=146, monthly=0, activation=0, target=3000, dd=2000, eval_cap=None, eval_daily=None,
        eval_consistency=0.50, min_days=0, time_limit=None, breach="close",
        f_lock_trigger=52100, f_lock_level=50100, f_daily=None, f_consistency=None,
        pay_mode="frac", buffer=0, require=0, frac=0.5, every="n_winning", q_days=5, q_min=150,
        caps=[2000], cap_after=2000, min_pay=500, split=0.90,
        note="EOD drawdown checked at the close only (sources conflict); locked MLL $50,100"),
    "Lucid Pro": dict(
        fee=172, monthly=0, activation=0, target=3000, dd=2000, eval_cap=None, eval_daily=1200,
        eval_consistency=None, min_days=0, time_limit=None, breach="close",
        f_lock_trigger=52100, f_lock_level=50100, f_daily=None, f_consistency=0.40,
        pay_mode="above", buffer=2100, require=54100, frac=1.0, every="daily", q_days=0, q_min=0,
        caps=[2000], cap_after=2500, min_pay=500, split=0.90,
        note="buffer $52,100; $54,100 for the first payout; funded consistency 40%; daily limit ASSUMED soft"),
    "Take Profit Trader": dict(
        fee=0, monthly=170, activation=130, target=3000, dd=2000, eval_cap=None, eval_daily=None,
        eval_consistency=0.50, min_days=5, time_limit=None, breach="intraday",
        f_lock_trigger=52000, f_lock_level=50000, f_daily=None, f_consistency=None,
        pay_mode="above", buffer=2000, require=0, frac=1.0, every="daily", q_days=0, q_min=0,
        caps=[10**9], cap_after=10**9, min_pay=0, split=0.80, funded_trail="intraday",
        note="$170/month + $130 activation; PRO drawdown is INTRADAY trailing (lock ASSUMED at $50,000); buffer $52,000; 80/20"),
    "Alpha Futures Zero": dict(
        fee=0, monthly=139, activation=0, target=3000, dd=2000, eval_cap=None, eval_daily=1000,
        eval_consistency=None, min_days=2, time_limit=None, breach="intraday",
        f_lock_trigger=52000, f_lock_level=50000, f_daily=1000, f_consistency=0.40,
        pay_mode="frac", buffer=0, require=0, frac=0.5, every="n_winning", q_days=5, q_min=200,
        caps=[1500], cap_after=1500, min_pay=0, split=0.90,
        note="$139/month list; eval consistency ASSUMED none (sources conflict); funded lock ASSUMED"),
    "Alpha Futures Advanced": dict(
        fee=0, monthly=209, activation=0, target=4000, dd=1750, eval_cap=None, eval_daily=None,
        eval_consistency=0.50, min_days=0, time_limit=None, breach="intraday",
        f_lock_trigger=51750, f_lock_level=50000, f_daily=None, f_consistency=None,
        pay_mode="frac", buffer=0, require=0, frac=0.5, every="n_winning", q_days=5, q_min=200,
        caps=[15000], cap_after=15000, min_pay=0, split=0.90,
        note="$4,000 target, $1,750 EOD; eval consistency 50% (sources say 40 or 50); funded lock ASSUMED"),
}


def _floor(peak, dd, cap, trig, level):
    f = peak - dd
    if cap is not None:
        f = np.minimum(f, cap)
    if trig is not None:
        f = np.where(peak >= trig, level, f)
    return f


def _day(eq, peak, l, c, dd, cap, trig, level, daily, breach, tick, intraday_peak_h=None):
    """One session, every account at once. Floor from the END-OF-DAY peak (or, for intraday trailing,
    from the running high). Returns new eq, day P&L, breached, new peak."""
    A, W = c.shape
    E0 = eq[:, None]
    lo = E0 + l; cl = E0 + c
    if intraday_peak_h is not None:                      # intraday trailing: the floor follows the running high
        hi = E0 + intraday_peak_h
        run = np.maximum(peak[:, None], np.concatenate([E0, np.maximum.accumulate(hi, 1)[:, :-1]], 1))
        floor = _floor(run, dd, cap, trig, level)
    else:
        floor = np.repeat(_floor(peak, dd, cap, trig, level)[:, None], W, 1)
    big = W + 1
    if daily is not None:
        st = lo <= E0 - daily
        t_s = np.where(st.any(1), st.argmax(1), big)
    else:
        t_s = np.full(A, big)
    if breach == "intraday":
        br = lo <= floor
        t_b = np.where(br.any(1), br.argmax(1), big)
    else:
        t_b = np.full(A, big)
    rows = np.arange(A)
    out = cl[:, -1].copy()
    is_b = (t_b < big) & (t_b <= t_s)
    is_s = (t_s < big) & ~is_b
    tb = np.minimum(t_b, W - 1)
    out[is_b] = np.minimum(floor[rows, tb], lo[rows, tb])[is_b]
    out[is_s] = (eq - daily - tick)[is_s] if daily is not None else out[is_s]
    breached = is_b | (out <= floor[:, -1])
    if intraday_peak_h is not None:
        newpeak = np.maximum(peak, np.where(is_b | is_s, peak, (E0 + intraday_peak_h).max(1)))
    else:
        newpeak = np.maximum(peak, out)
    return out, out - eq, breached, newpeak


def simulate(spec: dict, paths, rng, accounts: int = ACCOUNTS) -> dict:
    h_all, l_all, c_all = paths
    S = len(c_all)
    A = accounts
    tick = 1.0
    # ---------------- evaluation
    eq = np.full(A, START); pk = eq.copy(); best = np.zeros(A); days = np.zeros(A, int)
    state = np.zeros(A, int)        # 0 eval, 1 funded, -1 dead
    pass_day = np.full(A, -1)
    fees = np.full(A, float(spec["fee"]))
    if spec["target"] is None:      # no evaluation (Lightning)
        state[:] = 1; pass_day[:] = 0
    # funded state
    feq = np.full(A, START); fpk = feq.copy(); paid = np.zeros(A); paid84 = np.zeros(A)
    npay = np.zeros(A, int); first_pay = np.full(A, -1)
    cyc_q = np.zeros(A, int); cyc_best = np.zeros(A); cyc_start = np.full(A, START)
    trail_mode = spec.get("funded_trail", "eod")
    for d in range(TOTAL):
        # monthly subscription while in evaluation
        if spec["monthly"]:
            in_eval = state == 0
            fees[in_eval & (days % MONTH == 0)] += spec["monthly"]
        ev_ = np.flatnonzero(state == 0)
        if len(ev_):
            idx = rng.integers(0, S, len(ev_))
            for k in range(0, len(ev_), 800):
                a_, i_ = ev_[k:k + 800], idx[k:k + 800]
                ne, pnl, br, npk = _day(eq[a_], pk[a_], l_all[i_], c_all[i_], spec["dd"], spec["eval_cap"],
                                        None, None, spec["eval_daily"], spec["breach"], tick)
                eq[a_] = ne; pk[a_] = npk; days[a_] += 1
                best[a_] = np.maximum(best[a_], pnl)
                prof = ne - START
                ok = (~br) & (prof >= spec["target"]) & (days[a_] >= spec["min_days"])
                if spec["eval_consistency"]:
                    ok &= best[a_] <= spec["eval_consistency"] * prof
                if spec["time_limit"]:
                    br = br | ((days[a_] >= spec["time_limit"]) & ~ok)
                state[a_[br]] = -1
                p_ = a_[ok]
                state[p_] = 1; pass_day[p_] = d + 1; fees[p_] += spec["activation"]
        fu = np.flatnonzero((state == 1) & (pass_day <= d))
        if len(fu):
            idx = rng.integers(0, S, len(fu))
            for k in range(0, len(fu), 800):
                a_, i_ = fu[k:k + 800], idx[k:k + 800]
                ne, pnl, br, npk = _day(feq[a_], fpk[a_], l_all[i_], c_all[i_], spec["dd"], None,
                                        spec["f_lock_trigger"], spec["f_lock_level"], spec["f_daily"],
                                        spec["breach"], tick,
                                        intraday_peak_h=h_all[i_] if trail_mode == "intraday" else None)
                feq[a_] = ne; fpk[a_] = npk
                state[a_[br]] = -1
                live = a_[~br]
                pnl_l = pnl[~br]
                cyc_q[live] += pnl_l >= max(spec["q_min"], 1e-9)
                cyc_best[live] = np.maximum(cyc_best[live], pnl_l)
                # eligibility
                elig = np.ones(len(live), bool)
                if spec["every"] == "n_winning":
                    elig &= cyc_q[live] >= spec["q_days"]
                if spec["require"]:
                    elig &= feq[live] >= spec["require"]
                cyc_prof = feq[live] - cyc_start[live]
                if spec["f_consistency"]:
                    elig &= (cyc_prof > 0) & (cyc_best[live] <= spec["f_consistency"] * cyc_prof)
                if spec["pay_mode"] == "above":
                    amt = np.maximum(feq[live] - (START + spec["buffer"]), 0.0)
                else:
                    amt = np.maximum(spec["frac"] * (feq[live] - START), 0.0)
                cap = np.array([spec["caps"][m] if m < len(spec["caps"]) else spec["cap_after"]
                                for m in npay[live]], float) if len(live) else np.zeros(0)
                amt = np.minimum(amt, cap)
                elig &= amt >= max(spec["min_pay"], 1e-9)
                w = live[elig]; a_amt = amt[elig]
                paid[w] += spec["split"] * a_amt
                if d < HORIZON:
                    paid84[w] += spec["split"] * a_amt
                first_pay[w[first_pay[w] < 0]] = d + 1
                feq[w] -= a_amt; npay[w] += 1
                cyc_q[w] = 0; cyc_best[w] = 0.0; cyc_start[w] = feq[w]
        if not (state >= 0).any():
            break
    return {"p_pass": float((pass_day > 0).mean()) if spec["target"] else 1.0,
            "p_pass_84": float(((pass_day > 0) & (pass_day <= HORIZON)).mean()) if spec["target"] else 1.0,
            "p_payout_84": float(((first_pay > 0) & (first_pay <= HORIZON)).mean()),
            "p_payout_ever": float((first_pay > 0).mean()),
            "mean_fees": float(fees.mean()),
            "ev_84": float(paid84.mean() - fees.mean()),
            "ev_2y": float(paid.mean() - fees.mean())}


# ------------------------------------------------------------------ strategies
def _minute_paths(prod: str, window: str, sharpes: tuple[float, ...]) -> dict[float, tuple]:
    """One product loaded once; one path set per imposed Sharpe; the big arrays freed before returning."""
    import gc
    spec = s3.PRODUCTS[prod]
    y.SERIES = y.ROOT / "data" / "continuous" / f"{spec['series']}.parquet"
    y.MULT = spec["mult"]
    y.WINDOWS.update(s3.WINDOWS)
    dates, H, L, C, notional = y.load_sessions()
    post = dates >= y.ERA
    H, L, C = H[post], L[post], C[post]
    gc.collect()
    sd_s = float(C[:, -1].std())
    _, _, c0, _ = y.window_paths(H, L, C, window, 0.0)
    share = float(c0[:, -1].std() / sd_s)
    del c0
    out = {}
    rt = spec["rt"]
    for s in sharpes:
        h, l, c, _ = y.window_paths(H, L, C, window, s / math.sqrt(252) * sd_s * share)
        out[s] = ((h * notional).astype(np.float32), (l * notional - rt).astype(np.float32),
                  (c * notional - rt).astype(np.float32))
        del h, l, c
    del H, L, C
    gc.collect()
    return out


def _z02_paths() -> tuple:
    from futuresres.signals import z02_trial as zt
    dates, r_sp, r_ty, price, lo, hi = zt._data()
    held = zt._held(dates, r_sp, r_ty)
    pre = dates <= np.datetime64("2023-03-17")
    K = 1.0 / float(np.median(np.abs(held[pre & (held != 0)])))
    ct = zt._contracts(held, K, "sign_1")
    notional = float(price[np.isfinite(price)][-1]) * 5.0
    live = ct != 0
    c = ct * notional * r_sp
    l = np.where(ct > 0, ct * notional * lo, -ct * notional * hi)
    h = np.where(ct > 0, ct * notional * hi, -ct * notional * lo)
    c, l, h = c[live], l[live], h[live]
    sd = float(c.std())
    drift = 0.41 / math.sqrt(252) * sd - float(c.mean())
    cost = 3.07
    return ((h + drift)[:, None].astype(np.float32),
            (np.minimum(l + drift, c + drift) - cost)[:, None].astype(np.float32),
            (c + drift - cost)[:, None].astype(np.float32))


def strategy_paths(keys: tuple[str, ...] = ("MNQ_RTH_0", "MNQ_RTH_S1", "MGC_LON_0", "Z02_MES_041")) -> dict:
    out = {}
    want_mnq = tuple(s for k, s in (("MNQ_RTH_0", 0.0), ("MNQ_RTH_S1", 1.0)) if k in keys)
    if want_mnq:
        m = _minute_paths("MNQ", "rth_0930_1600", want_mnq)
        for k, s in (("MNQ_RTH_0", 0.0), ("MNQ_RTH_S1", 1.0)):
            if k in keys:
                out[k] = m[s]
    if "MGC_LON_0" in keys:
        out["MGC_LON_0"] = _minute_paths("MGC", "london_0300_1130", (0.0,))[0.0]
    if "Z02_MES_041" in keys:
        out["Z02_MES_041"] = _z02_paths()
    return out


def check() -> dict:
    """Reproduce decisions.md 82: Tradeify (user's terms), RTH 1 MNQ, post-2021, no edge -> P(pass) ~0.19,
    2-year EV ~ +$78 (+/- ~$25)."""
    paths = strategy_paths(("MNQ_RTH_0",))["MNQ_RTH_0"]
    r = simulate(SPECS["Tradeify Select Daily (user's terms)"], paths, np.random.default_rng(1), accounts=8000)
    ok = abs(r["p_pass"] - 0.193) <= 0.02 and abs(r["ev_2y"] - 78) <= 35
    return {**r, "reference": {"p_pass": 0.193, "ev_2y": 78}, "ok": bool(ok)}


def render(res: dict) -> str:
    w = ["# Prop-firm account types against the programme's strategies", "",
         "Generated by `python -m futuresres.reporting.z_firms`. Rules gathered 2026-10-09 from third-party "
         "summaries (several conflict); assumptions in each spec's `note`. Drift removed, edge imposed; "
         "post-2021 sessions. A computation, no trial. `decisions.md` §92.", "",
         f"Engine check against §82: {res['check']}", ""]
    strats = ["MNQ_RTH_0", "MNQ_RTH_S1", "MGC_LON_0", "Z02_MES_041"]
    w.append("## P(first payout within 84 trading days ≈ 4 months)")
    w.append("")
    w.append("| account | fees (mean) | " + " | ".join(strats) + " |")
    w.append("|---|---|" + "---|" * len(strats))
    for acct, row in res["cells"].items():
        w.append(f"| {acct} | ${np.mean([v['mean_fees'] for v in row.values()]):,.0f} | "
                 + " | ".join(f"{row[s]['p_payout_84']:.0%}" for s in strats) + " |")
    w.append("")
    w.append("## EV per attempt within 84 trading days (payouts by day 84 minus all fees) / over 2 years")
    w.append("")
    w.append("| account | " + " | ".join(strats) + " |")
    w.append("|---|" + "---|" * len(strats))
    for acct, row in res["cells"].items():
        w.append(f"| {acct} | " + " | ".join(f"{row[s]['ev_84']:+,.0f} / {row[s]['ev_2y']:+,.0f}" for s in strats) + " |")
    w.append("")
    w.append("## Assumptions per account")
    w.append("")
    for acct, spec in SPECS.items():
        w.append(f"- **{acct}** — {spec['note']}")
    return "\n".join(w)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true"); ap.add_argument("--log", action="store_true")
    ap.add_argument("--strategy", choices=("MNQ_RTH_0", "MNQ_RTH_S1", "MGC_LON_0", "Z02_MES_041"),
                    help="run one strategy in its own process and merge (the 2.7 GB machine)")
    a = ap.parse_args(argv)
    if a.check:
        chk = check()
        res = json.loads(OUT.read_text()) if OUT.exists() else {"cells": {}}
        res["check"] = chk
        OUT.write_text(json.dumps(res, indent=1) + "\n")
        print(json.dumps(chk, indent=1)); return 0
    if a.strategy:
        res = json.loads(OUT.read_text()) if OUT.exists() else {"cells": {}}
        if not res.get("check", {}).get("ok"):
            raise SystemExit("run --check first")
        p = strategy_paths((a.strategy,))[a.strategy]
        rng = np.random.default_rng(abs(hash(a.strategy)) % 2**32)
        for acct, spec in SPECS.items():
            r = simulate(spec, p, rng)
            res["cells"].setdefault(acct, {})[a.strategy] = r
            print(f"{acct:38} {a.strategy:12} pass {r['p_pass']:.2f} payout<=84d {r['p_payout_84']:.0%} "
                  f"EV84 {r['ev_84']:+6.0f} EV2y {r['ev_2y']:+6.0f}", flush=True)
        OUT.write_text(json.dumps(res, indent=1) + "\n")
        return 0
    if a.log and OUT.exists():
        res = json.loads(OUT.read_text())
    else:
        chk = check()
        if not chk["ok"]:
            raise SystemExit(f"engine fails its check against decisions.md 82: {chk}")
        paths = strategy_paths()
        rng = np.random.default_rng(92)
        res = {"check": chk, "cells": {}}
        for acct, spec in SPECS.items():
            res["cells"][acct] = {}
            for sname, p in paths.items():
                r = simulate(spec, p, rng)
                res["cells"][acct][sname] = r
                print(f"{acct:38} {sname:12} pass {r['p_pass']:.2f} payout<=84d {r['p_payout_84']:.0%} "
                      f"EV84 {r['ev_84']:+6.0f} EV2y {r['ev_2y']:+6.0f}", flush=True)
        OUT.write_text(json.dumps(res, indent=1) + "\n")
    OUT_MD.write_text(render(res))
    print(OUT_MD.read_text())
    if a.log:
        from futuresres.stats.trials import Trial, TrialLog
        log = TrialLog(ROOT / "measurements.jsonl")
        rec = log.append(Trial(trial_id=log.next_id("m"), hypothesis_id="Z-series", symbol="MNQ/MGC/MES",
                               date_range=("2021-01-01", "2026-09-11"), status="completed",
                               params={"kind": "firm_comparison", "cells": res["cells"], "check": res["check"]},
                               note="kind=computation; NOT a trial. Prop-firm account types priced against the "
                                    "programme's strategies. decisions.md 92."))
        print("logged", rec["trial_id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())

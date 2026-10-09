"""Y02 - the zero-edge evaluation EV under Tradeify's daily-account rules, on real MNQ paths.

A COMPUTATION on the firm's rules, driven by Y01's demeaned real sessions; no market claim, no trial.
`--log` writes one record to measurements.jsonl. decisions.md 80.

    python -m futuresres.reporting.y02_tradeify --check    # engine equivalence against Y01
    python -m futuresres.reporting.y02_tradeify
    python -m futuresres.reporting.y02_tradeify --log

THE RULES, as supplied by the user 2026-10-09, and the reading taken where they were ambiguous:

  floor        END OF DAY. The trailing floor is set from the highest END-OF-DAY balance - intraday highs
               do not raise it - and is $2,000 below that, fixed at $50,000 once that balance reaches
               $52,000. READING (primary): falling to the day's floor INTRADAY still fails the account.
               ALTERNATIVE (reported beside it): only the closing balance is tested.
  consistency  EVALUATION ONLY, 40%: pass requires profit >= $3,000 AND the best single day's profit
               <= 40% of total profit. A pass is tested at the END OF A DAY; a day that breaks the ratio
               means trading on until it holds. None in the funded account.
  time limit   NONE. Evaluations run until they pass or fail; capped at 2,000 sessions, and any still
               open there are reported, not counted as passes.
  payouts      Capped at $1,250 per payout until live, no maximum number. Only equity above the $52,000
               buffer is withdrawable; the trader keeps 90%. FREQUENCY NOT SUPPLIED: run at every
               session (daily), every 5 (weekly) and every 21 (monthly). When the account goes "live" -
               and so uncapped - was not supplied: the cap is applied throughout (conservative) and an
               uncapped run is reported beside it.
  unchanged    $50,000 start, +$3,000 target, $1,000 SOFT daily loss limit (decisions.md 75), $80 fee,
               no resets, $2.32 round trip, funded account followed 504 sessions (assumed).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Final

import numpy as np

import futuresres.reporting.y01_structure_ev as y

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
OUT_JSON: Final[Path] = ROOT / "reports" / "y02_tradeify.json"
OUT_MD: Final[Path] = ROOT / "reports" / "y02_tradeify.md"
CONSISTENCY: Final[float] = 0.40
CAP: Final[float] = 1_250.0
EVAL_MAX: Final[int] = 2_000
ACCOUNTS: Final[int] = 4_000
POLICIES: Final[tuple[tuple[str, int], ...]] = (("rth", 1), ("rth", 2), ("full", 1), ("full", 2))
FREQS: Final[dict[str, int]] = {"daily": 1, "weekly": 5, "monthly": 21}


def _floor(peak_eod: np.ndarray, lock: bool = True) -> np.ndarray:
    """$2,000 below the highest end-of-day balance. FUNDED: fixed at $50,000 once that balance reaches
    $52,000. EVALUATION (lock=False, user 2026-10-09): never fixed - at $52,999 the floor is $50,999."""
    if not lock:
        return peak_eod - y.TRAIL
    return np.where(peak_eod >= y.START + y.LOCK, y.START, peak_eod - y.TRAIL)


def day_eod(eq, peak_eod, h, l, c, n, intraday_breach: bool, lock: bool = True):
    """One session under an END-OF-DAY floor. Returns (new_eq, day_pnl, breached)."""
    A, W = c.shape
    E0 = eq[:, None]
    lo = E0 + l * n
    cl = E0 + c * n
    floor = _floor(peak_eod, lock)[:, None]
    big = W + 1
    stop = lo <= E0 - y.DAILY
    t_s = np.where(stop.any(1), stop.argmax(1), big)
    if intraday_breach:
        br = lo <= floor
        t_b = np.where(br.any(1), br.argmax(1), big)
    else:
        t_b = np.full(A, big)
    rows = np.arange(A)
    exit_eq = cl[:, W - 1].copy()
    is_b = t_b <= t_s
    is_b &= t_b < big
    is_s = (t_s < big) & ~is_b
    exit_eq[is_b] = np.minimum(floor[:, 0], lo[rows, np.minimum(t_b, W - 1)])[is_b]
    exit_eq[is_s] = (eq - y.DAILY - y.TICK_USD * n)[is_s]
    new_eq = exit_eq - y.RT_COST * n
    breached = is_b | (new_eq <= floor[:, 0])
    return new_eq, new_eq - eq, breached


def run_eval(paths, n, rng, intraday_breach: bool, consistency: float | None, accounts: int = ACCOUNTS,
             lock: bool = True):
    h_all, l_all, c_all = paths
    S = len(c_all)
    eq = np.full(accounts, y.START); peak = eq.copy(); best = np.zeros(accounts)
    alive = np.ones(accounts, bool); passed = np.zeros(accounts, bool); days = np.zeros(accounts)
    for d in range(EVAL_MAX):
        act = np.flatnonzero(alive & ~passed)
        if not len(act):
            break
        idx = rng.integers(0, S, len(act))
        for k in range(0, len(act), y.CHUNK):
            a_, i_ = act[k:k + y.CHUNK], idx[k:k + y.CHUNK]
            ne, pnl, br = day_eod(eq[a_], peak[a_], h_all[i_], l_all[i_], c_all[i_], n, intraday_breach, lock)
            eq[a_] = ne; days[a_] += 1
            best[a_] = np.maximum(best[a_], pnl)
            peak[a_] = np.maximum(peak[a_], ne)
            alive[a_[br]] = False
            profit = ne - y.START
            ok = (~br) & (profit >= y.TARGET)
            if consistency is not None:
                ok &= best[a_] <= consistency * profit
            passed[a_[ok]] = True
    open_ = alive & ~passed
    return {"p_pass": float(passed.mean()), "p_open_at_cap": float(open_.mean()),
            "days_to_pass_median": float(np.median(days[passed])) if passed.any() else float("nan"),
            "days_mean": float(days.mean())}


def run_funded(paths, n, rng, intraday_breach: bool, every: int, cap: float | None,
               accounts: int = ACCOUNTS, live_after: int | None = None) -> np.ndarray:
    h_all, l_all, c_all = paths
    S = len(c_all)
    eq = np.full(accounts, y.START); peak = eq.copy()
    alive = np.ones(accounts, bool); paid = np.zeros(accounts); n_payouts = np.zeros(accounts, int)
    for d in range(y.FUNDED_DAYS):
        act = np.flatnonzero(alive)
        if not len(act):
            break
        idx = rng.integers(0, S, len(act))
        for k in range(0, len(act), y.CHUNK):
            a_, i_ = act[k:k + y.CHUNK], idx[k:k + y.CHUNK]
            ne, _, br = day_eod(eq[a_], peak[a_], h_all[i_], l_all[i_], c_all[i_], n, intraday_breach)
            eq[a_] = ne
            peak[a_] = np.maximum(peak[a_], ne)
            alive[a_[br]] = False
        if (d + 1) % every == 0:
            excess = np.where(alive, np.maximum(eq - (y.START + y.LOCK), 0.0), 0.0)
            if cap is not None:
                capped = np.minimum(excess, cap)
                if live_after is not None:          # uncapped once this account has gone live
                    excess = np.where(n_payouts >= live_after, excess, capped)
                else:
                    excess = capped
            n_payouts += excess > 0
            paid += y.SPLIT * excess
            eq -= excess
    return paid


def check(seed: int = 5) -> dict:
    """Equivalence: with one bar per session an END-OF-DAY floor and an intraday floor are the same
    rule, so with no consistency rule, no daily limit and no cost, this engine must reproduce Y01's
    validated engine on the same demeaned Gaussian sessions."""
    rng = np.random.default_rng(seed)
    S = 4000
    x = rng.normal(0, 1, (S, 1)).astype(np.float32)
    x -= x.mean(); x *= 600.0 / x.std()
    paths = (x, x, x)
    saved = (y.DAILY, y.RT_COST)
    y.DAILY, y.RT_COST = 1e12, 0.0
    try:
        a = y.simulate(paths, 1, 8000, np.random.default_rng(1), True, 2000)["p_pass"]
        b = run_eval(paths, 1, np.random.default_rng(1), True, None, accounts=8000)["p_pass"]
    finally:
        y.DAILY, y.RT_COST = saved
    se = math.sqrt(a * (1 - a) / 8000)
    return {"y01_engine": a, "y02_engine": b, "tolerance": 4 * se, "ok": abs(a - b) <= 4 * se}


def run(seed: int = 20261009) -> dict:
    chk = check()
    if not chk["ok"]:
        raise SystemExit(f"Y02 engine disagrees with Y01: {chk}")
    dates, H, L, C, notional = y.load_sessions()
    eras = {"pre_2021": dates < y.ERA, "post_2021": dates >= y.ERA}
    rng = np.random.default_rng(seed)
    res = {"check": chk, "cells": [], "budget": {}}
    for era, mask in eras.items():
        for window, n in POLICIES:
            h, l, c, _ = y.window_paths(H[mask], L[mask], C[mask], window, None)
            usd = (h * notional, l * notional, c * notional)
            for intraday in (True, False):
                ev_ = run_eval(usd, n, rng, intraday, CONSISTENCY)
                noc = run_eval(usd, n, rng, intraday, None) if (intraday and era == "post_2021") else None
                for fname, every in FREQS.items():
                    for cap in (CAP, None):
                        if not intraday and (fname != "monthly" or cap is None):
                            continue                      # the alternative floor reading: one row
                        paid = run_funded(usd, n, rng, intraday, every, cap)
                        ev = ev_["p_pass"] * paid.mean() - y.FEE
                        row = {"era": era, "window": window, "contracts": n,
                               "floor": "eod_intraday_breach" if intraday else "eod_close_only",
                               "payout_every": fname, "cap": cap, **ev_, "expected_payout": float(paid.mean()),
                               "p_any_payout": float((paid > 0).mean()), "ev": ev}
                        if noc is not None and fname == "monthly" and cap == CAP:
                            row["p_pass_without_consistency"] = noc["p_pass"]
                        res["cells"].append(row)
                        if era == "post_2021" and intraday and fname == "monthly" and cap == CAP:
                            res["budget"][f"{window}_{n}"] = _budget(ev_["p_pass"], paid, rng)
                        print(f"{era:9} {window:4} n={n} {row['floor'][:12]:12} {fname:7} cap={cap} "
                              f"pass {ev_['p_pass']:.3f} open {ev_['p_open_at_cap']:.3f} payout "
                              f"{paid.mean():6.0f} EV {ev:+6.0f}", flush=True)
    return res


def drift_check(seed: int = 7) -> list[dict]:
    """The chosen policies under the primary reading (monthly, capped), post-2021, against an IMPOSED
    drift - a long position's annual Sharpe of -0.3, 0 and +0.3 - as Y01's sensitivity did."""
    dates, H, L, C, notional = y.load_sessions()
    post = dates >= y.ERA
    H, L, C = H[post], L[post], C[post]
    rng = np.random.default_rng(seed)
    sd_session = float(C[:, -1].std())
    out = []
    for window, n in (("rth", 1), ("rth", 2)):
        _, _, c0, _ = y.window_paths(H, L, C, window, 0.0)
        share = float(c0[:, -1].std() / sd_session)
        for s in (-0.3, 0.0, 0.3):
            h, l, c, _ = y.window_paths(H, L, C, window, s / math.sqrt(252) * sd_session * share)
            usd = (h * notional, l * notional, c * notional)
            e = run_eval(usd, n, rng, True, CONSISTENCY)
            paid = run_funded(usd, n, rng, True, FREQS["monthly"], CAP)
            out.append({"window": window, "contracts": n, "sharpe": s, "p_pass": e["p_pass"],
                        "expected_payout": float(paid.mean()), "ev": e["p_pass"] * paid.mean() - y.FEE})
            print(f"drift {window} n={n} S={s:+.1f}: pass {e['p_pass']:.3f} EV {out[-1]['ev']:+.0f}", flush=True)
    return out


def final_rules(seed: int = 11) -> dict:
    """Tradeify as confirmed 2026-10-09: EVALUATION floor trails the end-of-day balance with no lock
    (decisions.md 82); FUNDED floor fixed at $50,000 once the end-of-day balance reaches $52,000;
    intraday breach of the end-of-day floor fails; DAILY payouts,
    capped at $1,250 until the account goes live after 3 payouts on it (the per-account route; the
    10-in-total route across accounts is not modelled, so this is the conservative case); fee $80."""
    dates, H, L, C, notional = y.load_sessions()
    rng = np.random.default_rng(seed)
    sd_session = float(C[dates >= y.ERA][:, -1].std())
    out = {"cells": [], "drift": [], "budget": {}}
    for era, mask in (("pre_2021", dates < y.ERA), ("post_2021", dates >= y.ERA)):
        for window, n in (("rth", 1), ("rth", 2), ("full", 1)):
            h, l, c, _ = y.window_paths(H[mask], L[mask], C[mask], window, None)
            usd = (h * notional, l * notional, c * notional)
            e = run_eval(usd, n, rng, True, CONSISTENCY, lock=False)
            paid = run_funded(usd, n, rng, True, 1, CAP, live_after=3)
            ev = e["p_pass"] * paid.mean() - y.FEE
            out["cells"].append({"era": era, "window": window, "contracts": n, "p_pass": e["p_pass"],
                                 "days_to_pass_median": e["days_to_pass_median"],
                                 "expected_payout": float(paid.mean()),
                                 "p_any_payout": float((paid > 0).mean()), "ev": ev})
            if era == "post_2021" and window == "rth" and n == 1:
                out["budget"] = _budget(e["p_pass"], paid, rng)
            print(f"final {era} {window} n={n}: pass {e['p_pass']:.3f} payout {paid.mean():.0f} EV {ev:+.0f}",
                  flush=True)
    post = dates >= y.ERA
    _, _, c0, _ = y.window_paths(H[post], L[post], C[post], "rth", 0.0)
    share = float(c0[:, -1].std() / sd_session)
    for s in (-0.3, 0.0, 0.3):
        h, l, c, _ = y.window_paths(H[post], L[post], C[post], "rth", s / math.sqrt(252) * sd_session * share)
        usd = (h * notional, l * notional, c * notional)
        e = run_eval(usd, 1, rng, True, CONSISTENCY, lock=False)
        paid = run_funded(usd, 1, rng, True, 1, CAP, live_after=3)
        out["drift"].append({"sharpe": s, "p_pass": e["p_pass"], "ev": e["p_pass"] * paid.mean() - y.FEE})
        print(f"final drift rth n=1 S={s:+.1f}: EV {out['drift'][-1]['ev']:+.0f}", flush=True)
    return out


def _budget(p, payouts, rng, reps: int = 20000) -> dict:
    out = {}
    for k in (10, 20, 40):
        passes = rng.random((reps, k)) < p
        net = (passes * rng.choice(payouts, size=(reps, k))).sum(1) - y.FEE * k
        out[k] = {"p_net_positive": float((net > 0).mean()), "median": float(np.median(net)),
                  "p95": float(np.quantile(net, 0.95)), "mean": float(net.mean())}
    return out


def render(r: dict) -> str:
    w: list[str] = []
    a = w.append
    a("# Y02 — one $80 evaluation under Tradeify's daily-account rules, zero edge, real MNQ paths")
    a("")
    a("Generated by `python -m futuresres.reporting.y02_tradeify`. Rules and readings in the module "
      "docstring; `decisions.md` §80. Drift removed; a computation, no trial.")
    a("")
    c0 = r["check"]
    a(f"**Engine checked first** against Y01's validated engine (one bar per session, where an end-of-day "
      f"and an intraday floor coincide): {c0['y02_engine']:.3f} against {c0['y01_engine']:.3f} "
      f"(tolerance {c0['tolerance']:.3f}).")
    a("")
    a("## Primary reading — end-of-day floor, intraday breach fails, payouts capped at $1,250")
    a("")
    a("| era | policy | P(pass) | median days to pass | payout daily | weekly | monthly | EV daily | weekly | monthly |")
    a("|---|---|---|---|---|---|---|---|---|---|")
    for era in ("pre_2021", "post_2021"):
        for window, n in POLICIES:
            rows = {x["payout_every"]: x for x in r["cells"] if x["era"] == era and x["window"] == window
                    and x["contracts"] == n and x["floor"] == "eod_intraday_breach" and x["cap"] == CAP}
            d0 = rows["monthly"]
            a(f"| {era} | {window}, {n} MNQ | {d0['p_pass']:.1%} | {d0['days_to_pass_median']:.0f} | "
              + " | ".join(f"{rows[f]['expected_payout']:,.0f}" for f in FREQS) + " | "
              + " | ".join(f"**{rows[f]['ev']:+,.0f}**" for f in FREQS) + " |")
    a("")
    a("## Sensitivities, post-2021, monthly payouts")
    a("")
    a("| policy | primary (capped) | uncapped | close-only floor | P(pass) without the consistency rule |")
    a("|---|---|---|---|---|")
    for window, n in POLICIES:
        sel = [x for x in r["cells"] if x["era"] == "post_2021" and x["window"] == window and x["contracts"] == n
               and x["payout_every"] == "monthly"]
        prim = next(x for x in sel if x["floor"] == "eod_intraday_breach" and x["cap"] == CAP)
        unc = next(x for x in sel if x["floor"] == "eod_intraday_breach" and x["cap"] is None)
        clo = next(x for x in sel if x["floor"] == "eod_close_only")
        a(f"| {window}, {n} MNQ | {prim['ev']:+,.0f} ({prim['p_pass']:.0%}) | {unc['ev']:+,.0f} | "
          f"{clo['ev']:+,.0f} ({clo['p_pass']:.0%}) | {prim.get('p_pass_without_consistency', float('nan')):.0%} "
          f"(with it: {prim['p_pass']:.0%}) |")
    a("")
    if r.get("drift"):
        a("## Imposed drift, post-2021, primary reading, monthly capped payouts")
        a("")
        a("| policy | Sharpe -0.3 | 0 | +0.3 |")
        a("|---|---|---|---|")
        for window, n in (("rth", 1), ("rth", 2)):
            row = [d for d in r["drift"] if d["window"] == window and d["contracts"] == n]
            a(f"| {window}, {n} MNQ | " + " | ".join(f"{d['ev']:+,.0f} ({d['p_pass']:.0%})" for d in row) + " |")
        a("")
    if r.get("final_rules"):
        fr = r["final_rules"]
        a("## FINAL — Tradeify as confirmed: evaluation floor never locks; intraday breach fails; DAILY payouts, $1,250 cap until 3 payouts")
        a("")
        a("| era | policy | P(pass) | median days to pass | E[payout] | P(any payout) | EV per $80 |")
        a("|---|---|---|---|---|---|---|")
        for x in fr["cells"]:
            a(f"| {x['era']} | {x['window']}, {x['contracts']} MNQ | {x['p_pass']:.1%} | {x['days_to_pass_median']:.0f} | "
              f"{x['expected_payout']:,.0f} | {x['p_any_payout']:.0%} | **{x['ev']:+,.0f}** |")
        a("")
        a("RTH, 1 MNQ, post-2021, imposed drift: " + "; ".join(
            f"Sharpe {d['sharpe']:+.1f} → {d['ev']:+,.0f} ({d['p_pass']:.0%})" for d in fr["drift"]))
        a("")
        a("| RTH, 1 MNQ: K evaluations | outlay | P(net > 0) | median | 95th pct | mean |")
        a("|---|---|---|---|---|---|")
        for k, v in fr["budget"].items():
            a(f"| {k} | ${80 * int(k):,} | {v['p_net_positive']:.0%} | {v['median']:+,.0f} | {v['p95']:+,.0f} | {v['mean']:+,.0f} |")
        a("")
    a("## A budget of evaluations, post-2021, primary reading, monthly payouts")
    a("")
    a("| policy | K | outlay | P(net > 0) | median | 95th pct | mean |")
    a("|---|---|---|---|---|---|---|")
    for key, b in r["budget"].items():
        for k, v in b.items():
            a(f"| {key.replace('_', ', ')} MNQ | {k} | ${80 * int(k):,} | {v['p_net_positive']:.0%} | "
              f"{v['median']:+,.0f} | {v['p95']:+,.0f} | {v['mean']:+,.0f} |")
    a("")
    return "\n".join(w)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.reporting.y02_tradeify")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--log", action="store_true")
    ap.add_argument("--drift", action="store_true", help="add the imposed-drift check to the saved run")
    ap.add_argument("--final", action="store_true", help="add the confirmed-rules run to the saved run")
    args = ap.parse_args(argv)
    if args.final:
        r = json.loads(OUT_JSON.read_text())
        r["final_rules"] = final_rules()
        OUT_JSON.write_text(json.dumps(r, indent=1, default=float) + "\n")
        return main([])
    if args.drift:
        r = json.loads(OUT_JSON.read_text())
        r["drift"] = drift_check()
        OUT_JSON.write_text(json.dumps(r, indent=1, default=float) + "\n")
        return main([])
    if args.check:
        print(json.dumps(check(), indent=1))
        return 0
    if OUT_JSON.exists():
        r = json.loads(OUT_JSON.read_text())
    else:
        r = run()
        OUT_JSON.write_text(json.dumps(r, indent=1, default=float) + "\n")
        r = json.loads(OUT_JSON.read_text())
    for x in r["cells"]:
        if x["cap"] is not None:
            x["cap"] = float(x["cap"])
    OUT_MD.write_text(render(r))
    print(OUT_MD.read_text())
    if args.log:
        from futuresres.stats.trials import Trial, TrialLog
        log = TrialLog(ROOT / "measurements.jsonl")
        rec = log.append(Trial(
            trial_id=log.next_id("m"), hypothesis_id="Y-series", symbol="MNQ",
            date_range=("2015-11-20", "2026-08-27"), status="completed",
            params={"kind": "structure_ev_tradeify", "check": r["check"],
                    "cells": [{k: x[k] for k in ("era", "window", "contracts", "floor", "payout_every", "cap",
                                                 "p_pass", "expected_payout", "ev")} for x in r["cells"]],
                    "budget": r["budget"], "drift": r.get("drift"), "final_rules": r.get("final_rules")},
            note=("kind=computation; NOT a trial and NOT counted in N. Y02: zero-edge evaluation EV under "
                  "Tradeify's daily-account rules on demeaned real MNQ sessions. decisions.md 80."),
        ))
        print(f"logged {rec['trial_id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

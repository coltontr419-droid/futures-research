"""A18 - the demo checker: do the live tickets behave like the backtest? decisions.md 126.

    python -m futuresres.reporting.a18_demo_check shadow_log.csv [demo_log.csv]

For every finished ticket in the bot's shadow log (bot/schedule.py): the probability, on 2021-26 history (the same
1-minute paths as A07/A08, drift removed, stops at the stop price, a minute touching both = stop), that THIS bracket -
its take and stop in points, its contract count, its window - ends in a take, a stop or a time exit, and its expected
net P&L. Summed over the tickets: expected vs observed counts (a chi-square on three cells) and observed P&L against
the expected total with its standard deviation. Crude (MCL) uses the one-bar daily approximation (decisions.md 116),
so its expected rates are coarse. With demo_log.csv: on days marked traded, the change in the account's closing
balance against the shadow P&L - the execution gap (slippage, fills) per traded ticket.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
WINDOWS = {"MNQ": ("rth_0930_1600", 2.0), "MGC": ("london_0300_1130", 10.0)}
RT = {"MNQ": 2.32, "MGC": 3.32, "MCL": 3.32}
_PATHS: dict = {}


def _paths(product: str):
    if product not in _PATHS:
        if product == "MCL":
            import futuresres.reporting.a15_crude as c15
            h, l, c, _ = c15.mcl_paths("post")
            _PATHS[product] = (h, l, c, 100.0 / 1.0)          # one-MCL $ paths already
        else:
            import futuresres.reporting.a08_gold as a8
            h, l, c, _ = a8.era_paths("post", product, WINDOWS[product][0])
            _PATHS[product] = (h, l, c, None)                  # one-contract GROSS $ paths
    return _PATHS[product]


def expected(product: str, side: str, take_pts: float, stop_pts: float, n: int) -> dict:
    """P(take), P(stop), P(time exit) and the mean / SD of net P&L for one bracket on 2021-26 sessions."""
    import futuresres.reporting.a02_real as a2
    import futuresres.reporting.a15_crude as c15
    h, l, c, _ = _paths(product)
    mult = {"MNQ": 2.0, "MGC": 10.0, "MCL": 100.0}[product]
    if side == "short":                                       # a short's high is the long's low, mirrored
        h, l, c = -l, -h, -c
    W = np.full(len(c), take_pts * mult * n); L = np.full(len(c), stop_pts * mult * n)
    a2.STOP_FILL = "level"
    if product == "MCL":
        gross, stop, take = c15.one_bar_rule(0.0)(h * n, l * n, c * n, W, L)
    else:
        gross, stop, take = a2._bracket_day(h * n, l * n, c * n, W, L)
    net = gross - RT[product] * n
    return {"p_take": float(take.mean()), "p_stop": float(stop.mean()), "p_time": float(1 - take.mean() - stop.mean()),
            "mean_net": float(net.mean()), "sd_net": float(net.std())}


def check(shadow_csv: Path, demo_csv: Path | None = None) -> dict:
    rows = [r for r in csv.DictReader(open(shadow_csv)) if r["outcome"] in ("TAKE", "STOP", "TIME EXIT")]
    if not rows:
        return {"tickets": 0}
    exp = {"TAKE": 0.0, "STOP": 0.0, "TIME EXIT": 0.0}; obs = {"TAKE": 0, "STOP": 0, "TIME EXIT": 0}
    mu = var = 0.0; pnl = 0.0; per = []
    for r in rows:
        e = expected(r["product"], r["side"], float(r["take_pts"]), float(r["stop_pts"]), int(r["contracts"]))
        exp["TAKE"] += e["p_take"]; exp["STOP"] += e["p_stop"]; exp["TIME EXIT"] += e["p_time"]
        obs[r["outcome"]] += 1
        mu += e["mean_net"]; var += e["sd_net"] ** 2; pnl += float(r["pnl"])
        per.append({"entry": r["entry"], "product": r["product"], "outcome": r["outcome"], "pnl": float(r["pnl"]), **e})
    chi2 = sum((obs[k] - exp[k]) ** 2 / exp[k] for k in exp if exp[k] > 0)
    z = (pnl - mu) / math.sqrt(var) if var > 0 else float("nan")
    out = {"tickets": len(rows), "observed": obs, "expected": {k: round(v, 1) for k, v in exp.items()},
           "chi2_3cells": chi2, "chi2_p_approx": float(math.exp(-chi2 / 2)),        # 2 degrees of freedom
           "pnl_observed": pnl, "pnl_expected": mu, "pnl_sd": math.sqrt(var), "pnl_z": z, "per_ticket": per}
    if demo_csv and Path(demo_csv).exists():
        out["execution"] = execution_gap(rows, Path(demo_csv))
    return out


def execution_gap(shadow_rows: list[dict], demo_csv: Path) -> dict:
    """Traded tickets: the account's closing-balance change on the exit's trading day vs the shadow P&L."""
    eod = {}
    for r in csv.DictReader(open(demo_csv)):
        if r["event"] == "EOD" and r["pnl"] not in ("", None):
            eod.setdefault(r["product"], []).append((r["time"][:10], float(r["pnl"])))
    gaps = []
    for r in shadow_rows:
        if r.get("traded") != "yes":
            continue
        day = dt.datetime.fromisoformat(r["exit"]).date().isoformat()
        rec = [p for d, p in eod.get(r["product"], []) if d == day]
        if rec:
            gaps.append({"product": r["product"], "exit": r["exit"], "shadow": float(r["pnl"]), "actual": rec[-1],
                         "gap": rec[-1] - float(r["pnl"])})
    g = np.array([x["gap"] for x in gaps]) if gaps else np.array([])
    return {"traded_tickets_matched": len(gaps), "mean_gap": float(g.mean()) if len(g) else None,
            "median_gap": float(np.median(g)) if len(g) else None, "rows": gaps}


def render(r: dict) -> str:
    if not r.get("tickets"):
        return "No finished tickets in the shadow log yet."
    o, e = r["observed"], r["expected"]
    w = [f"# Demo check — {r['tickets']} finished tickets", "",
         "| outcome | observed | expected (2021–26 history, same brackets) |", "|---|---|---|"]
    w += [f"| {k} | {o[k]} | {e[k]} |" for k in ("TAKE", "STOP", "TIME EXIT")]
    w += ["", f"Chi-square {r['chi2_3cells']:.2f} (p ≈ {r['chi2_p_approx']:.2f}; below 0.05 means the live mix differs from history).",
          f"Shadow P&L ${r['pnl_observed']:+,.0f} against an expected ${r['pnl_expected']:+,.0f} ± ${r['pnl_sd']:,.0f} "
          f"(z {r['pnl_z']:+.2f}; zero edge, so the expected value is about minus the commissions)."]
    if "execution" in r:
        x = r["execution"]
        w += ["", f"Execution: {x['traded_tickets_matched']} traded tickets matched to closing balances; "
              + (f"mean gap actual − shadow ${x['mean_gap']:+,.2f}, median ${x['median_gap']:+,.2f} per ticket."
                 if x["mean_gap"] is not None else "none yet.")]
    return "\n".join(w)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("shadow"); ap.add_argument("demo", nargs="?")
    a = ap.parse_args(argv)
    print(render(check(Path(a.shadow), Path(a.demo) if a.demo else None)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

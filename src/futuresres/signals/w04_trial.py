"""W04's one trial on real data, and the economics row. Called by `python -m futuresres.signals.w04 --run`.

Refuses to run unless `reports/w04_injection.json` shows the injected effect recovered at an n no
larger than this run's post-2021 sample (STAGES.md, decisions.md 60). Writes `reports/w04_trial.md`
and `.json` (summary statistics only - no return series is committed) and appends ONE record to
`trials.jsonl`.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Final

import numpy as np
import polars as pl

from futuresres.data.daily_bars import DAILY_FILE, MARKETS, MONTHS, align, load_market
from futuresres.signals.portfolio import evaluate_portfolio
from futuresres.signals.w04 import (COMMISSION, ERA_BREAK, MICRO, N_AFTER, cost_fraction, sr_bar,
                                    weights)

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
INJECTION: Final[Path] = ROOT / "reports" / "w04_injection.json"
OUT_JSON: Final[Path] = ROOT / "reports" / "w04_trial.json"
OUT_MD: Final[Path] = ROOT / "reports" / "w04_trial.md"
FULL_BAR_T_NOTE: Final[str] = "unit-consistent SR* at the full sample's own T"


def post_2021_bar_count(path: Path = DAILY_FILE) -> int:
    """Union of the six markets' outright bar dates from 2021, Sundays dropped. Dates only."""
    pat = "^(" + "|".join(MARKETS) + f")[{MONTHS}][0-9]$"
    d = (pl.scan_csv(path).select("ts_event", "symbol").filter(pl.col("symbol").str.contains(pat))
           .select(pl.col("ts_event").str.slice(0, 10).str.to_date().alias("date"))
           .filter((pl.col("date").dt.weekday() != 7) & (pl.col("date") >= pl.date(2021, 1, 1)))
           .unique().collect())
    return d.height


def integer_book(dates, w, rets, prices, roots, post) -> dict:
    """The smallest integer-micro book the registered weights allow: each bar scaled so every held
    position rounds to at least one micro; dollar P&L net of the same per-contract costs."""
    notional = np.column_stack([prices[:, j] * MICRO[r][0] for j, r in enumerate(roots)])
    per_rt = np.array([COMMISSION + MICRO[r][1] for r in roots])
    held = w != 0
    need = np.where(held, 0.5 * notional / np.where(held, np.abs(w), 1.0), 0.0)
    k = need.max(axis=1)
    contracts = np.rint(k[:, None] * w / notional)
    pnl = np.sum(contracts * notional * rets, axis=1) - np.sum(np.abs(contracts) * per_rt, axis=1)
    p = pnl[post]
    gross_contracts = np.abs(contracts).sum(axis=1)[post]
    return {"daily_dollar_sigma": float(p.std(ddof=1)),
            "sharpe": float(p.mean() / p.std(ddof=1) * math.sqrt(252)),
            "contracts_median": float(np.median(gross_contracts)),
            "contracts_max": int(gross_contracts.max()),
            "share_of_days_over_30_micros": float((gross_contracts > 30).mean())}


def economics(sharpe: float, book_sigma: float) -> dict:
    from futuresres.reporting import w_prop_ev as ev
    rng = np.random.default_rng(20261003)
    out = {}
    for label, sig in (("sigma_150", 150.0), ("sigma_250", 250.0), ("integer_book", book_sigma)):
        e = ev.simulate_eval(rng, 6_000, sig, sharpe, hard_daily=False)
        f = ev.simulate_funded(rng, 6_000, sig, sharpe, hard_daily=False)
        out[label] = {"daily_sigma": sig, "p_pass": e["p_pass"], "expected_payout": f["expected_payout"],
                      "ev": e["p_pass"] * f["expected_payout"] - ev.FEE}
    return out


def run_trial() -> int:
    inj = json.loads(INJECTION.read_text()) if INJECTION.exists() else None
    t_post = post_2021_bar_count()
    if not inj or not inj.get("recovered") or inj["n_injection"] > t_post:
        raise SystemExit(f"refusing to run: outcome injection missing, not recovered, or at n > {t_post}")

    markets = [load_market(r) for r in MARKETS]
    dates, cols = align(markets)
    roots = list(MARKETS)
    rets = np.column_stack([cols[f"{r}:ret"] for r in roots])
    carry = np.column_stack([cols[f"{r}:carry"] for r in roots])
    prices = np.column_stack([cols[f"{r}:price"] for r in roots])
    avail = np.column_stack([np.isin(dates, m.dates) for m in markets])
    wt, wc = weights(dates, rets, carry, avail)
    cost = cost_fraction(roots, np.where(np.isfinite(prices), prices, np.nan))
    cost = np.nan_to_num(cost, nan=0.0)
    res = evaluate_portfolio(dates, [0.5 * wt, 0.5 * wc], rets, cost, ERA_BREAK, n_rotations=500)
    sleeves = {name: evaluate_portfolio(dates, [s], rets, cost, ERA_BREAK, n_rotations=0)
               for name, s in (("trend", 0.5 * wt), ("carry", 0.5 * wc))}

    post = res["post_2021"]; full = res["full"]
    bar_post = sr_bar(post["t"]); bar_full = sr_bar(full["t"])
    clears = bool(post["sharpe_net"] > bar_post)
    book = integer_book(dates, res["_weights"], rets, prices, roots, dates >= np.datetime64(ERA_BREAK))
    econ = economics(post["sharpe_net"], book["daily_dollar_sigma"])
    econ["integer_book_own_sharpe"] = economics(book["sharpe"], book["daily_dollar_sigma"])["integer_book"]

    summary = {
        "hypothesis": "W04", "n_after": N_AFTER, "first_held": res["first_held"],
        "last_bar": str(dates[-1]), "post_2021": post, "full": full, "pre_2021": res["pre_2021"],
        "bar_post_2021": bar_post, "bar_full": bar_full, "clears_post_2021_bar": clears,
        "rotation_null_post_2021": res["rotation_null_post_2021"],
        "sleeves": {k: {"post_2021": v["post_2021"], "full": v["full"]} for k, v in sleeves.items()},
        "integer_book": book, "economics_soft_limit": econ, "injection": inj,
    }
    OUT_JSON.write_text(json.dumps(summary, indent=1, default=float) + "\n")
    OUT_MD.write_text(render(summary))

    from futuresres.stats.trials import Trial, TrialLog
    log = TrialLog(ROOT / "trials.jsonl")
    rec = log.append(Trial(
        trial_id=log.next_id("t"), hypothesis_id="W04", symbol="portfolio",
        date_range=(res["first_held"], str(dates[-1])), status="completed",
        sharpe=post["sharpe_net"] / math.sqrt(252),
        params={"statistic": "post-2021 daily net Sharpe (per observation in `sharpe`)",
                "sharpe_annual_post_2021_net": post["sharpe_net"],
                "sharpe_annual_full_net": full["sharpe_net"], "bar_post_2021": bar_post,
                "bar_full": bar_full, "clears": clears, "t_post": post["t"],
                "rotation_share_at_or_above": res["rotation_null_post_2021"]["share_at_or_above_real"]},
        note="provenance=native; W04 trend+carry daily portfolio, one portfolio-level trial. decisions.md 76.",
    ))
    print(OUT_MD.read_text())
    print(f"logged {rec['trial_id']}")
    return 0


def render(s: dict) -> str:
    p, f, rn = s["post_2021"], s["full"], s["rotation_null_post_2021"]
    w: list[str] = []
    a = w.append
    a("# W04 — trend plus carry, daily portfolio: the trial")
    a("")
    a("Generated by `python -m futuresres.signals.w04 --run`. One trial; `hypotheses.yaml` W04; "
      "`decisions.md` §72–§76.")
    a("")
    a(f"**Verdict: {'CLEARS' if s['clears_post_2021_bar'] else 'DOES NOT CLEAR'} the post-2021 bar.** "
      f"Net Sharpe {p['sharpe_net']:.2f} against {s['bar_post_2021']:.2f} (T = {p['t']:,}).")
    a("")
    a("| | T | Sharpe gross | Sharpe net | bar |")
    a("|---|---|---|---|---|")
    a(f"| post-2021 (decides) | {p['t']:,} | {p['sharpe_gross']:.2f} | {p['sharpe_net']:.2f} | {s['bar_post_2021']:.2f} |")
    a(f"| full | {f['t']:,} | {f['sharpe_gross']:.2f} | {f['sharpe_net']:.2f} | {s['bar_full']:.2f} |")
    a(f"| pre-2021 | {s['pre_2021']['t']:,} | {s['pre_2021']['sharpe_gross']:.2f} | {s['pre_2021']['sharpe_net']:.2f} | — |")
    a("")
    a("| sleeve, net | post-2021 | full |")
    a("|---|---|---|")
    for k, v in s["sleeves"].items():
        a(f"| {k} | {v['post_2021']['sharpe_net']:.2f} | {v['full']['sharpe_net']:.2f} |")
    a("")
    a(f"**Rotation null (§54), post-2021 net Sharpe, {rn['n']} rotations:** mean {rn['mean']:.2f}, 95th "
      f"percentile {rn['p95']:.2f}; share at or above the real {rn['share_at_or_above_real']:.3f}.")
    a("")
    i = s["injection"]
    a(f"**Outcome injection (§60):** sought {i['sought_sharpe']:.2f} at n = {i['n_injection']:,}; mean "
      f"estimate {i['mean_estimate']:.2f} (truth {i['long_sample_truth']:.2f}), SD {i['sd_estimate']:.2f}; "
      f"power at the bar {i['power_at_bar']:.0%}; a true Sharpe of {i['sharpe_detectable_at_95pct']:.2f} "
      f"would clear it 95% of the time.")
    a("")
    b = s["integer_book"]
    a(f"**Integer-micro book:** daily $σ {b['daily_dollar_sigma']:,.0f}, Sharpe {b['sharpe']:.2f}, "
      f"median {b['contracts_median']:.0f} micros (max {b['contracts_max']}; over 30 on "
      f"{b['share_of_days_over_30_micros']:.0%} of days).")
    a("")
    a("**Economics, soft daily limit (EV per $80 evaluation; an economics row, never evidence):**")
    a("")
    for k, v in s["economics_soft_limit"].items():
        a(f"- {k}: σ ${v['daily_sigma']:,.0f}/day, P(pass) {v['p_pass']:.0%}, EV {v['ev']:+,.0f}")
    a("")
    return "\n".join(w)

"""X01 (the flatten tax) and X02 (the monthly-horizon detection floor). Measurements, no trial.

    python -m futuresres.reporting.x01_x02          # writes reports/x01_x02.{md,json}
    python -m futuresres.reporting.x01_x02 --log    # + two records in measurements.jsonl

decisions.md 77. Daily bars: GLBX.MDP3 ohlcv-1d (decisions.md 73-74), loaded by `data.daily_bars`.
Post-2021 decides (S8); full sample reported beside it. NO STRATEGY RETURN is computed: X01 uses
dispersions and fees, X02 uses dispersions and correlations of buy-and-hold monthly returns (no means).

X01 - THE FLATTEN TAX. A position held through the 17:00-18:00 break pays one micro round trip per
market per day held. Per instrument:
  fees     exchange + NFA per side, from secondary sources (CME's own fee-schedule PDF refuses
           automated download - stated in decisions.md 77, each figure labelled); the broker/clearing
           component is NOT KNOWN for this account and is ASSUMED at $1.08 per round trip - the
           residual of the programme's $1.82 MNQ round trip after MNQ's exchange and NFA fees.
  spread   ASSUMED one tick per round trip (no quote data on disk). One tick is the minimum a book
           can quote, so the true figure can only be equal or larger (decisions.md 71).
  drag     as a function of days in market d: d x cost in % of notional a year, and in Sharpe units
           for a position at its own volatility, sqrt(d) x (round trip / one day's $ sigma).

X02 - THE FLOOR. Non-overlapping calendar-month returns of each front contract. The test is the
programme's: a Sharpe must clear the unit-consistent SR* at its own T (decisions.md 73), so 80% power
for a true monthly Sharpe s needs s * sqrt(T) >= F_N + z_0.8, F_N the expected-maximum factor at N.
The single-test (one-sided 5%) floor is reported beside it. Pooling: effective number of independent
instruments from the eigenvalues of the measured monthly correlation matrix, (sum l)^2 / sum l^2.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Final

import numpy as np
from scipy.stats import norm

from futuresres.data.daily_bars import load_market
from futuresres.stats.dsr import expected_max_sharpe

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
OUT_JSON: Final[Path] = ROOT / "reports" / "x01_x02.json"
OUT_MD: Final[Path] = ROOT / "reports" / "x01_x02.md"
ERA: Final[np.datetime64] = np.datetime64("2021-01-01")

NFA: Final[float] = 0.02
BROKER_RT_ASSUMED: Final[float] = 1.82 - 2 * (0.35 + NFA)   # $1.08, residual of the MNQ assumption
#: micro -> (full-size root for prices, micro multiplier, tick $, exchange fee per side $, fee source)
MICROS: Final[dict[str, tuple[str, float, float, float, str]]] = {
    "MNQ": ("NQ", 2.0, 0.50, 0.35, "secondary: CME equity micros $0.35 (search summary, 2026 schedule)"),
    "MES": ("ES", 5.0, 1.25, 0.35, "secondary: as MNQ"),
    "MGC": ("GC", 10.0, 1.00, 0.60, "secondary: AMP notice, $0.50 -> $0.60 from 2025-02-01"),
    "MHG": ("HG", 2_500.0, 1.25, 0.62, "secondary: search summary, unverified"),
    "MCL": ("CL", 100.0, 1.00, 0.52, "secondary: search summary, unverified"),
    "M6E": ("6E", 12_500.0, 1.25, 0.43, "secondary: ~$0.45 incl. NFA and clearing (broker comparison), unverified"),
    "10Y": ("10Y", 1_000.0, 1.00, 0.30, "secondary: broker example $0.30 non-member, unverified"),
}
DAYS: Final[tuple[int, ...]] = (63, 126, 189, 252)
ELIGIBLE_MAX: Final[float] = 0.15       # Sharpe drag at d = 252; decisions.md 77
EXCLUDED_MIN: Final[float] = 0.30
MONTHLY_SHARPES: Final[tuple[float, ...]] = (0.1, 0.2, 0.3)
N_AT_REGISTRATION: Final[int] = 762     # the next trial
X_UNIVERSE: Final[tuple[str, ...]] = ("NQ", "ES", "GC", "HG", "CL", "ZN", "6E")
#: roots whose micro is not EXCLUDED by X01 (eligible or marginal) - filled from the X01 result
COST_SURVIVORS: Final[tuple[str, ...]] = ("NQ", "ES", "GC", "CL")


def x01() -> dict:
    out = {}
    for micro, (root, mult, tick, fee, src) in MICROS.items():
        m = load_market(root)
        post = m.dates >= ERA
        sd = float(m.ret[post].std(ddof=1))
        px = float(np.nanmedian(m.front_close[post]))
        if micro == "10Y":                      # yield-quoted: $1,000 per 1.00 of yield
            dollar_sigma = sd * px * mult
            notional = None
        else:
            notional = px * mult
            dollar_sigma = notional * sd
        rt = 2 * (fee + NFA) + BROKER_RT_ASSUMED + tick
        ratio = rt / dollar_sigma
        out[micro] = {
            "root": root, "post_2021_bars": int(post.sum()), "median_price": px,
            "notional": notional, "daily_dollar_sigma": dollar_sigma,
            "fee_source": src, "exchange_fee_side": fee, "round_trip_usd": rt,
            "round_trip_of_which_spread_assumed": tick, "round_trip_of_which_broker_assumed": BROKER_RT_ASSUMED,
            "round_trip_bps_notional": rt / notional * 1e4 if notional else None,
            "round_trip_over_day_sigma": ratio,
            "drag_pct_notional_by_days": ({d: d * rt / notional * 100 for d in DAYS} if notional else None),
            "sharpe_drag_by_days": {d: math.sqrt(d) * ratio for d in DAYS},
            "verdict": ("eligible" if math.sqrt(252) * ratio <= ELIGIBLE_MAX
                        else "excluded" if math.sqrt(252) * ratio > EXCLUDED_MIN else "marginal"),
        }
    return out


def _monthly(m) -> tuple[np.ndarray, np.ndarray]:
    months = m.dates.astype("datetime64[M]")
    lr = np.log1p(m.ret)
    keys, idx = np.unique(months, return_inverse=True)
    sums = np.bincount(idx, weights=lr)
    counts = np.bincount(idx)
    full = counts >= 15                          # drop the partial first and last months
    return keys[full], sums[full]


def _meff(c: np.ndarray) -> float:
    lam = np.linalg.eigvalsh(c)
    return float(lam.sum() ** 2 / (lam ** 2).sum())


def x02() -> dict:
    series = {}
    for r in X_UNIVERSE:
        k, s = _monthly(load_market(r))
        series[r] = dict(zip(k.tolist(), s))
    common = sorted(set.intersection(*(set(v) for v in series.values())))
    mat = np.array([[series[r][k] for r in X_UNIVERSE] for k in common])
    months = np.array(common, dtype="datetime64[M]")
    f_n = expected_max_sharpe(N_AT_REGISTRATION, 1.0)
    z80, z95 = norm.ppf(0.8), norm.ppf(0.95)
    out: dict = {"universe": list(X_UNIVERSE), "F_N": f_n, "N": N_AT_REGISTRATION, "eras": {}}
    for name, mask in (("full", np.ones(len(months), bool)), ("post_2021", months >= ERA.astype("datetime64[M]"))):
        x = mat[mask]
        c = np.corrcoef(x.T)
        iu = np.triu_indices(len(X_UNIVERSE), 1)
        meff_signed = _meff(c); meff_abs = _meff(np.abs(c))
        t = int(mask.sum())
        floors = {}
        for s in MONTHLY_SHARPES:
            sr_floor = ((f_n + z80) / s) ** 2
            alpha_floor = ((z95 + z80) / s) ** 2
            floors[s] = {"floor_sr_star": sr_floor, "floor_single_test": alpha_floor,
                         "pooled_n_abs": t * meff_abs, "pooled_n_signed": t * meff_signed,
                         "clears_sr_star_abs": bool(t * meff_abs >= sr_floor),
                         "clears_single_test_abs": bool(t * meff_abs >= alpha_floor),
                         "single_instrument_months": t,
                         "single_instrument_clears_sr_star": bool(t >= sr_floor),
                         "power_at_sr_star_abs": float(norm.cdf(s * math.sqrt(t * meff_abs) - f_n))}
        keep = [j for j, r in enumerate(X_UNIVERSE) if r in COST_SURVIVORS]
        meff_sub = _meff(np.abs(c[np.ix_(keep, keep)]))
        sub = {s: {"pooled_n": t * meff_sub, "floor_sr_star": ((f_n + z80) / s) ** 2,
                   "clears_sr_star": bool(t * meff_sub >= ((f_n + z80) / s) ** 2),
                   "power_at_sr_star": float(norm.cdf(s * math.sqrt(t * meff_sub) - f_n))}
               for s in MONTHLY_SHARPES}
        out["eras"][name] = {
            "cost_survivors": list(COST_SURVIVORS), "m_eff_cost_survivors": meff_sub,
            "floors_cost_survivors": sub,
            "months": t,
            "monthly_vol_pct": {r: float(x[:, j].std(ddof=1) * 100) for j, r in enumerate(X_UNIVERSE)},
            "corr": {f"{X_UNIVERSE[i]}-{X_UNIVERSE[j]}": float(c[i, j]) for i, j in zip(*iu)},
            "mean_abs_pairwise_corr": float(np.abs(c[iu]).mean()),
            "m_eff_signed": meff_signed, "m_eff_abs": meff_abs,
            "sr_star_monthly_at_T": f_n / math.sqrt(t),
            "floors": floors,
        }
    return out


def render(r: dict) -> str:
    w: list[str] = []
    a = w.append
    a("# X01 and X02 — the flatten tax and the monthly-horizon floor")
    a("")
    a("Generated by `python -m futuresres.reporting.x01_x02`. Measurements; no strategy return, no trial. "
      "`decisions.md` §77. Post-2021 decides.")
    a("")
    a("## X01 — one micro round trip per day held")
    a("")
    a("| micro | exch./side | round trip $ | of which assumed | bps of notional | / day's $σ | Sharpe drag d=63 | 126 | 189 | 252 | verdict |")
    a("|---|---|---|---|---|---|---|---|---|---|---|")
    for k, v in r["x01"].items():
        sd = {int(k2): v2 for k2, v2 in v["sharpe_drag_by_days"].items()}
        bps = f"{v['round_trip_bps_notional']:.2f}" if v["round_trip_bps_notional"] else "n/a (yield)"
        a(f"| {k} | ${v['exchange_fee_side']:.2f} | ${v['round_trip_usd']:.2f} | "
          f"${v['round_trip_of_which_broker_assumed'] + v['round_trip_of_which_spread_assumed']:.2f} | {bps} | "
          f"{v['round_trip_over_day_sigma']:.2%} | {sd[63]:.2f} | {sd[126]:.2f} | {sd[189]:.2f} | {sd[252]:.2f} | "
          f"**{v['verdict']}** |")
    a("")
    a(f"Verdict at d = 252: eligible ≤ {ELIGIBLE_MAX}, excluded > {EXCLUDED_MIN} of Sharpe. Drag scales "
      "with √d. Annual drag in % of notional is d × bps / 100.")
    a("")
    x = r["x02"]
    a(f"## X02 — monthly floor (F_N = {x['F_N']:.2f} at N = {x['N']})")
    a("")
    for era, e in x["eras"].items():
        a(f"### {era}: {e['months']} months; M_eff {e['m_eff_abs']:.2f} (|ρ|), {e['m_eff_signed']:.2f} (signed); "
          f"mean |ρ| {e['mean_abs_pairwise_corr']:.2f}")
        a("")
        a("| monthly Sharpe | SR\\* floor (months) | single-test floor | one instrument | pooled, all 7 (power) | pooled, cost survivors (power) |")
        a("|---|---|---|---|---|---|")
        for s, f in e["floors"].items():
            g = e["floors_cost_survivors"][s]
            a(f"| {s} | {f['floor_sr_star']:.0f} | {f['floor_single_test']:.0f} | {f['single_instrument_months']} | "
              f"{f['pooled_n_abs']:.0f} {'✓' if f['clears_sr_star_abs'] else '✗'} ({f['power_at_sr_star_abs']:.0%}) | "
              f"{g['pooled_n']:.0f} {'✓' if g['clears_sr_star'] else '✗'} ({g['power_at_sr_star']:.0%}) |")
        a("")
        a(f"Cost survivors {', '.join(e['cost_survivors'])}: M_eff {e['m_eff_cost_survivors']:.2f}. "
          "✓/✗ = pooled n against the SR\\* floor; power = P(clear SR\\*) at that true monthly Sharpe.")
        a("")
    return "\n".join(w)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.reporting.x01_x02")
    ap.add_argument("--log", action="store_true")
    args = ap.parse_args(argv)
    if args.log and OUT_JSON.exists():
        r = json.loads(OUT_JSON.read_text())
    else:
        r = {"x01": x01(), "x02": x02()}
        OUT_JSON.write_text(json.dumps(r, indent=1, default=str) + "\n")
        r = json.loads(OUT_JSON.read_text())
    OUT_MD.write_text(render(r))
    print(OUT_MD.read_text())
    if args.log:
        from futuresres.stats.trials import Trial, TrialLog
        log = TrialLog(ROOT / "measurements.jsonl")
        for kind, key in (("flatten_tax", "x01"), ("monthly_floor", "x02")):
            rec = log.append(Trial(
                trial_id=log.next_id("m"), hypothesis_id="X-series", symbol="universe",
                date_range=("2010-06-06", "2026-09-11"), status="completed",
                params={"kind": kind, **({"by_micro": {k: {kk: v[kk] for kk in ("round_trip_usd",
                        "round_trip_over_day_sigma", "verdict")} for k, v in r["x01"].items()}}
                        if key == "x01" else {"eras": {e: {kk: v[kk] for kk in ("months", "m_eff_abs",
                        "m_eff_signed", "mean_abs_pairwise_corr")} for e, v in r["x02"]["eras"].items()}})},
                note=f"kind=measurement; NOT a trial and NOT counted in N. X-series {key.upper()}. decisions.md 77.",
            ))
            print(f"logged {rec['trial_id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

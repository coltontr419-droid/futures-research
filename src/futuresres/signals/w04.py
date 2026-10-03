"""W04 - trend plus carry, daily portfolio. hypotheses.yaml W04; decisions.md 72-75.

    python -m futuresres.signals.w04 --inject      # outcome injection, synthetic; no real price read
    python -m futuresres.signals.w04 --run         # THE TRIAL: one record in trials.jsonl

A SIGNAL MODULE: it turns features into POSITIONS. Returns enter only as features (a trailing sum for
trend, a variance for sizing) - the scored series is built in `portfolio.evaluate_portfolio`, the one
place weights meet returns (test_signal_module_boundary).

Every rule below is the registered one; none is a choice made here.
  TREND   sign of the trailing 252-bar log return, at month end.
  CARRY   sign(C - expanding mean of the market's own C), at month end, once 252 carry readings exist.
  SIZE    each market at 1 / EWMA volatility (centre of mass 60 bars, demeaned, MOP's estimator); each
          sleeve scaled to unit ex-ante volatility on the EWMA covariance (same centre of mass); the
          two sleeves 50/50, netted per market.
  TIMING  month-end D's weights are first held on bar D+2 - one session after the reopen on D's
          evening, because a UTC close (19:00/20:00 ET) postdates that reopen - and held through bar
          D'+1 of the next month end D'.
  COSTS   one micro round trip per market per bar held: ASSUMED $1.82 commission plus one tick,
          in fractions of one micro's notional.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Final

import numpy as np

from futuresres.signals.portfolio import evaluate_portfolio

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
LOOKBACK: Final[int] = 252
COM: Final[float] = 60.0
DELAY: Final[int] = 2                       # first held bar after month-end bar D
ERA_BREAK: Final[str] = "2021-01-01"
N_AFTER: Final[int] = 761                   # N once this trial is logged

COMMISSION: Final[float] = 1.82             # ASSUMED, per micro round trip (decisions.md 71)
#: micro multiplier and one tick in dollars. ZN trades through the micro 10-year YIELD contract,
#: $10 per basis point, which has no price notional: its equivalent is ZN notional x 10 / DV01,
#: with ZN's DV01 ASSUMED at $70 (labelled; the cost is reported gross and net).
MICRO: Final[dict[str, tuple[float, float]]] = {
    "NQ": (2.0, 0.50), "GC": (10.0, 1.00), "HG": (2_500.0, 1.25),
    "CL": (100.0, 1.00), "6E": (12_500.0, 1.25), "ZN": (1_000.0 * 10.0 / 70.0, 1.00),
}


def month_ends(dates: np.ndarray) -> np.ndarray:
    """Indices of the last bar of each calendar month (the final, possibly partial, month included)."""
    m = dates.astype("datetime64[M]")
    return np.flatnonzero(np.r_[m[1:] != m[:-1], True])


def ewma_cov(r: np.ndarray, com: float = COM) -> np.ndarray:
    """EWMA covariance through each bar, demeaned by an EWMA mean: shape (T, M, M). Daily units."""
    a = 1.0 / (1.0 + com)
    t, m = r.shape
    mean = np.zeros(m); cov = np.zeros((m, m)); out = np.empty((t, m, m))
    for i in range(t):
        x = r[i]
        mean = (1 - a) * mean + a * x
        d = x - mean
        cov = (1 - a) * cov + a * np.outer(d, d)
        out[i] = cov
    return out


def sleeve_signs(rets: np.ndarray, carry: np.ndarray, avail: np.ndarray, ends: np.ndarray
                 ) -> tuple[np.ndarray, np.ndarray]:
    """(trend, carry) signs at each month end, shape (len(ends), M); 0 where not yet eligible."""
    lr = np.log1p(rets)
    csum = np.vstack([np.zeros(rets.shape[1]), np.cumsum(lr, axis=0)])
    seen = np.cumsum(avail, axis=0)                       # bars of own history through each bar
    finite = np.isfinite(carry)
    c0 = np.where(finite, carry, 0.0)
    c_sum = np.cumsum(c0, axis=0); c_n = np.cumsum(finite, axis=0)
    tr = np.zeros((len(ends), rets.shape[1])); ca = np.zeros_like(tr)
    for k, d in enumerate(ends):
        ok = seen[d] >= LOOKBACK
        if d + 1 >= LOOKBACK:
            past = csum[d + 1] - csum[d + 1 - LOOKBACK]
            tr[k] = np.where(ok, np.sign(past), 0.0)
        cok = (c_n[d] >= LOOKBACK) & finite[d]
        mean = np.divide(c_sum[d], np.maximum(c_n[d], 1))
        ca[k] = np.where(cok, np.sign(carry[d] - mean), 0.0)
    return tr, ca


def _unit_vol(sig: np.ndarray, cov: np.ndarray) -> np.ndarray:
    vol = np.sqrt(np.clip(np.diag(cov), 0, None))
    u = np.divide(sig, vol, out=np.zeros_like(sig), where=vol > 0)
    s = math.sqrt(max(float(u @ cov @ u), 0.0))
    return u / s if s > 0 else u * 0.0


def weights(dates: np.ndarray, rets: np.ndarray, carry: np.ndarray, avail: np.ndarray
            ) -> tuple[np.ndarray, np.ndarray]:
    """Per-bar weights of each sleeve, ALREADY DELAYED to the bars they are held on: (T, M) each,
    each sleeve at unit ex-ante daily volatility before the 50/50 combination."""
    ends = month_ends(dates)
    cov = ewma_cov(np.nan_to_num(rets))
    tr, ca = sleeve_signs(rets, carry, avail, ends)
    t = len(dates)
    wt = np.zeros_like(rets); wc = np.zeros_like(rets)
    for k, d in enumerate(ends):
        start = d + DELAY
        stop = ends[k + 1] + DELAY if k + 1 < len(ends) else t
        if start >= t:
            break
        wt[start:stop] = _unit_vol(tr[k], cov[d])
        wc[start:stop] = _unit_vol(ca[k], cov[d])
    return wt, wc


def cost_fraction(roots: list[str], prices: np.ndarray) -> np.ndarray:
    """One micro round trip as a fraction of one micro's notional, per bar and market."""
    out = np.empty_like(prices)
    for j, r in enumerate(roots):
        mult, tick = MICRO[r]
        out[:, j] = (COMMISSION + tick) / (prices[:, j] * mult)
    return out


def sr_bar(t_obs: int, n: int = N_AFTER) -> float:
    """Unit-consistent SR*, annualised: null variance of a daily Sharpe at T observations (decisions.md 73)."""
    from futuresres.stats.dsr import expected_max_sharpe
    return expected_max_sharpe(n, 1.0 / t_obs) * math.sqrt(252)


# --------------------------------------------------------------------------- outcome injection
def synthetic_world(rng, t: int, kappa: float, m: int = 6) -> dict:
    """Six markets, Student-t(5) daily returns, persistent carry; an edge of size kappa (in units of
    each market's daily sigma) planted on the CARRY sign the registered rule will compute."""
    dates = np.datetime64("1900-01-01") + np.arange(int(t * 7 / 5) + 30)
    dates = dates[np.is_busday(dates)][:t]
    sig = rng.uniform(0.005, 0.02, m)
    eps = rng.standard_t(5, (t, m)) / math.sqrt(5 / 3)
    carry = np.empty((t, m)); c = rng.normal(0, 0.05, m)
    for i in range(t):                                   # AR(1), half-life ~ 6 months
        c = 0.9945 * c + rng.normal(0, 0.004, m)
        carry[i] = c
    avail = np.ones((t, m), bool)
    _, ca = sleeve_signs(np.zeros((t, m)), carry, avail, month_ends(dates))
    held = np.zeros((t, m)); ends = month_ends(dates)
    for k, d in enumerate(ends):
        stop = ends[k + 1] + DELAY if k + 1 < len(ends) else t
        held[d + DELAY:stop] = ca[k]
    rets = sig * (eps + kappa * held)
    return {"dates": dates, "rets": rets, "carry": carry, "avail": avail,
            "cost": np.full((t, m), 0.0)}


def pipeline_sharpe(w: dict) -> float:
    wt, wc = weights(w["dates"], w["rets"], w["carry"], w["avail"])
    res = evaluate_portfolio(w["dates"], [0.5 * wt, 0.5 * wc], w["rets"], w["cost"], ERA_BREAK,
                             n_rotations=0)
    return res["full"]["sharpe_net"]


def calibrate(target: float, seed: int = 7, t_long: int = 60_000) -> float:
    """kappa such that the pipeline's own long-sample Sharpe equals the target."""
    lo, hi = 0.0, 0.5
    for _ in range(14):
        mid = (lo + hi) / 2
        s = pipeline_sharpe(synthetic_world(np.random.default_rng(seed), t_long, mid))
        lo, hi = (mid, hi) if s < target else (lo, mid)
    return (lo + hi) / 2


def inject(t_run: int, sought: float, reps: int = 200, seed: int = 20261003) -> dict:
    kappa = calibrate(sought)
    truth = pipeline_sharpe(synthetic_world(np.random.default_rng(99), 60_000, kappa))
    rng = np.random.default_rng(seed)
    est = np.array([pipeline_sharpe(synthetic_world(rng, t_run, kappa)) for _ in range(reps)])
    bar = sr_bar(t_run)
    se_mc = est.std(ddof=1) / math.sqrt(reps)
    bias = float(est.mean() - truth)
    return {"sought_sharpe": sought, "kappa": kappa, "long_sample_truth": truth,
            "n_injection": t_run, "reps": reps, "mean_estimate": float(est.mean()),
            "sd_estimate": float(est.std(ddof=1)), "bias": bias, "mc_se": float(se_mc),
            "recovered": bool(abs(bias) <= 3 * se_mc + 0.05 and abs(truth - sought) <= 0.05),
            "bar": bar, "power_at_bar": float((est > bar).mean()),
            "sharpe_detectable_at_95pct": float(bar + 1.645 * est.std(ddof=1))}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.signals.w04")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--inject", action="store_true")
    g.add_argument("--run", action="store_true")
    ap.add_argument("--t-run", type=int, default=None, help="post-2021 bars (injection n)")
    args = ap.parse_args(argv)
    if args.inject:
        from futuresres.signals.w04_trial import post_2021_bar_count
        t_run = args.t_run or post_2021_bar_count()
        r = inject(t_run, sought=sr_bar(t_run))
        out = ROOT / "reports" / "w04_injection.json"
        out.write_text(json.dumps(r, indent=1) + "\n")
        print(json.dumps(r, indent=1))
        return 0 if r["recovered"] else 1
    from futuresres.signals.w04_trial import run_trial
    return run_trial()


if __name__ == "__main__":
    sys.exit(main())

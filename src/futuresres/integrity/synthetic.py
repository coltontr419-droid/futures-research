"""Series with no edge by construction — CLAUDE.md §7.2.

Three generators, each destroying a different thing while preserving another. Running the
pipeline on all three is what makes "the pipeline reports nothing" mean something: a
harness can survive one null by luck and fail another.

    bootstrap_shuffle   preserves the return DISTRIBUTION, destroys all serial structure
    garch11             preserves VOLATILITY CLUSTERING and fat tails, has no drift edge
    random_walk         preserves drift and volatility only — the simplest possible null

CALIBRATION. The GARCH defaults are fitted to BTCUSDT 1m over 2020-01→2026-08 as measured
in `reports/data_quality.md` and its underlying bars:

    std        0.000915  per minute (0.0915%)
    skew      −0.218
    kurtosis   199.9     non-excess
    ACF(r²)    0.358 at 1m, 0.231 at 5m, 0.096 at 30m, 0.060 at 60m

Gaussian innovations cannot produce a kurtosis near 200 at any persistence, so the default
innovation is a standardised Student-t. This matters for §7.2: a noise test run on a series
far thinner-tailed than the real thing would be a weaker test than the data deserves, and
would let a harness through that only fails on genuine tails.

NO EDGE BY CONSTRUCTION. Every generator here produces returns whose conditional mean is
independent of anything observable at the time. Volatility is predictable in `garch11`; the
SIGN of the next return is not. Any strategy that appears profitable on this data is
measuring the harness, not the market.

CARRIED OVER FROM CRYPTO — THE MOMENTS ARE BTC's, NOT MNQ's. The GARCH defaults and the
BTC_1M_STD / BTC_ETH_1M_CORRELATION constants below describe the crypto series. They are
kept so the ported integrity tests still run and still pass, which proves the HARNESS
survived the port — but a null generated from BTC moments is not the null this project
needs.

Before the detection floor is re-measured (CLAUDE_FUTURES.md build step 8), fit these to
MNQ and MGC: the target std, the kurtosis via `nu`, and the volatility-clustering ACF. The
floor is expected to IMPROVE because index kurtosis is roughly an order of magnitude lower,
but that is a prediction and the whole point of measuring is that predictions get falsified.
"""

from __future__ import annotations

from typing import Callable, Final

import numpy as np

#: Fitted to BTCUSDT 1m, 2020-01 → 2026-08.
BTC_1M_STD: Final[float] = 0.000915
BTC_1M_KURTOSIS: Final[float] = 199.9
BTC_1M_SQ_ACF1: Final[float] = 0.358

#: GARCH(1,1) defaults, chosen by matching realized moments against the table above.
#: α=0.20, β=0.79 reproduces the lag-1 squared-return autocorrelation almost exactly
#: (0.363 against a measured 0.358), which is the property §7.2 actually names.
#:
#: ν=8 rather than something smaller is a deliberate trade. Very low ν (4–5) reaches a
#: sample kurtosis nearer the real 199.9, but only unstably: at ν=4.5 the same parameters
#: gave a sample kurtosis of 38 on one seed and 499 on another, because the fourth moment
#: of t(4.5) is barely finite and a handful of draws dominate it. A null whose own moments
#: swing by 13× between seeds makes a poor yardstick. ν=8 gives a stable kurtosis near 70
#: — far beyond the Gaussian 3, short of the real 200.
#:
#: That shortfall is a real limitation, not a rounding detail: this null is slightly
#: gentler in the tails than the traded series. `bootstrap_shuffle` applied to REAL
#: returns is the companion null that closes the gap, since it preserves the empirical
#: distribution exactly, kurtosis 199.9 included.
DEFAULT_ALPHA: Final[float] = 0.20
DEFAULT_BETA: Final[float] = 0.79
DEFAULT_NU: Final[float] = 8.0
DEFAULT_BURN: Final[int] = 5_000


def random_walk(
    n: int, rng: np.random.Generator, *, drift: float = 0.0, vol: float = BTC_1M_STD
) -> np.ndarray:
    """iid normal returns. The simplest null: no structure of any kind."""
    return rng.normal(drift, vol, n)


def bootstrap_shuffle(returns: np.ndarray, rng: np.random.Generator,
                      n: int | None = None) -> np.ndarray:
    """iid resample with replacement.

    Keeps the marginal distribution exactly — every fat tail in the original is still
    available — while destroying autocorrelation, volatility clustering and any genuine
    edge. A strategy that survives this is reading the distribution, not the sequence.
    """
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    if r.size == 0:
        raise ValueError("no finite returns to resample")
    return rng.choice(r, size=n if n is not None else r.size, replace=True)


def garch11(
    n: int,
    rng: np.random.Generator,
    *,
    target_std: float = BTC_1M_STD,
    alpha: float = DEFAULT_ALPHA,
    beta: float = DEFAULT_BETA,
    nu: float | None = DEFAULT_NU,
    mean: float = 0.0,
    burn: int = DEFAULT_BURN,
) -> np.ndarray:
    """GARCH(1,1) with Student-t innovations and zero conditional-mean edge.

        σ²_t = ω + α·ε²_{t-1} + β·σ²_{t-1}
        ε_t  = σ_t · z_t

    ω is derived from `target_std` so the unconditional variance matches the real series:
    ω = σ²(1 − α − β). Innovations are standardised to unit variance, so ν changes the
    tail without changing the scale — otherwise fattening the tail would silently inflate
    volatility too and confound the two effects.

    `mean` is a constant drift only. It is deliberately not a function of past returns:
    the moment the conditional mean depends on anything observable, the series has an edge
    and is no longer a null.
    """
    if not 0 < alpha + beta < 1:
        raise ValueError(
            f"alpha+beta must be in (0,1) for stationarity, got {alpha + beta}"
        )
    if nu is not None and nu <= 4:
        raise ValueError(f"nu must exceed 4 for finite kurtosis, got {nu}")
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")

    total = n + burn
    if nu is None:
        z = rng.standard_normal(total)
    else:
        z = rng.standard_t(nu, total) / np.sqrt(nu / (nu - 2.0))  # unit variance

    var = target_std ** 2
    omega = var * (1.0 - alpha - beta)

    eps = np.empty(total)
    sigma2 = var
    prev_eps2 = var
    for t in range(total):
        sigma2 = omega + alpha * prev_eps2 + beta * sigma2
        e = np.sqrt(sigma2) * z[t]
        eps[t] = e
        prev_eps2 = e * e

    return mean + eps[burn:]


def series_with_edge(
    n: int,
    rng: np.random.Generator,
    strength: float,
    *,
    persistence: int = 500,
    vol: float = BTC_1M_STD,
) -> np.ndarray:
    """A null series plus a slow, persistent, genuinely tradeable drift.

    `strength` is in units of one bar's volatility: the conditional mean of the next
    return is ±strength·vol depending on a regime that flips every few hundred bars. The
    regime is a function of past noise only, so the edge is real and causal — a moving
    average can see it without anything peeking forward.

    Persistence matters as much as strength. An edge that flips every bar is invisible to
    a crossover rule at any amplitude, so a power curve built on one would measure the
    signal family rather than the pipeline.
    """
    state = np.sign(
        np.convolve(rng.standard_normal(n), np.ones(persistence) / persistence, mode="same")
    )
    noise = rng.normal(0, vol, n)
    out = np.empty(n)
    out[0] = noise[0]
    out[1:] = strength * vol * state[:-1] + noise[1:]
    return out


#: Measured BTC/ETH 1m log-return correlation over 3,494,880 aligned bars, 2020-01→2026-08.
#: Stable by year: 0.759 (2025) to 0.868 (2022).
BTC_ETH_1M_CORRELATION: Final[float] = 0.801


def pooled_series_with_edge(
    n: int,
    rng: np.random.Generator,
    strength: float,
    *,
    correlation: float = BTC_ETH_1M_CORRELATION,
    n_instruments: int = 2,
    persistence: int = 500,
    vol: float = BTC_1M_STD,
) -> np.ndarray:
    """Equal-weight basket of correlated instruments sharing one edge regime.

    `strength` stays in units of a SINGLE instrument's volatility, so the swept parameter
    means the same thing pooled or not and the two floors are directly comparable.

    HOW MUCH POOLING CAN POSSIBLY HELP. Noise is built as
    `√ρ·common + √(1−ρ)·idiosyncratic`, giving each leg unit variance and every pair
    correlation ρ. A k-leg equal-weight basket then has noise variance ρ + (1−ρ)/k, so the
    SNR gain over one leg is 1/√(ρ + (1−ρ)/k). At the measured ρ = 0.801 and k = 2 that is
    **1.054×** — against the 1.414× that independent instruments would give. Correlation
    eats 87% of the diversification.

    Pooling the SAMPLE instead of the prices gives the same number, not a different one:
    two series correlated at ρ carry an effective sample size of 2n/(1+ρ) rather than 2n,
    so the gain is √(2/(1+ρ)) = 1.054× as well. There is no version of "use both
    instruments" that escapes ρ.
    """
    if not 0.0 <= correlation < 1.0:
        raise ValueError(f"correlation must be in [0,1), got {correlation}")
    if n_instruments < 1:
        raise ValueError(f"n_instruments must be >= 1, got {n_instruments}")

    state = np.sign(
        np.convolve(rng.standard_normal(n), np.ones(persistence) / persistence, mode="same")
    )
    common = rng.standard_normal(n)
    idio = rng.standard_normal((n_instruments, n))
    legs = np.sqrt(correlation) * common + np.sqrt(1.0 - correlation) * idio
    basket_noise = legs.mean(axis=0) * vol

    out = np.empty(n)
    out[0] = basket_noise[0]
    out[1:] = strength * vol * state[:-1] + basket_noise[1:]
    return out


def causal_signal_fn(window: int = 60) -> "Callable[[np.ndarray], np.ndarray]":
    """A strictly causal signal function: sign of the trailing mean return.

    Bar t uses returns[t−window+1 … t] and nothing else, so truncating the series after t
    cannot change it. This is the clean baseline the §7.1 calibration injects leaks into,
    and its false-positive rate is what makes any detection rate interpretable.
    """

    def signal(returns: np.ndarray) -> np.ndarray:
        r = np.asarray(returns, dtype=float)
        out = np.zeros(r.size, dtype=bool)
        if r.size >= window:
            c = np.concatenate([[0.0], np.cumsum(r)])
            out[window - 1:] = (c[window:] - c[:-window]) > 0
        return out

    return signal


def leaky_signal_fn(
    window: int = 60, leak_span: int = 1
) -> "Callable[[np.ndarray], np.ndarray]":
    """The same signal, contaminated with the mean of the NEXT `leak_span` bars.

    Bar t reads returns[t+1 … t+leak_span] — information that cannot exist at t. Where the
    future window runs past the end of the series it is simply absent, which is exactly
    what happens when the series is truncated: that is the asymmetry the re-derivation
    check exploits.

    `leak_span` is the calibration's independent variable. The shift test it replaces
    could only see leaks spanning many bars; the point of sweeping 1, 5 and 20 is to find
    out whether the replacement has the same blind spot.
    """

    def signal(returns: np.ndarray) -> np.ndarray:
        r = np.asarray(returns, dtype=float)
        n = r.size
        out = np.zeros(n, dtype=bool)
        if n < window:
            return out
        c = np.concatenate([[0.0], np.cumsum(r)])
        trailing = np.zeros(n)
        trailing[window - 1:] = (c[window:] - c[:-window]) / window

        # mean of returns[t+1 … t+leak_span], truncated at the end of the series
        t = np.arange(n)
        lo = t + 1
        hi = np.minimum(t + 1 + leak_span, n)
        count = hi - lo
        with np.errstate(invalid="ignore", divide="ignore"):
            ahead = np.where(count > 0, (c[hi] - c[lo]) / np.maximum(count, 1), 0.0)

        out[window - 1:] = (trailing + ahead)[window - 1:] > 0
        return out

    return signal


def describe(returns: np.ndarray) -> dict[str, float]:
    """Moments and volatility clustering, for comparing a generator against the real thing."""
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    c = r - r.mean()
    m2 = float((c ** 2).mean())
    s = r ** 2
    s = s - s.mean()
    denom = float((s * s).sum())

    def acf(lag: int) -> float:
        return float((s[:-lag] * s[lag:]).sum() / denom) if denom > 0 and lag < s.size else np.nan

    return {
        "n": float(r.size),
        "mean": float(r.mean()),
        "std": float(r.std(ddof=1)),
        "skew": float((c ** 3).mean() / m2 ** 1.5) if m2 > 0 else np.nan,
        "kurtosis": float((c ** 4).mean() / m2 ** 2) if m2 > 0 else np.nan,
        "sq_acf_1": acf(1),
        "sq_acf_5": acf(5),
        "sq_acf_30": acf(30),
        "sq_acf_60": acf(60),
    }

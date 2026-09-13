"""The matched control for STATE conditions — the S6 analogue the P-series needs.

WHY THIS EXISTS. `decisions.md` §54 settled that the P-series placebo question was misframed
rather than open, but only in part. Three of the four pieces were already answered:

    the LOCATION placebo (§37)      a category error here — a state has no location, so
                                    there is no arbitrary region to displace it to
    the ALIGNMENT null              already inside every S7 run as `signed_rotation_null`,
                                    which preserves firing count AND clustering exactly and
                                    destroys only the alignment with returns
    the HASH control (F14)          not rate-matched (fixed clock slots), and scoped to
                                    harness validation at ~45k events (§30)

The fourth was genuinely open, and it is what this module closes. **A state condition can
beat the rotation null by firing in favourable REGIMES rather than by carrying information.**
Rotation moves the firings into different times of day, different volatility regimes and
different years, so a condition that fires disproportionately at the open, or in high
volatility, or (like P01) mostly in recent years, is compared against a null that does not
hold those things constant. That is a difference in EXPOSURE, not in reaction — the same
sentence `levels/placebo.py` was written to enforce, arriving at the same programme from the
other direction.

THE DESIGN IS THE LEVEL DESIGN, TRANSPOSED. `make_region_placebo` matched the NUISANCE
(distance from price, which determines exposure) and varied the CLAIM (a real level against
an arbitrary region). Here:

    nuisance, matched       time-of-day bucket, volatility quantile
    claim, varied           the state HOLDS against the state does NOT hold
    diagnostic, free        the YEAR distribution — deliberately not matched, see below

For each real firing, a control firing is drawn from a DIFFERENT SESSION in the same
time-of-day bucket and the same volatility quantile, where the state did not hold. The
condition cannot then beat the control by firing in favourable regimes, because the control
fires in the same regimes by construction. **That claim is verified rather than asserted** —
`tests/test_state_control.py` builds a deliberately regime-loaded fake condition that DOES
beat a rotation null and confirms it does NOT beat this control, and a genuine state effect
that does.

THERE ARE TWO EXCLUSION MODES, AND THE CHOICE IS FORCED BY THE FIRING RATE — NOT FREE.

`"strict"` excludes whole sessions in which the state fires anywhere. That is the right rule
for a SESSION-LEVEL state: volume share is session-persistent (§47 measured autocorrelation
0.952, a 14.15-session half-life), so a quiet minute of a session that fired elsewhere is
contaminated by the very state it stands in for. It also makes "different session" automatic.

`"bar"` excludes only the firing bars, and still requires a different session. It exists
because strict mode is STRUCTURALLY UNAVAILABLE to a state that fires several times a
session, which was measured rather than reasoned about. The P03-shaped thin-move state on NQ
fires 7.81 times per session and touches **92.6% of sessions**, leaving a clean pool of 265
sessions out of 3,559 — and that residue is not representative, ranging from 0% of 2011 to
17.5% of 2025, so 37.4% of pairs fell back across years and the match FAILED. Under
independence such a state would touch ~99.9% of sessions, so no bucketing and no threshold
rescues strict mode here: it is arithmetic, not tuning.

**Bar mode's contamination costs power, not validity.** Its control bars sit in sessions that
fire elsewhere (the state clusters at 7.38x Poisson variance), so they are partly in-state,
which shrinks a real difference toward zero. It cannot manufacture one: the regimes are still
matched pair by pair, so a regime-loaded condition still has nothing to gain. A conservative
control is a different thing from a broken one, and `tests/test_state_control.py` runs the
regime-loaded fake through bar mode too rather than assuming the argument transfers.

`session_clustering()` reports the numbers the choice turns on, so an entry records evidence
for its mode rather than a preference.

THE YEAR IS MATCHED WHERE POSSIBLE, AND THE FAILURE TO MATCH IT IS THE DIAGNOSTIC. The first
version of this module left the year free and tested it by the same ratio check as the other
two axes, on the reasoning that a state whose base rate TRENDS — P01's micro share went 0.292
to 0.822 over 7.3 years (§48) — should be blocked rather than quietly corrected. **That design
was measured and it does not work.** With the year unmatched, a condition carrying NO year
trend at all already deviates 0.37 (median, up to 0.55) at the real sample's shape, ~258
sessions per year over 16 years, against a 0.25 tolerance — because how many high-volatility
sessions land in each year is itself random. The check would have failed well-behaved
conditions at the sample size it was built for, which makes it a broken check rather than a
strict one.

The fix is in the CONSTRUCTION, not the tolerance — loosening it until the synthetic world
passed would have been fitting the null to the test, the error `levels/placebo.py` records
about its own bounds. The control is now drawn from the same YEAR as well, falling back to the
full (time-of-day, volatility) pool only where that year has no eligible session, and the
FALLBACK RATE is reported as its own number. This is strictly better on both counts: a
non-trending condition matches cleanly, and a trending one runs out of same-year sessions in
exactly its late years and is blocked by ERA FALLBACK, which names the defect more precisely
than a year-share ratio did. A pure adoption clock now cannot produce a differential at all,
because the adoption level is held constant inside every pair.

THE CONTROL TAKES ITS OWN DIRECTION. `sweep_stage1` records the distinction: L07's placebo
inherited the real zone's direction because direction was a property of the GAP, while
L02/L03/L04's takes its own because direction is a property of the EVENT. For a state
condition the direction is computed at the bar by the same rule (the sign of the move being
faded, say), so it is a property of the event and the control must take its own. Forcing the
real firing's sign onto the control would compare a rule against a counterfactual that never
happened. Callers run the SAME rule at the control bar; this module supplies only the bars.

WHAT THIS MODULE DOES NOT DO. It never touches prices and never builds a return series —
`tests/test_signal_module_boundary.py` is the guard, and the reason is the drift bias of
2026-08-27. Callers compute per-event outcomes and hand them back to `paired_state_stats`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Final, Sequence

import numpy as np

#: How far the control's time-of-day and volatility distributions may differ from the real
#: firings', as a share ratio per bucket. These two axes are matched BY CONSTRUCTION, so a
#: deviation past a few percent is a bug in the construction rather than sampling noise —
#: the tolerance is tight on purpose and is not the place to absorb a real mismatch.
#: FIXED BEFORE THE FIRST RUN, 2026-09-13, and not to be widened to make an entry pass.
TOD_RATIO_TOLERANCE: Final[float] = 0.10
VOL_RATIO_TOLERANCE: Final[float] = 0.10

#: The year is matched where the sample allows, so its ratio test is a check on the matching
#: rather than a free diagnostic. It keeps the looser band `levels/placebo.py` gives its own
#: free axis (touch rate, ±25%) because the fallback path can leave a residue.
YEAR_RATIO_TOLERANCE: Final[float] = 0.25

#: Share of matched firings that may fall back to a different year before the era matching is
#: declared to have failed. Small on purpose: the fallback exists for thin years at the edges
#: of a sample, not as a route around a trending base rate. MEASURED, not guessed — with the
#: year unmatched, a condition with no trend deviates 0.37-0.55 at 16 years and ~258
#: sessions/year, so the free-year design was replaced rather than have its tolerance widened.
YEAR_FALLBACK_TOLERANCE: Final[float] = 0.05

#: Share of real firings that may fail to find any control bar before the comparison is
#: declared degenerate. A cell with no non-state session in it cannot be controlled at all.
UNMATCHED_TOLERANCE: Final[float] = 0.05

#: Buckets holding less than this share of real firings are excluded from the ratio tests.
#: A bucket with four firings produces a wild ratio that means nothing, and letting it drive
#: the verdict would make the check fail at random rather than on evidence.
MIN_BUCKET_SHARE: Final[float] = 0.01

#: Below this many paired events the paired statistic returns NaN rather than a number.
#: Same threshold as `sweep_stage1.MIN_EVENTS` and §6's "under 100 = no information".
MIN_EVENTS: Final[int] = 100

N_BOOT: Final[int] = 2000
N_PERM: Final[int] = 2000

#: Sentinel for a real firing that found no control bar.
UNMATCHED: Final[int] = -1


class ControlMismatch(RuntimeError):
    """The control firings are not matched to the real ones, so no comparison is valid."""


def control_pick(condition_name: str, session: int, tod: int, vol: int,
                 index: int, n_pool: int) -> int:
    """Deterministic index into a cell's control pool.

    SHA-256 of (condition, session, tod bucket, volatility quantile, index within session),
    never Python's salted `hash()` — the same discipline as `placebo.region_index`, and for
    the same reason: a salted hash forced a floor sweep to be discarded and re-run earlier in
    this project, because the control built in one process differed from the next.
    """
    key = f"{condition_name}|{session}|{tod}|{vol}|{index}|state-control".encode("ascii")
    digest = hashlib.sha256(key).digest()
    return int.from_bytes(digest[:8], "big") % max(n_pool, 1)


def trailing_vol_quantile(session_vol: np.ndarray, lookback: int,
                          n_quantiles: int) -> np.ndarray:
    """Each session's volatility rank against the PREVIOUS `lookback` sessions.

    Causal by construction: session i is ranked against i-lookback … i-1 and never against
    itself or the future. A full-sample quantile would be simpler and is what a matching
    variable is often allowed to be — but the same array is what a caller will reach for when
    building the state's own threshold, and at that point a full-sample quantile is
    lookahead. One causal helper, used for both, removes the chance to mix them up.

    Returns quantile indices in [0, n_quantiles), or -1 for the first `lookback` sessions,
    which have no history to be ranked against and must be dropped by the caller.
    """
    if lookback < n_quantiles:
        raise ValueError(f"lookback {lookback} < n_quantiles {n_quantiles}: too few prior "
                         f"sessions to define that many buckets")
    v = np.asarray(session_vol, dtype=float)
    out = np.full(v.size, -1, dtype=int)
    for i in range(lookback, v.size):
        window = v[i - lookback:i]
        finite = window[np.isfinite(window)]
        if finite.size < n_quantiles or not np.isfinite(v[i]):
            continue
        # share of the trailing window below this session, mapped to a bucket
        rank = float(np.mean(finite < v[i]))
        out[i] = min(int(rank * n_quantiles), n_quantiles - 1)
    return out


@dataclass(slots=True)
class ControlDraw:
    """The drawn controls, and how each one had to be drawn.

    `index` holds one bar index per real firing (or `UNMATCHED`); `fell_back` marks the pairs
    that could not be matched within their own year. The fallback is reported rather than
    absorbed because a condition that needs it in bulk has a trending base rate, which is the
    confound the whole design exists to hold constant.
    """

    index: np.ndarray
    fell_back: np.ndarray

    @property
    def fallback_rate(self) -> float:
        matched = self.index != UNMATCHED
        if not matched.any():
            return float("nan")
        return float(self.fell_back[matched].mean())


def _pools(idx: np.ndarray, keys: np.ndarray) -> dict[int, np.ndarray]:
    """Group bar indices by a packed integer cell key, once, for constant-time lookup."""
    if idx.size == 0:
        return {}
    order = np.argsort(keys, kind="stable")
    sorted_keys, sorted_idx = keys[order], idx[order]
    bounds = np.flatnonzero(np.diff(sorted_keys)) + 1
    return {int(k[0]): v for k, v in zip(np.split(sorted_keys, bounds),
                                         np.split(sorted_idx, bounds))}


@dataclass(slots=True)
class ClusteringReport:
    """The evidence an entry cites when it declares an exclusion mode."""

    firings_per_session: float
    sessions_touched_share: float
    variance_ratio: float
    clean_sessions: int

    @property
    def strict_is_available(self) -> bool:
        """Strict mode needs a clean pool big enough to be drawn from at all.

        The threshold is deliberately crude — below a fifth of sessions the residue is what
        the P03 measurement showed it to be: a handful of unrepresentative years. The precise
        number matters less than refusing to let a 7%-of-sessions pool look usable.
        """
        return self.sessions_touched_share <= 0.8


def session_clustering(state: np.ndarray, session: np.ndarray) -> ClusteringReport:
    """Firing rate, session coverage and over-dispersion. Measured, for the mode decision."""
    state = np.asarray(state, dtype=bool)
    session = np.asarray(session)
    codes = np.unique(session, return_inverse=True)[1]
    n_sessions = int(codes.max()) + 1 if codes.size else 0
    if n_sessions == 0:
        return ClusteringReport(0.0, 0.0, float("nan"), 0)
    per = np.bincount(codes[state], minlength=n_sessions)
    mean = float(per.mean())
    return ClusteringReport(
        firings_per_session=mean,
        sessions_touched_share=float((per > 0).mean()),
        variance_ratio=float(per.var() / mean) if mean > 0 else float("nan"),
        clean_sessions=int((per == 0).sum()),
    )


def make_matched_control(state: np.ndarray, session: np.ndarray, tod_bucket: np.ndarray,
                         vol_quantile: np.ndarray, *, condition_name: str,
                         year: np.ndarray | None = None,
                         session_exclusion: str = "strict") -> ControlDraw:
    """Control bar for each real firing: same (time-of-day, volatility, year), state absent.

    All arrays are parallel, one entry per BAR. `state` is boolean. Returns one entry per real
    firing, in firing order: the bar index of its control, or `UNMATCHED` where no eligible
    bar exists.

    Eligibility is deliberately strict: a control bar must be in a session where the state
    NEVER fires (see the module docstring — §47 measured 0.952 session autocorrelation), and
    must carry a defined time-of-day bucket and volatility quantile. Bars with a negative
    quantile — the `trailing_vol_quantile` warm-up — are eligible for neither side.

    When `year` is given, the draw is made from the firing's own year first and falls back to
    the year-blind pool only where that year holds no eligible bar; `ControlDraw.fell_back`
    records which. Passing `year=None` restores the year-blind draw, which is kept only so the
    measurement that rejected it stays reproducible — it is not the supported path.
    """
    state = np.asarray(state, dtype=bool)
    session = np.asarray(session)
    tod_bucket = np.asarray(tod_bucket, dtype=int)
    vol_quantile = np.asarray(vol_quantile, dtype=int)
    if not (state.size == session.size == tod_bucket.size == vol_quantile.size):
        raise ValueError("state, session, tod_bucket and vol_quantile must be parallel")
    if year is not None and np.asarray(year).size != state.size:
        raise ValueError("year must be parallel to state")

    if session_exclusion not in ("strict", "bar"):
        raise ValueError(f"session_exclusion must be 'strict' or 'bar', got "
                         f"{session_exclusion!r}")

    defined = (tod_bucket >= 0) & (vol_quantile >= 0)
    real_idx = np.flatnonzero(state & defined)
    if real_idx.size == 0:
        return ControlDraw(np.empty(0, dtype=int), np.empty(0, dtype=bool))

    eligible = defined & ~state
    if session_exclusion == "strict":
        eligible &= ~np.isin(session, np.unique(session[state]))
    clean_idx = np.flatnonzero(eligible)

    span = int(vol_quantile.max()) + 1
    cell = tod_bucket.astype(np.int64) * span + vol_quantile
    blind = _pools(clean_idx, cell[clean_idx])
    by_year: dict[int, np.ndarray] = {}
    if year is not None:
        y = np.asarray(year).astype(np.int64)
        n_cells = int(cell.max()) + 1
        by_year = _pools(clean_idx, y[clean_idx] * n_cells + cell[clean_idx])

    out = np.full(real_idx.size, UNMATCHED, dtype=int)
    fell_back = np.zeros(real_idx.size, dtype=bool)
    seen: dict[object, int] = {}
    for k, i in enumerate(real_idx):
        s = session[i]
        idx_in_session = seen.get(s, 0)
        seen[s] = idx_in_session + 1

        pool = None
        if year is not None:
            pool = by_year.get(int(y[i]) * n_cells + int(cell[i]))
        if pool is None or pool.size == 0:
            pool = blind.get(int(cell[i]))
            fell_back[k] = year is not None
        if pool is None or pool.size == 0:
            fell_back[k] = False
            continue
        pick = control_pick(condition_name, int(s), int(tod_bucket[i]),
                            int(vol_quantile[i]), idx_in_session, pool.size)
        # In bar mode the pool can contain the firing's own session, which strict mode
        # removes wholesale. Step forward deterministically rather than re-hashing, so the
        # choice stays reproducible and the scan terminates.
        if session_exclusion == "bar":
            step = 0
            while step < pool.size and session[pool[(pick + step) % pool.size]] == s:
                step += 1
            if step == pool.size:
                fell_back[k] = False
                continue
            pick = (pick + step) % pool.size
        out[k] = int(pool[pick])
    return ControlDraw(out, fell_back)


@dataclass(slots=True)
class ControlMatchReport:
    """The evidence that a control set is usable. Every field is measured, none assumed."""

    condition: str
    product: str
    n_real: int
    n_matched: int
    n_control_bars: int
    tod_shares_real: dict[int, float]
    tod_shares_control: dict[int, float]
    vol_shares_real: dict[int, float]
    vol_shares_control: dict[int, float]
    year_shares_real: dict[int, float]
    year_shares_control: dict[int, float]
    tod_max_ratio_dev: float
    vol_max_ratio_dev: float
    year_max_ratio_dev: float
    reuse_rate: float
    fallback_rate: float = 0.0
    failures: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures

    @property
    def verdict(self) -> str:
        return "MATCHED" if self.ok else "FAIL"

    @property
    def unmatched_rate(self) -> float:
        if self.n_real == 0:
            return float("nan")
        return 1.0 - self.n_matched / self.n_real


def _shares(values: np.ndarray) -> dict[int, float]:
    if values.size == 0:
        return {}
    keys, counts = np.unique(values, return_counts=True)
    return {int(k): float(c) / values.size for k, c in zip(keys, counts)}


def _max_ratio_deviation(real: dict[int, float], control: dict[int, float]) -> float:
    """Largest |control_share / real_share - 1| over buckets carrying real weight.

    Buckets below MIN_BUCKET_SHARE are skipped: a ratio computed on four firings is noise,
    and letting it decide the verdict would make the check fail at random. A bucket that
    carries real weight and is EMPTY on the control side scores 1.0 rather than infinity,
    which is already far outside every tolerance here.
    """
    worst = 0.0
    for bucket, r in real.items():
        if r < MIN_BUCKET_SHARE:
            continue
        worst = max(worst, abs(control.get(bucket, 0.0) / r - 1.0))
    return worst


def verify_control(condition: str, product: str, real_idx: np.ndarray,
                   draw: ControlDraw | np.ndarray, tod_bucket: np.ndarray,
                   vol_quantile: np.ndarray, year: np.ndarray,
                   strict: bool = True) -> ControlMatchReport:
    """Measure the matching requirements and fail loudly. §49's diagnostics, transposed.

    §49's level diagnostics were distance and touch ratios: one axis designed, one left free
    as an independent check. Here the designed axes are time-of-day and volatility and the
    free one is the year. `real_idx` and `control_idx` are parallel bar indices; entries
    where the control is UNMATCHED are excluded from the distributions and counted instead.
    """
    failures: list[str] = []
    real_idx = np.asarray(real_idx, dtype=int)
    if isinstance(draw, ControlDraw):
        control_idx, fell_back = np.asarray(draw.index, dtype=int), draw.fell_back
    else:
        control_idx = np.asarray(draw, dtype=int)
        fell_back = np.zeros(control_idx.size, dtype=bool)

    if real_idx.size != control_idx.size:
        failures.append(
            f"COUNT MISMATCH: {real_idx.size} real vs {control_idx.size} control. These are "
            f"built one-for-one, so a mismatch means the construction is broken."
        )

    paired = control_idx != UNMATCHED
    n_real, n_matched = int(real_idx.size), int(paired.sum())
    r_idx, c_idx = real_idx[paired], control_idx[paired]

    unmatched_rate = 1.0 - (n_matched / n_real if n_real else 0.0)
    if n_real and unmatched_rate > UNMATCHED_TOLERANCE:
        failures.append(
            f"DEGENERATE: {unmatched_rate:.1%} of real firings have no control bar "
            f"(tolerance {UNMATCHED_TOLERANCE:.0%}). Their (time-of-day, volatility) cells "
            f"contain no session in which the state never fires. This is a property of the "
            f"condition — it occupies its own regime — not a tuning failure, and no "
            f"bucketing fixes it."
        )

    tod_r, tod_c = _shares(tod_bucket[r_idx]), _shares(tod_bucket[c_idx])
    vol_r, vol_c = _shares(vol_quantile[r_idx]), _shares(vol_quantile[c_idx])
    year_r, year_c = _shares(year[r_idx]), _shares(year[c_idx])
    tod_dev = _max_ratio_deviation(tod_r, tod_c)
    vol_dev = _max_ratio_deviation(vol_r, vol_c)
    year_dev = _max_ratio_deviation(year_r, year_c)

    if n_matched and tod_dev > TOD_RATIO_TOLERANCE:
        failures.append(
            f"TIME-OF-DAY MISMATCH: worst bucket share ratio deviates {tod_dev:.2f} "
            f"(tolerance {TOD_RATIO_TOLERANCE:.2f}). Time of day is matched BY "
            f"CONSTRUCTION, so this is a defect in the construction, not sampling noise."
        )
    if n_matched and vol_dev > VOL_RATIO_TOLERANCE:
        failures.append(
            f"VOLATILITY MISMATCH: worst quantile share ratio deviates {vol_dev:.2f} "
            f"(tolerance {VOL_RATIO_TOLERANCE:.2f}). Volatility is matched BY CONSTRUCTION. "
            f"A real-minus-control difference here would be a difference in EXPOSURE."
        )
    fallback_rate = float(fell_back[paired].mean()) if n_matched else 0.0
    if n_matched and fallback_rate > YEAR_FALLBACK_TOLERANCE:
        failures.append(
            f"ERA FALLBACK: {fallback_rate:.1%} of pairs could not be matched within their "
            f"own year (tolerance {YEAR_FALLBACK_TOLERANCE:.0%}). Those years hold no session "
            f"in which the state never fires, which means the condition's BASE RATE TRENDS - "
            f"P01's micro share is the known case (§48). The era is then a confound the pair "
            f"cannot hold constant, and an adoption curve would read as a signal."
        )
    if n_matched and year_dev > YEAR_RATIO_TOLERANCE:
        failures.append(
            f"YEAR MISMATCH: worst year share ratio deviates {year_dev:.2f} (tolerance "
            f"{YEAR_RATIO_TOLERANCE:.2f}). The year is matched where the sample allows, so a "
            f"residue this large means the fallback path carried real weight."
        )

    n_control_bars = int(np.unique(c_idx).size)
    reuse = 1.0 - (n_control_bars / n_matched) if n_matched else float("nan")

    report = ControlMatchReport(
        condition, product, n_real, n_matched, n_control_bars,
        tod_r, tod_c, vol_r, vol_c, year_r, year_c,
        tod_dev, vol_dev, year_dev, reuse, fallback_rate, failures,
    )
    if strict and failures:
        raise ControlMismatch(
            f"{product} {condition}: the state control is not matched, so no "
            f"real-minus-control comparison on this condition is valid.\n  "
            + "\n  ".join(failures)
        )
    return report


def paired_state_stats(real: np.ndarray, control: np.ndarray, sessions: np.ndarray,
                       rng: np.random.Generator) -> tuple[float, ...]:
    """Paired real-minus-control, session bootstrap, paired permutation.

    Identical in construction to `sweep_stage1.paired_stats` (§38), which is pinned by a test
    rather than left to drift: the bootstrap resamples SESSIONS because events within a
    session are correlated, and the permutation swaps real and control within a pair because
    under the null which member is the real firing is exchangeable.

    It is reimplemented here rather than imported because `sweep_stage1` pulls in the level
    machinery, and a state condition has no levels. Returns
    (real mean, control mean, difference, ci low, ci high, n, p).
    """
    from futuresres.signals.stage1 import calibrated_alpha

    ok = np.isfinite(real) & np.isfinite(control)
    r, c, s = np.asarray(real)[ok], np.asarray(control)[ok], np.asarray(sessions)[ok]
    n = int(r.size)
    if n < MIN_EVENTS:
        return (float("nan"),) * 5 + (n, float("nan"))

    d = r - c
    obs = float(d.mean())
    idx_by_session = {int(v): np.flatnonzero(s == v) for v in np.unique(s)}
    keys = list(idx_by_session)
    boot = np.empty(N_BOOT)
    for b in range(N_BOOT):
        pick = rng.integers(0, len(keys), len(keys))
        boot[b] = d[np.concatenate([idx_by_session[keys[i]] for i in pick])].mean()
    eff_alpha = calibrated_alpha(max(len(keys), 2))
    lo, hi = np.percentile(boot, [100 * eff_alpha / 2, 100 * (1 - eff_alpha / 2)])

    null = np.empty(N_PERM)
    for i in range(N_PERM):
        null[i] = float((d * (rng.integers(0, 2, n) * 2 - 1)).mean())
    pval = float(np.mean(np.abs(null) >= abs(obs)))
    return float(r.mean()), float(c.mean()), obs, float(lo), float(hi), n, pval


def render_report(reports: Sequence[ControlMatchReport]) -> str:
    """The matching evidence, written out rather than asserted."""
    w: list[str] = []
    a = w.append
    a("# State-condition control matching")
    a("")
    a("**Every P-series result reports (real - control), not (real - 0).** A state condition "
      "can beat a rotation null by firing in favourable regimes rather than by carrying "
      "information: rotation preserves the firing count and its clustering but moves the "
      "firings into different times of day, volatility regimes and years. This document is "
      "the evidence that a real-minus-control comparison is valid at all.")
    a("")
    a(f"Controls are drawn from a DIFFERENT SESSION in the same time-of-day bucket and the "
      f"same volatility quantile, where the state never fires. Selection is SHA-256 of "
      f"(condition, session, bucket, quantile, index) - never Python's salted `hash()`.")
    a("")
    a("**The year is matched where the sample allows, and the fallback rate is reported.** "
      "Leaving the year free was tried first and measured: a condition with no year trend "
      "deviates 0.37-0.55 at ~258 sessions/year over 16 years, against a 0.25 tolerance, so "
      "the check would have failed well-behaved conditions. The construction was changed "
      "rather than the tolerance. A state whose base rate TRENDS runs out of same-year "
      "sessions in its late years and is blocked by ERA FALLBACK, which names the defect more "
      "precisely than a year-share ratio did.")
    a("")

    bad = [r for r in reports if not r.ok]
    if bad:
        a(f"## FAIL - {len(bad)} of {len(reports)} conditions are not matched")
        a("")
        a("**No real-minus-control comparison on these conditions is valid.**")
    else:
        a(f"## MATCHED - all {len(reports)} conditions")
    a("")
    a("| condition | product | n real | matched | control bars | ToD dev | vol dev | "
      "year dev | era fallback | reuse | |")
    a("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in sorted(reports, key=lambda r: (r.condition, r.product)):
        a(f"| {r.condition} | {r.product} | {r.n_real:,} | {r.n_matched:,} | "
          f"{r.n_control_bars:,} | {r.tod_max_ratio_dev:.3f} | {r.vol_max_ratio_dev:.3f} | "
          f"{r.year_max_ratio_dev:.3f} | {r.fallback_rate:.1%} | {r.reuse_rate:.1%} | "
          f"**{r.verdict}** |")
    a("")
    a(f"Tolerances, fixed before the first run: time-of-day {TOD_RATIO_TOLERANCE:.2f}, "
      f"volatility {VOL_RATIO_TOLERANCE:.2f} (both matched by construction, so these are "
      f"tight), year {YEAR_RATIO_TOLERANCE:.2f}, era fallback "
      f"{YEAR_FALLBACK_TOLERANCE:.0%}, unmatched share {UNMATCHED_TOLERANCE:.0%}.")
    a("")
    for r in bad:
        a(f"### FAILURES - {r.condition} / {r.product}")
        a("")
        for f in r.failures:
            a(f"- {f}")
        a("")
    return "\n".join(w)

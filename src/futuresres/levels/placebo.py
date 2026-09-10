"""Matched placebo levels, and the verification that they are actually matched.

LEVEL_HYPOTHESES.md, methodological core.

WHY THIS EXISTS. Price mean-reverts and continues around ARBITRARY levels. Volatility clusters
near any reference point price is currently trading through. So the null for a level test is
not "no reaction" - any level, real or invented, shows reaction. The null is **"no reaction
beyond a matched placebo level"**, and the reported effect is (real - placebo), never
(real - 0).

THE MATCHING IS THE WHOLE THING, AND IT IS NOT ASSUMED. If placebo levels sit further from
price, or are touched less often, than real ones, then any real-minus-placebo difference is a
difference in exposure rather than a difference in reaction - and the comparison would look
decisive while meaning nothing. `verify()` measures all three matching requirements and
**fails loudly** rather than returning a caveat nobody reads.

    count per session      identical by construction, and asserted anyway
    distance from price    compared as distributions, not as means
    touch frequency        compared as a ratio, with a hard tolerance

DETERMINISTIC SEEDING, NEVER `hash()`. Python's `hash()` is salted per process, so a placebo
built in one run would differ from the same placebo built in the next. That is the exact bug
that forced a floor sweep to be discarded and re-run earlier in this project. Offsets come
from SHA-256 of (session date, level type), which is reproducible across processes, machines
and months.

THE OFFSET RANGE IS +/-[0.3, 1.5] x A SCALE, and the sign is part of the hash. The lower bound
keeps the placebo far enough from the real level that they are not the same level; the upper
bound keeps it close enough that price reaches it about as often. Both bounds are load-bearing
and `verify()` is what says whether they were chosen well.

THE SCALE USED TO BE DAILY ATR(20) FOR EVERY LEVEL TYPE, AND THAT FAILED 53 OF 55 TYPES.
Placebos landed 3x to 63x further from price than the real levels they stood in for: real
levels were touched 30-96% of the time and those placebos 6-17%. `verify()` caught it, which
is what it is for - but nothing consumed the verdict, because no Stage 1 ever ran. The scale
is now `definitions.window_scale`, the intraday range over each level's own validity window.

THE BOUNDS THEMSELVES WERE NOT TOUCHED. 0.3 and 1.5 are as registered. Only the unit they
multiply changed, and it changed to the unit the matching criterion was always implicitly
asking for. Sweeping the bounds until matching passed would be fitting the null to the test.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from typing import Final, Sequence

import numpy as np

#: Offset magnitude in units of the scale passed to `make_placebo`. Fixed a priori and
#: UNCHANGED by the 2026-09-09 scale correction; never tuned to make a result appear.
OFFSET_LO: Final[float] = 0.3
OFFSET_HI: Final[float] = 1.5

#: How far the placebo touch rate may differ from the real one before the machinery is
#: declared broken. 25% is loose enough to allow ordinary sampling variation and tight enough
#: that a genuine mismatch - placebos sitting somewhere price rarely goes - is caught.
TOUCH_RATIO_TOLERANCE: Final[float] = 0.25

#: How far the median distance-from-price may differ, as a ratio. Distances are compared as
#: DISTRIBUTIONS (deciles) as well; this is the headline number.
DISTANCE_RATIO_TOLERANCE: Final[float] = 0.25


class PlaceboMismatch(RuntimeError):
    """The placebo levels are not matched to the real ones, so no comparison is valid."""


def offset_unit(day: date, level_type: str, index: int = 0) -> float:
    """Signed offset in ATR units, deterministic in (day, level_type, index).

    Returns a value in +/-[OFFSET_LO, OFFSET_HI]. The sign comes from a separate bit of the
    same digest, so magnitude and direction are independent.
    """
    key = f"{day}|{level_type}|{index}".encode("ascii")
    digest = hashlib.sha256(key).digest()
    # 32 bits of magnitude, one bit of sign, from disjoint parts of the digest
    magnitude = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
    sign = 1.0 if digest[4] & 1 else -1.0
    return sign * (OFFSET_LO + magnitude * (OFFSET_HI - OFFSET_LO))


def make_placebo(levels: np.ndarray, days: np.ndarray, level_type: str,
                 scale: np.ndarray) -> np.ndarray:
    """SUPERSEDED 2026-09-09. Placebo as the real level displaced by a hash-derived offset.

    Kept because the reasoning is worth finding, not because it is used. Its geometry is
    the defect: the real level is ALREADY displaced from the reference price by d, so
    adding a signed offset of magnitude ~d lands the placebo at ~2d or ~0, whose median is
    ~1.4d. That held at 1.32-1.54 across every level type, both products and three
    different scale rules, which is what showed the error was in the construction rather
    than in the size. `make_region_placebo` is the replacement. decisions.md 36 and 37.

    Placebo for each real level: real + hash-derived offset x that level's own scale.

    `scale` is PER LEVEL, not per session, and should come from
    `definitions.window_scale` - the intraday range over the window in which that level can
    actually be touched. It was daily ATR(20) until 2026-09-09; see the module docstring and
    decisions.md 36 for why that failed 53 of 55 level types.

    `levels`, `days` and `scale` are parallel arrays, one entry per real level. The result
    has the same length by construction, which is the count-matching requirement.
    """
    if not (levels.size == days.size == scale.size):
        raise ValueError("levels, days and scale must be parallel")
    out = np.empty_like(levels, dtype=float)
    seen: dict[object, int] = {}
    for i, (lvl, day) in enumerate(zip(levels, days)):
        idx = seen.get(day, 0)
        seen[day] = idx + 1
        out[i] = lvl + offset_unit(day, level_type, idx) * scale[i]
    return out


def region_index(day: date, level_type: str, index: int, n_pool: int) -> tuple[int, float]:
    """Deterministic (pool index, sign) for a matched arbitrary region.

    Same hashing discipline as `offset_unit` - SHA-256 of (day, level_type, index), never
    Python's salted `hash()`.
    """
    digest = hashlib.sha256(f"{day}|{level_type}|{index}|region".encode("ascii")).digest()
    pick = int.from_bytes(digest[:8], "big") % max(n_pool, 1)
    sign = 1.0 if digest[8] & 1 else -1.0
    return pick, sign


def make_region_placebo(levels: np.ndarray, refs: np.ndarray, days: np.ndarray,
                        level_type: str, scale: np.ndarray) -> np.ndarray:
    """THE NULL, as redefined 2026-09-09: an arbitrary region at a matched distance.

    A placebo is no longer "the real level, displaced". It is an ARBITRARY REGION drawn to
    have the same distance-from-price distribution as the real levels of its type. The
    hypotheses ask whether their levels react differently from ordinary regions price
    reaches equally often; DISPLACEMENT WAS ONLY EVER A METHOD for generating such regions,
    and it was a method with a defect - see `make_placebo` below.

    Construction: normalise each real distance by that level's own scale, then give each
    placebo a hash-chosen distance drawn from that pool of normalised distances, on a
    hash-chosen side, rescaled by its own level's scale. The distance distribution is
    therefore matched BY CONSTRUCTION rather than by tuning, and it is matched in
    volatility-normalised units so a quiet session does not inherit a busy session's spread.

    TOUCH RATE IS NOT FITTED, DELIBERATELY. Only distance is designed; touch frequency is
    left free and measured, so it remains an independent check that the region is comparably
    reachable. There is also a real tension: if a level type genuinely attracts price, then
    forcing equal touch rates would require moving the placebo closer, which would break
    distance matching and erase part of the very effect under test. The +/-25% tolerance is
    what absorbs that, and a residual touch gap is reported rather than engineered away.

    Returns NaN for every level when the real distance distribution is degenerate at zero -
    a level that sits exactly AT the reference price has no distance to match and admits no
    comparable arbitrary region. `verify` reports that as its own failure rather than
    pretending to a match.
    """
    if not (levels.size == refs.size == days.size == scale.size):
        raise ValueError("levels, refs, days and scale must be parallel")
    d = np.abs(levels - refs)
    with np.errstate(invalid="ignore", divide="ignore"):
        u = d / scale
    pool = u[np.isfinite(u)]
    if pool.size == 0 or float(np.nanmedian(pool)) <= 0.0:
        return np.full(levels.size, np.nan)
    out = np.empty(levels.size, dtype=float)
    seen: dict[object, int] = {}
    for i, (ref, s, day) in enumerate(zip(refs, scale, days)):
        idx = seen.get(day, 0)
        seen[day] = idx + 1
        if not (np.isfinite(ref) and np.isfinite(s)):
            out[i] = np.nan
            continue
        pick, sign = region_index(day, level_type, idx, pool.size)
        out[i] = ref + sign * float(pool[pick]) * float(s)
    return out


@dataclass(slots=True)
class MatchReport:
    """The evidence that a placebo set is usable. Every field is measured."""

    level_type: str
    product: str
    n_real: int
    n_placebo: int
    real_touch_rate: float
    placebo_touch_rate: float
    real_distance_median: float
    placebo_distance_median: float
    real_distance_deciles: list[float]
    placebo_distance_deciles: list[float]
    failures: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures

    @property
    def touch_ratio(self) -> float:
        if self.real_touch_rate <= 0:
            return float("nan")
        return self.placebo_touch_rate / self.real_touch_rate

    @property
    def distance_ratio(self) -> float:
        if self.real_distance_median <= 0:
            return float("nan")
        return self.placebo_distance_median / self.real_distance_median


def _deciles(x: np.ndarray) -> list[float]:
    finite = x[np.isfinite(x)]
    if finite.size == 0:
        return [float("nan")] * 9
    return [float(v) for v in np.percentile(finite, np.arange(10, 100, 10))]


def verify(level_type: str, product: str, real: np.ndarray, placebo: np.ndarray,
           real_distance: np.ndarray, placebo_distance: np.ndarray,
           real_touched: np.ndarray, placebo_touched: np.ndarray,
           strict: bool = True) -> MatchReport:
    """Measure the three matching requirements. Raises on failure when `strict`.

    `*_distance` is |level - reference price| at level creation, in price units.
    `*_touched` is a boolean per level: did price reach it within its validity window.
    """
    failures: list[str] = []

    if real.size != placebo.size:
        failures.append(
            f"COUNT MISMATCH: {real.size} real vs {placebo.size} placebo. These are built "
            f"one-for-one, so a mismatch means the construction is broken, not the tuning."
        )

    rt = float(real_touched.mean()) if real_touched.size else 0.0
    pt = float(placebo_touched.mean()) if placebo_touched.size else 0.0
    if rt > 0:
        ratio = pt / rt
        if abs(ratio - 1.0) > TOUCH_RATIO_TOLERANCE:
            failures.append(
                f"TOUCH-RATE MISMATCH: placebo touched {pt:.1%} vs real {rt:.1%} "
                f"(ratio {ratio:.2f}, tolerance +/-{TOUCH_RATIO_TOLERANCE:.0%}). The offset "
                f"range is wrong: placebos sit where price goes {'less' if ratio < 1 else 'more'} "
                f"often than the real levels, so any real-minus-placebo difference would be a "
                f"difference in EXPOSURE rather than in reaction."
            )

    if placebo.size and not np.isfinite(placebo).any():
        failures.append(
            "DEGENERATE: every real level of this type sits exactly AT the reference price, "
            "so there is no distance distribution to match and no arbitrary region is "
            "comparable to it. This is a property of the level definition, not a tuning "
            "failure, and no scale or construction fixes it."
        )

    rd = float(np.nanmedian(real_distance)) if real_distance.size else 0.0
    # A degenerate type yields an all-NaN placebo distance by design - the failure is
    # already recorded above, so the warning numpy would emit here is noise.
    if placebo_distance.size and np.isfinite(placebo_distance).any():
        pd_ = float(np.nanmedian(placebo_distance))
    else:
        pd_ = 0.0
    if rd > 0:
        dratio = pd_ / rd
        if abs(dratio - 1.0) > DISTANCE_RATIO_TOLERANCE:
            failures.append(
                f"DISTANCE MISMATCH: placebo median distance {pd_:.4g} vs real {rd:.4g} "
                f"(ratio {dratio:.2f}, tolerance +/-{DISTANCE_RATIO_TOLERANCE:.0%}). Placebos "
                f"are not sitting at a comparable distance from price."
            )

    report = MatchReport(
        level_type, product, int(real.size), int(placebo.size), rt, pt, rd, pd_,
        _deciles(real_distance), _deciles(placebo_distance), failures,
    )
    if strict and failures:
        raise PlaceboMismatch(
            f"{product} {level_type}: placebo machinery is not matched, so no "
            f"real-minus-placebo comparison on this level type is valid.\n  "
            + "\n  ".join(failures)
        )
    return report


def render_reports(reports: Sequence[MatchReport]) -> str:
    """The matching evidence, written out rather than asserted."""
    w: list[str] = []
    a = w.append
    a("# Placebo matching")
    a("")
    a("Generated by `python -m futuresres.reporting.level_rates`. "
      "LEVEL_HYPOTHESES.md, methodological core.")
    a("")
    a("**Every L-series result reports (real - placebo), not (real - 0).** Price reacts at "
      "arbitrary levels, so a raw reaction statistic is not evidence that a level matters. "
      "This document is the evidence that the placebo comparison is valid at all.")
    a("")
    a(f"Offsets are SHA-256 of (session date, level type, index within session), mapped to "
      f"+/-[{OFFSET_LO}, {OFFSET_HI}] x the INTRADAY RANGE OVER EACH LEVEL'S OWN VALIDITY "
      f"WINDOW. Deterministic across processes - never Python's salted `hash()`, which is "
      f"the bug that forced a floor sweep to be discarded and re-run earlier in this "
      f"project.")
    a("")
    a("**The scale was daily ATR(20) until 2026-09-09 and that failed 53 of 55 level types** "
      "- placebos sat 3x to 63x further from price than the real levels they stood in for, "
      "so every comparison would have measured exposure rather than reaction. The offset "
      "BOUNDS are unchanged; only the unit they multiply. See `decisions.md` 36.")
    a("")

    bad = [r for r in reports if not r.ok]
    if bad:
        a(f"## FAIL - {len(bad)} of {len(reports)} level types are not matched")
        a("")
        a("**No real-minus-placebo comparison on these level types is valid.** Any result "
          "would be a difference in exposure rather than in reaction.")
    else:
        a(f"## PASS - all {len(reports)} level types matched")
        a("")
        a("Touch rates and distance distributions agree within tolerance, so a "
          "real-minus-placebo difference can be read as a difference in reaction.")
    a("")

    a("## Matching, per level type")
    a("")
    a("| level type | product | n | real touch | placebo touch | ratio | real dist | placebo dist | ratio | |")
    a("|---|---|---|---|---|---|---|---|---|---|")
    for r in sorted(reports, key=lambda r: (r.level_type, r.product)):
        a(f"| {r.level_type} | {r.product} | {r.n_real:,} | {r.real_touch_rate:.1%} | "
          f"{r.placebo_touch_rate:.1%} | {r.touch_ratio:.2f} | "
          f"{r.real_distance_median:.4g} | {r.placebo_distance_median:.4g} | "
          f"{r.distance_ratio:.2f} | " + ("ok" if r.ok else "**FAIL**") + " |")
    a("")
    a(f"Tolerances: touch ratio +/-{TOUCH_RATIO_TOLERANCE:.0%}, distance ratio "
      f"+/-{DISTANCE_RATIO_TOLERANCE:.0%}. Both are hard - a level type outside them raises "
      f"`PlaceboMismatch` rather than returning a caveat.")
    a("")

    a("## Distance distributions, not just medians")
    a("")
    a("A median can match while the distributions differ. Deciles of "
      "|level - price at creation|:")
    a("")
    for r in sorted(reports, key=lambda r: (r.level_type, r.product)):
        a(f"**{r.level_type} / {r.product}**")
        a("")
        a("| | d1 | d2 | d3 | d4 | d5 | d6 | d7 | d8 | d9 |")
        a("|---|---|---|---|---|---|---|---|---|---|")
        a("| real | " + " | ".join(f"{v:.4g}" for v in r.real_distance_deciles) + " |")
        a("| placebo | " + " | ".join(f"{v:.4g}" for v in r.placebo_distance_deciles) + " |")
        a("")

    for r in bad:
        a(f"### FAILURES - {r.level_type} / {r.product}")
        a("")
        for f in r.failures:
            a(f"- {f}")
        a("")
    return "\n".join(w)

# N02 — round-number cross continuation (S7/S8)

> **Stages: S7 (multiplicity) and S8 (era split, economics).** Cleared S1–S6 on the corrected
> session-open population (`decisions.md` §49–§50). See `reports/STAGES.md`.

**Verdict: retired at S7. 0 of 3 cells separate, 0 BH survivors, and the cells disagree on
sign.** 3 trials; **N 756 → 759, SR\* 0.1369**, chain verified.

## Results — economics against the 0.48 bps MNQ cost floor

| d | paired n | real | placebo | diff | CI | p | \|diff\|/cost | power @ 3.5 bps |
|---|---|---|---|---|---|---|---|---|
| 2 pt | 3,439 | +0.102 | −1.036 | **+1.138** | [−1.15, +3.30] | 0.350 | 2.37× | 75% |
| 4 pt | 3,299 | −0.629 | −0.776 | **+0.147** | [−2.10, +2.25] | 0.900 | 0.31× | 78% |
| 8 pt | 3,035 | −1.038 | +0.034 | **−1.072** | [−3.46, +1.33] | 0.439 | 2.23× | 68% |

Pooled mean ≈ **+0.07 bps** against a registered **+2.0 to +5.0**. The pre-registered
refutation clause — *positive mean with no BH survivor* — is met.

**This is not the L12 case.** Power against the registered midpoint (3.5 bps) was 68–78%, so
the significance limb was reachable. The refutation also stands on magnitude alone: the pooled
effect is ~3% of the prediction's midpoint, and the cells cannot agree on direction.

## What was looked at (nothing cleared, but §46's rule was applied to the era split)

| check | result |
|---|---|
| direction mix, real vs placebo | 0.51 vs 0.51–0.52 — balanced |
| fire rates, real vs placebo | 7,179 vs 6,671 (d=2) — comparable; ~48% survive pairing on both legs |
| era split | **sign flips** — see below |
| scale stationarity of the condition | **FAILS** — the defect |

**The era split looked striking and is uninterpretable:**

| d | 2010–2018 | 2019–2026 | 2024–2026 |
|---|---|---|---|
| 2 | −1.83 (p 0.44) | +2.05 (p 0.14) | **+4.43, CI [+0.74, +8.14], p 0.033** |
| 4 | −4.63 (p 0.07) | +1.51 (p 0.27) | +3.77 (p 0.062) |
| 8 | **−8.66, CI [−14.4, −1.7], p 0.0075** | +0.78 (p 0.60) | +3.86 (p 0.084) |

**The cause is that N02 is specified in points on an index that rose 14×.** Median price was
1,939 in 2010 and 27,528 in 2026. The 50-point grid was 258 bps apart in 2010 and 18 bps in
2026; **d = 8 points was a 41 bps breakout in 2010 and a 2.9 bps one in 2026.** Each cell is a
different condition in each era, so an early-negative / late-positive pattern says nothing
about decay or emergence — it compares two different trades. The 2010–18 sample is also the
small, pre-splice NQ segment (595–808 pairs).

**The 2024–26 positive is not a finding.** It is one window of nine era sub-tests, two of which
reach nominal significance, in **opposite** directions, on top of a known scale confound.
Selecting it would be choosing the denominator after seeing the numerators.

## What this establishes

**Established:** the registered condition does not produce the registered effect on this
sample, with adequate power at the prediction's midpoint.

**Not established:** anything about Osler's stop-clustering mechanism. The condition was
mis-specified for a 16-year sample — its thresholds were not scale-invariant — so this null is
weak evidence about the mechanism. Round-number *levels* are legitimately in price units (that
is what makes them round); the penetration depth *d* should have been in bps or volatility
units, and the era split should have been pre-registered alongside it.

**MGC was never available as an S8 instrument** (§49: 11.5% touch rate), so there is no
cross-market evidence either way.

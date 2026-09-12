# L04 Stage 1 - session extremes, sweep and reclaim, against matched placebo regions

**Verdict: `stage1_inconclusive`. Five of eighteen cells separate against 0.90 expected -
and NONE survives the multiple-comparison correction.** 18 trials spent, 9 cells excluded.

The catalogue's definition: *inconclusive means the test ran with adequate power and the
reading did not resolve - nominal hits above chance, none surviving BH, mechanism
uncontradicted.* That is exactly this.

Every figure is **(real level) minus (matched placebo region)**, MGC, **H=180 pre-registered**,
cost floor **0.65 bps**, traded **counter to the penetration**. The control equalises where a
region sits and how often price is reached, and **nothing about how price arrived**
(`decisions.md` 37).

## The correction is the verdict

| | |
|---|---|
| cells separating | **5 of 18** |
| expected by chance at alpha 0.05 | 0.90 |
| **BH survivors** | **0** |
| best p | 0.0045 |
| BH rank-1 bar (0.05 x 1/18) | **0.00278** |

The strongest cell misses its bar by a factor of ~1.6. Once rank 1 fails, nothing below it can
be kept.

**And the 18 cells are not 18 independent tests.** L04/MGC sits at **98% pairwise overlap** of
firing minutes, and all five separations are `sess_Asia` at adjacent m/k. This is closer to
ONE result seen five times than to five findings. That cuts both ways: correlated tests make
BH conservative, and they also mean "5 against 0.90 expected" is not the evidence the count
suggests.

## Results

| level type | m | k | n | real | placebo | diff | CI | p | sep |
|---|---|---|---|---|---|---|---|---|---|
| sess_Asia | 8 | 2 | 2,715 | +0.538 | -3.006 | **+3.543** | [+1.12, +6.00] | 0.0045 | **YES** |
| sess_Asia | 4 | 2 | 3,393 | -0.175 | -2.702 | **+2.527** | [+0.56, +4.41] | 0.0135 | **YES** |
| sess_Asia | 4 | 3 | 3,484 | -0.111 | -2.476 | **+2.366** | [+0.53, +4.32] | 0.0125 | **YES** |
| sess_Asia | 8 | 3 | 3,007 | +0.009 | -2.218 | **+2.227** | [+0.06, +4.35] | 0.0495 | **YES** |
| sess_Asia | 4 | 5 | 3,523 | -0.277 | -2.407 | **+2.131** | [+0.30, +4.03] | 0.0175 | **YES** |
| sess_Asia | 2 | 5 | 3,575 | -0.684 | -2.432 | **+1.747** | [-0.01, +3.50] | 0.0610 | - |
| sess_Asia | 2 | 3 | 3,566 | -0.706 | -2.382 | **+1.675** | [-0.07, +3.43] | 0.0755 | - |
| sess_Asia | 2 | 2 | 3,544 | -0.765 | -2.312 | **+1.547** | [-0.18, +3.41] | 0.1070 | - |
| sess_Asia | 8 | 5 | 3,234 | -0.472 | -1.799 | **+1.327** | [-0.58, +3.31] | 0.2020 | - |
| sess_London | 4 | 5 | 674 | +0.973 | +1.575 | **-0.602** | [-4.98, +3.26] | 0.7795 | - |
| sess_London | 4 | 3 | 645 | +1.378 | +2.065 | **-0.687** | [-5.09, +3.44] | 0.7520 | - |
| sess_London | 4 | 2 | 608 | +0.064 | +0.982 | **-0.918** | [-5.61, +3.58] | 0.7170 | - |
| sess_London | 2 | 5 | 695 | +1.023 | +1.946 | **-0.924** | [-4.92, +3.28] | 0.6450 | - |
| sess_London | 2 | 3 | 693 | +1.042 | +1.981 | **-0.939** | [-5.15, +2.96] | 0.6435 | - |
| sess_London | 8 | 2 | 398 | -1.389 | -0.278 | **-1.110** | [-7.03, +4.72] | 0.7105 | - |
| sess_London | 8 | 3 | 469 | +1.315 | +2.465 | **-1.150** | [-6.45, +4.02] | 0.6515 | - |
| sess_London | 8 | 5 | 548 | +1.217 | +2.371 | **-1.154** | [-5.60, +3.28] | 0.6140 | - |
| sess_London | 2 | 2 | 680 | +0.672 | +2.053 | **-1.380** | [-5.62, +2.64] | 0.5035 | - |

**`sess_US` excluded** - 9 cells - placebo unmatched at a touch ratio of 1.33 (`decisions.md`
37). Recorded rather than dropped by omission.

`sess_Asia` 5/9 separated, +1.33 to +3.54. **`sess_London` 0/9, negative throughout**
(-1.38 to -0.60), on identical machinery.

## The bug hunt - four artifacts ruled out

Pre-committed in `decisions.md` 42: *if anything clears, look for the bug before writing it
up.* Best cell `sess_Asia m=8 k=2`, +3.54 bps at 5.5x the cost floor.

| check | result |
|---|---|
| placebo mispriced in the thin Asia window | **refuted** - distance ratio 0.94, fire rates 54.3% vs 54.6% |
| hold truncation at RTH_EXIT (1315) | **refuted** - 0.3% of entries lost, 5.0% clipped |
| direction mix | **refuted** - real 0.519 up, placebo 0.529 |
| drift x net-exposure gap | **refuted** - +0.043 of +3.543 bps, **1.2%** |

The drift check is the one that mattered. The real leg earns +2.99 long and -1.74 short, which
looks exactly like drift on an instrument that ran from ~1,200 to ~3,000. But measured
directly: drift at the entries is +2.34 bps, net exposure is -0.0387 (real) against -0.0571
(placebo), and the product explains 1.2% of the difference.

**A probe bug is recorded rather than hidden**: a first pass reported an "excess" column of
exactly 0.000 everywhere, which was an arithmetic identity (return minus signed drift cancels
by construction), not a finding. Discarded.

**London is the built-in control and it behaves differently in the right way.** It is 50.8%
truncated against Asia's 5.0%, and it is negative - so truncation cannot be manufacturing
Asia's positive.

## The era split - it does not decay and does not flip

| cell | 2010-2018 | p | 2019-2026 | p |
|---|---|---|---|---|
| m=8 k=2 | +1.914 | 0.2545 | **+5.092** | **0.0025** |
| m=4 k=2 | +2.484 | 0.0585 | +2.569 | 0.0735 |
| m=4 k=3 | +2.437 | 0.0445 | +2.293 | 0.1185 |
| m=8 k=3 | +0.959 | 0.5415 | +3.425 | 0.0300 |
| m=4 k=5 | +1.655 | 0.1765 | +2.619 | 0.0705 |

**Positive in both halves, 10 of 10.** This is not R01's pattern, where the effect decayed to
zero in the recent era, nor a sign flip.

**But the composition changed.** In 2010-2018 the real leg is NEGATIVE (-0.88 to -1.67) and
the difference comes entirely from the placebo being more negative. In 2019-2026 the real leg
turns POSITIVE (+0.61 to +2.05). The difference is stable; what produces it is not. That is
recorded as a caveat rather than smoothed over.

## What this establishes, and what it does not

**Not established, and this is the verdict:** that there is an effect. Nothing survives
correction. L04 is not promoted and nothing here licenses trading it.

**Established:** the nominal pattern is not one of the four artifacts checked, and it does not
live in one era. That is a materially different sentence from "a fluke", and it is why the
status is `stage1_inconclusive` rather than `retired`.

**The mechanism is uncontradicted, not supported.** The registered story is that session
extremes are reference prices participants transact against. Nothing here confirms that; the
difference could as easily be the control's behaviour in a thin session as the level's.

## If anyone wants to pursue it

A **new registration**, with `sess_Asia` specified in advance rather than selected as the best
of eighteen, tested on data that did not generate this result. What cannot be done is keeping
the Asia cells, dropping the rest, and re-running BH on a grid of five - that is choosing the
denominator after seeing the numerators, and the trial log exists to make it impossible.

This is the same bar `decisions.md` 38 set for L07's mirror and 40 for L11's replacement.

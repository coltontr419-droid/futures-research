# The matched control for state conditions — design and fault injection

Generated alongside `src/futuresres/signals/state_control.py`,
`tests/test_state_control.py` and `src/futuresres/reporting/state_control_feasibility.py`.
Decision record: `decisions.md` §55. **Nothing is registered. No trial is spent. This document
reports a control, not a result — no return series is scored anywhere in it.**

---

## 1. What was missing, and what already existed

`decisions.md` §54 found the P-series placebo question misframed rather than open. Three of
its four parts were already answered:

| part | status |
|---|---|
| the **location** placebo (§37) | a category error for a state — there is no location to displace |
| the **alignment** null | already in every S7 run: `signed_rotation_null` preserves the firing count and its clustering exactly, and destroys only the alignment with returns |
| the **hash** control (F14, §30) | not rate-matched (fixed clock slots), and scoped to harness validation at ~45k events |
| the **exposure** confound | **open — this is what was built** |

A state condition can beat the rotation null by firing in favourable **regimes** rather than
by carrying information. Rotation moves the firings into different times of day, volatility
regimes and years, so it does not hold those constant. That is a difference in exposure, not
in reaction — the sentence `levels/placebo.py` already enforces for levels.

## 2. The design, transposed from the level null

The level placebo matched the **nuisance** (distance from price, which determines exposure)
and varied the **claim** (a real level against an arbitrary region). The state control does
the same with different nuisances:

    matched      time-of-day bucket, volatility quantile, year
    varied       the state HOLDS  vs  the state does NOT hold
    reported     era-fallback rate, control-bar reuse, unmatched share

For each real firing, a control firing is drawn from a **different session** in the same
time-of-day bucket, the same volatility quantile and the same year, where the state does not
hold. Selection is SHA-256 of (condition, session, bucket, quantile, index) — never Python's
salted `hash()`, which is the bug that forced a floor sweep to be discarded earlier in this
project.

Diagnostics follow §49's distance and touch ratios: a share-ratio test per axis, each with a
**tolerance fixed before the first run**, and a `MATCHED`/`FAIL` verdict that raises rather
than returning a caveat nobody reads.

| axis | tolerance | matched by construction? |
|---|---|---|
| time of day | 0.10 | yes — so a deviation is a bug, not noise |
| volatility quantile | 0.10 | yes |
| year | 0.25 | where the sample allows; the shortfall is reported as ERA FALLBACK |
| era fallback | 5% | — |
| unmatched share | 5% | — |

The statistic is `paired_state_stats`: real-minus-control, bootstrap over **sessions**, and a
paired sign permutation. It is pinned by test against `sweep_stage1.paired_stats` (§38) so the
two cannot drift apart.

## 3. Fault injection — the claim is verified, not accepted

§54's claim was that a condition *cannot* beat this control by firing in favourable regimes,
because the control fires in the same regimes by construction. A claim of that shape is what
§52 was written about, so it is tested rather than asserted. 17 tests, all passing.

**The three that decide whether the control is worth having.** A deliberately regime-loaded
fake condition fires on **even-numbered sessions** inside a high-volatility, near-the-open
regime that carries drift. Session parity cannot relate to returns by construction — the F14
idea applied to the selection of sessions rather than to the direction of trades.

| # | test | result |
|---|---|---|
| 1 | the fake condition, carrying no information, **beats a rotation null** | confirmed — the danger is real, and if this ever stops holding the other two prove nothing |
| 2 | the same condition **does not beat the matched control** | confirmed — CI contains zero |
| 3 | a **genuine** state effect **does** beat it | confirmed — without this, (2) would also pass for a control that is null against everything |

**The rest.** Controls never sit in a session the state touches (strict mode) and never on a
firing bar; every pair matches on its cell individually, not on average; selection is
reproducible across processes; a condition that occupies its whole cell reports `DEGENERATE`
rather than a fake match, the distinction §49 drew; controls drawn from a corrupted volatility
or time-of-day array are caught with the matching failure kind; and a trending state is
blocked by `ERA FALLBACK`.

## 4. Two design changes forced by measurement, not by preference

**(a) The year is matched, not merely measured.** The first design left the year free and
tested it with the same ratio check as the other axes, so that a trending state would be
blocked. Measured, that check has a **noise floor**: how many high-volatility sessions land in
each year is itself random, so a condition with **no** year trend already deviates this much:

| sessions/year | years | year deviation, median | max |
|---|---|---|---|
| 100 | 6 | 0.46 | 1.62 |
| 200 | 6 | 0.25 | 0.52 |
| 262 | 16 | **0.37** | **0.55** |
| 700 | 6 | 0.16 | 0.27 |

At the real sample's shape — 4,125 sessions over 16 years, ~258 per year — a well-behaved
condition breaches the 0.25 tolerance. Widening the tolerance would have been fitting the null
to the test, the error `levels/placebo.py` records about its own bounds, so **the construction
changed instead**: the draw is stratified by year, with fallback where a year holds no
eligible session. Year deviation then measures **0.000** at every realistic size, while a
trending (P01-shaped) state is still blocked, now at ~28% era fallback. Both are pinned by
test.

**(b) Whole-session exclusion is structurally unavailable to a frequent state.** Excluding
every session in which the state fires anywhere is right for a **session-level** state —
volume share is session-persistent, autocorrelation 0.952 (§47) — but it assumes clean
sessions exist. On real data they largely do not (§5 below), so a `bar` mode was added that
excludes only the firing bars while still requiring a different session.

**Bar mode's contamination costs power, not validity.** Its control bars sit in sessions that
fire elsewhere, so they are partly in-state, which shrinks a real difference toward zero. It
cannot manufacture one, because the regimes are still matched pair by pair. The regime-loaded
fake is run through bar mode too rather than assuming the argument transfers: it is refused
there as well, and a genuine effect still survives.

The mode is chosen on measured evidence — `session_clustering()` reports firings per session,
share of sessions touched, over-dispersion and the clean-pool size — not on preference.

## 5. Feasibility on real data: P03-shaped, NQ, matching only

`python -m futuresres.reporting.state_control_feasibility`. **No returns are read.** The state
is fixed a priori: 5-minute RTH bars, |log return in bps| / bar volume, thresholded at the
trailing **90th percentile of the same 30-minute bucket over the previous 60 sessions**. NQ
rather than the spliced series, because §54 measured that the ratio steps up 3–5× at the
2019-05-31 contract change.

    bars 272,970    sessions 3,559    firings 27,791    7.81 per session
    sessions touched by the state          3,294  (92.6%)
    firings-per-session variance ratio     7.38  (vs Poisson)
    clean sessions                         265

| exclusion | matched | distinct control bars | reuse | era fallback | verdict |
|---|---|---|---|---|---|
| strict | 27,437 / 27,437 | 8,264 | 69.9% | **37.4%** | **FAIL** |
| bar | 27,437 / 27,437 | 25,483 | 7.1% | 0.0% | **MATCHED** |

**Strict mode fails on arithmetic, not on tuning.** A state firing 7.81 times in a ~77-bar
session touches almost every session; even a perfectly *independent* state at that rate would
touch ~99.9% of them. The 265 clean sessions that survive are not a representative sample —
they range from **0% of 2011 to 17.5% of 2025** — so 37.4% of pairs fall back across years and
69.9% of control bars are reused. No bucketing or threshold fixes it.

**Bar mode is clean on the same state**: every firing matched within its own year, 7.1% reuse.
So a P03-shaped condition **is** controllable, in bar mode, with the contamination recorded as
a power cost.

## 6. What this does and does not settle

**Settled.** The exposure confound now has a control, and the control has been fault-injected
in both modes. A regime-loaded condition cannot pass it. P03-shaped conditions are
controllable on the real sample.

**Not settled.** §17's structural limit is untouched: a condition firing about once per session
still has too few events for any control to help, and strict mode — the one appropriate to
session-level states such as P01 and P04 — is exactly the mode that fails on a frequent state,
so a session-level state must be checked for a clean pool before it is registered. Bar mode's
contamination is a power cost of unmeasured size; it biases toward the null, so it cannot
produce a false positive, but a null result under it is weaker evidence than a null under
strict mode.

**The lookback is a registered parameter, not a detail.** 60 sessions, fixed before running.
It sets the warm-up (566 sessions lost of 4,125), how fast the threshold tracks the volume
trend, and how much the state clusters. It must be carried in any P03 entry as a parameter and
counted against that entry's parameter budget.

# The L-series, closed

**12 hypotheses registered. 180 trials spent. Zero promoted.**

N went 576 → 756; SR\* 0.1334 → 0.1368; the trial chain verifies. Stage numbering throughout
is S1–S8 per `reports/STAGES.md`.

This is the terminal document for the level-reaction catalogue. It is the third such closure
in the programme, after the F-series (`futures_conclusion.md`) and the R-series
(`rseries_conclusion.md`).

---

## Per-hypothesis verdicts

| | stopped | outcome |
|---|---|---|
| **L01** VWAP reaction | S4 | blocked: best cell 211 MGC / 237 MNQ |
| **L02** opening range | S7 | absorption retired on a null, 0 of 27; **sweep arm withdrawn at S5** |
| **L03** prior-day extremes | S7 | retired on a null, 0 of 18 |
| **L04** session extremes | S7 | **inconclusive**: 5 of 18 nominal, 0 BH survivors |
| **L05** overnight range | S5 | degenerate condition; S4 arithmetic withdrawn |
| **L06** session open | S6 | **no valid control can exist** |
| **L07** fair value gaps | S8 | retired on economics: 108 of 108 separated, all negative |
| **L08** moving averages | S4 | blocked: best cell 698 / 705 |
| **L09** weekly/monthly | S4 | blocked: best cell 364 / 446 |
| **L10** placebo control | — | the control; spends no trials |
| **L11** Bollinger breakout | S5 | **withdrawn**: never a breakout test |
| **L12** Asia reclaim, out of sample | S7 | retired on economics: +0.306 bps at 0.64× cost |

---

## Why nothing was promoted, separated by cause

**This is the part worth reading.** "Zero promoted" is one number covering five different
failures, and they are not interchangeable.

### S4 — event count: L01, L08, L09 (3 of 12)
Blocked before any test, on arithmetic. Best cells of 211–705 independent observations against
requirements of 2,862–19,722. **These blocks are firmer than the original gate claimed.** The
gate used a universal tabulated `e` — the top rung of a censored injection ladder, 14–16 bps
at 180m — which is ~5× the empirical resolution of a paired test. Recomputed against a
realistic `e`, these hypotheses would need **7.3–12.4 bps** to produce a BH survivor, against
a programme maximum observed effect of **5.0 bps**. The generic ladder was generous; the blocks
were understated. *No statement about the market.*

### S5 — the condition did not discriminate: L11, L02-sweep, L05 (2.5 of 12)
Withdrawn, not tested. All three used `confirmed_break` against a level price already sat
strictly inside, so the condition fired on **every** level at a fixed minute. *No statement
about the market either* — these never asked a coherent question.

### S6 — no control can exist: L06 (1 of 12)
`open_CME` and `open_RTH` sit exactly at the reference price, so the distance distribution is
identically zero and no matched arbitrary region is comparable. Not a measurement gap and not
tunable: the comparison its registration asks for does not exist.

### S7 — retired on nulls: L02-absorption, L03 (2 of 12)
Ran with adequate power, found nothing. 0 of 27 and 0 of 18 against 1.35 and 0.90 expected.
**They are not equally informative.** L03's mechanism was properly exposed; L02's was not —
its story is the 09:30 equity cash open and MGC's equivalent is the 08:20 COMEX open, so MGC
tested cross-asset spillover. That asymmetry was recorded **before** the run (§42), when a
positive would have been the inconvenient case.

### S7 — inconclusive: L04 (1 of 12)
The only result that got close. 5 of 18 nominal separations, best +3.54 bps at 5.5× the cost
floor — and **zero BH survivors**. It cleared S5, S6, four artifact checks and the S8 era
split, failing only multiplicity. Its observed effect sat **below its own BH bar** of 3.72 bps,
so the S7 failure reflects resolution at the edge as much as correction. The out-of-sample test
(L12, MNQ, 76% power against that magnitude) delivered +0.306 bps: **that magnitude does not
replicate.** Whether a smaller real effect exists is untested.

### S8 — retired on economics: L07, L12 (2 of 12)
The only two to reach the last stage, and both died there rather than on significance. L07
separated in **108 of 108 cells** and was negative in every one, at 1.8×–10.3× the cost floor.
L12 delivered 0.64× its cost floor. **At large event counts significance is nearly assured;
economics is what decides.**

---

## The transferable findings

These outlive the catalogue. Nothing here is about gold or the Nasdaq.

### 1. A shared helper silently broke three hypotheses, and a summary statistic hid it

`confirmed_break` tested a run of k closes beyond a level **in either direction**. Applied to
a level price already sits inside — an opening range, an overnight range, a Bollinger band —
one side is satisfied at the first bar and stays satisfied. Every level fires at
`valid_from + (k−1)`; `k` becomes an offset rather than a selection; a level set's high and low
fire at the same `(row, minute)` and collapse to one event.

Measured: entry-minute **sd 0.05**, all 8,234 levels firing, **99.6%** high/low collision. A
sound condition shows sd 16–370 and 1–4% collision.

**It was invisible in every summary the project printed**, because a condition that fires on
everything produces a large, stable, plausible firing count.

**The §41 retraction matters more than the defect.** §40 concluded the problem was confined to
L11, on two pieces of evidence: L02's firing rates spread across cells (3,001–5,724) where a
degenerate condition would be flat, and 98–99% aggregate overlap rather than a degenerate 100%.
**Both were artefacts of aggregation.** The spread came from L02's sound *absorption* cells
while its *sweep* cells were flat; the overlap figure is a per-hypothesis maximum dominated by
the sound cells. The error was **reasoning about a condition from summary statistics of its
output** — and the only thing that reveals this defect is the entry-minute distribution, which
no report carried.

Fixed in the function: `direction` is now required, and a precondition raises above 25% of
levels starting beyond the level.

### 2. S5 had no name, so the stages ran out of order

L11's **S6 placebo was measured before anything checked its condition discriminated.** The
matching came back clean — distance ratios 0.90–1.06 — and those numbers were meaningless,
because the treatment had not cleared S5. **Matching a control to a condition that cannot
select events is a well-formed computation on an ill-formed input.**

Nothing could notice, because the project had names for "Stage 0" and "Stage 1" and no name at
all for condition validity. **The check that catches it was built reactively, after L11 had
already failed** — and then immediately found the same defect in L02's sweep arm and L05. A
check that exists only because something went wrong is a post-mortem, not a gate.

S5 is now a permanent gate: no condition proceeds to S6 until it passes. **S6 results computed
before S5 passed are discarded, not reinterpreted.**

### 3. One registration in 26 ever stated a predicted magnitude

Across the F-, R- and L-series, **only L12** wrote down how big its effect should be. The
F-series stated none; R03's prediction is mechanistic; R01's bps figures are cost floors.

**So no null in this programme was ever checkable against its own predicted effect.** Every S4
verdict was rendered against a tabulated default — a censored ladder whose top rung is a bound
presented as a floor — and every null was reported without saying what size of effect it could
have seen.

L12 is simply the first time a magnitude existed to check, and checking it found the
significance limb was reachable only in the **top fifth** of its own range (6.8% power at the
bottom). The lesson is the general one: **a registration that states a direction and a
mechanism but not a magnitude cannot produce an interpretable null.**

The proposed S2 check requires a magnitude or an explicit waiver, and **surfaces rather than
auto-rejects** — a small predicted effect is often still worth an economics-only test, and
rejecting by default would filter out exactly those.

### 4. Pooling was never available: L10 is the only disjoint route

Maximum pairwise overlap of firing minutes:

| | overlap | aggregate route |
|---|---|---|
| **L10** — the placebo control | **1% MGC / 5% MNQ** | **OPEN (disjoint)** |
| L01–L09, L11, L12 | **97%–100%** | CLOSED |

**Every substantive hypothesis in the catalogue has a closed aggregate route.** The only
disjoint one is the control, which reaches no verdict. Buying sample size by pooling a
hypothesis's cells is unavailable everywhere it would have helped — the cells re-enter on the
same touches. That is a property of level-based hypotheses **as a class**, not of any entry,
and it is why the whole series resolves on per-cell event counts.

It also means the BH denominators throughout are conservative: 18 correlated cells are not 18
independent looks. That cuts both ways, and both are recorded — a raw count of separations
overstates the evidence by the same token.

---

## What the L-series cost and what it bought

180 trials, raising SR\* from 0.1334 to 0.1368 for every hypothesis that follows. In exchange:
three hypotheses blocked on arithmetic before testing, three withdrawn for conditions that
never asked a question, one shown to be uncontrollable by construction, two nulls, one
inconclusive, and two refuted on economics with the effect measured rather than assumed.

**The most valuable outputs are the four methodological findings above, not the verdicts.** A
catalogue that promotes nothing is the expected result — `CLAUDE_FUTURES.md` says a run
promoting a Sharpe 4.0 strategy is almost certainly a bug. What this series added is a named
gate that did not exist, a shared helper that silently invalidated three registrations, a
measurement of how conservative the detection gate actually is, and the discovery that the
programme had never once written down how large an effect it expected to find.

## Open, and not blocking

- **L07's direction-mix asymmetry** — whether real and placebo entries fire on bullish versus
  bearish zones in the same proportion. If not, drift contributes to §38's sign.
- **The `d` ATR reference period for L01/L06/L08** — a specification question, deliberately
  frozen. Choosing the period that makes L01 schedulable would be choosing a parameter to get
  a result.
- **`f01_rates` OOM** — a machine limitation, documented in `CHECKPOINT.md`.
- **L04 revival**, if ever wanted: a new registration naming `sess_Asia` in advance, on data
  that did not generate it, with a magnitude stated and checked against the reachable
  threshold.

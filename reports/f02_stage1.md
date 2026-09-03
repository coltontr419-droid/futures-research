# F02 - order_imbalance_conditional_overnight_reversal, Stage 1

Run by `python -m futuresres.signals.f02`. CLAUDE_FUTURES.md §5, §6, §7.6.

## Every cell is uninformative, and the gate did not predict that

**144 cells run, 0 informative.** The detectability gate showed F02 with an open per-cell route on MGC at 120m and 240m and an open aggregate route on 5 of 6 combinations. Both were computed on a **declared** firing rate of one per session, and the declared rate was wrong.

| | gate assumed | actually fires |
|---|---|---|
| per cell | 4,006-4,125 | **106-666** |
| aggregate (2 windows) | 6,142-8,250 | **~210-1,330** |

Two causes, neither propagated into the gate:

1. **The condition is threshold-gated.** It fires only when `|imb| > k*sigma`, which is 6-23% of rows depending on k - not every row. A declared rate of "one per session" counted the *opportunity*, not the *trigger*.
2. **The regime split is mandatory and halves the sample again.** Pre-2021 holds ~3,100-3,200 rows and post-2021 ~1,730. The gate assessed F02 on the full sample because nothing told it the hypothesis must be evaluated in two eras.

This is the same class of error as `decisions.md` §13, which the §13 fix did not catch: that repair addressed scan multiplicity and *unmeasured* rates, but F02's rate was **declared and wrong**, which no test was looking for. Every threshold-gated hypothesis in the catalog carries the same defect - see §21.

## Multiplicity

| instrument | era | arm | cells | nominal | expected | BH survivors |
|---|---|---|---|---|---|---|
| MGC | pre-2021 | sell_imb | 18 | 0 | 0.90 | **0** |
| MGC | pre-2021 | buy_imb | 18 | 0 | 0.90 | **0** |
| MGC | post-2021 | sell_imb | 18 | 0 | 0.90 | **0** |
| MGC | post-2021 | buy_imb | 18 | 0 | 0.90 | **0** |
| MNQ | pre-2021 | sell_imb | 18 | 0 | 0.90 | **0** |
| MNQ | pre-2021 | buy_imb | 18 | 0 | 0.90 | **0** |
| MNQ | post-2021 | sell_imb | 18 | 0 | 0.90 | **0** |
| MNQ | post-2021 | buy_imb | 18 | 0 | 0.90 | **0** |
| **all** | both | both | 144 | 0 | 7.20 | **0** |

**Benjamini-Hochberg is applied within each (instrument, era, arm) family and then across the whole hypothesis.** The within-family view is what the catalog asks for; the all-cells row is the honest multiplicity, because all 144 looks were taken.

## Effect against the detection floor

| instrument | era | arm | events (max) | aggregate bps | net | best cell | floor | best/floor |
|---|---|---|---|---|---|---|---|---|
| MGC | pre-2021 | sell_imb | 666 | -0.23 | **-0.88** | +2.30 | 14.34 | 0.16x |
| MGC | pre-2021 | buy_imb | 701 | -0.66 | **-1.31** | +0.84 | 4.17 | 0.20x |
| MGC | post-2021 | sell_imb | 350 | +0.65 | **+0.00** | +2.84 | 14.34 | 0.20x |
| MGC | post-2021 | buy_imb | 408 | +0.39 | **-0.26** | +5.98 | 14.34 | 0.42x |
| MNQ | pre-2021 | sell_imb | 577 | +1.13 | **+0.65** | +2.38 | 2.57 | 0.93x |
| MNQ | pre-2021 | buy_imb | 707 | -0.97 | **-1.45** | +2.32 | 15.66 | 0.15x |
| MNQ | post-2021 | sell_imb | 393 | +3.27 | **+2.79** | +12.97 | 15.66 | 0.83x |
| MNQ | post-2021 | buy_imb | 393 | +0.37 | **-0.11** | +3.04 | 15.66 | 0.19x |

**The floor column is quoted for orientation only.** A detection floor describes the smallest effect that could be recovered *at the sample where it was measured*. These cells hold 106-666 events against floors measured at 2,862 and up, so the applicable floor here is higher than any measured, by an unknown amount. The ratios understate the gap.

## The regime split, which is the reason this hypothesis exists separately

F13 - the unconditional overnight drift - was **excluded** from this catalog because its own authors measured it as decayed since 2021. F02 is the conditional version, and the exclusion note requires it to carry a mandatory regime split. An effect living only in the pre-2021 half is a decayed effect, not a live one.

| instrument | pre-2021 rows | post-2021 rows |
|---|---|---|
| MGC | 3,098 | 1,739 |
| MNQ | 3,210 | 1,732 |

| instrument | arm | pre-2021 aggregate | post-2021 aggregate | direction of change |
|---|---|---|---|---|
| MGC | sell_imb | -0.23 | +0.65 | not decayed |
| MGC | buy_imb | -0.66 | +0.39 | decayed |
| MNQ | sell_imb | +1.13 | +3.27 | not decayed |
| MNQ | buy_imb | -0.97 | +0.37 | decayed |

**This comparison cannot settle the decay question and is reported for completeness only.** Neither era's cells are informative, so a difference between them is a difference between two quantities that are individually indistinguishable from zero. Reporting it as a decay finding would be exactly the error the uninformative marking exists to prevent.

## Which instrument carries a verdict

**Neither.** The gate named MGC as the instrument with an open per-cell route, at 120m and 240m, and that route closes once the real firing rate is used: MGC's best cell holds 666 events against a floor measured at 2,862 and up. MNQ was already below the swept range at every horizon.

Worth stating plainly, because the mechanism points the other way: **F02 is an equity-index hypothesis.** Its counterparty story is the NYSE closing auction and dealers carrying index inventory overnight. MGC is in the registered symbol list and so was run, but a gold contract has no NYSE closing auction, and an MGC result would have been the wrong instrument for this claim even had it been informative. The standing MGC coverage caveat applies on top: 46.14% of this window's minutes are carried forward rather than traded, the lowest coverage of any window in the study.

## No real-data control exists at this event regime

F14, the catalog's negative control, fires ~13 times a session and reaches ~48,000-52,000 events. It established that the harness declines to promote a mechanism-free signal **at that sample size**. F02's cells hold 106-666 events.

**No control can be built at F02's regime on this data.** A once-a-session condition yields ~3,500 events before any threshold gating; F02 fires on 6-23% of those and then splits the remainder in two. Measured candidates at the once-a-session regime resolved in 2 of 12 combinations (`reports/control_candidates.md`), and F02 sits an order of magnitude below even that. So this null carries the §7.2 synthetic GARCH assurance - the harness does not promote idealised noise - and **nothing from F14**. That distinction is stated here rather than left for a reader to infer.

## Data

| instrument | rows | 15:00-06:00 ET minutes traded |
|---|---|---|
| MGC | 4,837 | 46.14% |
| MNQ | 4,942 | 63.52% |

The window spans the CME maintenance break (17:00-18:00 ET) and the thin overnight tape, so a low traded fraction is expected rather than a data fault. It is reported because forward-filling inserts zero returns and biases toward apparent significance - in a run that separates on nothing, that bias had no opportunity to matter.

## Trial cost

**144 trials** - 3 k x 2 windows x 3 holds x 2 arms x 2 eras x 2 instruments. The largest single spend in this catalog, and it raises SR* for everything still untested. Both arms and both eras are what the registered protocol asks for; the cost is recorded rather than avoided by quietly dropping an axis.

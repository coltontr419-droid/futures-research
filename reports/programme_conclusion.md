# The futures research programme — terminal report

**Six series registered; a seventh and an eighth drafted and closed at S2; two single hypotheses
registered and blocked; a ninth series (W, daily horizons) designed, one hypothesis registered and
retired; a tenth (X, monthly horizon) closed at its floor measurement. 96 candidates drafted, 38
registered, 771 trials across two hash-chained logs. Nothing promoted.**

**No edge accessible at this cost structure and account size was found in intraday, calendar or
non-price futures signals, across six independently designed series.**

This is the last document the programme produces. It is written for a reader who has seen none
of the code, none of the logs and none of the earlier reports, and it should be sufficient on its
own to decide whether the question is worth reopening. Every number was measured in one of two
repositories — `futures-research` and `r-series-research` — unless it is labelled an estimate.
References of the form §nn point to `futures-research/reports/decisions.md`, the running record
of every decision, which is never rewritten; corrections are added as new sections.

Written 2026-09-13.

---

## 1. What was being attempted

**The account.** A proprietary-trading futures account with three rules that bind on design, not
just on execution:

| rule | what it forbids |
|---|---|
| **flat by 17:00 ET, every day** | any hold crossing the daily close, including every 24-hour or overnight-into-next-day position |
| **trailing drawdown** | the floor starts 4% below the starting balance and trails the equity peak until the peak reaches +4%, then stays at breakeven permanently (confirmed with the firm, 2026-09-13) |
| **no opposite positions on correlated products** | long one index and short another at the same time |

**The instruments.** MNQ (Micro E-mini Nasdaq-100) as the primary contract and MGC (Micro Gold) as
a second, uncorrelated one. NQ, the full-size Nasdaq contract, supplies the long single-contract
history, because MNQ only exists from May 2019.

**The data.** CME Globex 1-minute bars (open, high, low, close, volume) from Databento, June 2010 to
27 August 2026 — about 4,125 sessions. **No trade-by-trade, order-book or aggressor-side data** was
ever used; the `trades` field in the bars is empty.

**The cost floor.** 0.48 basis points round trip on MNQ and 0.65 on MGC: commission plus an
*estimated* one-tick spread that was never measured. One basis point (bp) is 0.01%. On a $48,000
MNQ contract 0.48 bps is about $2.30.

**The question.** Is there a repeatable, pre-registered edge in these contracts large enough to
trade at that floor, and provable against the number of things that were tried?

---

## 2. How a claim was tested

Every idea passed through eight stages, in order, and stopped at the first it failed.

| stage | question | failing it means |
|---|---|---|
| **S1** mechanism | who loses money to this trade, and why do they keep doing it? | a pattern, not a trade |
| **S2** pre-registration | are all parameters and the predicted size fixed before testing? | any result is a selection |
| **S3** firing rate | how often does it fire, *measured*? | nothing downstream is interpretable |
| **S4** detection floor | is the effective sample large enough to see the effect? | the test cannot produce evidence |
| **S5** condition validity | does the condition select events at all? | the treatment is not a treatment |
| **S6** control | does it beat a matched placebo or control? | a raw number measures exposure |
| **S7** multiplicity | does it survive the count of everything tried? | indistinguishable from luck |
| **S8** out-of-sample and economics | does it survive the post-2021 half, and clear cost? | real but gone, or real but unprofitable |

**Terms used below.**
- **Trial.** One comparison, appended to an append-only, hash-chained log *before* it runs. Nothing
  is deleted, including withdrawn hypotheses. **N** is the count.
- **SR\*.** The Sharpe ratio the best of N worthless strategies would reach by chance. Any candidate
  has to clear it before its Sharpe means anything. At N = 760 it is 0.1368.
- **BH.** Benjamini–Hochberg correction at a 5% false-discovery rate, applied within a hypothesis's
  cells.
- **Placebo / control.** The same trade run somewhere that should *not* work — an arbitrary price
  level at a matched distance, or a matched session where a state does not hold. The reported effect
  is always real minus control, never real minus zero.
- **Effective n and DEFF.** Events inside one session move together, so a thousand events can carry
  far fewer independent observations. The design effect (DEFF) is the ratio.
- **Detection floor / BH bar.** The smallest effect the test can distinguish from zero at its sample
  size and multiplicity.

---

## 3. The six series

### F — the base catalog: 14 registered, 576 trials

Published intraday and calendar effects: intraday momentum, the conditional overnight drift, the
half-hour cycle, gold's LBMA auction flow, volatility compression, cash-open drive, gold session
momentum, cross-asset regimes, settlement flow, two canonical technical rules, pre-FOMC drift, the
unconditional overnight drift, and a timestamp-hash negative control.

**Of 14, exactly one was tested at adequate power** — F05, volatility compression, 45 informative
cells at 11,000–18,600 events, best cell 0.05× its floor. It came back empty.

| outcome | hypotheses |
|---|---|
| tested at adequate power, null | F05 |
| ran, but no sample could carry a verdict | F02, F07 |
| tested only on a narrow route | F03, F04, F06 |
| never run — arithmetic or premise closed them | F01, F08, F10, F11 |
| excluded before any trial | F12 (pre-FOMC: ~128 events, and the hold crosses 17:00), F13 (overnight drift, decayed since 2021) |
| never scheduled | F09, F14 (the control) |

**What closed it: event scarcity.** Most mechanisms fire once a session, and sixteen years of that
is about 4,000 observations against a detection floor needing 19,722 on MNQ. F02 declared one firing
per session and delivered 106–707 per cell.

### R — relative value and flow: 5 registered, 10 trials (a separate log)

Built on one piece of arithmetic: a market-neutral spread has about 0.45× the volatility of a single
leg, which cuts the sample needed by roughly 5×. **The premise held; the trades did not.**

| | what it tested | closed on |
|---|---|---|
| R01 | NQ/ES intraday relative value | **economics** — a real effect, +0.452 bps at t ≈ 9.25, against a 0.96 bps two-leg floor, and decaying by 3.3× within the sample |
| R02 | micro–mini basis as a retail flow signal | **its own gate** — basis half-life 0.249 bars against a 1.5-bar threshold; nothing persists to trade |
| R03 | leveraged-ETF rebalance flow | **event count** — 3,415 usable sessions against 19,722 required |
| R04 | cross-sectional ranking across the futures complex | **account permission** — a long/short book is exactly what the account prohibits |
| R06 | prop-evaluation sizing as a barrier option | **complete**; a computation, not a hypothesis |

### L — price levels: 12 registered, 180 trials

Reactions at VWAP, opening ranges, prior-day and session extremes, overnight ranges, the session
open, fair-value gaps, moving averages, weekly/monthly levels, Bollinger bands, and an out-of-sample
Asia-session reclaim. Every result was real minus a distance-matched placebo level.

| stopped at | hypotheses |
|---|---|
| S4, too few events | L01, L08, L09 (best cells 211–705 against 2,862–19,722) |
| S5, condition fired unconditionally | L05, L11, L02's sweep arm |
| S6, no valid control can exist | L06 (levels sit at the reference price; nothing to match) |
| S7, null | L02 absorption (0 of 27), L03 (0 of 18); L04 inconclusive (5 of 18 nominal, 0 survive BH) |
| S8, economics | L07 (108 of 108 cells separate, all **negative**, at 1.8–10.3× cost); L12 (+0.306 bps, 0.64× cost) |

### N — levels revisited: 10 candidates, 3 registered, 3 trials

A second pass at level mechanisms with stronger published grounding. Four declined on arithmetic
before registration, one deferred, one closed as a conditioner with no primary, one never a trade.

- **N04, N05** (swing-pivot traps and sweeps): withdrawn at S6 — median distance from price 0.000,
  61.4% exactly zero, so no placebo can match them.
- **N02** (round-number cross continuation, Osler's stop-cluster mechanism): ran at S7, pooled
  ~+0.07 bps against a registered +2.0 to +5.0, 0 of 3 cells, retired. **Its thresholds were in index
  points on an index that rose 14×**, so an 8-point break was 41 bps in 2010 and 2.9 bps in 2026.

### P — non-price observables: 13 candidates, 1 registered, 1 trial

Participation share, spread-volume contamination, thin-move illiquidity, order-flow imbalance, open
interest, positioning. Nine closed on arithmetic before any trial — below their BH bar, or unable to
state a magnitude at all.

- **P03** (thin-move reversion, Amihud/Kyle): the only one to reach S7. Its horizon was measured from
  the state's own 3.5-minute decay and its magnitude from impact measured on the series: a firing
  carries 9.18 bps of excess displacement. Pre-registered to clear if more than 6.8% of that reverted
  within 15 minutes. **Measured: 0.86%.** Real minus control +0.079 bps against +0.625; the real leg is
  **−0.28 bps net of cost**, so it loses money before significance matters.

### Q — a portfolio of event and calendar edges: 12 candidates, 0 registered, 0 trials

Designed as a portfolio from the start, on the arithmetic that four to six edges at Sharpe ~1.0 with
correlation ≤ 0.1 reach what one edge at Sharpe 2.1 would. **Closed at S1–S2 without spending a
trial:**

1. **Q01 (conditional overnight drift) is F02**, at 87.1% firing overlap. F02 already looked at the
   same post-2021 selloff nights on the same data, so there is no fresh test on disk.
2. **Q01 and Q02 are one bet.** Their conditioning variables correlate at Spearman +0.972 (+0.991
   since 2021), and on every Q01 night Q02 takes the same side.
3. **Q02 crosses the 17:00 ET hard exit** as written.
4. **Q03 and Q04 were already excluded** as F12.
5. **Every predictable candidate is below or straddling its post-2021 BH bar**: Q01 straddles, Q02,
   Q03, Q05 and Q06 are below. Q04 and Q07 state no direction; Q08–Q12 are not signals.

**The one remaining route was considered and rejected on arithmetic.** A clean Q01 test needs data
nobody has looked at. Matching the post-2021 sample's power needs **1,397 sessions**; ten have
accumulated since the data ends, at ~245 usable sessions a year. **That is a 5.7-year wait**, not a
deferred decision.

---

## 4. What bound, across all six

"Nothing promoted" covers four different constraints, and they are not interchangeable.

### Cost — decided most of what could actually be measured

When a test had enough data, it found an effect too small, or of the wrong sign, to pay for itself.
**Across four series nothing failed for want of precision where the sample was adequate** (§45).

| | effect | against cost |
|---|---|---|
| L07 | negative in every one of 108 cells | 1.8–10.3× the floor, wrong way |
| L12 | +0.306 bps | 0.64× |
| R01 | +0.452 bps, decaying 3.3× | 0.47× a two-leg 0.96 floor |
| P03 | real leg +0.20 gross | −0.28 net |

At a 15-minute horizon the cost floor (0.48) and the BH bar (0.463–0.625) coincide. Below roughly that
horizon, cost binds before significance does.

### Sample — decided most of what could not be measured

| | available | needed |
|---|---|---|
| F-series, once-per-session mechanisms | ~4,000 | 19,722 |
| F02 per cell | 106–707 | 2,862+ |
| R03 | 3,415 sessions | 19,722 |
| L01, L08, L09 best cells | 211–705 | 2,862–19,722 |
| F12, pre-FOMC | ~128 events | — |
| Q03, post-2021 FOMC days | ~46 | — |
| Q01 forward test | 10 sessions | 1,397 |

**The sample cannot be extended where it matters.** Going back further only adds to the pre-2021 half,
and the post-2021 half — the one that decides (§7) — is about 1,390–1,440 sessions whatever the start
date.

### Permission — closed things the market was never asked about

- **17:00 ET flat**: F12's 24-hour pre-FOMC hold, Q02's hold into the evening session.
- **No correlated opposite positions**: R04, the strongest unexplored idea in the R-series, closed
  before any work because a long/short book is the prohibited structure at any size.
- **The trailing drawdown**: with no edge, the chance of reaching the +4% lock before a 4% drawdown is
  exp(−1) = **36.8% at every position size**. Sizing multiplies an edge; it cannot supply one.

### Specification — the design itself was wrong

- **Conditions that did not select anything**: L11, L05, L02's sweep arm fired on every session (see
  section 5, finding 1).
- **Controls that cannot exist**: L06, N04, N05.
- **Thresholds in the wrong units**: N02 in points on a 14× index.
- **A declared firing rate wrong by up to 40×**: F02.
- **An instrument where the mechanism is undefined**: 72 of F02's 144 trials went to gold, which has no
  NYSE closing auction.
- **A proxy measuring the wrong thing**: Q01's price-change-per-volume is an illiquidity measure, not
  an order-imbalance one (its correlation with a volume-classified imbalance ratio is 0.792, against
  0.774 for the raw return it divides).

---

## 5. What transfers

Each of these was found because something got measured that did not have to be.

**1. The `confirmed_break` defect (§40–§41).** A shared "price broke a level" function triggered on a
run beyond the level in *either* direction, and price at the sampling minute is never exactly on a
level. So L11's Bollinger breakout fired on the first bar of every session, its upper and lower bands
fired at the same minute, and its placebo matched cleanly against a condition that selected nothing.
The same defect was then found in L02 and L05. **Rule:** a direction is now a required argument, the
guard raises rather than warns, and conditions are checked for firing-minute variance before anything
else.

**2. The missing-magnitude gap (§45).** Of 26 registrations across three series, **one** stated a
predicted effect size. That one, L12, carried a significance requirement reachable only in the top
fifth of its own predicted range (bar 2.82 bps against +1.3 to +3.5). **Rule:** every registration
states a magnitude and checks it against the BH bar at its expected n, before running.

**3. S5 before S6 (§46, STAGES).** L11's placebo came back with distance ratios of 0.90–1.06 — clean,
and meaningless, because the condition had not been shown to discriminate. **Rule:** condition
validity is a permanent gate, and control results computed before it passes are discarded, not
reinterpreted.

**4. The `valid_from` placebo convention (§46).** Placebo levels are matched on distance from price at
the moment a level becomes valid, not at trade time. No hypothesis trades at that moment, which made
the convention look wrong. Measured, trade-time distance collapses to 0.2–0.6 across eight level
types, so matching there matches on nearly zero. **`valid_from` is right because it measures
reachability.** Switching would have rescued the swing-pivot hypotheses by breaking the control for
every other level type.

**5. Session versus event as the unit (§45, §54).** Events inside a session are correlated, so the
session is the unit of observation. Design effects measured 1.14 (sparse events), 2.19 (round numbers)
and 65.6 (volume climaxes). N06 fired 18.8 times a session and looked well-powered; on 386 qualifying
sessions its bar was 17 bps. Raw counts overstated effective n by 2.8–13.7×.

**6. Scale invariance (§51–§52).** The index rose 14× from 2010 to 2026, so any threshold in ticks or
points ran a different trade in each era, and every pooled check passed while the condition drifted
underneath. Ratios are not automatically safe: price-change-per-contract steps 3–5× at the NQ→MNQ
contract change. **Rule:** thresholds in bps, volatility units or a rank within their own trailing
distribution — or the price range stated and the era split pre-registered.

**7. The mode partition (§54–§55).** A *state* (a market condition rather than a price level) has no
location, so it needs a different control: a matched session in the same time-of-day bucket,
volatility quantile and year where the state does not hold. A state firing several times a session
touches almost every session — P03's touched 92.6%, leaving 265 unrepresentative clean sessions — so
it must be controlled bar by bar. A once-a-session state must be controlled by excluding whole
sessions, which fails exactly when clean sessions are scarce. **Rule:** a clean-pool check at
registration for any session-level state.

**8. Outcome fault-injection for nulls (§58, §60).** A null produced by a sign error or an off-by-one
looks identical to a real one. P03's outcome path was tested against a known injected reversion
before its null was believed. **Now a standing rule, stricter than what P03 did** (§7 below).

**9. Clearing a within-entry correction is not clearing the programme's bar (§63, §64).** BH within
an entry and SR\* across the programme answer different questions, and a result can pass the first
while failing the second. Four of the S-series' nine entries — RSI, Bollinger, MACD, stochastic,
each in its shortest-timeframe cell — separated from their matched reference at 1.19–1.88 bps,
inside their own within-entry BH bar. Converting SR\* to the same units (a per-event effect has
per-observation Sharpe equal to effect over per-event noise, so the effect that merely reaches SR\*
is SR\* times that noise) put all four roughly half of the prevailing SR\* at the N they would add.
**Rule:** a registration's own BH bar is necessary and not sufficient; the comparison that decides
anything is against the trial log's cumulative SR\* at the N the entry would face, not the N it was
designed against.

**10. A filter that closes every candidate it can evaluate is stronger evidence than one that closes
most of them (§63, §64).** The P-series closed 9 of 13 candidates at no trial cost, but five of
those could not state a predicted magnitude at all and were closed by being unreachable rather than
by being measured against a bar; the Q-series closed 12 of 12, seven the same way. The S-series
closed 9 of 9, and every one of the nine had stated a direction and a mechanical trade rule, so every
one was actually tested against the arithmetic rather than exempted from it. **An unpredictable
candidate survives a filter by sitting outside its reach, not by passing through it** — zero
unpredictable candidates is the harder number to produce, not the easier one, because every entry
had to be evaluated rather than waved past.

**11. A ratio of one series' own moments still drifts when the price grid under it does not scale
(§65, §66).** Finding 6 covers a ratio whose denominator trends: P03 divided a price move by contract
volume, which steps 3–5× at the NQ→MNQ splice and trends on its own. T02's jump fraction is the other
case. J = (RV − BV) / RV is built from **one** return series over **one** window, so both terms scale
together and a change in price level cancels exactly — and J still **halved across eras** (index
median 0.093 → 0.049, MGC 0.112 → 0.046). The tick grid is fixed in price units while price rose: as
the index tick shrank from 0.56 to 0.12 bps, the share of 1-minute returns that are exactly zero fell
from 18% to 3%, and each zero removes two bipower terms against one realised-variance term. So a fixed
J threshold selected a different share of windows in each era. **A reader applying finding 6 to J would
have concluded it was safe** — it has no trending denominator — so finding 6 does not cover this; it
was found only because J was measured by era rather than declared scale-free from its algebra.
**Rule:** any statistic computed from prices on a tick grid is checked by era against the share of
zero returns, however its algebra scales; thresholds on it are ranks within its own trailing
distribution.

**12. Citing a prior entry as evidence requires matching on what it tested, not on what it is about
(§69–§71).** V01 (reopen displacement reversion) was registered with L02's absorption-arm null — 0 of
27 — beside its mechanism, because both name the same counterparty: whoever is positioned against thin
depth when real liquidity arrives. But L02 tested the 09:30 cash-open range, on MGC only, where it
measured spillover from the equity open into gold, and a note written before it ran said its null
could not refute its own mechanism. Nothing had ever tested V01's mechanism. The record would have
read as "refuted in advance" by an entry that never examined the reopen. **Rule:** before a prior
entry is cited for or against a new one, check its session and clock, instrument, horizon, condition,
and any pre-written limit on what its result can establish. A shared counterparty is a mechanism
match, not an evidence match.

---

## 6. Errors found inside corrections

**Corrections are where provenance is least likely to be checked, because the reasoning feels
finished.** These were all caught, and every one is recorded under its own section rather than
quietly fixed.

| where | the correction | the error inside it |
|---|---|---|
| §40 → §41 | L11's defect declared L11-specific | the defect was in a shared function and also broke L02 and L05 |
| §47 → §49 | N02's firing rate re-measured, overturning the draft's assumption | the population it measured admitted a level only when price reached it, so real levels were touched 100% by construction |
| §52 → §53 | a scale-invariance gate added | fault-injecting it showed the gate looser than its own specification — it accepted half the escape hatch |
| §45 → §53 | the selectivity analysis that followed L12's corrected pre-registration | its "0.65 firings per session" optimum did not survive re-measurement in bps; the curve rises to the tightest setting tested |
| §54 | the P-series draft, written after §45 and §52 | repeated both errors — counted bars as observations, and called a ratio scale-invariant because it was a ratio |
| §55 | the state control's year check | an unmatched year had a noise floor of 0.37–0.55 against a 0.25 tolerance; it would have failed well-behaved conditions |
| §56 → §57 | a √2 SE inflation for a difference of two means | **the constant being inflated was already a difference SE** (64.7/√4,052 = 1.016, L12's own paired bootstrap), so the correction double-counted |
| §57 | a module built to replace recalled literature with measurement | contained an invented one-tenth cutoff that declared CLEARS |
| §59 | a session volatility window | the session open was taken at 23:59 rather than 18:00, giving **130.5 bps — almost exactly the familiar ~130 daily figure**, and so a wrong answer indistinguishable from a right one. Corrected: 126.3 |
| §59 → §60 | "3,415 is not in the repo" | checked one repository of two; it is R03's measured ceiling |
| §67, §68 | U01's gap count, on the NQ→MNQ splice | **2010–2012 index sessions end in the evening in the vendor's own data** — the 2010-06-08 session holds 119 rows ending 20:30 ET, none in RTH, identical in the vendor CSV, the parsed parquet and the continuous series (median ~110 bars a session in 2010–2012 against 1,380 now). Each such session's "prior close" was an evening print, and the next reopen showed a **fake 21-hour break**. Every bar was valid and no check failed; the count was wrong downstream. Found through that break-length anomaly, not through the fill rates, and the validity rule that fixed it can only REMOVE sessions, so it cannot bias the count toward the floor |

**The pattern.** Almost none were arithmetic slips. Each was a quantity computed correctly for a
different object than the one in hand: a constant from a different statistic, a count of the wrong
unit, a ratio with a non-stationary denominator, a figure from the other repository. **Check the
provenance of any constant a correction adjusts, and treat a number that matches expectation as
unverified until its window is.**

---

## 7. Two standards adopted at close, and what they say about earlier findings

**The era break is 2021-01-01, and the post-2021 half decides.** The best-documented anomaly in this
instrument class, the overnight drift, was declared gone since 2021 by its own authors; R01 decayed
3.3× within its sample. A result holding only before 2021 is not a result.

**A null counts only from a pipeline demonstrated to recover an injected effect of the size being
sought, at the run's own noise and sample size.** Recovering a larger effect, or the same effect on a
larger sample or quieter synthetic noise, shows that the plumbing works, not that the test could see
what it was looking for.

Both are written into the stage reference and enforced as registry gates for any future entry, and
both gates were fault-injected.

**The second standard is a caveat on the past, not only a rule for the future.** Four series reported
nulls before it existed. Every one of those nulls falls below it — **not because nothing was injected,
but because the injections were the wrong size**:

| series | nulls | the injection that existed | why it falls short |
|---|---|---|---|
| F | F03, F05, F06 (F02, F07 uninformative) | a planted ~90 bps edge; detection floors from injected effects | far above any sought effect; floors used a different effect construction |
| L | L02, L03, L12 (L04 inconclusive) | a paired statistic recovering +2.0 bps | at 5 bps per-event noise against ~65 on real data |
| N | N02 | the same | the same |
| P | P03 | +4.0 bps recovered as +3.45 | 6.4× its 0.625 threshold, at n = 400 |

The R-series reported no null: its closures were a separation, a measured half-life, arithmetic and
permission.

**No closure is reversed**, because most rest on economics or event count, which need no power
argument. **What changes is one word.** Where a null was the reason for closure — F05 included, the
one F-series test called adequately powered — it now reads *not found by a pipeline never shown to see
this size*, not *absent*.

---

## 8. Provenance notes

1. **The drawdown table in the Q-series handoff is only partly reproducible under its own rule.** The
   standard trailing-drawdown formula reproduces five of its nine cells within 2.3 points, one within 5,
   and misses three by 13–22 points. No finite time horizon explains them; the best, five years, still
   misses one cell by 24. Its source is unverified. The rule it assumed was also wrong: the lock is at a
   +4% peak, not +10%.
2. **3,415 sessions** is R03's measured usable-session ceiling in the R-series, attributed in a later
   brief to the F-series. The nearest figure in `futures-research` is 3,435 sessions with a complete
   last-30-minute window.
3. **Sessions available since the data ends** were quoted as twelve; measured, ten.
4. **N = 760 is one log.** It covers F, L, N and P. The R-series' 10 trials are in a separate chain.
   The programme total is 770.
5. **Literature figures** (the 3.6%/yr overnight drift, 49 bps pre-FOMC, turn-of-month concentration)
   were used only as labelled estimates for S2 filtering, never as evidence. Several were recalled
   rather than checked, and are marked so where they appear.

---

## 9. Conclusion

**No edge accessible at this cost structure and account size was found in intraday, calendar or
non-price futures signals, across six independently designed series.**

That is a finding, and it is bounded:

- **It is about this cost structure**: 0.48 bps round trip on micro contracts.
- **It is about this account**: flat by 17:00 ET, a trailing drawdown, no correlated opposite positions.
- **It is about this information**: 1-minute bars, with no trade, quote or aggressor-side data.
- **It is about these horizons**: intraday to one session.

Within those bounds it is not a statement that the tests were too weak to see anything. Where samples
were adequate, effects were found — R01's at t ≈ 9.25, L07's in 108 of 108 cells — and they were too
small, the wrong sign, or decaying. Where samples were not adequate, the arithmetic said so before any
trial was spent. The caveat in §7 weakens the word *absent* on specific nulls; it does not change
which way the evidence points.

### The sharpest form of the result — added 2026-09-29, promoted from `decisions.md` §61

**Trading more often cannot close the gap.** This is stronger than any individual null, because it
does not depend on any one hypothesis being right or any one sample being adequate.

The edge a strategy needs *per trade* falls as it trades more often — spread a fixed annual target
over more trades and each one has to carry less. So "trade more frequently" looks like a route out.
It is not. Computed for one MNQ contract ($48,000 notional) against a $50,000 account, the **gross**
bps required per trade, and its ratio to **+0.452 bps, the largest effect this programme measured
anywhere** (R01):

| trades/yr | gross needed @10% | @15% | @20% | ×R01 @15% |
|---|---|---|---|---|
| 245 | 4.732 | 6.858 | 8.983 | 15.2× |
| 1,000 | 1.522 | 2.042 | 2.563 | 4.5× |
| 5,000 | 0.688 | 0.792 | 0.897 | 1.8× |
| 25,000 | 0.522 | 0.542 | 0.563 | 1.2× |

**The ratio falls, but it converges to 1.062× and never reaches 1.** The limit is not a modelling
artefact: as trades → ∞ the required *net* edge per trade → 0, so the required *gross* edge → the
cost floor itself, 0.48 bps. And **0.48 > 0.452**. The round-trip cost alone exceeds the best effect
ever measured here, so no trade frequency, holding period or position size reaches profitability.

Sizing cannot help either, for the reason §4 already gives about the drawdown: sizing multiplies an
edge and cannot supply one. A negative net edge scales to a larger negative number.

**What this closes, and what it does not.** It closes "trade it more often" and "trade it bigger" as
routes, permanently, on measured numbers rather than on a null. It leaves §10 exactly as written: the
gap is closed only by a **larger effect** (which needs different information) or a **lower cost**
(which needs a different cost structure) — and §10.3 already shows that full-size contracts at
0.22 bps do not rescue any specific result on record.

---

## 10. What would have to change

For the question to be worth reopening, at least one of the four binding constraints has to move.

1. **Information, not ideas.** Aggressor-side trade data or order-book data is the one information
   class never examined — signed order flow, true order imbalance, book depth. Every series here read
   the same 1-minute bars. This is a data purchase, and it changes what is measurable rather than what
   is guessed.
2. **Permission.** An account allowing correlated long/short positions reopens R04, the strongest
   unexplored idea on record. An account allowing holds through 17:00 ET opens daily and multi-day
   horizons, which this programme could not touch.
3. **Cost.** Full-size contracts cost about 0.22 bps rather than 0.48, but need an account sized for
   10× the notional. **This alone would not reopen anything recorded:** L12's +0.306 bps would clear
   0.22 but failed significance in 0 of 9 cells; R01's +0.452 would still sit below a 0.49 bps
   NQ-plus-ES floor, and was decaying; P03's real leg is +0.20.
4. **Time.** Genuinely unseen data. The only clean remaining test, Q01, needs about 5.7 years of new
   sessions.

**What would not: starting a seventh series.** Six independently designed series — published
anomalies, relative value, price levels, revisited levels, non-price observables and a portfolio of
event and calendar edges — failed on the same four constraints. A seventh drafted against the same
1-minute bars, the same cost floor and the same account inherits all four. So does re-running any
closed hypothesis with new parameters. **A seventh series would be widening the search until something
appears, which is exactly what the trial log exists to prevent.**

**This was then tested rather than left as an argument, 2026-10-02 (§63, §64, CLOSED).** A seventh
series was designed specifically so that it would not be the widening-search case the paragraph
above warns against — nine mechanically specifiable retail indicators, each a separate hypothesis
with a stated direction and trade rule, its overlap with the existing registry checked before any
new cell was drafted, anything requiring discretion dropped and the reason recorded — and it closed
on arithmetic anyway, without registering anything or spending a trial.

**Five of its nine entries were already in the registry**, one of them — fair value gaps — having
already been run at the only event count in the programme adequate to answer this series' own
question: L07, **108 of 108 cells separating, negative in every one**, at 1.8–10.3× cost. The
remaining 270 trials the series would spend would raise N to 1,030 and SR\* to 0.1406, and **the
required per-event effect at that SR\* is 9.10 bps at a 180-minute horizon and 3.71 bps at 30
minutes, against a largest predicted magnitude of 2.0 bps and a largest effect ever measured here of
5.79 bps.** Four entries clear their own BH correction in their shortest-timeframe cells and all
four sit below the prevailing SR\* at roughly half of it — finding 9 above. All nine entries stated
a predictable magnitude and none escaped the filter by being unpredictable, which finding 10 above
records as the stronger result, not the weaker one. The paragraph two above predicted the outcome;
the arithmetic is on file so the prediction is checkable rather than rhetorical.

**Three weaknesses in the design are recorded as unresolved, not as settled against it** (§64): five
of the nine entries have no firing rate measured at any timeframe and rest on an extrapolation
rule; one entry's threshold, as drafted, is in price points rather than bps and repeats the exact
scale error that retired N02; and five pairs of entries have unmeasured collinearity, any one of
which could turn out to be a single bet counted twice, as Q01 and Q02 were. None of the three
changes the arithmetic above — they are gaps in the design that a future registration would have to
close, not grounds on which the current close could be reversed.

**An eighth series, 2026-10-02 — the statistical character of the price path (§65, §66, CLOSED).**
How price arrived, rather than where, when or in what state. Two zero-trial measurements and an S2
filter; nothing registered, no trial spent.

- **A volume clock closes the methodological route.** It was the one idea that attacked a binding
  constraint rather than looking for a new effect. Effective n **falls** under it (0.48× on MNQ,
  0.41× on MGC): there are no dead bars to remove, only right-skewed traded minutes to merge. So the
  floor that blocked L01, L08 and F01 is a power floor that resampling does not move.
- **Splitting by the sign of the conditioning move validates the sign-symmetric design** every series
  used rather than exposing it: L07 (all 108 cells), P03 and R01 each carry their effect on both
  sides, at power §60 accepts. It also closes the L07 direction-mix question open since the L-series.
- **T02 and T04 are not collinear but each fails on its own** — T02's condition holds in 57–94% of
  windows, T04's in under 0.2% — and **T03 repeats finding 9**, clearing its own BH bar while sitting
  below SR\*. T06 restates F05; T07 has no primary to condition.

**With it the statistical-character axis is closed alongside level, state and time — the fourth and
last structural dimension reachable from the data on disk** (where price is, when, in what state the
market is, how price arrived). Like the Q- and S-series, it closed at S1–S2 on arithmetic and on
measured properties of its own conditions, not on nulls at adequate power. **What remains requires a
data purchase or an account structure permitting constructions this one does not** — §10's items 1
and 2. The data item is concrete here: a true volume clock, and a jump/diffusion split free of the tick
grid, both need trade-level data.

---

## 11. The ledger

| log | N | covers | SR\* | chain |
|---|---|---|---|---|
| `futures-research/trials.jsonl` | **762** | F 576, L 180, N 3, P 1, Q 0, W 1, Z 1 | **0.1368** | verifies |
| `r-series-research/trials.jsonl` | **10** | R01 9, R02 1 | never binding | verifies |

Controls, firing-rate measurements and computations (F14, L10, R06, the Q09 drawdown arithmetic) are
logged to separate `measurements.jsonl` files and spend no trials. Withdrawn and excluded hypotheses
stay in the registry, and their trials stay in N.

| series | drafted | registered | trials | promoted |
|---|---|---|---|---|
| F | 14 | 14 | 576 | 0 |
| R | 5 | 5 | 10 | 0 |
| L | 12 | 12 | 180 | 0 |
| N | 10 | 3 | 3 | 0 |
| P | 13 | 1 | 1 | 0 |
| Q | 12 | 0 | 0 | 0 |
| **S** | **9** | **0** | **0** | **0** |
| **T** | **7** | **0** | **0** | **0** |
| **U01** (single) | **1** | **1** | **0** | **0** |
| **V01** (single) | **1** | **1** | **0** | **0** |
| **W** | **5** | **1** | **1** | **0** |
| **X** | **7** | **0** | **0** | **0** |
| **Y** | **7** | **0** | **0** | **0** |
| **Z** | **2** | **1** | **1** | **0** |
| **total** | **105** | **39** | **772** | **0** |

"Drafted" counts candidates written up as hypotheses in a series document. The R-series also named an
R05 direction that was never drafted as a hypothesis, and it is not counted.

**The S row was added 2026-10-02** — a seventh series, retail indicators against a matched arbitrary
reference, **designed and closed at S2 but not registered**; see `reports/S_SERIES_DESIGN.md` and
`decisions.md` §63–§64. It is counted here because a series that is drafted and not registered is
still a series the search looked at, which is exactly how Q is counted. **N, SR\* and the two chains
are unchanged.** Five of its nine entries are already in `hypotheses.yaml` under another letter (L07,
F10, L01, L08/F11, L11, F11), so §10's argument above is not merely unrefuted by it — the S-series is
the clearest instance of it on record.

**The T row was added 2026-10-02** — an eighth series, the statistical character of the price path,
**two measurements run and the rest closed at S2, nothing registered**; `T_SERIES_CANDIDATES.md` and
`decisions.md` §65. **N, SR\* and the chains are unchanged.** Its two zero-trial measurements changed
no closed conclusion: a volume clock does not move the binding floor, and L07, P03 and R01 each carry
their effect on both sides of a sign split.

**The U01 row was added 2026-10-02** — a single hypothesis from an unsourced third-party claim
("large opening gaps fill only ~8% of the time"), **registered and blocked on event count**: 104 and
46 gaps of 0.4% or more in sixteen years against floors of 5,884 and 2,862. Its fill-rate curve
tracks a driftless random walk, and gaps that size fill 46–100% of the time here (46–81% where n exceeds three). `decisions.md` §67.

**The V01 row was added 2026-10-03** — reopen displacement reversion, a mechanism written after U01's
fill curve showed the effect and registered post-hoc, marked so. **Blocked at its ceiling**: even if
every valid daily reopen fired, 2,469 and 1,926 events against floors of 5,884 and 2,862 — so no
threshold had to be chosen, and no forward return was computed. `decisions.md` §69.

**The W row was added 2026-10-03** — a ninth series at **daily horizons**, which this report's §10
filed as forbidden and which chained 18:00-to-16:55 session holds reach (subject to the firm's
confirmation). Measured: the chain keeps 98–99% of a day's variance at ~0.4% of a day's SD per round
trip, so **cost stops binding**. What binds instead is the multiple-testing bar for daily strategies
(Sharpe 0.96–1.39 at N = 760) and, under §62's objective, the drawdown risk budget. Its best candidate,
trend plus carry (prior 0.77–1.27), is the first in nine series whose published prior reaches a
multiple-testing bar here. Designed, not registered. `decisions.md` §72.

**W04 was registered 2026-10-03** — trend plus carry across six sectors, one portfolio-level trial,
decided at the unit-consistent post-2021 bar (≈1.39), registered before its daily data was bought and
amended before any of it was read. Its success condition, prop-evaluation EV for this account, was
computed: ≈+$2,300 per $80 evaluation at the bar's Sharpe, at a small optimal size that one MNQ
contract already exceeds. `decisions.md` §73.

**W04 was run 2026-10-03 (trial t00767) and retired**: post-2021 net Sharpe −0.42 against its bar of
1.31, and only 0.31 before costs — it would not have cleared at zero cost. The run also corrected the
W-series' central premise: **cost does bind at a daily horizon on low-volatility markets** — a daily
round trip is ~5% of a day's SD on the euro and 10-year micros against 0.5% on MNQ, and equal-risk
sizing loads exactly those, costing 0.73 of Sharpe. N 761, SR\* 0.1368. `decisions.md` §76.

**The X row was added 2026-10-03** — a tenth series at the monthly horizon, drafted outside this
repository, **closed at its own floor measurement with nothing registered.** Three of its seven
candidates repeat W work (TSMOM and carry ran as W04's sleeves). Measured: the daily flatten tax
excludes the euro, 10-year and copper micros on cost, and post-2021 the seven markets pool to 255
effective months against 404 needed to see a 0.2 monthly Sharpe at the SR\* bar (185 on the cost
survivors). A null at this horizon could rule out only effects two to three times the literature's
per-market TSMOM. `decisions.md` §77.

**The blocked-entry reconciliation was recorded 2026-10-09.** Every event-count block — the eight
registry entries blocked on event count, R03 and F12 — was re-derived under current conventions: counts
per cell and measured, the withdrawn L05 count, effective n, and the post-2021 half. **No gap narrowed.**
Two entries carried superseded numbers, and both corrections widen the gap. F01's "4,125 events" was a
pre-§22 declared ceiling; measured, its best cell is 3,523 (MNQ) and 3,449 (MGC) and its worst 66 and
115, which is 5.6× and 1.63× short at the best cell, up from 4.8× and 1.4×. L05's block rested on a
count of a condition that fires on every session, withdrawn in §45, and its 0.79× — the closest any
recorded count came to a floor — belonged to that withdrawn condition; its status is now `excluded`, as
L11's is. **V01's 1.15× at the 180-minute proxy is the narrowest live figure and is not a candidate**:
it is a ceiling count with every reopen firing and no threshold applied, and at its own 60-minute
horizon it is 2.25× short, and 4.9× short on the post-2021 half (all three with the Sunday reopens V01's
wording excludes; as defined, 1.49×, 2.92× and 6.2×). **The §65 caveat applies to the source
reconciliation**, which ran on Sonnet at the user's instruction and recomputed from the record rather than
measuring; the F01 counts are the §22 measurement carried forward. `decisions.md` §78.

**The Y row was added 2026-10-09** — an eleventh series that stops searching the market and measures
the account instead. On 2,638 real MNQ sessions with drift removed, **one $80 evaluation is worth about
+$60 to +$127 at zero edge**, positive in every window and both eras, because the firm absorbs losses
beyond the fee; a martingale argument puts the structural value near +$82 and says sizing cannot move it
much. It is a lottery with positive expectation — ten evaluations finish net positive 26% of the time —
and it rests on account rules not yet supplied. Nothing registered; no trial. `decisions.md` §79.
Under Tradeify's daily-account rules (§80) it stays positive at **+$93 to +$145 per evaluation** with
one MNQ during regular hours, the 40% evaluation consistency rule being what sets that size.
With the rules confirmed (§81: intraday breach fails, daily payouts, a $1,250 cap until live) it is
**+$85 to +$125 per evaluation**, and ten evaluations finish net positive about half the time.
**Corrected (§82):** Tradeify's evaluation floor keeps trailing past $52,000, which lowers this to
**+$62 to +$78 per evaluation** (pass rate 18–19%; ten evaluations net positive 40% of the time).
Across sessions, directions and gold (§83) the choice of window mostly picks noise; two policies hold in
both eras — **MNQ 09:30–16:00 long and MGC London 03:00–11:30 long, about +$70 to +$80 each.**
**Replayed through real history in order (§85), that value shrinks and widens:** drift removed, +$1 (MNQ)
and +$44 (MGC) per evaluation, and anywhere from −$61 to +$162 once real clustering is kept. The
structure's value is best read as roughly $0–80 per $80 fee, with uncertainty as large as the estimate.

**The Z row was added 2026-10-09** — a twelfth series on a different basis: take evidence from outside,
not from searching this data. Published calendar and event anomalies were checked and found to decay
after publication; the lead candidate is **front-running institutional rebalancing (Harvey, Mazzoleni &
Melone 2025: Sharpe ~1 over 1997–2023, a forced counterparty, no post-publication record yet)**, to be
replicated exactly and tested on the 3.5 years after its sample ends. Designed; awaiting the user's
ruling on its decision rule. `decisions.md` §86.

**Z02 was run 2026-10-09 (trial t00768) and confirmed under the user's rule** — the first hypothesis in
twelve series to pass its own pre-registered test. On 3.5 years after the paper's sample, the MES leg of
the rebalancing signal earned a net Sharpe of +0.51, beating 98.4% of its rotation null; the posterior is
0.50 ± 0.28. In the Tradeify account, one MES in the signal's direction is worth about **+$410 per $80
evaluation** at the posterior — subject to verifying that sizing on forward data. Not promoted: the
programme's promotion bar is SR\*, which this rule replaced. `decisions.md` §87–§88.
**In the account it does not pay (§89):** on today's contract size and replayed from every start date in
real order, one MES by the signal is about break-even. Closed for the account; the finding stands.

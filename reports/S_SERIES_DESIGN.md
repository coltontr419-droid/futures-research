# The S-series — retail indicators against a matched arbitrary reference

**DESIGNED, NOT REGISTERED. No trial spent. N stays 760, SR\* stays 0.1368, both chains verify.**
Nothing was added to `hypotheses.yaml`. S5, S6 and S7 were not run.

Written 2026-10-02. Arithmetic in `reports/s_series_s2.json`, produced by
`python -m futuresres.reporting.s_series_s2`; nothing in the tables below is transcribed by hand.
Stage numbering is S1–S8 per `reports/STAGES.md`. References of the form §nn point to
`reports/decisions.md`.

**This is a seventh series and is accounted for as one** — in the ledger of
`programme_conclusion.md` §11, in `CHECKPOINT.md`'s state block, and against the stopping rule
in `CHECKPOINT.md` and §61/§62. It is not a side investigation, and the fact that the programme
closed after six series is not a reason to hold it to a lower standard. It is a reason to hold
it to the stated one.

---

## 0. The question, and the one thing already known about it

**The question.** Do common retail indicators produce price behaviour distinguishable from a
matched arbitrary reference — an equally-reachable region or an equally-frequent state that
carries none of the indicator's meaning?

**That question already has one high-powered answer on file, and it is the reason this series
is designed the way it is.** L07 asked exactly it, for fair value gaps, at the largest event
counts anywhere in the programme (23,545–655,490 firings per cell). It came back:

| | |
|---|---|
| cells separating from their matched placebo | **108 of 108**, both instruments, all three horizons |
| direction of the difference | **negative in every cell** |
| size against the round-trip cost floor | **1.8×–10.3×** |
| decomposition | **the real zone loses while the matched region wins** (§38) |

So the answer for fair value gaps is **yes, distinguishable — and the distinguishability runs
the wrong way.** Conditioning a trade on the region being a real fair-value gap *reverses the
sign*. That is a stronger result than a null, and it is already paid for.

Two things follow for the design, and they are not optional.

1. **"Distinguishable" is not "tradeable."** An entry that separates from its reference has
   established a difference, which may be negative, may be a timing artefact (L07's real and
   placebo entries differ by up to 81 minutes in time of day, §38) and may be below cost. The
   S-series inherits L07's structural limitation along with its design: the §37 placebo
   equalises *where* a region sits and *how often price reaches it*, and nothing about **how
   price arrived**.
2. **The mirror is not available.** The obvious reading of L07 — trade the opposite direction —
   is not registrable, because the sign came from looking at this data, the registered mechanism
   predicts reaction at the zone rather than continuation through it, and the timing confound
   manufactures a positive difference as easily as a negative one (§38). The same bar applies to
   every S-entry: **no entry may be registered in a direction this repository's own results
   suggested.**

---

## 1. Overlap with prior work — reported before anything was designed

Five of the nine proposed entries are already in `hypotheses.yaml` under a different series
letter. **Three of the five have measured firing rates on disk.** This table is the single most
important thing in this document, and it was built by reading the registry rather than by
recalling the programme's history.

| S | indicator | prior registry entry | its status | measured on disk? | **this entry is** |
|---|---|---|---|---|---|
| **S01** | fair value gaps | **L07** `fair_value_gap_fill` | **retired at S8**, 108 trials spent | yes — firing rates at 1m/5m, and **in bps at 15m/30m** (`peak_bps_l07.json`) | **repeat** |
| **S02** | RSI(14) | **F10** `rsi_mean_reversion_control` | retired, unpowered, never run | yes — 30m/60m/120m (`firing_rates.md`) | **timeframe extension** |
| **S03** | VWAP | **L01** `vwap_reaction` | blocked at S4 | yes — 18 cells (`level_rates.md`) | **repeat** |
| **S04** | EMA(20/50/200) | **L08** `moving_average_reaction` (+ **F11** `ma_crossover_control`) | L08 blocked at S4; F11 **retired on premise** | yes — 36 cells at 5m and 15m | **timeframe extension** |
| **S05** | volume profile POC/VAH/VAL | **none** | — | no | **new** |
| **S06** | Bollinger bands | **L11** `bollinger_breakout` | **withdrawn at S5** — never actually tested | only `degenerate_measurements`, which its entry says are not evidence | **repeat** |
| **S07** | MACD(12,26,9) | **F11** `ma_crossover_control` | **retired on premise**, never run | F11's in-state bars at 30m/60m/120m | **repeat** |
| **S08** | stochastic %K/%D | **none** directly; F10's family | — | no | **new** |
| **S09** | classic floor pivots | **none** as specified; a deterministic function of **L03**'s inputs | L03 retired on a null, 0 of 18 | L03's prior-day touch counts | **new** |

Also covered by prior work and named in the brief: **L02** opening range (retired on a null, 0 of
27; its sweep arm withdrawn at S5), **L03** prior-day sweeps (retired, 0 of 18), **L04** session
extremes (`stage1_inconclusive`, 5 of 18 nominal, 0 BH survivors). None of the three is proposed
again. L04 is the only one with a live revival path, and §43 fixed its terms: a new registration
naming `sess_Asia` in advance, on data that did not generate the result, with a magnitude stated.
The S-series does not claim that slot.

### For the repeats: does re-running cost trials for information already on file?

**Yes for three of the four, and the answer differs per entry rather than being a blanket
judgement.**

| S | would a re-run buy anything? |
|---|---|
| **S01** FVG | **No.** 108 trials already bought the answer at event counts 4–100× anything else in the programme, and §53 re-measured it in bps so the scale objection is already closed. Re-running spends ~30 trials to re-derive a measured −1.18 to −5.01 bps. The only part not on file is 1h and 4h, and §4 below shows those cells fall *below* the detection floor — so the extension buys the cells that cannot answer and repeats the cells that already did. |
| **S02** RSI | **Partly new.** F10's rate was measured but F10 **never ran**, so there is no S7 result for RSI. What is on file is the arithmetic that closed it: 1,585–5,594 events against a swept range starting at 19,722. The 5m and 15m cells are genuinely unmeasured. |
| **S03** VWAP | **No.** L01's rate is measured at 237 events in its best cell. Re-running cannot raise it, because the timeframe axis does not add levels (§3). |
| **S04** EMA | **Partly new.** 30m, 1h and 4h are unmeasured; 5m and 15m are measured and 8× below floor. |
| **S06** Bollinger | **Genuinely new.** L11 was withdrawn before it was ever tested, and the `confirmed_break` defect that withdrew it is **fixed** — `direction` is now a required argument and the precondition raises (§41). This is the one repeat where the prior entry produced no information at all. |
| **S07** MACD | **No, and worse than no.** F11 was retired **on premise**, not on power: a fast/slow MA crossover is time-series momentum, the same family as F01, so a promotion would be unreadable as either harness failure or true detection. MACD is the difference of two EMAs. **It inherits F11's premise retirement, and no amount of sample fixes a premise.** |

---

## 2. What is dropped, and why

The brief asks for anything mechanically specifiable and the removal of anything that is not.
**Specifiable means a second person, given only the written specification and the same bars,
produces the same firing minutes.** That is the test applied below, and it is stricter than
"can be coded" — almost anything can be coded once someone picks the free choices.

| dropped | why |
|---|---|
| **Fibonacci retracements / extensions** | The swing high and swing low are chosen by eye. Mechanising them ("the extreme of the last N bars") replaces the discretion with a free parameter N and produces a *different* indicator from the one retail traders use. |
| **Order blocks, supply-and-demand zones, "smart money concepts"** | The zone is drawn by eye and published definitions disagree on which candle is the block. The nearest mechanical version was tried: **N04/N05** swing-pivot traps and sweeps, **withdrawn at S6** because median distance from price was 0.000 and 61.4% were exactly zero, so **no placebo can match them** (§46). That is a structural bar, not a specification gap. |
| **Trendlines and chart patterns** (head-and-shoulders, triangles, flags, wedges) | Anchor-point selection is discretionary; no two practitioners draw the same line on the same chart. |
| **Elliott wave, harmonic patterns** (Gartley, bat, butterfly) | Wave and point labelling is discretionary *and retrospectively revisable*, which is worse — the specification changes after the outcome is known. |
| **Wyckoff accumulation/distribution phases** | Phase classification is a discretionary reading of the same bars. |
| **Ichimoku Kinko Hyo** | Mechanically specifiable, but it is five components read jointly, and the brief excludes combined signals. Its one separable limb — price crossing the kumo boundary — is a displaced moving average with a band, i.e. **S04 and S06 again**. |
| **Supertrend, Keltner channels, parabolic SAR** | All mechanically specifiable, and all the same object: *a band at k × volatility around a moving average*, differing from Bollinger only in the volatility estimator (ATR versus standard deviation). Registering them separately would be **S06 three more times** at 30 trials each. Folded into S06 as a pre-registered estimator parameter, not given entries. |
| **OBV, Chaikin money flow, accumulation/distribution line** | Mechanically specifiable, but these are **non-price observables — the P-series class, and the P-series is closed** with 13 candidates, 1 registration, 0 promotions. They also walk straight into §54's correction: a volume-derived ratio is *not* scale-invariant because the denominator is not stationary (median 1m bar volume runs 16 in 2010 to 784 in 2026, and steps 3–5× at the NQ→MNQ splice). |

**One dropped item is dropped on a stronger ground than discretion, and it is worth separating.**
N04/N05 are not unspecifiable — they were specified, registered and withdrawn because the
*control* cannot exist. Any S-entry whose levels sit at or adjacent to the current price inherits
that, exactly as **L06** does (`open_RTH` and `open_CME` sit at the reference price, so there is
no distance to match, §37). This is checked per entry in §5.

---

## 3. One design finding that applies before any arithmetic: the timeframe axis is not one axis

The brief specifies five timeframes — 5m, 15m, 30m, 1h, 4h — for every entry. **They do not mean
the same thing for all nine, and treating them as one axis would overstate the series by about a
third.**

| entry kind | what changing the timeframe does | are the 5 timeframes 5 hypotheses? |
|---|---|---|
| **state entries** — S01 FVG, S02 RSI, S06 Bollinger, S07 MACD, S08 stochastic | changes **the object**. A 4h RSI(14) reads 14 four-hour bars; a 5m RSI(14) reads 14 five-minute bars. Different indicator, different firings. | **yes** |
| **level entries** — S03 VWAP, S05 volume profile, S09 floor pivots | changes **only the detection granularity**. Session VWAP, the session POC and the prior-session pivot are the same prices whatever bars you look at them on. | **no** — one level set, sampled five ways |

For the three level entries this is not a quibble. The L-series measured **97–100% pairwise
overlap of firing minutes for every substantive hypothesis**, with the placebo control the only
disjoint route (§level_conclusion, finding 4). So S03, S05 and S09's five timeframe cells
re-enter on the same touches. Two consequences, and both are recorded because they pull in
opposite directions:

- **BH over 30 cells is conservative** — 30 correlated cells are not 30 independent looks.
- **A raw count of separations overstates the evidence by the same token.** This is the L04
  trap: 5 of 18 separations that were "closer to ONE result seen five times than to five
  findings" (§43).

**It does not reduce the trial cost.** N counts comparisons appended to the log, not independent
ones. Five correlated cells still spend five trials and still raise SR\* for everything that
follows. **Correlation makes a grid cheaper in evidence and no cheaper in trials** — which is the
worst of both, and is the argument for shrinking these three grids rather than for discounting
them.

---

## 4. The S2 arithmetic — magnitude, bar, cost, and the method's own validation

### Method

Inherited unchanged from §54 (P-series) and §59 (Q-series) so the S-series filter is comparable
to theirs rather than freshly favourable:

```
bar       = z(1 − 0.05/(2k)) · anchor(H) / √units      BH rank-1 at FDR 0.05, within the entry
anchor(H) = 64.7 · √(H/180) bps per event             L12's measured paired bootstrap (§57)
units     = raw firings / DEFF                        effective, not raw (§45: raw overstates 2.8–13.7×)
k         = 30                                        cells in the entry's own grid
```

**DEFF is measured, not assumed, and the measurement is unflattering.** `peak_bps_l07.json`
reports DEFF for an intrabar indicator at the two timeframes in this brief's range:
**5.79 at 15m rising to 12.72 at 30m**. The Q-series bracketed DEFF at 1.14–2.19; for the
objects this series proposes, the only measurement available is **3–6× worse than that
bracket's top**. State entries are given 5.8 — the measured bracket's *low* end, the generous
choice. Level entries are given 2.19, the measured once-per-session family (§45).

**Post-2021 decides** (STAGES.md, S8, adopted §60). Every bar is therefore reported post-2021,
which multiplies it by 1/√0.337 = **1.72×**, because post-2021 is 1,390 of 4,124 sessions and
extending the sample backwards adds only to the half that does not decide.

### Before using it: does this arithmetic recover verdicts already on file?

§60's standard — *a null counts only from a pipeline demonstrated to recover the effect it was
looking for* — is about runs rather than filters, but the same discipline applies to a filter
that is about to close nine entries. Checked against the programme's three measured effects with
a known S7 outcome:

| case | effect | per-event sd | Sharpe | vs SR\* then | predicted | **recorded outcome** |
|---|---|---|---|---|---|---|
| **L07** @ tf=15m, w=1.6 bps | 5.790 | 22.8 | **0.2539** | 0.1357 | clears | **separated in 108/108 cells** ✓ |
| **L04** best cell | 3.543 | 64.7 | 0.0548 | 0.1367 | does not clear | **nominal separation, 0 BH survivors** ✓ |
| **L12** | 0.306 | 64.7 | 0.0047 | 0.1367 | does not clear | **0 of 9 cells separated** ✓ |

**Three for three, and the discriminating case is the positive one.** A filter that only ever
says "below the bar" would reproduce L04 and L12 by accident; it reproduces L07's separation as
well, which is the direction that could have falsified it.

### The result

Predicted magnitudes are **priors and say so** (§54's rule), except S01's, which is a
*measurement* — L07's own difference. Every range includes zero where the mechanism is
self-fulfilling, because decay since publication is the stated prior (§59).

| S | overlap | predicted bps | BH bar, post-2021, H=180m | at H=30m | vs cost 0.48 | vs its own bar |
|---|---|---|---|---|---|---|
| **S01** FVG | repeat | **1.18–5.79 (MEASURED, NEGATIVE)** | 3.56 – 29.38 | 1.45 | above | **above, at the top** |
| **S02** RSI | tf extension | 0 – 2.0 (prior) | 4.61 – 29.97 | 1.88 | above at top | below at H=180m; **straddles at H=30m, 5m cell only** |
| **S03** VWAP | repeat | 0 – 1.5 (prior) | **33.68** | 13.75 | above at top | **below by 9–22×** |
| **S04** EMA | tf extension | 0 – 1.5 (prior) | 16.82 – 21.17 | 6.87 | above at top | **below by 4.6–11×** |
| **S05** volume profile | **new** | 0 – 1.5 (prior) | **6.90** | 2.82 | above at top | **below by 1.9–4.6×** |
| **S06** Bollinger | repeat | 0 – 2.0 (prior) | 3.54 – 24.51 | 1.45 | above at top | below at H=180m; **straddles at H=30m, 5m cell only** |
| **S07** MACD | repeat | 0 – 2.0 (prior) | 3.44 – 23.87 | 1.41 | above at top | below at H=180m; **straddles at H=30m, 5m cell only** |
| **S08** stochastic | **new** | 0 – 2.0 (prior) | 2.91 – 18.95 | 1.19 | above at top | below at H=180m; **straddles at H=30m, 5m cell only** |
| **S09** floor pivots | **new** | 0 – 1.5 (prior) | **7.33** | 2.99 | above at top | **below by 2.0–4.9×** |

**Two horizons are reported on purpose.** The bar falls as √H while the cost floor does not, so
choosing H=30m opens four entries and choosing H=180m closes them. **Picking the horizon that
closes the series would be choosing a parameter to get a result, and so would picking the one
that opens it** (§53 is a record of exactly that error being made in the other direction). Both
are shown; §6 resolves it with a number that does not depend on the choice.

### The firing rates behind those bars

Measured where measured, extrapolated by a stated rule where not, labelled per cell in
`s_series_s2.json`. The pattern that matters:

| S | 5m | 15m | 30m | 1h | 4h |
|---|---|---|---|---|---|
| **S01** FVG | 56,310 ᴇ | **18,770 ᴍ** | **6,601 ᴍ** | 3,301 ᴇ | 825 ᴇ |
| **S02** RSI | 33,564 ᴇ | 10,550 ᴇ | **5,594 ᴍ** | **2,966 ᴍ** | 793 ᴇ |
| **S03** VWAP | **237 ᴍ** | 237 ᴍ | 237 ᴍ | 237 ᴍ | 237 ᴍ |
| **S04** EMA | **659 ᴍ** | **705 ᴍ** | 850 ᴇ | 950 ᴇ | 600 ᴇ |
| **S05** volume profile | 5,643 ᴇ | ← same level set → | | | |
| **S09** floor pivots | 5,000 ᴇ | ← same level set → | | | |

ᴍ measured · ᴇ extrapolated. MNQ, full sample. MNQ's 180-minute detection floor is **5,884**.

**Three readings of that table, and the third is the one nobody would guess.**

1. **The state entries fall with timeframe and the floor does not.** FVG runs 18,770 at 15m to
   825 at 4h — a 23× fall. RSI crossings halve with every doubling of bar length (5,594 → 2,966
   → 1,585, measured). **So the 1h and 4h cells this brief asks for are the cells least able to
   answer**, on both. The timeframe extension buys its new cells at the wrong end.
2. **The level entries do not move at all**, for the reason in §3, so extending their timeframes
   buys exactly nothing — five copies of one number.
3. **S03 and S04 are caught in a vise with no setting that escapes it.** Both fire only
   **237** and **659–950** times because of a precondition — price must sit ≥ d ATR away for
   15–30 minutes before the touch counts. Remove it and the condition fires on nearly every bar,
   because price crosses a VWAP or an EMA constantly: that is **the L11/L05/L02-sweep degenerate
   condition, which failed S5** with entry-minute sd 0.05 and 99.6% high/low collision (§41).
   Keep it and the count is 6–25× below the floor and fails S4. **There is no intermediate
   setting that passes both**, and searching for one is parameter selection. This is also why
   the open `d` ATR reference-period decision (`CHECKPOINT.md`) cannot be resolved *in order to*
   schedule these: choosing the period that makes them fire is choosing a parameter to get a
   result, and it was frozen for that reason.

---

## 5. Per-entry registration requirements that are not yet met

Each entry below owes the four things the registry now gates on. Marked ✗ where it is not met by
the design as drafted, because a design that quietly assumes its gates will pass is the §54
failure — a draft written *after* its correction, repeating it.

| S | magnitude stated & checked (S2) | scale-invariant thresholds (S2) | valid control exists (S6) | collinearity measured |
|---|---|---|---|---|
| **S01** | ✓ measured | ✓ bps gap width, already re-specified §53 | ✓ L07's placebo matched 12/12 | — |
| **S02** | ✓ prior, below bar | ✓ RSI is unit-free | **state** → needs the §55 matched control, **bar mode** | ✗ **vs S08** |
| **S03** | ✓ prior, below bar | ⚠ ATR multiples are invariant but **which ATR is an open decision** | ✓ matched region; VWAP is not at the reference price | ✗ **vs S05** |
| **S04** | ✓ prior, below bar | ⚠ same open ATR decision | ✓ matched region | ✗ **vs S06, S07** |
| **S05** | ✓ prior, below bar | ✓ bin width in bps, value area at 70% | ✓ matched region | ✗ **vs S03** |
| **S06** | ✓ prior, straddles at H=30m | ✓ k standard deviations | **state** → §55 control, bar mode | ✗ **vs S04** |
| **S07** | ✓ prior, straddles at H=30m | ✗ **sign change is unit-free, but any threshold on MACD *magnitude* is in price points — the N02 error exactly** (an 8-point break was 41 bps in 2010 and 2.9 bps in 2026). Must be normalised by price or by trailing rank. | **state** → §55 control, bar mode | ✗ **vs S04** |
| **S08** | ✓ prior, straddles at H=30m | ✓ %K is bounded 0–100 | **state** → §55 control, bar mode | ✗ **vs S02** |
| **S09** | ✓ prior, below bar | ⚠ **pivots are price levels by construction** — admissible only under S2's escape hatch: state the price range and pre-register the era split | ✓ matched region | ✗ **vs S03, L03** |

### The collinearity gates cost no trial and should be run before any registration

This is the Q01/Q02 precedent, and it is the cheapest thing in this document. §59 measured two
candidates' conditioners at **Spearman +0.972 full sample, +0.991 post-2021**, with
P(Q02 long | Q01 fires) = 100% — **the first two candidates of a portfolio built on ρ ≤ 0.1 were
one bet**, and finding that out cost nothing. Five pairs here are structurally suspect:

| pair | why they may be one hypothesis |
|---|---|
| **S02 ↔ S08** | RSI and stochastic %K are both bounded position-in-range measures on the same bars. Different normalisation, same object. |
| **S04 ↔ S06** | A Bollinger band *is* a moving average ± k·σ. The middle band is S04. |
| **S04 ↔ S07** | MACD is the difference of two EMAs. **F11 retired an MA crossover on premise** as "the same family as F01". |
| **S03 ↔ S05** | VWAP is the volume-weighted **mean** price of the session; POC is the volume-weighted **mode**. Two statistics of one distribution. |
| **S09 ↔ S03/L03** | PP = (prior H + L + C)/3, and R1/S1 are reflections of it. **A deterministic function of the three numbers L03 already tested** (retired, 0 of 18). |

**Four of the nine entries are at risk of being a second look at another entry in the same
series**, which is the one multiplicity cost the trial log cannot price: N counts the
comparisons, not whether two of them were the same bet.

---

## 6. The multiplicity cost, kept as two separate objects

### Within an entry: BH across its own timeframe and parameter cells

Each entry is **30 cells** = 5 timeframes × 3 parameter settings × 2 instruments, at one
horizon. BH rank-1 at FDR 0.05 over k=30 gives z = 3.1440, and the bar per entry at its expected
n is the right-hand columns of §4's table. Stated per entry, post-2021, at H=180m:

| S | best cell's bar | worst cell's bar |
|---|---|---|
| S01 | 3.56 | 29.38 |
| S02 | 4.61 | 29.97 |
| S03 | 33.68 | 33.68 |
| S04 | 16.82 | 21.17 |
| S05 | 6.90 | 6.90 |
| S06 | 3.54 | 24.51 |
| S07 | 3.44 | 23.87 |
| S08 | 2.91 | 18.95 |
| S09 | 7.33 | 7.33 |

**For reference, the largest effect the programme has ever measured anywhere is 5.79 bps**
(L07 at tf=15m in bps units; 5.008 at tick widths; R01's +0.452 is the largest *positive* one).
**Four of the nine — S03, S04, S05 and S09 — have a best-cell bar above that number.**

### Across the programme: N and SR\* do not reset

They are permanent and shared — paid by every future hypothesis **including the one that would
have promoted** (§61). Running the series in the order S01…S09, at 30 trials each:

| after | N | SR\* | SR\* as a required per-event effect, H=180m | at H=30m |
|---|---|---|---|---|
| *pickup* | **760** | **0.1368** | 8.85 bps | 3.61 bps |
| S01 | 790 | 0.1373 | 8.88 | 3.63 |
| S02 | 820 | 0.1378 | 8.91 | 3.64 |
| S03 | 850 | 0.1382 | 8.94 | 3.65 |
| S04 | 880 | 0.1387 | 8.97 | 3.66 |
| S05 | 910 | 0.1391 | 9.00 | 3.67 |
| S06 | 940 | 0.1395 | 9.02 | 3.68 |
| S07 | 970 | 0.1399 | 9.05 | 3.69 |
| S08 | 1000 | 0.1402 | 9.07 | 3.70 |
| **S09** | **1030** | **0.1406** | **9.10** | **3.71** |

**The last entry in the sequence faces N = 1,030 and SR\* = 0.1406.** The series adds **270
trials**, a 36% increase in N, and raises SR\* by **+0.0038** — about twice the +0.0019 that one
series costs at the measured mean of 128 trials (§61). The projection holds the trial-Sharpe
variance fixed at its current 0.0018559; new trials would change it too, and the direction is
not predictable, so the SR\* figures are projections and labelled as such.

### Where the two objects meet, and this is the answer the brief asks for

**The brief's own test:** *an entry that clears its own BH bar but sits below the prevailing SR\*
has not cleared anything.* Making that comparison requires putting both in the same units, since
SR\* is a Sharpe and the bars are in bps. A per-event effect *e* against per-event noise
anchor(H) has per-observation Sharpe *e*/anchor(H), so the effect that merely **reaches** SR\* is
SR\* · anchor(H) — the last two columns above.

| | H=180m | H=30m |
|---|---|---|
| SR\* as a required effect, at N=1,030 | **9.10 bps** | **3.71 bps** |
| largest predicted magnitude in the series (S02/S06/S07/S08, top of range) | 2.0 | 2.0 |
| largest effect the programme has ever measured | 5.79 | 5.79 |

**Every entry that straddles its own BH bar at H=30m sits below the prevailing SR\* at the same
horizon.** S02, S06, S07 and S08 reach their own bars at 1.19–1.88 bps in their 5m cells, and
SR\* at the N they would face requires **3.64–3.70 bps**. They clear the within-entry correction
and fail the across-programme one by a factor of about two.

**And the comparison does not turn on the horizon.** At H=180m the required effect is 9.10 bps
and nothing in the series predicts above 2.0. At H=30m it is 3.71 and nothing predicts above 2.0.
**The only entry whose magnitude reaches SR\* in either column is S01 — whose magnitude is
measured rather than predicted, and is negative.** That is not a coincidence: it is L07 being
the one entry with the event count to produce an effect that large, and L07 is already retired.

---

## 7. The filter result, in the brief's three categories

The P-series filter closed 9 of 13 candidates at no trial cost; the Q-series filter closed 12 of
12. **This one closes 9 of 9**, and the two categories it uses are different from theirs.

### Plausibly above both the BH bar and the cost floor: **one, and it is already answered**

**S01 (fair value gaps)**, at 1.18–5.79 bps against a best-cell bar of 3.56 and a cost floor of
0.48 — **above both, 2.5–12× cost, and reaching SR\* at H=30m.** It is the only entry in the
series with the event count to produce an effect that size, and the reason is visible in §4's
firing table: 18,770 effective-unit-bearing firings at 15m where every other entry has hundreds.

**It is above both bars because it has already been measured, and what was measured is
negative.** Registering S01 spends ~30 trials to re-derive §38 and §53. **The information is on
file; the trials are not refundable.**

### Below one or both: **six**

| S | below what |
|---|---|
| **S03** VWAP | **below its bar by 9–22×.** 237 events, and §4's vise means no setting raises that without failing S5. |
| **S04** EMA | **below its bar by 4.6–11×.** 659–950 events; same vise. |
| **S05** volume profile | **below its bar by 1.9–4.6×** — the closest of the three new entries, and the only new entry whose event count is in the right order of magnitude. |
| **S09** floor pivots | **below its bar by 2.0–4.9×**, and a deterministic function of L03's inputs. |
| **S02** RSI, **S06** Bollinger, **S07** MACD, **S08** stochastic | **above their own bars at H=30m in their 5m cells only, and below the prevailing SR\* by ~2× in every cell at every horizon.** By the brief's own test, they have not cleared anything. |

### Cannot be predicted: **none — and that is itself a finding**

The P-series could not state a magnitude for 5 of 13 and the Q-series for 7 of 12, because those
candidates were conditioners, contamination tests or computations with no trade rule. **Every
S-entry states a direction and a trade rule, so every one is predictable.** That is what a series
of mechanically specifiable indicators looks like, and it is the one respect in which the
S-series is cleaner than its two predecessors.

**It does not help.** Being predictable is what *allows* the arithmetic to close them; the
P- and Q-series' unpredictable candidates survived their filters only in the sense that the
filter could not reach them. **Nine of nine predictable and nine of nine below the operative bar
is a worse result than nine of thirteen**, not a better one.

---

## 8. Against the stopping rule

The rule in `CHECKPOINT.md` is a gate on designing, and it requires a candidate series to state
where it sits against both conditions **in its own registration, before a trial is spent**. Stated
here instead, because nothing is being registered.

### Condition 1 — the success bar (§62, two objects)

The operative bar is post-lock, intraday marks, events among survivors, **held to whichever of
the rate bar and the ruin bar is higher**: for 15% annual return at ≤3 drawdown events with
first-year P(floor) ≤ 10%, **SR ≥ 2.06**, which is **15.1× SR\***. Phase 1 is a ruin probability,
not a rate: at Sharpe 1.31 the account still fails to survive it 43.6% of the time.

**No S-entry has a route to it.** The required per-trade *gross* edge converges to 1.062× the
best effect the programme ever measured, because the 0.48 bps cost floor alone exceeds R01's
0.452 (§9 of the terminal report). The largest magnitude any S-entry predicts is 2.0 bps, which
is not obviously below that — **but it is a prior with no measurement behind it, and the one
S-entry with a measurement behind it is negative.** The honest statement is not that the
arithmetic forbids 2.0 bps; it is that **nothing in this series has produced evidence of 2.0 bps,
and the entry with the power to produce such evidence produced −1.18 to −5.79.**

### Condition 2 — expected value against cost

Base rate: 35 registered across six series, **0 promoted**. At the measured mean of 5.83
registrations per series, P(a seventh series promotes ≥1) is **7.8%** on a Jeffreys prior and
14.8% on Laplace, so a promotion must be worth **6.8–12.8× one series' cost**. The rule-of-three
40.7% is a 95% upper bound on what 35 observations cannot exclude and is not an estimate.

**The S-series' cost is above the mean series, not below it.** 270 trials against a mean of 128
and a median of 6.5, and **+0.0038 of permanent SR\***. And the base rate is *optimistic* here
for a reason specific to this series: **five of nine entries are already in the registry**, so
the S-series is not drawing from the same urn as the first six — it is substantially re-drawing
from it.

### Condition 3 — "we cannot think of new hypotheses" is not a valid termination condition

Stated in `CHECKPOINT.md` §3 and it cuts against this series rather than for it. The S-series was
generated from a list of popular indicators, which is **unbounded and cheap** — there are dozens
more, and §2's dropped list is longer than the kept one. A series assembled that way is selected
by *availability*, not by evidence, and the terminal report names the failure precisely:
*"a seventh series would be widening the search until something appears, which is exactly what
the trial log exists to prevent."*

**What would change the answer is in §10 of the terminal report and none of it is here:**
aggressor-side or order-book data (a purchase — and note that the "self-fulfilling order
clustering" mechanism every one of these indicators relies on is a claim *about order flow*,
which is the one information class never examined); an account permitting correlated long/short
positions or holds through 17:00 ET; a lower cost structure; or genuinely unseen data.

---

## 9. What is recommended, and it is not a registration

**Nothing registered. No trial spent. S5, S6 and S7 not run.** If the series is taken further,
the order is set by what costs nothing:

1. **The five collinearity measurements in §5.** Spearman between S02/S08, S04/S06, S04/S07,
   S03/S05 and S09/L03's inputs. **No trial.** The Q01/Q02 precedent says this can collapse four
   entries into two before anything is registered, and it logs to `measurements.jsonl` on the
   same reasoning that keeps firing rates out of N.
2. **Firing rates for the five entries with no measurement of their own** — S05, S06, S07, S08,
   S09 — at all five timeframes. **No trial** (§22: a declared rate never gates, only a measured
   one). §4's extrapolations for these five are the weakest numbers in this document: S05 and S09
   are scaled off L03's measured touch counts and S06, S07 and S08 off bar counts and F11's
   in-state bars, and **three of the five straddle at H=30m on the strength of them.**
3. **S06 only, if anything.** It is the single entry that is both a genuine information gain
   (L11 was withdrawn before it was ever tested, and the defect that withdrew it is fixed) and
   plausibly above its own bar in its 5m cell. It would still need the §55 matched state control
   in bar mode, a clean-pool check, and an acknowledgement that it sits below the prevailing
   SR\* by about 2×.
4. **Not registrable as specified:** S01 (answered — repeat of 108 trials), S03 and S04 (the S4/S5
   vise, no setting passes both), S07 (inherits F11's premise retirement; a premise is not fixed
   by sample), S09 (a deterministic function of a retired null's inputs), S02 and S08 (below the
   prevailing SR\*, and probably one hypothesis rather than two).

**The honest summary, in the same form §54 used for the P-series:** of nine entries, one is worth
running and only after two measurements that cost no trials — and that one would clear its own
correction while failing the programme's.

---

## 10. Ledger

Accounted for as a seventh series, with the counts a seventh series has at this point.

| series | drafted | registered | trials | promoted |
|---|---|---|---|---|
| F | 14 | 14 | 576 | 0 |
| R | 5 | 5 | 10 | 0 |
| L | 12 | 12 | 180 | 0 |
| N | 10 | 3 | 3 | 0 |
| P | 13 | 1 | 1 | 0 |
| Q | 12 | 0 | 0 | 0 |
| **S** | **9** | **0** | **0** | **0** |
| **total** | **75** | **35** | **770** | **0** |

`futures-research/trials.jsonl` N = **760**, SR\* **0.1368**, chain verifies.
`r-series-research/trials.jsonl` N = **10**. Programme total **770**. Unchanged by this document.

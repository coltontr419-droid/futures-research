# Decisions log

Choices made during the data build that were not settled by the spec, recorded here rather
than resolved silently. Each states what was decided, what the alternative was, and what
would change the answer.

---

## 1. Outrights are identified by symbol grammar, not `instrument_class`

**The spec says to filter on `instrument_class`. It is not in this batch.** `metadata.json`
records `schema: ohlcv-1m` only — no `definition` schema, and therefore no
`instrument_class` field anywhere in the 806 data files.

**Decided:** fall back to the CME symbol grammar — `^ROOT+MONTH+YEAR$` for an outright, two
well-formed outrights joined by a hyphen for a spread — applied to all 806 files, with
anything matching neither form reported rather than guessed at. 0 files were unrecognised.

**Rejected:** a substring test for a hyphen. The crypto project's own tests reject it, in
both directions: a spread whose symbol carries no hyphen would be kept, and an outright
whose symbol contains one would be dropped. The grammar check requires both legs to parse.

**This is weaker than `instrument_class` and the report says so.** What would change it: a
new batch job requesting the `definition` schema. The parser prefers `instrument_class`
whenever it is present.

---

## 2. Contracts are keyed by `instrument_id`, and the canonical code carries a four-digit year

**CME single-digit year codes repeat every decade and this batch spans sixteen years**, so
the same symbol string names two different contracts, and `split_symbols` writes both into
one file. Measured:

| raw_symbol | instrument_id | window | price range |
|---|---|---|---|
| `NQZ5` | 12809 | 2014-09-22 .. 2015-12-18 | 3,901 – 4,739 |
| `NQZ5` | 158704 | 2024-12-27 .. 2025-12-19 | 16,873 – 26,396 |

77 symbol strings are affected. Concatenating by symbol would produce a "contract" whose
price jumps five-fold mid-series — and **no OHLC, duplicate or outlier check would catch it**,
because every individual bar is valid.

**Decided:** key by `instrument_id`; emit `contract` as `NQZ2015` / `NQZ2025`.

**The expiry year is derived, then asserted.** A contract expires at or after its last bar,
so the expiry year is the smallest year ≥ the last bar's year congruent to the symbol's year
digit mod 10. `assert_unique_contract_codes` enforces that no two contracts resolve to the
same code — and **it caught a real collision on the first run**: `MGCG8` is Feb 2028 with 214
bars from 2026-04-08, and an earlier rule that simply took the last bar's year labelled it
`MGCG2026`, which would have overwritten the genuine Feb 2026 contract on disk.

---

## 3. The expected-bar calendar is measured per year, not hard-coded

**The gap check is the point of the validator, and a fixed maintenance window is wrong here.**
CME moved the Globex close during this sample. A single 17:00–17:59 ET break flagged 2,029
perfectly good bars, including NQ prints of 240,000–320,000 contracts at 17:25–17:35 ET in
2010–2015 — settlement-period volume under the old schedule, unmistakably real.

**Decided:** measure the closed window per product per year from coverage, and assert its
SHAPE — exactly one contiguous closure of 45–90 minutes per year. The schedule change then
appears as a finding rather than a fault:

- MGC 2010: closed 17:15–17:59 ET (45 min) → from 2016: 17:00–17:59 (60 min)

**Acknowledged circularity:** the data defines the expectation the data is judged against.
What makes it a real check is the shape assertion, which can and does fail — NQ 2010–2015
shows *two* separate closures per year and is reported as FAIL. That is a genuine finding:
the modern single-break session model does not describe pre-2016 NQ, and any session-anchored
hypothesis on NQ before 2016 needs a different model.

**Not decided by me:** what the pre-2016 NQ intraday structure actually was. It is reported,
not adjudicated.

---

## 4. Absent bars are not counted as gaps

`ohlcv-1m` aggregates trades, so **a minute with no trades produces no bar at all** — measured:
0 zero-volume bars across all 15.3M. For a thin contract, absence means no trade, not missing
data. A flat every-minute expectation would report millions of false gaps.

**Decided:** report coverage; flag only what a liquid book cannot innocently produce — a
contiguous run of ≥15 absent minutes inside 09:30–16:00 ET.

**Consequence for §3 checks 5 and 6** (zero-volume runs, zero-volume-with-live-range): they
cannot fail on this dataset. They are reported as **N/A with the count**, not PASS. A check
that cannot fail must not be allowed to look like evidence.

---

## 5. The NQ→MNQ splice is licensed by a measurement, not an assumption

Verified on 25,657 matched minutes in May 2019:

- median close ratio MNQ/NQ = **1.000000000**, range 0.997640–1.002847
- median absolute difference **0.25 index points** — exactly one tick
- 63.4% of matched minutes within one tick

**Decided:** concatenate with no scaling factor. MNQ is one tenth the *notional* of NQ, not
one tenth the price.

Residual differences are microstructure: two separate books, so a minute's close is the last
trade in each and they do not trade in lockstep. The check asserts the **ratio** and reports
the difference **distribution**, so a one-tick residual cannot be mistaken for a convention
problem — and a factor-of-ten one could not be missed.

---

## 6. The kurtosis prediction was falsified, and the falsification is kept

`FUTURES_STRATEGY_HYPOTHESES.md` predicts index futures run "an order of magnitude lower"
kurtosis than BTC and that the 46-event DSR wall "drops to roughly 5 events".

Measured: **MGC at one minute is γ₄ = 226.5, fatter-tailed than Bitcoin's 199.9.** MNQ is
115.1 — lower by 1.7×, not ten. At 60 minutes the floor falls from 46 to 18, a real 2.6×
improvement but not the predicted tenfold one, and the lowest floor found anywhere is 10 at
180 minutes.

**Decided:** report the falsification as the headline of `reports/kurtosis.md` rather than a
footnote, and correct the "wall is gone" framing. The prediction's *direction* was right at
long horizons and wrong at one minute, which is exactly where a one-minute strategy would
live.

---

## 7. The GARCH null fit searches clustering as well as tail

**ν alone cannot reach MNQ's kurtosis.** With the inherited crypto parameters (α 0.20,
β 0.79) the generator floors at γ₄ ≈ 191 even with near-Gaussian innovations, because
volatility clustering contributes kurtosis on top of the innovation's own. A first pass
silently accepted that shortfall and tested the pipeline against a null 66% fatter than
intended.

**Decided:** fit (ν, α) jointly, holding α+β so persistence is preserved while the tail
thins, and report the **achieved** kurtosis beside the target. Both now match exactly.

**Recorded caveat:** in that first, mis-fitted pass the MGC null promoted 1 of 8. The
correctly-fitted run is 0/16. Two generators matching the same kurtosis behaved differently,
which says the result is sensitive to how the tail splits between innovation fatness and
clustering — so the §7.2 PASS is provisional until the Stage 1 bootstrap α is recalibrated
on futures moments.

---

## 8. The calibration seeding was unreproducible, and had to be redone

`cell_seed` originally used `abs(hash((seed, product, horizon, nb)))`. Python randomises
string hashing per process, so the same key gave **1,576,282,033 in one interpreter and
976,449,620 in the next** — the calibration could not be reproduced from its own recorded
seed, which §10 requires ("seed all RNG; log seeds").

**Decided:** SHA-256 of the joined key, verified stable across processes; and the first
floor sweep, which had already completed under the unstable seeding, was **discarded and
re-run** rather than kept. Its numbers were measured but not re-derivable, and in a project
whose entire premise is that results can be checked, that is not a number worth keeping.

**Also added:** per-cell checkpointing to both parts. Five session teardowns have killed a
long run in this project; each cell now writes and flushes its own line, so an interruption
costs the cell in flight rather than the run. Checkpointing is only *sound* because the
seeding was fixed first — resuming with process-dependent seeds would silently stitch
together cells drawn from different random streams.

The crypto project had both of these and I did not carry them over at the start.

---

## 9. The α calibration is one number, not six

The measurement was run per product and per horizon precisely because MNQ (γ₄ = 115) and
MGC (γ₄ = 226) differ so much at one minute. **They do not separate.** The spread between
cells at a given block count is 0.8–1.5 points against ±0.96 Monte Carlo error, and the
horizons do not separate either.

**Decided:** one calibration, and only two regimes within it — the per-block values above
100 blocks were 0.0409 / 0.0411 / 0.0402 / 0.0413, a 0.0011 range against ±0.0039 error on
each. Carrying five anchors would encode that wobble as structure and make the table
non-monotone in a quantity with no reason to be. The 24 cells at ≥100 blocks are pooled
into one number (48,000 reps, ±0.19).

**Rejected:** per-product calibration. It would have been fitting noise, and the evidence
that it would is in the report rather than merely asserted.

---

## 11. MGC's 70.85% RTH coverage is a standing caveat, not an F03 footnote

Measured while running F03: MGC trades **70.85%** of RTH minutes against MNQ's **98.31%**.
Analyses on a fixed minute grid must forward-fill the rest.

**Decided:** record it in `CLAUDE_FUTURES.md` §3 as a property of the instrument that every
MGC result inherits, rather than as a note on the one hypothesis that surfaced it. Filing it
under F03 would mean rediscovering it at F04, F05 and F07.

**Why it biases toward significance.** Forward-filling inserts zero returns, thinning
measured volatility; a thinner denominator inflates every t-like quantity built on it. So an
MGC null is weaker evidence than the same null on MNQ, and an MGC positive weaker still.

**Consequence adopted:** an MGC result that agrees with MNQ stands; an MGC result that
stands alone carries an explicit discount. Where a verdict rests on both instruments, the
report names which one carried it — for F03, MNQ at 98% coverage did, and MGC alone would
not have sufficed.

**Not decided:** whether to restrict MGC analysis to a liquid sub-era or to an event-time
rather than clock-time grid. Both would change what is being tested and neither is needed
until an MGC-only result actually matters.

---

## 12. Retirements are graded, and the grade is recorded

`retired` is one status but it does not carry one strength of evidence, and collapsing that
would make the catalog read as more settled than it is.

| | F03 | F04 |
|---|---|---|
| events on the deciding instrument | **150,355** | **3,880** |
| deciding instrument | MNQ, **98.31%** coverage | MGC, **70.47%** coverage |
| best cell vs detection floor | below on both | **0.30×** |
| pre-registered failure mode | **yes** — the catalog named aggregation as the biggest weakness, and it arrived | no — the catalog's stated worry was the 10:00 ET confound, never reached |
| confound control run | n/a | **no** — nothing separated, so it would have characterised noise |

**F03 was refuted.** It had 150,000 events on a 98%-covered instrument, detectability had
cleared it, and the catalog predicted the exact failure mode that then occurred. That is the
strongest form this evidence takes.

**F04 is soundly retired but not equally so.** Smaller sample, and the instrument that
carries the verdict is the one carrying the coverage qualifier — under §11 an MGC null is
the weaker kind. The 3–11× gap to the floor is far outside what a fill artefact could
produce, and coverage bias runs toward finding *more* rather than less, so the direction is
not in doubt. The strength is simply lower.

**Decided:** every retirement records what carried it — the deciding instrument, its
coverage, the sample size, the margin to the detection floor, and whether the failure mode
was pre-registered. Where a retirement is weaker than an earlier one, the entry says so
explicitly and names the comparison, as F04's does against F03's.

**Why this matters later.** A catalog of nine retirements looks like nine equal facts. If
one of them is ever revisited — because spread gets measured, or more data arrives, or a
condition is restated — the question is which retirements were thin. That has to be legible
from the registry, not reconstructed from git history.

**Owed if F04 is revived:** the same-clock-time random-day confound control for the PM
auction's collision with 10:00 ET US liquidity. The catalog requires it and it was never
reached.

---

## 13. The detectability gate was counting the wrong events, and two retirements rested on it

**The error.** `FIRES_PER_SESSION` stored how often a hypothesis's condition fires *across
its whole scan*. But Benjamini-Hochberg tests **cells**, and a cell fixes the scanned
dimension — so the sample that decides a cell is one firing per session, not thirteen. The
gate credited:

| | gate said | per cell, actually | inflation |
|---|---|---|---|
| F03 | 53,625 | 234–2,384 (median 1,172) | **13×** |
| F04 | 8,250 | 3,554–3,880 | **2×** |
| F07 | 48,072 | ~4,000 | **12×** |

Every combination those three ran was marked RESOLVABLE. Under the corrected gate, F03's
cells are **all** below the swept range, F04 keeps only MGC at 120m, and F07 keeps nothing.

**Found by** trying to schedule F07 and noticing its detectability row claimed 48,072 events
for a condition that fires twelve times a session over ~4,000 sessions — the arithmetic only
works if each cell gets all twelve firings, which it does not.

**The second-order error, caught immediately after.** Pooling a scan's cells usually
restores the sample, and that is how F03 keeps a verdict. But it only works when the
positions are **disjoint in time**. F03's 13 half-hour slots are 13 separate trades, so
pooling genuinely multiplies observations. F07's 12 slots are twelve predictors of *one*
target — the catalog regresses the last half-hour on each of the first twelve — so every
cell enters on the same 15:30 minute of the same session. Pooling stacks correlated readings
of one ~4,000-session sample. Treating that overlap as sample would have repeated the
original error one level up. `SCAN_POSITIONS_DISJOINT` now encodes it.

**What changed, and what did not.**

- **F03 stays retired, on different evidence.** Its per-cell BH result ("8 nominal hits
  against 5.9 expected, none surviving") is now known to be uninformative — those cells were
  never powered. The refutation rests entirely on the **aggregate**: 150,355 events across 13
  disjoint slots, −0.46 bps gross and −0.94 net, on a 98%-covered instrument, with the
  aggregate above the swept range. That is a real, powered, negative result. The verdict
  survives; the reasoning behind it was corrected.
- **F04 stays retired, on a narrower base.** Only MGC at 120m is per-cell informative, plus
  both instruments' aggregates. The 0.30× best-cell-to-floor figure came from a 60m cell now
  known to be uninformative and has been withdrawn; the surviving comparison is MGC 120m at
  0.09× its floor, which points the same way.
- **F07 is `stage1_uninformative`.** Not retired: no evidence was obtainable at any level.

**Why the whole class of error is worth a section.** Both mistakes have the same shape —
counting observations that are not independent as though they were. Scan breadth buys
trials, never power; overlapping positions buy neither. A gate that gets this wrong is worse
than no gate, because it launders an underpowered null into a confident one and the report
reads identically either way.

**Cost.** F07's 72 trials bought nothing and still enter N. F03's and F04's runs were not
wasted — their aggregates carry their verdicts — but their per-cell sections were.

---

## 10. Still outstanding, and blocking

- ~~The Stage 1 bootstrap α calibration is still crypto's.~~ **RESOLVED 2026-08-29** —
  measured at 0.0345 below 100 blocks and 0.0409 above, applied in `signals/stage1.py`.
- ~~The detection floor is still crypto's 0.1592×.~~ **RESOLVED 2026-08-29** — measured per
  product and horizon; see `reports/calibration.md`.
- **20 of 60 (hypothesis, instrument, horizon) combinations cannot support a null**, all
  limited by event rate rather than data. See `reports/detectability.md`. F01 — the
  catalog's top-ranked hypothesis — is blocked at both its stated holds.
- **Spread is still an estimate, not a measurement.** §4 carries 0.10 bps for MNQ and 0.12
  for MGC as estimates. At 60m and 180m the detection floor is 5–33× the whole cost floor,
  so spread barely matters there; at 1m it is the dominant term.
- **Three hypotheses have been through Stage 1.** F03 and F04 retired, F07 recorded
  `stage1_uninformative`. All three predate the §13 gate correction and their reports
  should be read with §13 open. See §12 for how the two retirements are graded.
- **The §13 correction is now applied registry-wide** (2026-09-02). 35 of 40 previously
  cleared combinations are blocked; 5 remain. `reports/detectability.md` carries the
  before/after diff and a per-hypothesis table of which verdict routes are open.
- **F05, F08, F10 and F11 are blocked on a MISSING MEASUREMENT, not a finding.** Their
  conditions state no per-session firing rate and none was ever counted. An unmeasured
  rate used to fall through to the data ceiling — the most generous possible assumption,
  applied where least was known. It now blocks. **Counting those four firing rates is a
  data measurement, not a Stage 1 run, and it is the single highest-value unblocking
  task available.** F10 and F11 are the controls, so the catalog currently cannot say
  what its own controls are powered to detect.
- **Only F02, F04 and F06 have an open per-cell route, and all five open cells are MGC** —
  the instrument carrying the standing coverage caveat. Any near-term per-cell verdict
  will rest on the weaker kind of null. F02, F03 and F04 have open aggregate routes.
- **F01's aggregate route is closed for the same reason as F07's**: its two entry times
  (15:00, 15:30) share a 15:55 exit, so the positions overlap and pooling adds almost
  nothing.
- **F04's confound control is owed if it is ever revived** — the same-clock-time
  random-day benchmark for the PM auction against 10:00 ET US liquidity.

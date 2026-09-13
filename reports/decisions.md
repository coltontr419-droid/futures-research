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

## 14. Choices made while counting the four uncounted firing rates

The conditions for F05, F08, F10 and F11 do not fully determine how to count their firings.
Each gap was resolved once, in public, rather than tuned.

| hypothesis | the gap | chosen | why |
|---|---|---|---|
| F05 | condition names neither the compression midpoint nor sigma | midpoint = mean close of the armed hour, sigma = std of those same closes | the only quantities the armed window itself supplies; anything else imports an outside scale |
| F05 | evaluated how often? | at each session hour boundary | "realized_vol(1h) ... at the same clock time" implies an hourly grid |
| F08 | sigma over what window? | trailing 20 sessions at the **same clock time** | matches F05's convention; a flat rolling window would mix 03:00 volatility into a 14:00 threshold |
| F10 | RSI on which bars? | bars of the hold's own length | otherwise RSI(14) means something different at each horizon and the three holds stop being comparable |
| F11 | "round values", never specified | fast 10, slow 30 | the registry left this genuinely open; it is a free choice and had to be made once rather than swept |

**F05's specification gap is the one worth flagging.** Its condition says to enter "on the
first close beyond k*sigma from the compression midpoint" but never says *by when*. Given a
whole session to break in, **14,846 of 15,770 armings break — a 94% rate**. The compression
filter does real work; the break condition, unbounded, does almost none. That is a defect in
the registered condition, not a property of the market, and F05 should not be scheduled
until the condition names a deadline. Recorded here rather than silently patched, because
choosing a deadline now would be choosing a parameter after seeing the data.

**F11 is a state, not an event.** Long whenever the fast MA is above the slow one means
always in the market: its firings equal its bar count and its independent count equals the
data ceiling. Only 6,420 actual position changes underlie MNQ's 164,775 30-minute
observations. The old fall-through-to-data-ceiling default was accidentally right for F11
and wrong for the other three — which is why an accident is not a policy.

**F10, a control, cannot resolve anywhere.** 5,594 independent events at best against 19,722
needed on MNQ; RSI(14) crossings through 30 and 70 are simply rare. A control that comes
back empty is supposed to be reassuring, but an underpowered control coming back empty is
indistinguishable from a powered one doing its job. **The catalog currently cannot verify
its own negative control**, and no amount of care elsewhere substitutes for that.

**F08 loses 30% of its sample to the cross-asset join** — 3,307,036 of 4,728,809 MNQ minutes
have a matching MGC minute. The standing MGC coverage caveat appears here as an outright
sample cut rather than as forward-filling, and it binds the only genuinely cross-asset
hypothesis in the catalog.

---

## 15. Two integrity gaps found while writing the status report

**`trials.jsonl` has never been written.** `src/futuresres/stats/trials.py` — the
hash-chained append-only trial log — was ported from the crypto repo with its tests, and its
tests pass, but **no Stage 1 runner calls it**. N is currently reconstructed by counting rows
in `reports/f*_cells.json`, which is exactly the reconstruction an append-only log exists to
make unnecessary: it is unverifiable, it silently loses anything not persisted, and it would
not detect a deleted trial. Every future Stage 1 run must write to it before anything else.

**F03's MGC cells were never persisted.** Its report covers both instruments and its
retirement quotes an MGC aggregate, but `reports/f03_cells.json` holds only MNQ's 117 rows.
117 trials were spent and their per-cell results exist nowhere. They are added to N from the
report rather than dropped, and the gap is marked in `reports/catalog_status.md` rather than
hidden by a tidier-looking number.

Both were found by trying to compute N honestly. Neither changes a verdict. Both mean the
catalog's own record of what it has spent is weaker than its record of what it found.

---

## 16. The trial log is now the source of truth, and measurements are kept out of N

**What was wrong.** `stats/trials.py` — the hash-chained append-only trial log — was ported
from the crypto repo with its tests, and its tests passed, and no runner ever called it. N
was being reconstructed by counting rows in `reports/f*_cells.json`. That reconstruction
cannot detect a deleted trial, and it silently loses anything never persisted, which is
exactly what happened to F03's 117 MGC cells: its retirement quoted an MGC aggregate whose
per-cell results existed nowhere on disk.

A log that nothing writes to is worse than no log. Its passing tests imply a discipline that
is not being practised, and it invites exactly the false confidence that the log exists to
prevent.

**What was done.**

- `signals/logged_run.py` provides `stage1_run(...)`, a context manager that **raises
  `UnloggedRun` if the log did not grow** by the time the block exits. Every runner's
  `main()` now runs inside it.
- `tests/test_trial_logging.py` **discovers runner modules by glob** rather than by a list,
  so a runner written next month is covered the moment it exists, not when someone remembers
  to add it. It asserts each one wraps `main()` in `stage1_run` and calls `record(...)`
  inside the block, and separately that the machinery raises when nothing is recorded.
- F03, F04 and F07 were backfilled from their cell files, marked `reconstructed`.
- F03 was re-run on both instruments to persist its missing MGC cells.

**Reconstructed is a weaker record than native, and is marked so.** A backfilled trial's
timestamp is the backfill's, its within-run ordering is whatever the output file happened to
hold, and nothing proves that file was not edited between the run and the backfill — which
is precisely the property an append-only hash chain provides and which these records, by
construction, cannot have. They count toward N because a look at the data is a look at the
data. They are not evidence that a log was being kept.

**Firing-rate measurements are chained separately and are NOT in N.** This is the one real
judgement call here. It is tempting to put all 102 rows in `trials.jsonl` so that everything
lives in one file. That would be wrong:

> N exists to deflate a Sharpe for the number of chances a candidate had to look good by
> accident. A firing-rate measurement has no Sharpe and computes no return series — it
> counts how often a condition triggers. It could never produce a candidate, so it cannot
> have contributed a chance for one to appear by accident.

Adding them would raise SR\*, making the bar stricter. Stricter sounds safe, and the
instinct to err that way is usually right, but **a bar set by a category error is not
conservative — it is just wrong**, and it would penalise every future candidate for looks
that could not have found anything. They go to `measurements.jsonl`, same machinery, same
guarantees, reported separately in `catalog_status.md`.

**The re-run reproduced F03 exactly, which is the reproducibility check the repo never had.**
Re-running both instruments to recover the missing MGC cells also re-computed MNQ's 117.
All 117 matched the committed originals: identical event counts, identical `mean_bps` to
1e-9, identical p-values to 1e-12. MGC's recovered aggregate is +0.03 bps, matching the
figure its retirement quotes. That is evidence the SHA-256 cell seeding introduced earlier
actually holds across processes and across months — previously asserted by a unit test, now
demonstrated on a real 234-cell run.

**What this does not fix.** The context manager guarantees the log grew; it cannot verify
that *every* cell was passed to `record()`. Nothing inside a run can check that. The
structural tests are what stand in for it, and they check the shape of the code rather than
the completeness of a particular run.

---

## 17. The negative control is not a control, and could not have been

Two separate problems, found by asking whether F10 could be replaced.

**F10 fails on power.** 1,585-5,594 independent events against a swept range starting at
19,722. An unpowered control coming back empty is indistinguishable from a powered one
working correctly, so it cannot support the one claim it exists to support.

**F11 fails on premise, and would have failed at any sample size.** Its entry justifies it
as "the canonical published trend rule [with] no counterparty story". That is a *prediction
about the market* - that the rule is arbitraged away - and it is contestable: a fast/slow MA
crossover is time-series momentum, which in futures specifically is among the
best-documented anomalies in the literature, and the managed-futures industry is built on
it. Decisively, **F01 in this catalog is a momentum hypothesis and F11 is a slow momentum
rule.** If the harness promoted F11 there would be no way to separate a pipeline failure
from a correct detection of a real effect - which is exactly the distinction a control
exists to draw. The same objection applies more weakly to F10 against F02, the reversal
hypothesis.

**Decided:** a control's premise must be *"this cannot relate to future returns by
construction"*, never *"this should have been arbitraged away"*. The second is a hypothesis
wearing a control's label, and both current controls are that.

**The structural finding, which is the important part.** Candidates were measured at three
firing regimes (`reports/control_candidates.md`). A once-a-session condition yields ~3,500
events against MNQ's 19,722. **No control of any construction can clear the bar on MNQ in
the regime where most of this catalog's hypotheses live.** F10's problem was never RSI; it
was firing rate, and any replacement matching those hypotheses' regime fails identically.

So a replacement validates the harness **in a different regime from the one most hypotheses
use**. It can show the pipeline does not promote a mechanism-free signal on real futures
data at F03-like event counts. It cannot show that at F01-like counts, because at those
counts nothing is demonstrable - which is why those hypotheses are blocked in the first
place. Any claim the control licenses carries that scope, and must not be generalised past
it.

**Rejected design, recorded because it looked good.** `sign(sin(t/500))` fires every bar and
clears the sample requirement easily. It is rejected because a periodic direction beats
against the session cycle and can pick up genuine time-of-day structure. That exact
construction is the §7 POSITIVE control - the property making it a good positive control
disqualifies it as a negative one.

**Nothing was registered.** `hash-slot` (SHA-256 of the bar timestamp, low bit, fired at each
30-minute RTH slot open, holds 30/60/120) is the recommendation, resolvable in 12 of 12
combinations, with its parameters fixed in writing before any run so that "fixed a priori"
is checkable rather than asserted. Registering it, and deciding what to do with F10 and F11,
is a call for the user.

---

## 18. F14 registered as the control; both predecessors retired

**Registered as F14, not F12.** F12 was requested, but F12 is the excluded
`pre_fomc_announcement_drift` entry and reusing the id would have erased a deliberate
exclusion and the two independent reasons behind it. F14 is the next free id.

**Parameters fixed in writing before any run**, which is the entire point of the ordering:
SHA-256 of the bar's ISO timestamp, low bit -> long/short, fired at each 30-minute RTH slot
open, holds {30, 60, 120}, MNQ and MGC. `param_cap: 0` - there is nothing to sweep, so
"fixed a priori" is checkable rather than asserted in good faith.

**The scope statement lives in a FIELD, not a comment.** It was first written as a YAML
comment block, which `yaml.safe_load` discards - so every tool reading the registry would
have seen a control with no stated scope, and the test asserting the scope exists failed
against the loaded entry rather than the file. Anything a tool must check has to survive
parsing. `control_scope` now carries it and a test asserts both halves.

**F11 retired on premise, F10 on power, and the distinction is preserved by a test.** F11
was *powered* - 43,759 to 173,879 independent events, resolvable everywhere - and still
could not serve, because its premise was that a canonical trend rule should have been
arbitraged away. That is a contestable market prediction, and a fast/slow MA crossover is
time-series momentum, the same family as F01. Recording it as merely another underpowered
control would lose the only interesting thing about it, so
`test_a_retired_control_says_which_of_the_two_failures_it_was` fails if the two reasons blur.

Both keep `is_control: true` though retired: a reader tracing why the catalog's control
changed needs to find them as controls, not as ordinary retired hypotheses.

**What the catalog now cannot claim.** F14 covers F03-like event counts only. F01, F02, F04,
F06 and F09 live in the once-a-session regime and have no real-data control, and none can be
built on this sample. When reporting a null from any of them, that gap is stated rather than
covered by F14's assurance.

---

## 19. The control passed, and what that does and does not establish

F14 ran on both instruments and **did not separate**: 0 nominal separations against 0.30
expected by chance, 0 BH survivors, aggregate +0.06 bps on MNQ and -0.08 on MGC, both
negative net of cost. Long share 0.497 on both, so the hash is not degenerate. No halt.

**What it establishes.** The harness declines to promote a signal that cannot relate to
future returns by construction, on real futures data with real gaps, real volatility
clustering and real session boundaries, at ~48,000-52,000 event samples. That is strictly
more than the §7.2 synthetic GARCH nulls establish, because those test idealised noise.

**What it does not establish, and this is the part to keep saying.** Nothing about
~4,000-event samples. F02, F04, F06 and F09 fire once a session, reach ~3,500 events, and
have no real-data control available at any construction. A null from any of them carries the
§7.2 synthetic assurance and nothing more.

**Two design points that only surfaced by writing the runner.**

*The hash is taken from the CALENDAR, not from the bar.* A grid position's timestamp is
built from its session date and minute-of-day, so a forward-filled minute hashes identically
to a traded one. Had the hash used the bar's own recorded timestamp, a filled minute would
have inherited the previous trade's stamp - and the direction would have become a function
of **trading activity**, which is a property of the market. That would have quietly turned
the control into a hypothesis, by the same route that sank F11, and it would not have been
visible in any result.

*Event counts exceed the registration estimate, as expected.* `control_candidates.md`
measured 9.2 firings a session by requiring a traded bar at the exact slot minute; the
pipeline forward-fills, as F03 and F04 do, so all 13 slot opens fire. The registration
figure was a conservative lower bound on the same quantity. More events, not fewer.

**F14 stays `untested`.** `stage1_passed` is not used: a control behaving correctly has not
passed in the sense that status carries for a hypothesis, because it was never a candidate.
`control_result: pass` records the outcome, and the entry says it should be re-run whenever
the harness changes - the opposite of a resolved entry.

**These are the first natively logged trials.** Every earlier record in `trials.jsonl` was
backfilled; F14's 6 were written by the runner inside `stage1_run`, which is what the wiring
was for.

---

## 20. Choices F02's condition did not determine

| the gap | chosen | why |
|---|---|---|
| sigma for `k*sigma` | trailing 20-session std of the 15:00-16:00 ET return, strictly prior sessions | same-clock-time, matching the convention already fixed for F05 and F08; a flat rolling window would mix other hours' volatility into the threshold |
| exit rule | hold is the parameter, window is the entry anchor | the condition says both "exit at the window close" and "hold in {1,2,4}h"; treating the window as the exit would leave the hold axis doing nothing |
| era boundary | 2021-01-01 | the date the authors' own decay finding names |
| both arms | run separately, sell_imb primary | the catalog says the symmetric condition is "tested separately and expected to be weaker"; reporting it is how that prediction gets checked rather than assumed |

The grid spans 15:00 ET to 06:00 ET the next day, 900 minutes a row, because the trade does.
Rows are keyed by the date of the 15:00 observation, so a bar before 06:00 belongs to the
previous day's row.

---

## 21. A DECLARED firing rate can be wrong, and section 13's fix did not cover that

**The failure.** The gate showed F02 with an open per-cell route on MGC at 120m and 240m and
an open aggregate on 5 of 6 combinations. Running it produced 106-707 events per cell
against a declared 4,006-4,125 - wrong by an order of magnitude, and every cell uninformative.

**Two causes, neither propagated into the gate.**

1. **The condition is threshold-gated.** F02 fires only when `|imb| > k*sigma`, measured at
   6-23% of rows depending on k. The declared rate of "one per session" counted the
   OPPORTUNITY - one imbalance reading per session per window - not the TRIGGER.
2. **The mandatory regime split halves the sample again.** Pre-2021 holds ~3,100-3,200 rows,
   post-2021 ~1,730. Nothing told the gate this hypothesis must be evaluated in two eras,
   because the split requirement lives in F13's exclusion note rather than in F02's fields.

**Why section 13 missed it.** That repair addressed two things: scan multiplicity, and rates
that were *never counted*. It added a test that every hypothesis has a declared **or**
measured rate. It did not, and could not, check whether a **declared** rate was correct - a
declaration is exactly the thing a test has no independent source for.

**The class, not the instance.** F01, F06 and F09 are all conditionally triggered - on
`|r1| > k*ATR`, on a confirmed breakout, on a settlement-window move - and all declare 1.0.
Every one of those is an upper bound on the opportunity, not a measurement of the trigger.
They are now flagged `THRESHOLD_GATED` in the gate, and their rows must be read as optimistic
until measured. **F01 is already closed on both routes at its declared rate**, so measuring
it can only confirm that; F06 and F09 have rows the gate currently reports as open and those
should not be trusted.

**Decided:** a declared rate is provisional. A hypothesis whose condition contains a
threshold, a confirmation, or any filter beyond "the clock reached this time" must have its
rate MEASURED before its gate row is used for scheduling. Counting is cheap - `firing_rates`
does it without spending a trial - and the alternative is discovering the error by spending
144 trials, which is what happened here.

**Second-order note on multiplicity.** F02 produced 0 nominal separations against 7.2
expected at alpha=0.05. Zero is not evidence of an unusually clean null; within each
(instrument, era, arm) family the 18 cells share entry dates heavily - same k selects the
same days, and the three holds are nested - so the effective number of independent looks is
far below 144. The expected-by-chance column is computed as `alpha * n_cells` and is
therefore an overestimate wherever cells overlap this much. It is reported unchanged because
correcting it would require an effective-independence estimate this pipeline does not have,
but it should not be read as "seven separations failed to appear".

---

## 22. Declared firing rates no longer gate anything

**The rule.** The detectability gate reads `reports/measured_rates.json` and nothing else. A
hypothesis with no MEASURED rate is UNSCHEDULABLE, not optimistically cleared. Declarations
survive as `DECLARED_ESTIMATE`, are never consulted by `assess()`, and exist only so the gap
between what a condition looks like it should fire at and what it does can be seen.

**Why, in one line.** §21: F02 declared 1.0, measured 0.061, and no test could have caught
it — a declaration has no independent source to check against.

**What "measured" now means.** The condition's own threshold applied (`k*sigma`, `k*ATR`,
breakout confirmation), any mandatory regime split applied with the **worst era** gating,
counted per Stage 1 cell, and — for a hypothesis that has already run — taken straight from
its cell file, which is the strongest measurement available because it is what the pipeline
actually produced.

**Magnitude of the correction, worst cell per hypothesis:**

| | previously gated on | measured | factor |
|---|---|---|---|
| **F01** | 4,125 | **66** | **62.5x** |
| F03 | 4,125 | 234 | 17.6x |
| F11 | 78,888 | 12,285 | 6.4x |
| F10 | 5,594 | 1,585 | 3.5x |
| F14 | 32,587 | 12,285 | 2.7x |
| F06 | 4,125 | 1,621 | 2.5x |
| F02 | 251 | 106 | 2.4x |
| F05 | 14,559 | 8,190 | 1.8x |
| F09 | 4,125 | 2,365 | 1.7x |
| F04, F07 | 4,125 | 3,387-3,420 | 1.2x |

**Only two combinations changed status** — F06 MGC at 120m and 180m, RESOLVABLE to MIXED.
That is a much smaller headline than the factors above, and the reason is worth stating: most
of the catalog was already blocked, and a hypothesis that is 4.8x short of the bar is not
made more blocked by discovering it is 62x short. **The status labels understate how badly
the gate was misinformed.** F01's real per-cell sample is 66 events at its most selective
setting, against a floor that resolves at 19,722.

**F09 is NOT threshold-gated, and an earlier note in this project said it was.** Its
condition enters at S-15min on every session with no filter; its rate is bounded only by data
availability and by a flat pre-move. It measures 2,365-3,406 rather than the declared 4,125,
and the shortfall is missing bars at the exact pre-window minute, not a threshold. The
earlier claim is corrected here rather than left standing.

**Two tests hold the line.** `test_declared_rates_never_gate` parses `assess()` and fails if
it references the declared table — the failure mode being a future edit that reintroduces a
helpful-looking fallback ("use the declaration when no measurement exists"), which is exactly
what let F02 through. `test_every_hypothesis_has_a_declared_or_measured_firing_rate` became
`measured`-only: a declaration no longer satisfies it.

**The gate's own remediation instruction was a no-op.** Three places — the loader
docstring, the `FIRING RATE UNMEASURED` message, and a test failure message — told anyone
who hit a blocked row to run `python -m futuresres.reporting.measured_rates`. That module
had no `main()`. The command printed nothing, did nothing, and exited 0, so the file the
whole gate now depends on could only be produced by an ad-hoc script that lived outside the
repo. Fixed: the module has `main()` and `--check`, and `--check` confirms the committed
cache reproduces exactly from a fresh measurement.

`test_every_documented_entry_point_actually_runs` now scans the source for every
`python -m futuresres...` string and fails if the named module has no `main()`. **A
remediation instruction that silently does nothing is worse than none** — it converts a
blocked row into a puzzle, and it hides that an artifact has no reproducible provenance.

**Cost.** Measuring all twelve takes 16 seconds and spends no trial. Discovering the same
thing by running F02 cost 144 trials and took SR\* from 0.0902 to 0.1402.

---

## 23. F05's deadline, and the defect the deadline did not fix

**The deadline is derived, not chosen: 60 minutes from the end of the armed hour.** The
mechanism is volatility clustering, which forecasts NEAR-TERM expansion. A realized-vol
estimate is informative over a horizon on the order of its own estimation window - that is
what the decay of the autocorrelation in |returns| means - so a vol measured over one hour
speaks to the next hour, not the next six. Independently: the trigger measures distance from
the COMPRESSION MIDPOINT, which goes stale within hours. Both arguments give one compression
window. It is ONE VALUE, not a new grid axis; sweeping {30, 60, 90} would turn a
specification repair into a tuning opportunity.

**It does not fix the vacuity, and that is the finding.** Re-measured with the deadline
applied, F05 still fires on **79-91% of armings**:

| k | break rate |
|---|---|
| 1.5 | ~90% |
| 2.0 | ~86% |
| 2.5 | ~80% |

**The cause is that sigma is measured on the compressed window itself.** Compression SELECTS
hours with small sigma, so k*sigma is a small distance, and price almost always travels that
far within the next hour. The tighter the compression, the easier the trigger. The filter
selects for exactly the condition that makes the trigger nearly certain.

**The open decision, deliberately not taken here:** what should k*sigma be measured against?

  (a) the compressed hour's own sigma - current, self-defeating
  (b) the trailing 20-session sigma at the same clock time - the quantity the p20 filter
      already compares against, so a break would mean "price moved a NORMAL-sized amount",
      which is what an expansion claim actually asserts
  (c) an ATR-scaled distance

**(b) is the reading most consistent with the rest of the condition**, but adopting it
changes the registered hypothesis and must be a deliberate decision rather than a repair made
mid-audit. F05 is `schedulable: false` until it is settled.

Note what makes this dangerous: **F05's routes are OPEN on event count.** A vacuous condition
with plenty of events produces a confident-looking result about nothing, and no event-count
gate can catch it.

---

## 24. Stage 0: instruments must be derived from the mechanism

**F02 ran 72 trials on an instrument where its hypothesis is not defined.** Its counterparty
is the NYSE closing-auction participant; gold has no NYSE closing auction. `symbols: [MNQ,
MGC]` was set by habit, and nothing in the pipeline asked whether the mechanism could hold in
both - because nothing required the question to be answered. Those trials count toward N,
because the looks happened, but they could never have been evidence either way.

CLAUDE_FUTURES.md 5.10 now requires `mechanism_instruments` on every entry: a primary, a
secondary that may be null, and a rationale. The retroactive audit:

| | finding |
|---|---|
| **F02 / MGC** | **cannot hold** - no NYSE closing auction. Registration error. |
| **F06 / MGC** | **attenuated** - 09:30 ET is the EQUITY cash open; gold's is COMEX 08:20. On MGC it tests a cross-asset spillover, not the registered mechanism. |
| **F01 / MGC** | **attenuated** - leveraged gold ETFs exist but the complex is orders of magnitude smaller and is not pegged to the equity close. |
| F04 / MNQ, F07 / MNQ | **control** - already registered and reported as confound controls rather than second tests. |
| F08 | **requires both** by construction; neither leg is optional. |
| F03, F05, F09, F14 | hold in both. |

An `attenuated` instrument may still be run. What it may not do is silently carry a verdict.

---

## 25. Audit of the remaining untested candidates

Asked for the same class of defect the F05 deadline and the F02 instrument error represent.
**No parameters were chosen; where a decision is needed, the decision is stated.**

**F06 - two defects, now `schedulable: false`.** `vol_filter in {none, >median}` never says
median OF WHAT over WHAT WINDOW; `measured_rates` had to invent a reading to count at all,
and that reading changes the event count and therefore whether F06's routes are open. Plus
the MGC instrument attenuation above. *Decision required: what quantity the vol filter
thresholds, and over what lookback. The same gap exists in F01 and should be settled once for
both.*

**F08 - three defects, now `schedulable: false`.** The phrase "the lower volume-weighted
move" decides which leg is traded, and therefore decides the strategy's direction, and is
defined nowhere - return times volume, return divided by volume, and VWAP displacement give
different and sometimes opposite answers. The traded instrument varies per event, so
`symbols` does not mean what it means elsewhere and F08's per-instrument gate rows are not
comparable with any other hypothesis's. And its mandatory regime split lives in a
falsification note rather than a field - **exactly how F02's split escaped the gate.**
*Decisions required: how the volume-weighted move is computed; how the traded leg is
recorded; where the regime boundary falls.*

**F09 - the cleanest entry in the catalog, with one thing to remember.** No undefined
threshold, both directions named, a settlement time given per instrument. Nothing needs
deciding. Its defect is overlap with F01, which its own falsification note predicted: on MNQ,
F09 enters at 14:45 and F01 at 15:00 or 15:30, all out by ~15:55, so counting both as
independent evidence about the same afternoon would be double-counting. **Moot today** - F01
is blocked and F09 is closed on both routes at 2,365-3,406 measured events - and it stops
being moot the moment either is revived. Recorded, not fixed; F09 stays schedulable.

---

## 26. The control was re-run, and re-running it is not free

F14 was re-run after the gate changes, as its entry requires. Identical to the first run to
the fourth decimal - 0 nominal separations, 0 BH survivors, long share 0.497 - which also
demonstrates the seeding is stable across a day of pipeline edits.

**A tension worth naming: each control re-run spends 6 trials.** The entry says to re-run
whenever the harness changes, and the harness changes often. Those trials raise SR* for every
real candidate, on behalf of a hypothesis that can never be promoted. The same argument that
put firing-rate measurements in a separate log (section 16) applies here: a control cannot
produce a candidate, so arguably it cannot have contributed a chance for one to appear by
accident. The counter-argument is that F14 does compute a real return series on real prices,
unlike a firing-rate count.

**Not resolved here.** N currently includes the control's 12 trials across two runs. If
re-running on every harness change becomes routine, that grows without bound and the question
has to be answered.

---

## 27. F05: the registered condition did not test its own mechanism

**Adopted option (b) as a SPECIFICATION CORRECTION, not a parameter choice.** The trigger
now references the median of the trailing 20 sessions' sigma at the same clock time, rather
than the compressed window's own sigma.

**Why it is a correction and not a tuning decision.** Compression forecasts EXPANSION, and
expansion means volatility RETURNING TOWARD NORMAL. A trigger asserting expansion must
therefore measure against normal volatility. Measuring against the compressed window's own
sigma tests something else entirely: whether price moves a *compressed-sized* distance after
a compressed hour, which is nearly guaranteed and which the mechanism never claimed. The
registered version was not a weaker test of volatility clustering - it was a test of a
different proposition.

It also unifies the condition. The p20 arming filter already compares against the trailing
20 sessions at the same clock time; the trigger now uses the same window and the same
quantity, so F05 holds ONE notion of "usual volatility at this hour" instead of two
incompatible ones.

**Effect - the k axis discriminates for the first time:**

| k | before (own sigma) | after (normal sigma) |
|---|---|---|
| 1.5 | ~90% | 72-78% |
| 2.0 | ~86% | 57-64% |
| 2.5 | ~80% | 44-50% |

Under the old reading k moved the break rate by 10 points across its whole range; it now
moves it by 30. A parameter that did nothing now does something, which is what it means for
a condition to have been mis-specified rather than merely loose.

**Routes remain open: 5 of 6 per-cell** - MNQ 120m/180m and MGC 60m/120m/180m. MNQ 60m drops
to BELOW SWEPT RANGE at 6,965 measured events against 19,722. The 60-minute break deadline
from section 23 is unchanged. **F05 is schedulable again.**

---

## 28. F06's vol_filter is settled; F01's is not

**F06:** this session's realised volatility, computed from its own RTH minute returns,
against the MEDIAN REALISED VOLATILITY OVER THE TRAILING 20 SESSIONS, strictly prior. One
lookback, matching the 20 sessions used throughout the catalog.

**Effect:** measured events fall to 1,708 on MNQ and 1,785 on MGC. **MNQ closes entirely.**
MGC 120m and 180m remain open as MIXED - 2 of 6.

**Both remaining routes are on MGC**, where F06's mechanism is attenuated: 09:30 ET is the
EQUITY cash open, so on gold the condition tests a cross-asset spillover rather than the
registered claim (section 24). F06 is schedulable, but it can now only be tested on the
instrument where its mechanism is weakest, and that should be known before trials are spent.

**F01's identical gap is NOT settled.** It has `>median` and `>p66` variants and no stated
quantity or lookback. Only F06's was decided. F01 is `blocked_insufficient_events` and will
not run, so nothing rests on it - but the reading used to count it is a measurement
convenience, and if F01 is ever revived that must be decided first. The function is named
`f01_vol_filter` and says so.

---

## 29. F08 retired on PREMISE - the mechanism does not name a direction

**The mechanism identifies a divergence, not a mispricing.** It says that when MNQ and MGC
move the same direction sharply during a risk-off signal, "one of them is wrong". That is a
statement that the pair is inconsistent. It does not say WHICH leg is wrong, and a strategy
needs that.

**The condition supplied a direction anyway**, fading "the weaker-conviction leg (the lower
volume-weighted move)". That rule appears nowhere in the mechanism, nothing derives it, and
it is not well defined - return times volume, return divided by volume, and displacement
from VWAP give different and sometimes opposite answers. **A rule invented at the condition
stage to fill a gap the mechanism left is a free parameter wearing a mechanism's clothes.**

**So a result would have been unreadable in both directions.** A pass would not support the
mechanism, which never predicted that direction. A failure would not refute it, which never
predicted the opposite either.

**This is a premise failure, alongside F11, and NOT a power failure.** F08 measured 530-6,151
independent events with 5 of 6 routes open. It had the sample. It would have failed at any
sample size. The catalog now has three retirements with distinct causes and the distinction
is load-bearing:

| | cause | had the sample? |
|---|---|---|
| F10 | sound premise, **no power** | no |
| **F11** | **premise** - a momentum rule as a control for a catalog containing a momentum hypothesis | yes |
| **F08** | **premise** - the mechanism licenses no direction | yes |
| F03, F04 | evidence | yes |

Never run; no trials spent.

---

## 30. Control runs moved out of N

**The argument is section 16's, applied one level up.** N deflates a Sharpe for the number of
chances a candidate had to look good by accident. A negative control is mechanism-free BY
CONSTRUCTION and could never produce a candidate, so it cannot have contributed such a
chance. F14's entry also requires re-running it whenever the harness changes - which, at 6
records a run, would grow the multiple-testing budget without bound on behalf of something
that can never be promoted (the tension flagged in section 26).

**N: 498 -> 486. SR\*: 0.1409** (V rose to 0.002141 as the control's near-zero Sharpes left
the variance).

**Rewriting an append-only log is serious, so nothing was destroyed.** The pre-migration file
is kept verbatim as `trials.superseded-2026-09-02.jsonl`, its chain verifies, and a test
asserts every record in it appears either in the live log or - by its recorded original id -
in `measurements.jsonl`. A log that can be rewritten without an archive is just a mutable
file.

**The routing is structural, not remembered.** `log_path_for()` derives the destination from
the registry's `is_control`, so a future control runner cannot put records in N by forgetting
to. The obvious failure mode here was a one-off migration followed by the next F14 run
re-polluting the log.

**What did NOT move.** F14's 12 records are logged, verifiable and reportable - they simply
do not spend trials. The control still ran, still passed, and its result still stands.

---

## 31. F05 ran and did not separate

First hypothesis run under a corrected condition, and the first INFORMATIVE null in the
catalog. 54 cells, 54 trials.

| | informative | nominal | expected | BH survivors |
|---|---|---|---|---|
| MGC | 27 of 27 | 1 | 1.35 | **0** |
| MNQ | 18 of 27 | 0 | 0.90 | **0** |

MNQ at 60 minutes is UNINFORMATIVE - 6,965 measured events against 19,722 - and its nine
cells are excluded from the verdict.

**The effect is nowhere near the floor.** Best informative cell is MNQ p15 k=2.5 H=180 at
+0.79 bps on 5,812 events: **0.05x its detection floor**, p=0.2137. The one nominal
separation is on MGC and does not survive BH. Aggregates are negative net of cost on both,
-0.88 bps MGC and -0.44 MNQ.

**This is what an informative null looks like, and the catalog has not had one before.** F02
and F07 came back empty from samples that could never have shown anything. F05 had 11,000 to
18,600 events across 45 informative cells. The sample was there; the effect was not.

**MNQ carries the stronger null** at 83.16% coverage against MGC's 64.16%. Both point the
same way, which is the easy case - the standing MGC caveat would have mattered had MGC
separated and MNQ not. F05's mechanism is generic to speculative price series and holds in
both, so neither is a control for the other and neither is the wrong instrument.

**No real-data control exists at this event regime.** F14 validated the harness at
~48,000-52,000 events; F05's cells hold 6,965-18,591. This null carries the section 7.2
synthetic GARCH assurance and nothing from F14.

**Status left unchanged pending a decision.** The evidence supports retirement - informative
cells, adequate sample, nothing within 20x of the floor - but that call is not made here.
`schedulable: false` so nothing re-runs it meanwhile.

**A note on what the correction bought.** Had F05 run as registered, it would have fired on
79-91% of armings with a trigger that shrank whenever the filter fired, and the resulting
null would have been a statement about a condition that tested nothing. The correction did
not produce a positive result - it produced a null that means something.

---

## 32. `next_id` was derived from the record count, and the migration broke it

Found by F05's first run failing with `trial_id 't00487' is already in the log`.

`TrialLog.next_id()` returned `f"t{len(self) + 1:05d}"`, on the reasoning that an
append-only log only grows so the count is the high-water mark. **Moving the control records
out (section 30) falsified that**: the log held 486 records whose ids ran to t00492, so the
count-derived next id collided with an existing one.

The log refused the duplicate rather than accepting it, which is the log working exactly as
designed - a repeated id makes N ambiguous. The fault was the id scheme. `next_id` now takes
the maximum suffix already used, which is monotonic regardless of what the log contains.

Worth noting the shape: a helper whose correctness depended on an invariant ("only ever
grows") that a later, deliberate change removed. Nothing tested the helper against a log with
gaps, because until section 30 no such log could exist.

---

## 33. F05 retired, and where it sits among the six retirements

**Retired on an informative null.** 45 informative cells across 11,000-18,600 events, 1
nominal separation against 1.35 expected, 0 BH survivors on either instrument, best
informative cell at **0.05x** its detection floor. Aggregates negative net of cost on both.

MNQ carries the stronger null at 83.16% coverage against MGC's 64.16%, and **both
instruments point the same way** - so the standing MGC caveat never had to be adjudicated.
It would have mattered had MGC separated and MNQ not.

**No real-data control exists at this event regime.** F14 validated the harness at
~48,000-52,000 events; F05's cells hold 6,965-18,591, and no control can be built between
those regimes on this data. The null carries the section 7.2 synthetic GARCH assurance and
nothing from F14. That limit is part of the verdict, not a footnote to it.

**The specification correction is what made the null meaningful.** As registered, the trigger
measured k*sigma against the compressed window's OWN sigma, so compression shrank the trigger
distance exactly when the filter fired: 79-91% of armings broke, and k moved the rate by ten
points across its whole range. A null from that condition would have been a statement about a
trigger that fires almost always - about nothing. Both repairs were derived from the
mechanism and recorded before the run, which is what distinguishes a correction from a tuning
choice made after seeing a result.

### The six retirements, graded

Section 12 established that retirements are not uniform and that the grade is recorded. With
six of them the picture is worth consolidating:

| | cause | deciding instrument | sample | strength |
|---|---|---|---|---|
| **F05** | **informative null** | MNQ, 83.16% | **45 informative cells, 11,000-18,600 events** | **strongest - the sample was demonstrably there** |
| F03 | evidence | MNQ, 98.31% | aggregate 53,625 independent; per-cell UNINFORMATIVE | strong on the aggregate route only |
| F04 | evidence | MGC, 70.47% | only MGC 120m per-cell informative | weakest of the evidence retirements |
| F08 | **premise** | n/a | 530-6,151, 5 of 6 routes open | had the sample; the mechanism licensed no direction |
| F11 | **premise** | n/a | 43,759-173,879 | had the sample; a momentum rule cannot control a momentum catalog |
| F10 | **power** | n/a | 1,585-5,594 vs 19,722 | sound premise, could never resolve |

Three distinct causes, and the distinction is load-bearing. **F05 is the only one where a
hypothesis was tested at adequate power and the market said no.** F03's per-cell result was
uninformative and its verdict rests on its aggregate; F04's narrowed to a single instrument
and hold. F08 and F11 failed before any data mattered. F10 could not have produced evidence
at all.

**What that says about the catalog.** Of 14 registered hypotheses, exactly one has been
tested to a standard where a null means the effect is absent rather than undetectable. The
binding constraint has been event scarcity, registration defects and control design - not the
absence of signal. Six closures, and only one of them is about the market.

---

## 34. F06 retired, F14 re-confirmed, and the catalog closed

**F06.** 36 cells on MGC, 36 trials. 12 informative cells at ~3,950 events, 0 nominal
separations against 0.60 expected, 0 BH survivors, every informative cell negative, best at
0.00x its floor, aggregate -0.62 gross and -1.27 net.

Graded per section 12: deciding instrument **MGC at 70.88% coverage where the mechanism is
ATTENUATED**, sample 12 cells at ~3,950 events, margin to floor 0.00x, failure mode
**pre-registered twice** - the entry's own note says to treat a positive result with more
suspicion than a negative one, and the scope limit was recorded before the run.

**Weaker than F05's retirement on every axis**: a quarter the informative cells, a quarter
the events, lower coverage, a deciding instrument that does not hold the mechanism, and an
open route that cleared on 2,862 - the lowest resolving threshold in the study.

**MNQ was not run and that is not a null.** It is closed on every route at 1,708 events
against 19,722. Spending 36 trials there would have raised SR* for nothing. So **the
registered mechanism has never been tested on the instrument it describes**, and F06's
retirement does not claim otherwise.

**F14 re-run** under current settings, third time: 0 separations, 0 BH survivors, long share
0.497, identical to the prior runs. It logged to `measurements.jsonl` automatically via
`log_path_for()` - the routing added in section 30 worked without anyone remembering it.

**A runner bug caught before it mattered.** F06's first draft compared every hold against
MGC's 60-minute resolving threshold (5,620) instead of the per-proxy figure, which would have
marked its only informative cells as blocked and produced a report claiming F06 had no open
routes at all. The floor cells are per (product, horizon) and the mapping is by nearest
horizon in log space; a single constant cannot express that.

---

## 35. The catalog is closed

`reports/futures_conclusion.md` is the terminal document, written to stand alone.

**14 registered, 576 trials, SR\* = 0.1334, 0 promoted.** The headline: **exactly one
hypothesis - F05 - was tested at adequate power.** Every other closure turned on event
scarcity, registration defects, control design or exclusion, none of which is a statement
about the market.

**The number worth remembering: F02 and F07 together consumed 216 of 576 trials - 38% - and
neither could produce evidence.** That is the price of a gate that was wrong, and it is why
`gate_history.md` exists.

**The structural finding.** At 1 minute the detection floor sits BELOW the cost floor, so
economics binds. At 60 minutes and beyond the detection floor sits far ABOVE it, so
detection binds. Every hypothesis in this catalog operates at 30 minutes or longer, which
means **all of them live on the side of the crossover where the limit is statistical rather
than economic**. "No edge found" is usually the wrong reading of these results; "could not
have found one" is usually the right one.

**What closes and what does not.** The catalog as registered is closed. The research is not.
Reopening it usefully needs conditions that fire several times a session rather than once,
instruments where the mechanisms actually live, conditions specified tightly enough that no
decision remains after registration, and a real-data control that reaches the once-per-session
regime. Until that last one exists, every verdict in that regime rests on synthetic noise
alone.

---

---

## 36. The L-series reconciled — a remote, a stale checkpoint, and a placebo that is still wrong

Four things were wrong with how the L-series was recorded, and one is still wrong with the
L-series itself. None of them was a bug in a calculation. **All of them were a gap between
what had been measured and what the record said had been measured.**

### The repo had no remote, and it is the one every other programme depends on

`futures-research` had **28 local commits and no remote**, on a single Windows machine, while
`r-series-research` quoted its detection floors — the 19,722 figure that closes hypotheses in
another repository — as settled fact. A disk failure would have taken the calibrations and
left the conclusions that rest on them.

Now at `github.com/coltontr419-droid/futures-research`, **private**, all 28 commits pushed.
`.gitignore` was verified doing its job first: `.env` is untracked (only `.env.example` is in),
and `data/` and every `*.parquet` are excluded. The pack is 2.7 MB.

### The registry said the work had not been done, four days after it was done

The batch completed **2026-09-05** and was committed as `fb07e80`. All ten L entries still
read `status: untested` with **no `firing_rate` block at all**, while
`reports/level_rates.json` held a measured count for every one of 315 cells.

**Neither half was wrong. They just never met.** The reports were generated and committed; the
registry was not updated to consume them. A later reader checking `hypotheses.yaml` — which is
the file the pipeline treats as authoritative — would correctly conclude the L-series was
unmeasured and re-run twenty minutes of work, which is exactly what the checkpoint told them
to do.

Reconciled now. Each entry carries a `firing_rate` block with the measured per-product
numbers and a `verdict_route_measured` block with the route the measurement actually
supports. **The registered `verdict_route` is deliberately left as written** — it records what
was *assumed* before measuring, and "ASSUMED CLOSED" sitting next to "measured closed at 100%
overlap" is worth more than either alone.

**The reconciliation was text surgery, not a YAML round-trip.** `hypotheses.yaml` carries 857
comment lines and the comments are the record; `yaml.safe_dump` would have silently deleted
every one of them.

### The checkpoint outlived its own instruction

`reports/CHECKPOINT.md` led with "the one thing that must be re-run" and named the batch that
had already completed three days later. It stood that way for four days.

**A checkpoint that survives the work it describes is its own failure mode**, and it is worse
than a stale report because a checkpoint is written to be obeyed. It is updated rather than
deleted, with the fact that it went stale left in it.

### The placebo scale was daily ATR for every level type, and `verify()` had already said so

Placebo offsets were `±[0.3, 1.5] × ATR(20)` where ATR(20) is **daily** true range, at
`definitions.py:62`, for a one-minute fair-value gap and a prior-month extreme alike.

Measured consequence, read back out of git rather than recalled: **53 of 55 level
types unmatched.** Placebo distances ran **1.05× to 62.7×** the real ones and touch
ratios **0.07× to 0.94×**, against a ±25% tolerance. Every real-minus-placebo comparison on those types would have measured **exposure, not
reaction** — which is the exact failure the placebo exists to prevent.

**The guard was not missing. It fired and nobody read it.** `verify()` computed the mismatch,
`render_reports` wrote "FAIL — 53 of 55" at the top of `placebo_match.md`, and it was
committed in that state. Nothing consumed the verdict because **no Stage 1 ever ran**, so
nothing was ever blocked by it. A control that fails loudly into an empty room is
indistinguishable from one that passes.

### The push was insurance, and the insurance had a hole in it

**`.gitignore` line 9 read `data/`, unanchored, so it matched any directory named `data` at
any depth — including `src/futuresres/data/`, the entire data layer.** Five modules and 1,975
lines: `batch_ftp`, `parse`, `splice`, `roll`, `validate`. **Zero of them had ever been
committed, in any commit this repository ever made.**

That is the layer that builds every series the calibrations rest on. The detection floors the
R-series quotes as settled fact — 19,722 and the rest — are computed from output this package
produces, and the package existed on exactly one disk.

**So the remote created above was insurance with a hole in the one layer that mattered most.**
Pushing 28 commits looked like the fix and was not; a clean clone got the analysis and none of
the machinery that generates its inputs. The correction is a leading slash: `/data/` anchors
the rule to the repository root.

**This exact bug was already found and fixed in `r-series-research`**, whose `.gitignore`
carries `/data/` with a comment explaining that the unanchored form "silently ignored
`src/rseries/data/` — the entire data-layer source package". **The fix never propagated back
to the repository it was learned from.** A lesson recorded in the derivative project and not
in the original is a lesson half-learned.

**Measured consequence, not estimated.** A clean clone was made and its suite run with the
editable install neutralised, because an editable install points back at the working tree and
would have hidden the whole thing — the first attempt at this measurement did exactly that and
had to be discarded.

| | tests collected |
|---|---|
| working tree, data layer present | **370** |
| clean clone | **300**, plus 3 collection errors |

**The 70-test gap is the finding, not the number.** It splits two ways:

- **65 tests** in `test_batch_ftp.py`, `test_parse_and_splice.py` and `test_roll.py` — committed
  files importing a package that was never committed. In a clean checkout they do not fail,
  they fail to *collect*, which is a different and quieter thing.
- **5 tests** in `test_signal_module_boundary.py`, which is parametrized over the modules it
  finds by globbing. **The guard that enforces module discipline was silently checking five
  fewer modules for everyone but this machine**, and an under-parametrized guard stays green
  while covering less. That file contains a test named
  `an empty parametrize is a silent skip, and a silent skip stays green forever` — the same
  failure mode it warns about, one directory over.

**One module is simply gone.** `src/futuresres/data/__pycache__/dbn_load.cpython-311.pyc` and
`tests/__pycache__/test_dbn_load.*.pyc` are on disk with no corresponding source, no live
references, and **no git history to recover them from**, because the directory was never
tracked. Whatever `dbn_load` was, it was deleted and the deletion left no record. That is the
cost of the gap stated as concretely as it can be stated.

**No credentials were exposed by committing it.** FTP credentials are read from
`DATABENTO_FTP_USER` and `DATABENTO_FTP_PASSWORD` at run time; the diff carries no literal.
`/data/` still excludes the 548 MB of extracts, and `.env` is still ignored.

### Why it did not propagate — and the premise that it had been settled is wrong

It is tempting to say this correction was already settled for L01, L06 and L08 and merely
failed to reach the placebo. **That is not what happened, and the record should not say it
did.**

`CHECKPOINT.md` states the opposite in as many words: *"`d ATR` does not say which ATR, and
that decides whether L01, L06 and L08 are testable at all"*, filed as an **F05-class
specification gap** and explicitly **recorded rather than resolved**, because *"choosing the
period that makes L01 look schedulable would be choosing a parameter to get a result."* It is
still open. It is item 2 on the resume list.

So the honest answer to why it did not propagate is: **there was nothing to propagate.** But
the near-miss is the instructive part, and it has a shape this project has seen before:

- The ambiguity was filed under **"which hypotheses are testable"**, because that is where it
  bit first — it changes L01's firing rate.
- The placebo uses **the same ATR for an entirely different purpose**, and lives under **"is
  the control valid"**.
- Those are different sections of the same document, and **the shared dependency was invisible
  from either one.** Nobody asked whether the scale ambiguity that decides an event count also
  decides whether the control is matched.

**The two questions are not equally open, and that asymmetry is what licenses fixing one and
not the other.** For L01, the ATR choice sets the firing rate, so picking it to taste is
picking a parameter to get a result, and it stays frozen. For the placebo, there is an
**external, pre-registered criterion** — the matching test, with its ±25% tolerances fixed
before any of this — and satisfying a criterion that was registered in advance is not the same
act as choosing a number until an effect appears. `Grid.atr()` now carries a comment saying
precisely this, so the next reader does not "fix" L01 by analogy.

### The correction, and it is not enough

**The scale is now the intraday range over each level's own validity window**
(`definitions.window_scale`). The reasoning: `touches` tests every level against the remainder
of *its own row*, so a prior-month level and a one-minute gap are both live for the rest of a
single trading day and no longer. The question a placebo must match is *how far price travels
while this level is reachable*, and that is the range over `ROW_MINUTES - valid_from` minutes,
interpolated log-log across ten measured horizons from one minute to the full day.

At the full-day horizon it reproduces the mean session high-low range exactly, which sits
within about 1% of daily true range - the two differ only by the overnight gap term. That is
why the level types that already matched under the daily scale are essentially undisturbed by
the correction: for a level live all day, the new scale and the old one are nearly the same
number. The correction bites precisely where it should, on levels whose window is short.

**The offset bounds were not touched.** 0.3 and 1.5 are as registered. Only the unit they
multiply changed. Sweeping the bounds until matching passed would be fitting the null to the
test.

**Re-measured result: 3 of 55 level types match. It still fails.**

| level types that match | product |
|---|---|
| `prior_month` | MGC |
| `prior_week` | MGC |
| `sess_US` | MGC |

Distance ratios now span **1.05× to 32.77×** and touch ratios **0.16× to
1.25×** against a ±25% tolerance. Better, and not close enough.

### The residual is geometric, not a matter of scale — and fixing it is a decision not taken

Measured across three candidate scale rules, on both products, the failure does not move the
way a scale error should:

| scale rule | matched, MGC | matched, MNQ |
|---|---|---|
| daily ATR(20) — the old one | 2/28 | 0/28 |
| intraday range over the validity window — the new one | 3/28 | 0/28 |
| the real levels' own median creation distance | 2/28 | 2/28 |

The third rule sets the offset so its *magnitude* equals the real distance, and it still fails
— at a distance ratio of **1.32–1.54 on every single level type and both products**. That
stability is the diagnosis. The placebo is built as `level + offset × scale`, but the level is
**already displaced** from the reference price by the real distance `d`. Adding a signed offset
of magnitude ≈ `d` gives a placebo at either ≈ `2d` or ≈ `0`, whose median is ≈ `1.4d`. **No
choice of scale removes a bias that comes from the construction rather than the size.**

The fix is to make the placebo's distance distribution match **by construction**: solve for the
multiplier that equalises the medians, using geometry alone — level, reference price and the
hash offsets — with **no touch data entering the calibration**, so the touch-rate half of the
criterion stays an independent test of whether the control is comparably reachable.

**That change was not made.** It alters what the control *is*, from "the real level, displaced"
to "an arbitrary level at a matched distance". That is a methodological decision about the
null, not a bug fix, and it belongs to whoever owns the specification. `CHECKPOINT.md` item 3
carries it.

### Decisions taken rather than resolved silently

1. **The daily-ATR scale for L01, L06 and L08's `d ATR` precondition is UNCHANGED**, and
   `Grid.atr()` now says why in a comment. Changing it would change those hypotheses' firing
   rates. The placebo scale was changed because its criterion is external and pre-registered.
2. **The registry keeps its registered `verdict_route` alongside the measured one.** Nine of
   ten aggregate routes were assumed closed and measured closed at 97–100% overlap; the
   assumption was right, and a record that shows it was *checked* is worth more than one that
   quietly agrees.
3. **Statuses use only the existing vocabulary.** 5 entries move to
   `blocked_insufficient_events` (L01, L05, L06, L08, L09); 5 stay `untested` (L02, L03, L04, L07, L10). Four of those stay
   untested because their best cell clears the 180-minute floor on at least one instrument
   and they are genuinely untested rather than blocked; only **L07** clears it on *both*.
   Inventing a status like "measured but unrunnable" would have been easier and would have
   made the registry unqueryable.
4. **`L10` stays `untested` although its event count is far below the floor, because it is a
   CONTROL and a control is never `blocked_insufficient_events`.** The first pass of this
   reconciliation applied the event-count rule uniformly and blocked it — which would have
   left the entire L-series with **no live control at all**, since L10 is what validates the
   placebo machinery every L-series comparison depends on.
   `tests/test_registry_consistency.py` caught it by asserting the live control set is
   exactly `{F14, L10}`. **The registry's own tests found a modelling error in the code
   written to update the registry**, which is the argument for having them.
5. **A blocked entry surrenders its `test_order` but keeps `registered_test_order`.** Nulling
   the live order without claiming the slot would erase that L01 was scheduled *tenth* and
   would leave an unexplained gap in the ordering. That is the same handling the retired
   F-series entries already use, and a test enforces it.
6. **No Stage 1 was run and no trial was spent.** N stays at **576** and SR\* at **0.1334**.
7. **`L10`'s firing rate changes with the placebo scale** and no other hypothesis's does — L10
   *is* the placebo control, so its condition depends on the offset. The new numbers are in
   `level_rates.md`; the other nine are unchanged by the correction, as they must be.

### The state this leaves the L-series in

The three measurements cross, and the crossing is the finding. **The correction moved it
without breaking it**, which is worth stating precisely, because the naive reading of "3 of 55
now match" is that a route opened. It did not.

The three matched level types are `prior_week`/MGC, `prior_month`/MGC — both **L09** — and
`sess_US`/MGC, which is **L04**. Set against their own event counts:

| matched level type | hypothesis | cells' firings | 180m floor | short by |
|---|---|---|---|---|
| `prior_week`, `prior_month` (MGC) | L09 | 46–364 | 2,862 | 8–62× |
| `sess_US` (MGC) | L04, US cells only | 168–399 | 2,862 | 7–17× |

**L04 is the sharp case, because the crossing now happens inside one hypothesis.** Its best
cell fires 5,130 times, comfortably clear of the floor — but that is an **Asia**-session cell,
and `sess_Asia`'s placebo fails at a distance ratio of 3.69 and a touch ratio of 0.40. The
cells whose control *is* valid are the **US**-session ones, and they fire 168 to 399 times.
Within a single registered hypothesis, on a single instrument: **the cells with the events have
no control, and the cells with the control have no events.**

The rest is unchanged:

- **L07** remains the only hypothesis clearing the floor on **both** instruments, and all six
  of its FVG level types still fail matching — at distance ratios of 10.6× to 32.8×, the worst
  in the study.
- **L10** remains the only open aggregate route, and it is the placebo control, which spends no
  trials.

**No L-series hypothesis has a resolvable sample and a valid placebo in the same cells.** That
is not a result about markets and must not be written up as one. It is a statement about what
this catalog can currently ask.

---

## 37. The null redefined: an arbitrary region, not a displaced level

**This is a change to what the L-series compares against, not a repair of how it is sized.**
It was taken as a specification decision after §36 measured that the previous null could not
be matched at any scale.

### What changed

| | old | new |
|---|---|---|
| a placebo is | the real level, displaced by a hashed offset | an **arbitrary region** at a matched distance |
| distance match | attempted by choosing a scale | **by construction** |
| touch match | attempted | **left free and measured** |

```
scale_i    = intraday range over level i's own validity window
u          = { |real_level - reference| / scale }   over all levels of this type
placebo_i  = reference_i  ±  hash(date, level_type, index) drawn from u  ×  scale_i
```

### Why — the hypotheses never asked about displacement

**L07 asks whether fair-value-gap zones react differently from ordinary regions price reaches
equally often.** That is the claim. Displacing a real level was a *method* for producing such
a region, and a reasonable one. **It was never the null.** Treating the method as the
definition is what let a defect in the method masquerade as a property of the comparison.

**And the method had a defect no parameter removes.** A real level already sits at distance
`d` from the reference price, so adding a signed offset of magnitude `~d` puts the placebo at
`~2d` or `~0`, median `~1.4d`. Measured, that ratio sat at **1.32-1.54 across every level
type, both products, and three different scale rules**. Geometric, not dimensional.

The §36 scale correction — daily ATR to the intraday validity window — is **retained**. It is
the right unit and it is what the new construction normalises by. It moved matching from 2 of
55 to 3 of 55 and stopped, which is precisely what identified the residual as structural.

### What it costs, stated plainly

**A matched-distance arbitrary region is a WEAKER control than a displaced real level.**

A displaced level inherits the history of the level it came from: same session, same approach,
the same sequence of prices that brought the market to that neighbourhood. Comparing against
it holds constant **how price arrived**. An arbitrary region does not. It equalises where the
region sits and how often price reaches it, and nothing else.

**So a surviving real-minus-placebo difference now carries one more competing explanation:**
that price *arrives* at real levels differently, rather than *reacting* at them differently.
The new control cannot separate those. A result under it means "reacts differently from an
equally-reachable arbitrary region", which is a weaker claim than "reacts differently given
the same approach", and it should be written up in those words.

**The trade was accepted knowingly.** The stronger control was not available: its geometry
guaranteed a 1.4x distance mismatch, so it was never delivering the comparison it appeared to.
**A weaker control that is matched beats a stronger one that is not**, because an unmatched
control measures exposure and reports it as reaction. What was lost is real; what was gained
is that the comparison exists at all.

### Re-measured: does it pass?

**48 of 55 level types match, against 3 of 55 under the displaced null.**

| | displaced null | arbitrary region |
|---|---|---|
| matched | 3/55 | **48/55** |
| distance ratio | 1.05x - 32.8x | **0.74x - 1.10x** |
| touch ratio | 0.16x - 1.25x | **0.74x - 1.33x** |

Tolerance is +/-25% on both. **Touch was not fitted** - only distance is designed - so the
touch column is an independent check that the regions are comparably reachable, and it is the
stronger of the two results.

### Which hypotheses now have BOTH a matched control and the events to use it

**The test applied here is the strict one**, because the loose version of this table is how
§36 got a claim wrong. It is not enough that a hypothesis has *some* matched level type and
*some* cell above the floor. **The matched level type has to be the one the qualifying cell
actually uses.** Under the displaced null, L04's best cell was an Asia-session cell while its
only matched type was the US-session one — a hypothesis that looked ready and was not.

Best cell **whose own level type is matched**, per hypothesis and product:

| hypothesis | product | level type carrying it | firings | 180m floor | |
|---|---|---|---|---|---|
| **L02** | MGC | `or15` | 5,724 | 2,862 | **2.0× clear** |
| **L03** | MGC | `prior_rth` | 4,674 | 2,862 | **1.6× clear** |
| **L04** | MGC | `sess_Asia` | 5,130 | 2,862 | **1.8× clear** |
| **L07** | MGC | `fvg_w2_1m` | 655,490 | 2,862 | **229× clear** |
| **L07** | MNQ | `fvg_w2_1m` | 535,428 | 5,884 | **91× clear** |

**Five routes are open that had none before.** L04's Asia cells now carry a matched control in
their own right, so the trap that caught §36 does not apply — it was checked rather than
assumed.

Matched control, still short on events:

| hypothesis | product | level types matched | best cell | 180m floor | |
|---|---|---|---|---|---|
| L01 | MGC | 3/3 | 211 | 2,862 | 14x short |
| L01 | MNQ | 3/3 | 237 | 5,884 | 25x short |
| L02 | MNQ | 3/3 | 5,178 | 5,884 | 1x short |
| L03 | MNQ | 2/2 | 3,762 | 5,884 | 2x short |
| L04 | MNQ | 3/3 | 5,442 | 5,884 | 1x short |
| L05 | MNQ | 1/1 | 4,669 | 5,884 | 1x short |
| L08 | MGC | 6/6 | 698 | 2,862 | 4x short |
| L08 | MNQ | 5/6 | 705 | 5,884 | 8x short |
| L09 | MGC | 2/2 | 364 | 2,862 | 8x short |
| L09 | MNQ | 1/2 | 446 | 5,884 | 13x short |
| L10 | MGC | 3/3 | 91 | 2,862 | 31x short |
| L10 | MNQ | 3/3 | 40 | 5,884 | 147x short |

### L06 has no valid control and cannot get one

`open_CME`, `open_RTH` sit **exactly at** the reference price, so their distance distribution is identically
zero. There is no distance to match and no arbitrary region is comparable. `verify` reports
this as its own failure kind rather than as a mismatch, because **no scale and no construction
fixes it** - it is a property of the level definition. L06 is not blocked on measurement or on
tuning; the comparison its registration asks for does not exist.

### Still unmatched, and these must not run Stage 1

- `ema20_15m` / MNQ
- `prior_month` / MNQ
- `sess_US` / MGC

### Decisions taken rather than resolved silently

1. **Touch rate is deliberately NOT fitted.** Fitting it would erase part of the effect under
   test: a level type that genuinely attracts price would have its placebo pulled closer to
   equalise touch, breaking the distance match in the process. The construction takes no touch
   data as input and a test pins that by signature.
2. **Distances are pooled in volatility-normalised units**, then rescaled by the receiving
   level's own scale, so a quiet session does not inherit a busy session's spread.
3. **The old `make_placebo` is kept, not deleted.** A test pins that it still produces the
   ~1.4x bias, so the construction cannot be reintroduced by accident and the reasoning stays
   findable.
4. **The degenerate case fails loudly with its own message** rather than silently producing a
   placebo equal to the real level, which is what a naive implementation would emit.
5. **No Stage 1 was run and no trial was spent.** N stays at **576**, SR\* at **0.1334**.

---

## 38. L07 ran. Every cell separates, and that was never the question

108 cells, both instruments, real fair-value-gap zones against matched placebo regions.
Trials were logged before the run; N went 576 -> 684 and SR\* 0.1335 -> 0.1357.

**The market-state comparison leads this entry rather than the effect size**, because it
decides what the effect size is allowed to mean.

### First: what the market was doing when each entry fired

`decisions.md` 37 recorded that the redefined null is a **weaker** control - it equalises
where a region sits and how often price reaches it, and **not how price arrived**. A
fair-value gap forms by definition right after a fast directional move, so the obvious
competing explanation was that real entries sit downstream of volatility spikes while their
placebos do not. That would widen the difference with gap width without any difference in
reaction at the zone, and L07's result does widen with gap width.

**Measured, and the volatility story runs the other way:**

| product | prior 30m vol, real/placebo | prior 60m vol | distance from open | entry time, real minus placebo |
|---|---|---|---|---|
| MGC | 0.96x | 0.97x | 0.98x | **-16 min** (-43 to -9) |
| MNQ | 0.92x | 0.93x | 0.96x | **-47 min** (-81 to -11) |

Real entries follow **less** prior volatility than their placebos, by 4-11%, not more. The
mechanism is intelligible once seen: a placebo sits at a hash-drawn distance on either side,
so price must travel to reach it, while a real zone sits adjacent to the bars that created
it. Distance from session open matches within 4%. **The confound this measurement was built
to catch is not there.**

**But a different one is, and it is material.** Real entries fire a median of 16 minutes
earlier than their placebos on MGC and 47 minutes earlier on MNQ, ranging to 81. Real and
placebo entries are not sampling the same part of the session, and both volatility and drift
vary across it. **This design cannot separate that**, exactly as 37 said it could not separate
arrival effects generally. The specific story changed; the structural limitation did not.

Worth recording for anyone reading the numbers below: median entry times sit between 05:35
and 09:50 ET. **These are mostly overnight trades, not RTH ones.**

### Second: the statistic, which carries almost no information

| | MGC | MNQ |
|---|---|---|
| tests | 54 | 54 |
| nominal separations | **54** | **54** |
| expected by chance at alpha=0.05 | 2.7 | 2.7 |
| BH survivors at FDR 0.05 | **54** | **54** |

**108 of 108. Every cell, both instruments, all three horizons.** This was predicted in
advance and is not a finding. At 24,788 to 863,490 paired events a separation is assured for
any effect that is not exactly zero, so the p-value here measures sample size, not substance.
The pre-registered expectation was that L07's raw fill statistic would look impressive and be
equally impressive for placebos; what the design actually delivers is that **the difference**
is impressive too, and the question is only how large it is and what it can be attributed to.

### Third: the economics, which is the deciding number

| | MGC | MNQ |
|---|---|---|
| difference range | -5.008 to -1.176 bps | -4.962 to -1.191 bps |
| every cell negative | yes | yes |
| cost floor, round trip | 0.65 bps | 0.48 bps |
| absolute difference as a multiple of cost | **1.8x - 7.7x** | **2.5x - 10.3x** |

**The difference is large relative to cost and it is negative everywhere.** Under the
registered direction - counter to the move that created the gap - entering at a real
fair-value gap is worse than entering at a matched arbitrary region, by several times the
round-trip cost, on both instruments, at every horizon and every parameter setting tested.

### The decomposition is sharper than the difference

| product | horizon | real, mean bps | placebo, mean bps | difference |
|---|---|---|---|---|
| MGC | 60 | -1.069 | +0.915 | -1.984 |
| MGC | 120 | -1.493 | +1.322 | -2.814 |
| MGC | 180 | -1.706 | +1.565 | -3.271 |
| MNQ | 60 | -1.008 | +1.149 | -2.157 |
| MNQ | 120 | -1.249 | +1.669 | -2.918 |
| MNQ | 180 | -1.427 | +1.945 | -3.373 |

**It is not that the real zone is less good. The real zone loses and the placebo wins.** The
same directional rule, applied at an arbitrary region at a matched distance, is positive;
applied at a fair-value gap, it is negative. Conditioning on the region being a real gap
**reverses the sign** of the trade.

And the effect scales with the thing the mechanism says should matter most:

| product | gap width | mean difference at H=180 |
|---|---|---|
| MGC | w=2 | -2.51 bps |
| MGC | w=4 | -3.06 bps |
| MGC | w=8 | -4.25 bps |
| MNQ | w=2 | -2.68 bps |
| MNQ | w=4 | -3.31 bps |
| MNQ | w=8 | -4.12 bps |

### What this establishes, and what it does not

**Established, subject to the timing confound above:** the registered L07 trade is not
merely unprofitable, it is systematically worse than an equally-reachable arbitrary region.
The hypothesis as registered - that price returns to fill the zone because unfilled interest
sits there, so riding the fill is profitable - is refuted in the direction it was stated.
L07's own registry entry said in writing that it did not believe its counterparty existed.
That scepticism is now measured rather than asserted.

**Not established, and these are not small:**

1. **That the difference is a reaction at the zone.** Real and placebo entries differ
   systematically in time of day by up to 81 minutes. The design cannot separate a difference
   in reaction from a difference in when the trade happens.
2. **That the mirror trade works.** See below. This is the important one.
3. **Anything about direction-mix asymmetry.** Whether real and placebo entries fire on
   bullish versus bearish zones in the same proportion was not measured. If they do not, the
   underlying drift could contribute to the sign. Recorded as an open competing explanation
   rather than dismissed.

### The mirror hypothesis is NOT registered, and will not be on this evidence

The obvious reading is that the opposite direction would be positive by the same margin. **It
is not being registered, for three reasons, and none of them is trial budget.**

**The sign came from looking at this data.** Registering the opposite direction now is
selecting a hypothesis by its result. Spending trials on it does not repair that - the
multiple-testing budget prices the searches you declare, not the ones the data suggested after
the fact.

**It has no mechanism.** The registered story is unfilled orders finally getting filled, which
predicts *reaction at the zone* - price arriving and being absorbed - not *continuation
through it*. Inverting the trade keeps the arithmetic and discards the reason, which is the
thing this catalog requires an entry to state before it may be tested at all.

**And the confounds above apply to the mirror exactly as they apply to the original.** A
timing difference that could manufacture a negative difference could manufacture a positive
one just as easily.

**If it is worth testing, it must be frozen and evaluated on data that did not generate it:**
pre-2019 NQ history if L07 did not consume it, or forward. That is a different registration
with its own mechanism section, and it is not this one.

### Decisions taken rather than resolved silently

1. **`l07_cells.json` was committed before any analysis was written.** The 72 cells at H=60
   and H=120 had no committed record anywhere, and the H=180 cells survived only as printed
   console output from a run that crashed after logging its trials.
2. **All 36 H=180 cells were verified to reproduce the earlier run exactly**, events and
   difference to four decimal places, before the reused trials were accepted as describing
   it. Had they not reproduced, this would have counted as a fresh look and spent another 108.
3. **Nothing was excluded.** All six fair-value-gap level types match their placebo on both
   instruments, 12 of 12, checked against `placebo_match.md` before use rather than assumed.
   The exclusion path exists, is tested, and simply did not fire.
4. **The detection floors in `calibration.md` are not the applicable bar here** and are not
   used as one. Those figures were measured at a particular sample size - 8,190 independent
   observations at the smallest - and L07 carries between 24,788 and 863,490 paired events, so
   the floor that applies is far lower than the tabulated one. The cost floor is the bar this
   entry uses, and it is the bar the result is reported against.
5. **The market-state comparison spent no trial.** It searches nothing and cannot produce a
   candidate, so it logged to `measurements.jsonl` as m00115 on the same reasoning that keeps
   firing rates out of N.

## 39. The gitignore fix exposed a second missing dependency; L11 registered unmeasured

Two unrelated things, both consequences of the same repair.

### The 372/360/12 claim is confirmed, and it needs one package nobody declared

Verified on a clean checkout of `9fd2ae5`: **360 passed, 12 skipped, 372 collected.** The 12
skips are `test_roll.py`'s "batch not parsed into data/parquet", which is by design.

**But it does not reproduce from `pip install -e ".[dev]"` alone.** The first run gave 2
collection errors:

```
src/futuresres/data/parse.py:69: in <module>
    import zstandard
E   ModuleNotFoundError: No module named 'zstandard'
```

`zstandard` was not in `pyproject.toml`. Installing it turns 2 errors and 360 tests into
exactly the claimed 372/360/12, which is what pins the diagnosis: the undeclared dependency
was the whole gap.

**This is the gitignore bug's shadow, not a separate oversight.** For as long as the
unanchored `data/` rule excluded `src/futuresres/data/` from every commit (36), no clean
clone could import the package - so no clean clone could ever discover what it needed, and
the requirement lived only in the working environment of the one machine that had the files.
The dependency was untestable for the same reason the code was invisible. Anchoring the rule
made the package importable, and the first thing importing it revealed was that it could not
be imported.

**Fixed by declaring `zstandard>=0.22`**, with a comment saying why it was missing. The lesson
is not "check dependencies" - it is that **an untracked module has untracked requirements**,
and restoring one does not restore the other. Anything else that package needs at runtime and
that happens to be installed on the PC is still unverified here; the tests exercise the import
path, which is the part that can be checked from a clean clone.

### L11 registered - Bollinger band breakout, Stage 0 only

Registered 2026-09-10. **`schedulable: false`, no firing rate, no placebo match, no Stage 1,
no trial. N stays at 684 and SR\* at 0.1357.**

**The mechanism is weak and the entry says so in the same terms L08 does.** No institution
executes against a 20-period 2-sigma band. The only story is self-fulfilling order clustering
at default platform settings - which is *the same premise that disqualified F11 as a control*,
because it is a claim about the market rather than a structural fact about it. Testing it is
legitimate; the grade reflects the prior, D+.

**Period 20 and k 2.0 are frozen a priori and the freeze is load-bearing.** The mechanism is
that *these particular numbers* are the watched ones. A period chosen because it scored better
would carry no self-fulfilling story at all - it would be an ordinary volatility-breakout rule
with a fitted lookback, which is a different hypothesis with no mechanism section. L08's
condition already names the tell in these words: *"if 47 works and 50 does not, that is the
tell."* The level type's own name records the settings (`bb20k2_60m_upper`), so a swept
variant appearing in a later report is visible as one.

**Upper and lower are separate level types.** Price is not symmetrically placed between the
bands, so their distance distributions differ; one shared type would let a placebo drawn for
the upper stand in for the lower and quietly break the matching.

**Provenance recorded, and it carries no weight.** The idea came from a third-party claim with
**no accessible trial count, no cost assumption and no control**. There is no way to know how
many settings were tried before that one was published, whether the reported edge survives a
spread, or what it was compared against. An unaudited claim is a reason to ask the question
and is not evidence for the answer. It is written into the entry because where an idea came
from belongs in the record even when the answer is "nowhere usable" - a later reader should
not assume this arrived with support it never had.

**The two required measurements were NOT taken, and that is a machine limitation.**
`data/continuous/` does not exist on this laptop, so the firing rate and the placebo match
cannot be counted here. What was done instead:

- `bollinger_levels` is written and **unit-tested on synthetic input** - band arithmetic
  against an independently computed mean and population sigma, zero-width bands on a
  motionless market, upper never below lower, warm-up NaN rather than back-filled, and the
  two level types distinct. None of that needs the real series.
- The L11 block in `reporting/level_rates.py` is written and committed, so the measurement is
  one run away on a machine holding the data.
- `firing_rate.measured: false` and `placebo_match.measured: false` are recorded **as false
  rather than left absent**, which is the distinction 36 was about: an entry with no
  `firing_rate` block reads as unmeasured-and-unnoticed, one with an explicit false reads as
  unmeasured-and-known.

**No rate was declared.** Declaring an expected one would be precisely the substitution the
F05 history warns about, where an unmeasured rate fell through to the most generous
assumption available exactly where least was known.

**The placebo match is genuinely open, not a formality.** Bands widen with volatility, so a
boundary's distance from price is not stationary the way a prior-week extreme's is. That is
the kind of thing the +/-25% distance and touch criteria exist to catch, and an unmatched
level type must not run Stage 1 (37).

### Decisions taken rather than resolved silently

1. **`zstandard` declared rather than the import made optional.** `parse.py` cannot read a
   `.zst` extract without it; a lazy import would turn a missing dependency into a runtime
   failure deep in a batch parse instead of an import-time one.
2. **L11 gets `registered_test_order: 20` and `test_order: null`**, the same handling every
   unscheduled entry uses, so the ordering has no unexplained gap.
3. **The aggregate route is assumed closed across `kbars`, and NOT assumed either way for
   upper against lower.** kbars nests - a break confirmed at 3 bars was confirmed at 1 - so
   those cells share entries almost entirely. Whether the two sides are disjoint is a
   measurement and is left as one.
4. **The mirror of L07 is still not registered**, and nothing here changes that. 38 gives the
   reasons; none of them was trial budget.

### The registry's own tests caught four defects in the registration

Written up because 36 decision 4 made the same point and it held again: the entry was wrong
in four ways and `test_registry_consistency.py` found all of them before the commit.

1. **`test_order: null` on an `untested` entry.** The rule is that untested non-control
   entries carry a live order - an entry outside the ordering is invisible to it. L11 is
   `untested` rather than `blocked_insufficient_events`, because it is short a *measurement*,
   not short *events*; nothing about the market is being claimed. So it needs a live order.
2. **`registered_test_order: 20` left an unexplained gap at 19.** Orders 1-18 were taken.
   Corrected to 19. The gap rule exists so that a missing number always means a resolved
   hypothesis rather than a typo, and it worked exactly that way here.
3. **No catalog section.** `LEVEL_HYPOTHESES.md` had no `## L11` heading, so registry and
   catalog disagreed in both directions - two separate tests, one for each direction, which
   is why the disagreement could not be half-fixed.
4. Fixed **in the entry and the catalog, never by loosening a test** - the same handling 36
   used for the five registry defects its tests caught then.

**None of these would have been visible by reading the entry.** They are relational
properties - between an entry and the ordering, and between two documents - and that is the
category a human review reliably misses.

### Open, and recorded rather than closed

- **L07 direction-mix asymmetry.** Whether real and placebo entries fire on bullish versus
  bearish zones in the same proportion is still unmeasured. If they do not, drift contributes
  to the sign of 38's result. Carried from 38 unchanged.
- **The `d ATR` reference period for L01/L06/L08** remains frozen. It is a specification
  change, not a bug fix, and picking the period that makes L01 schedulable would be picking a
  parameter to get a result.


## 40. L11 withdrawn: what was registered was never a breakout test

Registered 2026-09-10, withdrawn 2026-09-11. **Never run at Stage 1, no trial ever spent.
N stays 684 and SR\* stays 0.1357.** Nothing already closed is disturbed.

### The defect, measured rather than inferred

The suspicion came from a summary statistic - every one of L11's six cells reported an
identical firing count, and disjointness reported 100% overlap. That is weak evidence and
two different things could produce it, so it was checked against the code path and the
arrays rather than read off the counts.

`kbars` IS wired into the firing condition - `level_rates.py` called
`D.confirmed_break(g, lv, kb, product)`, and `confirmed_break` uses `k_bars` to decide which
bar triggers. So this was never the benign case where a rate counts level-touches and the
parameter discriminates later.

Measured on MGC, all 4,004 levels, both boundaries:

```
kbars=1: fired 4004, entry minute min=991  max=991     <- ZERO VARIANCE
kbars=2: fired 4004, minute 992..995
kbars=3: fired 4004, minute 993..1001
  kb1 vs kb2: identical minutes 0 of 4004
```

**991 is exactly `valid_from`** (`RTH_OPEN + 60 + 1`). The condition fires on the FIRST BAR
IT EXAMINES, for every level, every session.

**The cause.** `confirmed_break` triggers on a run beyond the level in EITHER direction
(`run_u >= k_bars or run_d >= k_bars`). Price at 10:31 is never sitting exactly on a
Bollinger band - it is above it or below it - so one of the two runs is satisfied at j=0 and
stays satisfied. The registered condition reduces to **"sample price at 10:31 and trade
whichever side of the band it is already on"**, once per session.

Three consequences follow, and the third is the one that matters:

1. **`kbars` is an offset, not a selection.** It moves entry by exactly `k-1` bars. Every
   level fires under every setting; no cell selects a different population.
2. **`upper` and `lower` fire at identical `(row, minute)`.** That is the 100% disjointness
   figure - not `kbars` cells colliding with each other, whose minutes never coincide, but
   the two sides being the same event with opposite direction labels. The summary statistic
   was right and my first reading of it was wrong.
3. **The six-cell grid is one event per session wearing six labels.**

### Withdrawn, not restated

Removing `kbars`, adding a price-inside-band precondition and separating the two directions
produces a **different condition, not a narrowed one**. The honest record is a withdrawal
and a fresh registration if one is ever wanted - not an entry quietly repaired until it
works. The entry carries `status: excluded`, the vocabulary F12 and F13 already use.

**The trial cost falling is a CONSEQUENCE of finding the defect and was not a reason for the
change.** Recording that explicitly because the reverse - trimming a grid and discovering a
justification afterwards - is the failure this catalogue exists to prevent.

### The measurements do NOT carry over, and they are labelled so

The degenerate run produced a firing rate (4,004/cell MGC, 4,123 MNQ) and a placebo match
(all four level types inside tolerance, distance ratios 0.90-1.06). **Both are properties of
the defective condition and neither is a property of L11.** A real breakout condition selects
a different and far smaller population, so both would have to be measured again from nothing.
They are kept in the registry under `degenerate_measurements` with that warning attached,
because deleting them would hide what was actually run.

The generated report rows were REVERTED rather than committed, so `level_rates.md`,
`placebo_match.md`, `disjointness.md` and `level_rates.json` carry no L11 rows. The L11
measurement block is removed from `level_rates.py` so it cannot regenerate them.
`D.bollinger_levels` is kept and still unit-tested - the band arithmetic is correct and a
corrected condition would use it - but no registered hypothesis consumes it.

### The placebo prediction is OUTSTANDING, not wrong

Before measuring, this project predicted a band placebo would probably FAIL to match, because
bands widen with volatility so distance-from-price is not stationary the way a prior-week
extreme's is. All four matched, and it is tempting to record the prediction as refuted.

**It was not tested.** The entry population was every session at a fixed minute, so
distance-from-price was effectively fixed by construction - the very non-stationarity the
prediction is about never entered the measurement. Whether a band placebo matches when the
entry population is selected by an ACTUAL breakout is unknown and untested.

Recorded as outstanding. A prediction marked wrong on evidence that could not bear on it is
worse than one left open.

### What a corrected condition would need - WRITTEN UP, NOT REGISTERED

Not a registration. A statement of what would have to be specified, so the decision to
register or drop is made on a clear description rather than re-derived later.

1. **An inside-band precondition.** The break must be from inside to outside. Requires price
   to have been within the band for some qualifying period before the trigger, so "beyond the
   band" marks a transition rather than a standing state. Without it there is no event.
2. **Directional separation.** `confirmed_break` fires on either direction against a single
   level, which is what collapsed `upper` and `lower` onto the same instant. The upper band
   needs an UPWARD break only and the lower band a DOWNWARD break only - a different call,
   not a different parameter.
3. **Counting a level once rather than twice.** With both boundaries live each session, a
   session can produce an upper event and a lower event. Whether those are one hypothesis or
   two, and whether a session that breaks both is counted once or twice, must be settled
   BEFORE measuring - it changes the event count and therefore the detection floor.
4. **A firing rate and placebo match measured fresh**, inheriting nothing from above.
5. **A mechanism section that survives the correction.** The self-fulfilling story was never
   reached. It is not disproved; it was not examined.

Whether that is worth a registration is not decided here.

### L10 is the only open route in the L-series

Worth recording in the closeout rather than left in a report. Maximum pairwise overlap of
firing minutes, per hypothesis:

| | overlap | aggregate route |
|---|---|---|
| **L10** (the placebo control) | **1% MGC / 5% MNQ** | **OPEN (disjoint)** |
| L01-L09, L11 | 97% - 100% | CLOSED (overlapping) |

**Every substantive hypothesis in the catalogue has a closed aggregate route.** The only
disjoint one is the control, which spends no trials and reaches no verdict. Pooling a
hypothesis's cells to buy sample size is unavailable everywhere it would have helped - the
cells re-enter on the same touches. That is a property of level-based hypotheses as a class,
not of any one entry, and it is part of why the L-series resolves on per-cell event counts.

### The rebuild verified itself on the way through

The `level_rates` run that produced all this was the first on the rebuilt data. **Every
L01-L10 firing rate came back unchanged** - the diff against the committed reports contained
no `L0*` lines at all. With `batch_contents.md` and `splice.md` already reproducing
byte-identically, that is a third independent confirmation that the rebuilt series are the
same objects the original research read.

One cosmetic difference: a placebo distance of `nan` became `0` for `open_CME` and
`open_RTH`, the degenerate L06 level types whose real distance is identically zero. The
verdict (**FAIL**) and the reasoning are unchanged; it is a median-of-empty formatting
difference between this machine and the PC, and it is recorded rather than passed over.

### Decisions taken rather than resolved silently

1. **`status: excluded`**, not a new status. F12 and F13 already use it for entries removed
   on grounds other than a result, and inventing `withdrawn` would make the registry
   unqueryable for no gain (36 decision 3).
2. **`registered_test_order: 19` is kept, `test_order` nulled.** Same handling every resolved
   entry uses; nulling both would leave an unexplained gap in the ordering.
3. **`kbars` was checked for blast radius and is L11-specific in effect.**
   `confirmed_break` has three call sites - L02 (opening range), L05 (overnight range) and
   L11. For L02 and L05 the level is one price starts AT or near, so "first run of k closes
   beyond" is a real test; their rates vary across cells (L02/MGC spans 3,001-5,724) and
   their overlaps are 98-99% rather than a degenerate 100%. The failure is specific to
   applying it to a band price already sits strictly inside.
4. **No spent trial is affected.** The log holds 684 trials across F02-F07 and L07 only, and
   no logged `params` key is `kbars`. L02, L03, L04, L05 and L11 have never run Stage 1, so
   the "logged trials exceed distinct cells" risk does not arise anywhere.


## 41. The defect was in `confirmed_break`, not in the entries calling it

L11 (40) was not a one-off. A firing-minute variance check against L02, L03, L04 and L05 as
registered found the same failure in two more places, and located it in the shared function
rather than in any entry.

### Retraction: the "L11-specific" conclusion in 40 was wrong

40 concluded the defect was confined to L11, on two pieces of evidence: L02's firing rates
spread across cells (MGC 3,001-5,724) where a degenerate condition would be flat, and L02/L05
showed 98-99% aggregate overlap rather than a degenerate 100%.

**Both were artefacts of aggregation.**

The rate spread came from L02's **absorption** cells, which are sound, while its **sweep**
cells were degenerate - the hypothesis-level range mixed the two arms and the flat half
disappeared into it. The 98-99% overlap is a per-hypothesis MAXIMUM over all pairs, and the
sound absorption cells dominate the statistic that gets printed.

**The error was reasoning about a condition from summary statistics of its output.** The only
thing that shows this defect is the entry-MINUTE distribution, and no report carried one.
Recorded because the same reasoning would fail the same way again.

### What was measured

For every cell: entry-minute min/max/sd, the share of identical minutes between adjacent
parameter settings, and whether the high and low of the same session fire at the same
(row, minute).

**DEGENERATE - every condition built on `confirmed_break`:**

| cell | fired | minute sd | adjacent-k identical | hi/lo same (row, min) |
|---|---|---|---|---|
| L02 sweep W=15, MGC | 7,954 (all) | 16.1 | **0.0%** | **3,644/3,975 (92%)** |
| L02 sweep W=15, MNQ | 7,453 (all) | **0.10** | **0.0%** | **3,573/3,615 (99%)** |
| L02 sweep W=60, MNQ | 7,453 (all) | **0.07** | **0.0%** | 3,593/3,615 (99%) |
| L05 on_range, MNQ | 8,234 (all) | **0.05** | **0.0%** | **4,093/4,110 (99.6%)** |

Every level fires. The entry minute equals `valid_from` (945 = 930+15, 990 = 930+60,
930 = RTH_OPEN). `k` shifts entry by exactly `k-1` bars, so adjacent settings share **no**
minutes at all. The high and low of the same session fire at the same minute and collapse to
one key. MNQ's sd of **0.05 minutes** is the cleanest statement of it: no variance whatsoever.

**SOUND - every condition built on `sweep_reclaim`:**

| cell | fired (m=2/4/8) | minute sd | hi/lo collision |
|---|---|---|---|
| L02 absorb W=15 | 5,769 / 5,596 / 4,841 | 71-76 | 2.8% |
| L03 prior_rth | 4,679 / 4,589 / 4,143 | 368-370 | 1.4% |
| L04 Asia | 5,142 / 5,071 / 4,621 | 187-189 | 1.6% |
| L04 London | 2,066 / 1,988 / 1,602 | 82 | 3% |
| L04 US | 393 / 325 / 201 | 16.8 | 0/1 |

Counts fall with `m`, minute sd is 16-370 rather than ~0, collisions are 1-3%. **L03 and L04
are sound as registered.**

### The cause, and why it is the function's fault

`confirmed_break` tested a run of k closes beyond the level in **either** direction. Applied
to a level price already sits strictly inside - an opening range, an overnight range, a
Bollinger band - one side is satisfied at the first bar and stays satisfied. The function
cannot express the intended question for such a level, and it said nothing about that.

**It silently broke three registered hypotheses**: L02's sweep arm, L05, and L11. Each looked
healthy in the firing-rate table, because a condition that fires on everything produces a
large, stable, plausible count.

**Fixed in the function.** `direction` is now a required keyword ("up" or "down"), so the
either-direction shape is no longer expressible. A precondition counts the levels already
beyond the level when the scan starts and raises `DegenerateCondition` above 25% - the
measured failures ran at 100%. `tests/test_confirmed_break_guard.py` pins the refusal, and
also pins the property whose absence was the defect: a path beyond for exactly two bars must
confirm at k=2 and **not** at k=3, so k selects rather than offsets.

### L02: absorption runs, sweep is withdrawn

The two arms are registered as mutually exclusive price paths, so the absorption variant
stands alone coherently. Its 81 cells (27 at H=180) are sound and will run. The 27 sweep
cells are withdrawn.

**If the sweep correction is ever wanted it is a NEW REGISTRATION competing on its own merits
alongside L11's, not an inherited slot.** Correcting it means a directional break with an
inside-range precondition - a different condition, not a narrowed one - and it must earn a
place against everything else unregistered rather than inherit L02's grade, tier or test
order.

### L05 is noted, not withdrawn

L05 was already `blocked_insufficient_events` and cannot run, so nothing downstream changes.
Its measurement block is removed from `level_rates.py`: the 8,234 figure was a count of
SESSIONS rather than of breaks, and continuing to publish a meaningless rate is worse than
publishing none. Its entry records the defect.

### Decisions taken rather than resolved silently

1. **The guard raises rather than warns.** A warning in a batch that prints hundreds of lines
   is a warning nobody reads - which is precisely how 36's placebo FAIL sat in a committed
   report for four days.
2. **25% is the threshold, not 0%.** A level price is genuinely approaching will occasionally
   be crossed before the scan starts; refusing all of them would ban legitimate use. The
   measured failures were at 100%, so the exact threshold is not load-bearing.
3. **The degenerate cells are deleted, not recorded as zero.** A cell that never asked a
   coherent question has no firing rate, and a zero would read as "measured, found nothing".
4. **No trial is affected.** L02, L03, L04 and L05 have never run Stage 1. N stays 684,
   SR\* stays 0.1357.


## 42. Written BEFORE the run: what L02 on MGC can and cannot establish

Recorded before a single trial was logged, because the point of writing it now is that the
outcome is unknown. An interpretive constraint agreed after seeing the number is not a
constraint.

### L02 runs MGC-only by necessity, where its mechanism is weakest

**The registered mechanism is the equity cash open.** 09:30 ET is the largest
participant-composition change of the US equity day, and L02's story is that overnight
positioning meets cash liquidity there. **Gold's equivalent event is the COMEX open at
08:20 ET**, which is a different time and a different set of participants.

The registry has said so since registration: on MGC this tests **cross-asset spillover**
rather than the registered mechanism, it is **attenuated exactly as F06 was**, and a positive
result there would not support the mechanism as written.

**MNQ, where the mechanism actually lives, is unavailable for an unrelated reason.** Its best
cell fires 5,178 times against a 5,884 detection floor at 180m - 0.88x, short by about 12%.
Not a statement about the market; a statement about sample size.

So the only resolvable route is the one where the mechanism is weakest. **That is a
constraint on what the run can establish, not a reason not to run it.**

### The consequence, stated while the outcome is unknown

**A POSITIVE RESULT ON MGC DOES NOT SUPPORT THE REGISTERED CLAIM.** The registered claim is
about the equity cash open. A positive on gold would be evidence of something else - most
plausibly cross-asset spillover, possibly the placebo construction, possibly noise surviving
63 tests.

**And it MUST NOT be reinterpreted as a spillover finding after the fact.** If the number
comes back positive, "this shows cross-asset spillover" is a hypothesis selected by its
result. Spillover was not the registered mechanism, carries no pre-stated prediction about
direction or magnitude, and would be reached by looking at the answer first.

This is the same refusal 38 applied to L07's mirror trade, and for the same reason: *the
multiple-testing budget prices the searches you declare, not the ones the data suggested after
the fact.* If cross-asset spillover from the equity open into gold is worth testing, it is a
new registration with its own mechanism section, its own trials, and ideally data that did not
generate it.

**A NULL on MGC is correspondingly weak evidence** against the registered mechanism, for the
mirror-image reason: the mechanism was never properly exposed. It closes the resolvable route
and does not refute the claim.

### What a clean outcome would look like

- **Null on MGC** - the expected outcome. L02 closes with its registered route unexposed, and
  the entry records that MNQ was short on events rather than that the mechanism failed.
- **Positive on MGC** - triggers a bug hunt before any write-up, exactly as 38 required and
  R01 before it. At 3,300-5,800 events per cell against a 2,862 floor, separation is likely
  for any effect that is not zero, so the deciding number is the size against the 0.65 bps
  MGC cost floor, not the p-value.

### The same limit does NOT apply to L03 and L04

Their mechanisms are about prior-day and session extremes as reference prices, which is not
an equity-specific story. MGC is a legitimate instrument for both. They are MGC-only for the
event-count reason alone: MNQ's best cells sit at 0.64x and 0.93x of the 180m floor.

### Decisions taken rather than resolved silently

1. **The run proceeds despite the attenuation.** The alternative is leaving the L-series'
   last testable route unrun on the grounds that it might be uninformative, which is a
   decision to not measure. The limit is recorded instead.
2. **63 trials, N 684 -> 747, SR\* 0.1356 -> 0.1367.** Cheap against what it closes.
3. **H=180 is the sole pre-registered horizon.** At H=60 the MGC floor is 5,620 and every
   cell of all three is below it, so those cells cannot reach a verdict. 60 and 120 are
   withdrawn, not parked.


## 43. L02, L03 and L04 ran. Two nulls and one that did not resolve

63 trials spent and logged before the runs. **N 684 -> 747, SR\* 0.1356 -> 0.1367**, chain
verified. Reports in `reports/l02_stage1.md`, `l03_stage1.md`, `l04_stage1.md`.

| | live cells | excluded | separated | expected | BH survivors | status |
|---|---|---|---|---|---|---|
| L02 absorption | 27 | 0 | **0** | 1.35 | 0 | retired |
| L03 | 18 | 0 | **0** | 0.90 | 0 | retired |
| L04 | 18 | 9 | **5** | 0.90 | **0** | **stage1_inconclusive** |

### L02 and L03 are nulls, and they are not equally informative

**L03 is the stronger.** Prior-day extremes as reference prices is not an equity-specific
story, so MGC is a legitimate test of the registered claim; MGC-only was an event-count
constraint alone. The claim was tested where it should hold and produced nothing.

**L02's null is weak, exactly as 42 said in advance.** Its mechanism is the 09:30 ET equity
cash open against gold's 08:20 COMEX open, so MGC tested cross-asset spillover rather than the
registered claim, and MNQ was short on events. The route is closed; the mechanism was never
exposed. **That asymmetry was written down before the run so it could not be adjusted after
it.** It was recorded when a positive would have been the inconvenient case, and it reads the
same way now that the result is null.

### L04 did not resolve, and the distinction is deliberate

Five of eighteen separate against 0.90 expected, all `sess_Asia`, and **none survives BH**.
Best cell +3.54 bps at 5.5x the cost floor, p=0.0045 against a rank-1 bar of 0.00278 - short
by a factor of about 1.6.

**The count overstates the evidence.** L04/MGC is at 98% pairwise overlap and every separation
is adjacent m/k on one level type, so it is closer to ONE result seen five times than to five
findings. This cuts both ways and both are recorded: correlated tests make BH conservative,
and they also mean "5 against 0.90" is not what the count suggests.

**Four artifacts were ruled out** before anything was written, per 42:

| check | result |
|---|---|
| placebo mispriced in the thin Asia window | refuted - distance ratio 0.94, fire rates 54.3% vs 54.6% |
| hold truncation at `RTH_EXIT` | refuted - 0.3% lost, 5.0% clipped |
| direction mix | refuted - 0.519 vs 0.529 |
| drift x net-exposure gap | refuted - **1.2%** of the difference |

Drift was the live hypothesis and it failed. The real leg earns +2.99 long and -1.74 short,
which is what drift looks like on an instrument that ran from ~1,200 to ~3,000 - but measured
directly, drift at those entries is +2.34 bps, net exposure is -0.0387 real against -0.0571
placebo, and the product explains **+0.043 of +3.543 bps**.

**`sess_London` is the built-in control and behaves correctly.** It is 50.8% truncated against
Asia's 5.0% and it is NEGATIVE throughout, so truncation cannot be manufacturing Asia's
positive.

**The era split is positive in both halves, 10 of 10** - it neither decays like R01 nor flips.
But the composition changes: in 2010-2018 the real leg is negative and the difference comes
from the placebo being more negative; in 2019-2026 the real leg turns positive. Stable
difference, unstable ingredients. Recorded rather than smoothed.

**So: not promoted, not tradeable, and not retired either.** `stage1_inconclusive` is the
catalogue's own term for exactly this - ran with adequate power, nominal hits above chance,
none surviving BH, mechanism uncontradicted. Calling it retired would claim more than the
evidence supports in one direction; calling it a finding would do so in the other.

### A probe bug found in my own bug hunt

The first drift pass reported an "excess" column of exactly 0.000 for every row. That was an
arithmetic identity - the signed return minus the signed drift cancels by construction - not a
result. It was caught before anything was written up and the column was discarded.
**Recorded because a bug hunt that reports a tautology as a clean bill of health is worse than
no hunt at all.**

### Decisions taken rather than resolved silently

1. **L04 is `stage1_inconclusive`, not `retired`.** The distinction is load-bearing (13): a
   result that did not resolve is not the same as a claim that failed.
2. **The five Asia cells were NOT re-tested as a grid of five.** Keeping them and dropping the
   rest, then re-running BH on the smaller denominator, is choosing the denominator after
   seeing the numerators. The trial log exists to make that impossible.
3. **All three keep `registered_test_order` and surrender `test_order`** - the same handling
   every resolved entry uses, so the ordering carries no unexplained gap.
4. **`sess_US`'s 9 cells are recorded as EXCLUDED with their measured reason**, not dropped.
   A type that vanishes from a report is indistinguishable from one nobody thought of.

### The rebuild switched on tests that had never run, and they did not fit

`test_roll.py` was OOM-killed on its own (exit 137) after this work. The cause is the data
rebuild SUCCEEDING: six of its tests carry
`skipif(not (PARQUET / "symbol=NQ").exists())`, so for the life of this project they silently
skipped. With `data/parquet` present they execute for the first time - and they call the EAGER
`load_product` on real NQ/MNQ/MGC, which is exactly the path 41 replaced because it cannot fit
in 2.7 GB.

**So the "366 passed" this repo has been quoting was partly a count of tests that were not
running.** A skip is not a pass, and a suite whose green depends on absent data is reporting
the data's absence rather than the code's health.

**Fixed by pointing them at the streaming path, which does not change what they test.** Their
subject is the roll CALENDAR on real data - NQ/MNQ rolling before the third Friday, MGC before
its delivery month, expiry forward-only - and the continuous series holding one contract per
session with crossover sessions absent. None of that is about which loader built the volume
table. `daily_volume_streaming` replaces `load_product` + `daily_volume` in five tests, and
`sink_continuous` into a temp file replaces `continuous_series` in two. Both substitutions are
already pinned equivalent by `test_streaming_roll.py`. **18 passed**, 191s.

**The eager functions are verified by EQUIVALENCE, not by execution at full scale on this
machine.** They remain in the codebase and remain tested on a synthetic fixture; they are not
exercised against 4.7M-bar products here. Stated rather than left implied by a green suite.

### The suite no longer runs in one process on this box

Individually every file passes - 383 tests across 16 files. Run together they accumulate past
~900 MB and the run is killed. No single test is heavy; the total is. **Run per-file on this
hardware**, or on a machine with more headroom. This is the fifth instance of the same
pattern in this programme and the machine has been the constraint every time, not the code.

### Reviving L04 requires a new registration

`sess_Asia` named in advance rather than selected as the best of eighteen, on data that did not
generate this result. Same bar 38 set for L07's mirror and 40 for L11's replacement. No
inherited slot, grade or test order.


## 44. One stage numbering, and the stage that did not exist (S1-S8)

**`reports/STAGES.md` is now the canonical reference.** Every document, run report and entry
here names the stage number it concerns.

    S1 Mechanism   S2 Pre-registration   S3 Firing rate   S4 Detection floor
    S5 Condition validity   S6 Placebo   S7 Multiplicity   S8 Out-of-sample and economics

### Old language is mapped, not rewritten

**Stage 0 ~ S1-S2. Stage 1 ~ S6-S8.** Historical entries in this file are left exactly as
written. They were true when written, and rewriting them would destroy the record of what was
known when - which is the whole point of keeping a decisions log rather than a summary. The
mapping lives in `STAGES.md`.

**The retired language named two of the eight things this programme does.** S3 and S4 were
real work with no stage name. And S5 had no name at all.

### The ordering finding: L11's S6 was measured before S5 was checked

40 recorded that L11's placebo matched on all four level types - distance ratios 0.90-1.06,
touch ratios inside tolerance - and treated that as a surprise worth noting, since the
prediction had been that band width would break matching.

**Those numbers were meaningless, and not because the placebo was wrong.** The TREATMENT had
not cleared S5. L11's condition fired unconditionally at a fixed minute on every session, so
the entry population was "every session at 10:31" and distance-from-price was fixed by
construction. **A placebo matched against a degenerate treatment tells you nothing about
either.** Matching a control to a condition that cannot select events is a well-formed
computation on an ill-formed input.

41 already recorded that the placebo prediction is therefore OUTSTANDING rather than refuted.
This entry records the more general fact: **the stages were run out of order, and nothing in
the process could notice, because one of them had no name.**

### S5 is now a permanent gate

**The firing-minute variance check was built reactively - after L11 had already failed.** It
then immediately found the same defect in two more registered hypotheses: L02's sweep arm,
Tier A and graded B, and L05. **A check that exists only because something already went wrong
is a post-mortem, not a gate.**

Promoted. **No condition proceeds to S6 until it passes S5.** Three parts, all measured:
firing-minute variance, parameter discrimination (adjacent settings must change WHICH events
fire, not merely when), and directional collapse (a level set's high and low must not fire at
the same `(row, minute)`).

The cost of running it is minutes. The cost of not running it was three hypotheses, one
carried for a day with a clean-looking placebo report attached to a condition that could not
select events.

**Corollary, and it binds: S6 results computed before S5 passed are DISCARDED, not
reinterpreted.** L11's ratios stay in its entry under `degenerate_measurements` with that
warning attached.

### Where every hypothesis stopped, in the new numbering

| | stopped at | |
|---|---|---|
| L01, L05, L08, L09 | **S4** | below the detection floor |
| L06 | **S6** | no valid control can exist - levels sit at the reference price |
| L11, L02-sweep | **S5** | withdrawn; conditions fired unconditionally |
| L02-absorption, L03 | **S7** | retired on nulls |
| L04 | **S7** | inconclusive - cleared S5, S6 and the S8 era split, failed only multiplicity |
| L07 | **S8** | retired on economics, with all 108 cells separating |
| L12 | **S5** | registered, S3/S6 measured, awaiting the gate |

**L04 is the sharpest illustration of why the numbering helps.** "L04 failed Stage 1" is
unreadable. "L04 cleared S5, S6 and the S8 era split and failed S7" says exactly what happened
and exactly what a revival would have to beat.

### A second ordering gap found while wiring L12

**The scheduling gate could not pass ANY L-series hypothesis.** It reads
`reports/measured_rates.json`, which contains only F-series entries; the L-series S3 rates live
in `reports/level_rates.json`, produced by a different generator, and nothing connected them.
This was invisible for as long as every L entry was `schedulable: false` - the gate skips those
- and surfaced the moment L12 became the first one scheduled.

**Same shape as 36: two halves of the record that never met.** L02, L03 and L04 ran earlier in
this session without the gate ever being consulted.

Fixed by routing, not by declaring: `level_rates` now computes non-overlapping event counts per
horizon (the S4 number, which it never stored), and `measured_rates` reads them. Where it meets
an older file with no independence column it **skips rather than substituting the firing
count** - passing overlapping entries off as independent is the exact overstatement S3 exists
to prevent, and 21's factor-of-forty error is why that matters.

### Decisions taken rather than resolved silently

1. **`stopped_at` is a new FIELD, not a new status.** The status vocabulary is a closed set
   whose members drive filters; adding stage names to it would make the registry unqueryable.
   The field carries the stage and a required `stopped_at_reason`.
2. **Two tests enforce it**: every L entry names a valid stage with a reason, and `STAGES.md`
   defines all eight and retains the old-language mapping. A dangling canonical reference is
   worse than none.
3. **Historical entries stay as written.** See above.


## 45. L12 out of sample (S7/S8), an unsatisfiable pre-registration, and six memory fixes

L12 ran. **9 trials, N 747 -> 756, SR\* 0.1368**, chain verified.
Report: `reports/l12_stage1.md`. **Retired at S7 on S8 economics, not on significance.**

| | |
|---|---|
| cells separating | 0 of 9 |
| mean difference | **+0.306 bps**, positive in 8 of 9 |
| registered range | +1.3 to +3.5 bps -> **4-11x short** |
| MNQ cost floor | 0.48 bps -> **0.64x, not tradeable** |
| smallest p | 0.5810 |

### The pre-registration contained an unsatisfiable criterion, and nobody noticed

L12's prediction required a positive mean **and** at least one BH survivor. **The second limb
was unreachable across most of the range it was written for**, and this was checked only after
the run - prompted by a challenge to the draft write-up, not by any gate.

**The tabulated S4 floor is not the applicable bar** (38 decision 4): MNQ/180m's 15.66 bps is
the smallest injected effect promoted at >=80% for a slow regime flipping every ~500 bars,
which is a far harder problem than a paired mean difference. **The applicable bar is the
test's own bootstrap SE of 1.016 bps**, giving a BH rank-1 threshold of **2.82 bps**:

| true effect | P(BH survivor) |
|---|---|
| 1.3 bps - bottom of the registered range | **6.8%** |
| 2.82 bps - the bar | 50.1% |
| 3.5 bps - top of the registered range | 74.9% |

So a survivor was reachable only in the **top fifth** of the registered range. **A prediction
whose lower four-fifths cannot produce the required outcome can essentially only fail.**

**Citing p=0.5810 as refutation would have been the S4 error this programme exists to
prevent** - a null from a test that could not have detected the effect. The refutation rests
on magnitude and economics, which need no power argument at all.

### Proposed standing S2 check: SURFACE, do not auto-reject

At registration, compute the effect size a BH survivor would require at the expected n and
compare it to the registered range. Report above / straddling / below.

**It must not auto-reject.** A prediction below the reachable threshold is not always
disqualifying, and rejecting by default would quietly filter out exactly the small-effect
hypotheses that are still worth testing on cost grounds. Three legitimate responses:

1. **Register it as an economics-only test with the significance limb explicitly waived.**
   L12 should have been this. The economics limb refuted it cleanly and needed no p-value.
2. **Increase n** - a longer sample, a second instrument, a shorter horizon.
3. **Proceed knowingly**, with the low power recorded in the entry so a null cannot later be
   read as evidence of absence.

The check costs five lines. Not having it cost a registration whose headline criterion could
not be met.

### The retroactive audit: the defect is isolated, for a worse reason than it sounds

Every registered hypothesis across the F-, R- and L-series was audited for a predicted
magnitude that could be checked against a reachable threshold.

**Result: L12 is the ONLY hypothesis in 26 that ever registered one.**

- **F-series (14):** no prediction field, no predicted magnitude anywhere in the registry.
- **R-series (5):** R03 carries a `distinguishing_prediction`, but it is MECHANISTIC and
  directional - *"days with a large index return but a small NET rebalance requirement should
  show NO effect"* - with no magnitude. R01's only bps figures are COST floors, not predicted
  effects.
- **L-series (12):** L12 alone.

**So the S2 check has nothing to audit retroactively, because the field it would check did not
exist.** That is a larger gap than the one it was meant to find: 25 of 26 registrations state
a direction and a mechanism but never say *how big* the effect should be - which means their
nulls were never checkable against a detection threshold either.

The honest reading of L12's defect is therefore not "a slip in one entry". **It is the first
time the programme wrote down a magnitude at all, and the first opportunity to notice that
nothing checks one.** The proposed S2 check should require a magnitude or an explicit waiver,
not merely validate one when volunteered.

### L04's entry corrected, status unchanged

**L04's observed +3.54 bps sat below its own BH rank-1 bar of 3.72 bps** (SE 1.244, 18
tests). No survivor was reachable at the effect size actually observed, so "failed the
correction" understates it - L04 was also operating at the edge of its resolution. Recorded in
its entry under `resolution_note`.

**Status unchanged: `stage1_inconclusive`, `stopped_at: S7`.** Mechanism uncontradicted is
still the right reading; this makes the inconclusiveness better understood, not different.

**An over-claim in the L12 draft is withdrawn.** "An independent instrument shows BH was right
rather than conservative" is too strong when L12 could not have produced a survivor across
most of its own range. What L12 settles: 76.2% power against +3.54 bps, delivered +0.306, so
**that magnitude does not replicate**. What it does not settle: a smaller real effect, where
power was 7-21%.

### Six memory fixes to open the L-series gate (S3/S4 plumbing)

Getting L12 through the gate took six fixes, all the same disease - eager frames on a 2.7 GB
machine - and two ordering gaps.

1. **`roll`: the global sort.** Avoidable rather than expensive; the front month advances
   monotonically so contracts are contiguous non-overlapping session runs (41).
2. **`splice`: same treatment**, NQ entirely before MNQ.
3. **`levels.load`:** read four columns instead of eleven, released the frame before
   allocating grids. 875 -> 626 MB.
4. **`level_rates`: packed firing keys into int64.** A Python `set` of `(row, minute)` tuples
   cost ~130 MB for ONE L07 cell; 6.9 MB packed, a ~20x reduction.
5. **`load_1m`: scan with projection pushdown.** It read all eleven parquet columns - three of
   them strings - then selected four, on 4.73M rows.
6. **`measure_all`: lazy frames.** A first attempt used a single-slot cache that evicted on
   switch and **broke `f08_rates`**, which is cross-asset and legitimately needs both products
   at once. The fix was the projection, not the eviction.

**`f01_rates` remains OOM-killed at ~1,064 MB and is NOT fixed.** `--only` was added so a
subset can be refreshed without re-running it; the merge prints what it carried forward
(`873 refreshed, 248 carried forward`) and `--check` still compares a full fresh measurement,
so the cache cannot drift unnoticed. **Recorded as open, not resolved.**

### Where the S4 `e` actually came from: a universal ladder, never a prediction

Since 25 of 26 entries never stated a magnitude, every S4 computation used an `e` from
somewhere else. It is `reports/floor_cache.json`: **one fixed ladder of ten injected effect
sizes in units of one bar's volatility at the horizon**, identical for every hypothesis.

    0.001  0.00188  0.00355  0.00669  0.01262  0.02378  0.04481  0.08446  0.15918  0.3

The gate never asks "can you detect YOUR effect". It asks **"is your n at least the n at which
the sweep detected ITS smallest detectable effect"** - `effective_n < smallest_resolving_n`
becomes `BELOW SWEPT RANGE`. The operative `e` per cell:

| product | horizon | operative floor | bps | source |
|---|---|---|---|---|
| MNQ | 180m | 0.3x | 15.66 | **ladder top rung** |
| MGC | 180m | 0.3x | 14.34 | **ladder top rung** |
| MGC | 60m | 0.3x | 4.17 | **ladder top rung** |
| MNQ | 60m | 0.08446x | 2.57 | ladder |
| both | 1m | 0.04481x | - | ladder |

Not a cost floor, not a prior series, not a prediction. A tabulated default.

### The ladder's top rung is a CENSORED BOUND, not a measurement

At 60m and 180m the operative floor is the **top rung the sweep ever tested**, so the floor is
only bracketed in **(0.1592, 0.3]** - nothing larger was tried. At MNQ/180m the bracket turns
on a **0.72 versus 0.80 promote rate at 25 reps, whose CI is 0.52-0.86**.

**Anything reading `floor_cache.json` inherits a bound presented as a floor.** That warning is
now written into the JSON itself - five of six cells carry
`_WARNING_censored_bound` - because a later reader opens the data file, not the reasoning. The
loader ignores unknown keys, so it is inert to the pipeline.

### The four S4 blocks re-examined: a realistic `e` makes them STRONGER

Against the tabulated gate, L01, L08 and L09 sit at **0.01x to 0.24x** of the required n. But
the tabulated `e` is the wrong bar for a paired test - the same error found in L12, where 15.66
tabulated against 2.82 empirical. Recomputing with L12's **measured** bootstrap SE scaled as
1/sqrt(n), and BH rank-1 within each grid:

| | product/H | n | SE | BH bar | |
|---|---|---|---|---|---|
| L01 | MGC 60m | 211 | 4.45 | **12.35 bps** | block holds |
| L01 | MNQ 60m | 237 | 4.20 | **11.65 bps** | block holds |
| L08 | both 60/180m | 698-705 | 2.44 | **7.29-7.32 bps** | block holds |
| L09 | both 60/180m | 364-446 | 3.06-3.39 | **9.16-10.14 bps** | block holds |

**The largest difference this programme has ever measured is 5.0 bps (L07).** L04 gave 3.5,
R01 0.45, L12 0.31. Every blocked hypothesis needs **7.3-12.4 bps** to produce a survivor -
above anything observed anywhere in four series.

**THE DIRECTION OF THE CORRECTION IS UNAMBIGUOUS: a realistic `e` makes all four blocks
STRONGER, not weaker.** 14-16 bps at 180m is roughly 5x the empirical resolution of a paired
test, so the generic ladder demanded LESS n than a realistic effect requires. **The gate was
generous and the blocks were understated.** No status changes, but the closeout should say the
blocks are firmer than the original arithmetic claimed rather than softer.

### The missing-magnitude gap is programme-wide, and that is the more important half

The L12 defect is not an isolated slip. **1 of 26 registrations across the F-, R- and L-series
ever stated a predicted magnitude.** F-series: none. R-series: R03's
`distinguishing_prediction` is mechanistic with no magnitude; R01's bps figures are cost
floors. L-series: L12 alone.

**So no null in this programme was ever checkable against its own predicted effect.** Every
S4 verdict was rendered against a tabulated default, and every null was reported without a
statement of what size of effect it would have been able to see. L12 is simply the first time
a magnitude was written down and therefore the first time anything could be checked at all.

That is a larger finding than the unsatisfiable criterion it surfaced, and it is the half that
should carry into any future programme: **a registration that states a direction and a
mechanism but not a magnitude cannot produce an interpretable null.**

### L05 corrected: S5, and its S4 arithmetic is withdrawn

L05 was recorded as blocked at S4. **It stops at S5**: its condition is degenerate
(`confirmed_break` on the overnight range, entry-minute sd 0.05, all 8,234 levels firing,
99.6% high/low collision), so it cannot reach S6 at any n.

**And its S4 block no longer rests on a live measurement.** 41 removed the degenerate
measurement block from `level_rates.py`, so L05 has no record in `measured_rates.json`. The
event count that once justified the S4 block described a condition firing on every session - a
count of SESSIONS, not of breaks - and is withdrawn with it.

### Selectivity, not firing rate, is this programme's design lever

**A standalone finding, not N-series background.** Measured on L07 by sweeping gap width as a
selectivity knob across 6-216 firings/session:

| | loosening 5.05x |
|---|---|
| effect | **x0.513** (decay exponent 0.412) |
| BH bar | **x0.364** (fall exponent 0.624) |
| eff/bar | improves 1.41x - **statistically loosening WINS** |
| eff/cost | **degrades 0.51x - economically it LOSES, by more** |

The asymmetry is structural: **the cost floor is fixed and does not shrink with n.** Every
extra event makes an effect easier to PROVE and less worth HAVING.

**And across four series nothing has ever failed for want of precision.** L07 separated in
108 of 108 cells and died on cost. L12 gave p=0.58 and was retired at 0.64x cost. R01
separated and sat 2.1x below its floor. The binding constraint has always been economics.

**Therefore selectivity, not firing rate, is the design lever for anything this programme
registers.** That is transferable beyond the N-series and belongs alongside the
`confirmed_break` defect and the missing-magnitude gap.

**Corollary: `w`/`L` is the cheap knob, `tf` the expensive one.** Tightening w 8->32 at 5m
moves eff/cost 10.34 -> 17.38 while eff/bar only falls 7.43 -> 5.34. Tightening tf 5m -> 30m
collapses eff/bar 7.43 -> 4.61 for almost no economic gain. Tighten level QUALITY first.

### The eff/cost optimum lies outside every range this programme has swept

Extending L07's sweep past its own grid edge found eff/cost still climbing at w=32 and
peaking only at **w=24/tf=30m - 18.41x, at 0.65 firings/session**. Every sweep in four series
has explored TOWARD looseness from a starting point that was never itself justified.

**Future series should start tight and sweep toward looseness.**

### The premise that selected the N-series draft was wrong, and how it was corrected

The draft's organising principle was that once-per-session conditions were the L-series'
structural defect and high firing rates would fix it. **The measurement says the opposite:**
the eff/cost optimum sits at **0.65 firings/session**, essentially where the L-series already
operated (L12 at 1.46, L04 at 1.5). They were near the ECONOMIC optimum and the binding
constraint was effect size.

The correction took three measured steps, each needing the previous one to be interpretable:

1. **The unit of observation.** `paired_stats` resamples SESSIONS, not events. Measured design
   effects: L12-like 1.14, round-number 2.19, **volume-climax 65.6**. An extra within-session
   event buys 0.87, 0.46 and **0.02** respectively. A blended number would misprice two
   families in opposite directions.
2. **The decay exponents** - effect 0.412 against bar 0.624, above.
3. **The boundary** - the optimum lies outside every swept range.

**A worked error, recorded as such.** N06 was ranked third in the draft and is in fact the
worst candidate in the set: 18.8 firings/session landing at a **17 bps** BH bar - above
anything this programme has observed - on only **386 qualifying sessions**, because z>3 volume
days ARE the crisis days and every event inside one is a single observation. Same shape as the
errors 41 and 45 already record: **a number that looked like an advantage was an artifact of
not checking what the unit of observation actually was.**

### N04 and N05 registered; N01, N03, N06, N10 declined

**Registered** (S2 closed, S3 measured, S5 passed, S6 not yet built, no trial spent):

- **N04 failed-breakout trap** - provable across its whole predicted range: 2.0-5.0 bps
  against a BH bar of 1.42, eff/cost 7.3x. The §41 guard was verified to DISCRIMINATE, raising
  on the opening range at 44.2% already-beyond and passing on swing pivots.
- **N05 swing sweep-reclaim** - **the marginal registration, and its entry says so.** 1.5-4.0
  against a bar of 1.83-2.05, so the bottom of the range is unreachable. Registered under the
  S2 surface-don't-reject rule because the upper two thirds are reachable at eff/cost 5.7x.

**They are not duplicates: measured overlap 2.1%**, because N04 enters at the break bar and
N05 at the reclaim bar. That was measured rather than assumed, because two hypotheses on one
level set is exactly how the L-series lost its aggregate route.

**An uplift was considered and DECLINED.** Tightening implies, under L07's 0.412 exponent, an
effect uplift of x1.54 - which would have raised N04 to 3.1-7.7 and N05 to 2.3-6.2. The
PARAMETERS may be informed by a transferred curve because they are a specification choice; the
PREDICTED MAGNITUDE is different in kind, because S2 judges the hypothesis against it.
Uplifting it would set the bar partly by transfer from a refuted mechanism, and that exponent
is the first thing to fail if the transfer does not hold. Recorded in both entries with the
figure, so a later reader sees it was considered rather than missed.

**Declined:**

- **N06 volume-climax** - 111 effective units, a 17 bps bar on 386 sessions. Unprovable at any
  plausible magnitude.
- **N10 post-release fade** - best eff/cost in the draft (6.2-16.7x) and still wrong: eff/bar
  0.9, and with ~800 events the ECONOMIC estimate carries a +/-6 bps interval, so the
  economics-only waiver rescues nothing either.
- **N01 approach reversal** - near-duplicate of N02 on the same level population, lower
  eff/cost, straddles. Its mutual-control argument is good but costs a registration to buy
  what N02's own placebo already provides.
- **N03 roundness gradient** - k=45 from five roundness classes drives the bar to 1.98 against
  a 1.5-3.0 prediction. The family's best falsification test cannot afford its own
  multiplicity.
- **N08 deferred** (provable but k=36, and time-of-day is the easiest place in the set to
  overfit). **N07 outstanding** pending a persistence check on MNQ/NQ volume share - R02 closed
  because the BASIS had no memory, and volume share must be shown to differ. **N09 is not a
  registration** - non-directional by its own text.

**Transfer limitation, stated in both entries rather than footnoted:** every optimum and both
exponents are measured on L07, whose mechanism 38 REFUTED. Drift was excluded at 1.2% so the
effect is real and reproducible even though its interpretation is wrong, and the curve is
plausibly generic to thresholded conditions - but it is a transfer, not a fit. If N04/N05's
own selectivity behaviour diverges once measured, the parameters are wrong and must be
revisited.

### Two ordering gaps

**The scheduling gate could not pass ANY L-series hypothesis.** It reads
`measured_rates.json`, which held only F-series entries, while the L-series S3 rates live in
`level_rates.json` from a different generator. Invisible while every L entry was
`schedulable: false` - the gate skips those - and it surfaced the moment L12 became the first
one scheduled. **Same shape as 36.** Fixed by routing, not declaring: `level_rates` now
computes non-overlapping counts per horizon - the S4 number it never stored - and
`measured_rates` reads them, **skipping rather than substituting `firings`** where the column
is absent.

**`level_rates` had never stored an independence count at all**, so the S4 number the gate
needs did not exist in the file the L-series writes. That is why the bridge could not be a
one-liner.

### Decisions taken rather than resolved silently

1. **`source: "level_rates"` added to the allowed set**, named. It routes a genuine
   measurement; the gate exists to exclude declarations, so this is not loosening it.
2. **`SCAN_POSITIONS["L12"] = 1`, `DISJOINT = False`**, justified by L04's measured 98%
   overlap rather than assumed.
3. **L12 retired on economics with the significance limb explicitly set aside.** Retiring it
   on p=0.58 would have been the cheaper sentence and the wrong one.
4. **The S2 check surfaces rather than rejects**, for the reason above.


## 46. The placebo distance convention, examined for the first time; N04/N05 withdrawn

Two hypotheses have now been closed by a placebo - L06 and, here, N04/N05 - and the
convention that decides those closures had never been examined. It is examined now, and it
holds.

### The freestanding result: `valid_from` is correct because it measures REACHABILITY

`verify` matches a placebo on |level - ref| taken at `valid_from`. **No hypothesis trades at
`valid_from`** - each trades later, at a touch, a break or a reclaim - so the obvious
objection is that the harness matches distance at a moment the hypothesis never trades at.

Measured on MGC, both conventions, every level type already matched:

| level type | at `valid_from` | at trade time | ratio |
|---|---|---|---|
| L03 prior_rth | 5.80 | 0.30 | 0.052 |
| L03 prior_full | 8.90 | 0.50 | 0.056 |
| L04 sess_Asia | 3.80 | 0.30 | 0.079 |
| L04 sess_London | 6.60 | 0.30 | 0.045 |
| L04 sess_US | 5.40 | 0.20 | 0.037 |
| L02 or15 | 1.60 | 0.30 | 0.187 |
| L02 or30 | 2.30 | 0.30 | 0.130 |
| L02 or60 | 3.10 | 0.30 | 0.097 |

**Trade-time distance collapses to 0.2-0.6 across eight level types whose `valid_from`
distances span 1.6 to 8.9.** That is not a coincidence and not a property of these
hypotheses: it is what "trading at the level" MEANS. Price is at the level at the moment the
trade triggers, for every level type, by construction.

**So matching at trade time would be matching on a constant.** It would carry no information,
would place every placebo at the current price, and would equalise nothing.

**`valid_from` is correct, and the reason is now stated rather than assumed: it measures
REACHABILITY** - how far price must travel to reach the level. That is exactly what 37's null
requires, because the touch rate is then an INDEPENDENT check that the arbitrary region is
comparably reachable. Match on a quantity that is ~0 everywhere and the touch check has
nothing to be independent of.

### A retraction, the same shape as 41

I proposed re-specifying the reference to trade consideration, on the grounds that N04 does
not trade at `valid_from`. **That was wrong, and it would have rescued pivots by breaking the
convention for the other eight level types.** The premise was true - no hypothesis trades at
`valid_from` - and irrelevant, because it is true of every hypothesis equally.

Same shape as 41's retraction: **a conclusion drawn from one case that a measurement across
the population immediately refutes.** There the evidence was L02's aggregated rate spread;
here it was a single level type's divergence. In both cases the fix was to measure the
general claim rather than reason from the instance.

### N04 and N05 withdrawn at S6

**A swing pivot is definitionally at-the-money when confirmed.** The fractal test asserts the
bar is the extreme of its neighbours, so at the moment the level becomes tradeable price is
still there:

| | median distance at `valid_from` | zero-share |
|---|---|---|
| **swing_L20_5m** | **0.000** | **61.4%** |
| every other level type | 1.60 - 8.90 | 0.1% - 7.1% |

It is also the ONLY level type whose distance is SMALLER at `valid_from` (0.00) than at trade
time (0.60); every other type runs the other way by a factor of 5-27x.

`verify` returns **DEGENERATE** on both products - *"a property of the level definition, not a
tuning failure, and no scale or construction fixes it"* - the identical verdict L06 receives
for `open_RTH` and `open_CME`. **Same class, same reason, and no trial spent.**

**S5 had passed and S3 had cleared the floor.** N04 fired 6.4-6.7/session with entry-minute sd
327 and up/down discriminating; N05 3.2-4.0/session with sd ~255 and counts falling with m;
their mutual overlap was 2.1%. **None of it mattered**, which is exactly why the placebo was
built before the S3 rates were routed - L11's rate also cleared its floor while the hypothesis
died at S5.

**A specification defect was caught on the way**, and it is worth recording because it nearly
hid the real one. A first draft of `swing_pivots` set `ref_price = price`, forcing distance to
zero BY DEFINITION. Corrected to the close at `valid_from`, which is the convention every
other level type uses - and the distance is still zero, because of what a pivot IS. The bug
and the property looked identical from the output; only fixing the bug revealed the property.

### The N-series draft produced ZERO registrations, and that is the correct outcome

Ten candidates in, none registered, **N unchanged at 756**:

| | |
|---|---|
| declined on arithmetic before touching data | **4** - N06, N10, N01, N03 |
| withdrawn at S6 | **2** - N04, N05 |
| deferred | **1** - N08, k=36 and time-of-day overfits easily |
| not a registration | **1** - N09, non-directional by its own text |
| still unmeasured | **2** - N02 cross frequency, N07 persistence |

**A drafting process that filters ten to zero without spending a trial is the gate working.**
Recorded explicitly because a later reader sees an empty series and reads wasted effort. What
it cost: no trials, no N, no SR\* movement. What it bought: the selectivity finding (45), the
measured design effects by family, the boundary result, and this convention check - none of
which existed before and all of which constrain every future registration.

**The draft's own premise was refuted in the process** (45): it selected for firing rate, and
the measurement put the economic optimum at 0.65 firings/session, essentially where the
L-series already operated.

### Decisions taken rather than resolved silently

1. **`swing_pivots` is KEPT in `definitions.py`** though no registered hypothesis uses it. It
   is correct code with a documented defect-and-fix in its docstring, and deleting it would
   erase why the level type cannot be controlled. `bollinger_levels` is kept on the same
   reasoning (40).
2. **N04/N05 get `status: excluded`, `param_cap: 0`**, and are named in the pinned excluded
   set with their reason - the same handling L11 received.
3. **The convention was NOT changed.** It was tested and it held. Recording a convention that
   survived examination matters as much as recording one that failed: the next person to
   propose trade-time matching should find this entry rather than re-derive it.


## 47. N02 measured and registered; N07 closed on a positive persistence result

The two measurements 46 left open. Both spent no trial; N stays 756.

### N02: the draft's assumption was backwards, and it decides the candidate

The draft assumed crosses were a SUBSET of approaches and therefore rarer - *"lower than
N01"*. **Measured on MNQ: of 32,590 round-number events, 26,200 (80.4%) CROSS and 6,390
(19.6%) merely approach. Cross/approach = 4.10.** Price that reaches a round number usually
goes through it.

The definition was fixed before measuring and not adjusted after: through the level by >= 2
points on the far side from the approach, within 60 minutes.

**This reverses both round-number candidates' verdicts:**

| | events | units | BH bar | predicted | verdict |
|---|---|---|---|---|---|
| **N02 crosses** | **26,200** | 11,963 | **1.64** | 2.0-5.0 | **PROVABLE ACROSS RANGE** |
| N01 approaches | 6,390 | 2,918 | **3.32** | 1.5-4.0 | only the top 27% reachable |

N02 had been judged to STRADDLE at eff/bar 1.4 on an assumed 12,000 events; the measured
26,200 moves it clear at eff/bar 2.13, eff/cost 7.3x. **N01 was correctly dropped, by a wider
margin than the estimate showed.**

**Registered at S2, `schedulable: false`.** S5 and S6 are still owed. S6 is EXPECTED to be
buildable - round levels sit at a distance from price, which is exactly what N04/N05 lacked
(61.4% zero-distance, 46) - but that is an expectation and must be verified, not assumed.

### N07: volume share PERSISTS, and R02's failure was specific to the basis

Measured like for like against R02's basis, which closed at a half-life of **0.25 bars**:

| series | AR(1) phi | half-life | ac at lag 30 |
|---|---|---|---|
| volume share, 1-minute | 0.877 | **5.29 bars** | 0.832 |
| volume share, per session | 0.952 | **14.15 sessions** | 0.848 |

**But most of that is deterministic, and saying so is the point.** MNQ's share of the pair
rose from **0.292 in 2019 to 0.822 in 2026** - a secular adoption trend, not information.
Stripping the time-of-day profile and the yearly mean:

| | phi | half-life |
|---|---|---|
| raw | 0.877 | 5.29 |
| minus time-of-day mean | 0.872 | 5.06 |
| **minus time-of-day AND yearly mean** | **0.617** | **1.44 bars** |

**The residual still persists at ~6x R02's basis** (1.44 against 0.25 bars), with
autocorrelation 0.428 still at lag 60.

**Which of the two outcomes this is, stated explicitly as required.** It is the SECOND branch:
the retail-participation angle survives in a form the basis did not. That says something
specific about why R02 failed. **R02 tested the BASIS - a price difference between two
contracts on the same underlying, which arbitrage forces to mean-revert almost instantly.
Volume share is a participation measure, and nothing arbitrages it.** R02's failure was a
property of the observable it chose, not of the retail-participation idea.

That is the first evidence in this programme that the angle survives at all, and it is
recorded as such rather than as an open item.

**N07 is nevertheless CLOSED as a registration.** It is a CONDITIONER, not a standalone
signal - it re-evaluates a primary hypothesis stratified by participation quantile, and
conditioners multiply k. With N02 the only registrable primary and N02 itself not past S5/S6,
there is nothing to condition. **Closed as: question answered, available as a conditioner if
and when a primary survives, not registered now.** Registering it before a primary exists
would spend k on nothing, which its own draft entry warned against.

### Decisions taken rather than resolved silently

1. **The cross definition was not tuned.** N02 had no headroom at the assumed count, and the
   instruction was explicit that a failure stays a failure. It passed on the first definition
   tried; had it failed, the definition would not have been adjusted to rescue it.
2. **N07's persistence is reported with its deterministic component separated.** Reporting
   the raw 5.29-bar half-life alone would have overstated it by ~4x, and a secular adoption
   trend is persistent without being informative.
3. **N02 is registered but NOT schedulable.** S5 before S6, S6 before routing - the ordering
   46 and 40 establish.


## 48. Why R02 failed: it chose the one observable on that pair that cannot persist

**A programme-level finding, not an N07 registration note.** It reopens a direction rather
than closing one, and a later session should find it here rather than rederive it.

### The isolation

R02 tested the **MNQ/NQ basis** - the price difference between two contracts on the same
underlying - and closed because the basis had a half-life of **0.25 bars**. That was read at
the time as the micro/mini relationship carrying no information.

**It is not. A price difference between two contracts on one underlying is arbitraged, and
arbitrage forces it to revert almost instantly.** The 0.25-bar half-life is not a discovery
about retail participation; it is a restatement of the fact that the pair is arbitraged.

**Volume share is a participation measure on the same pair, and nothing arbitrages it:**

| observable, same pair | half-life |
|---|---|
| basis (R02's choice) | **0.25 bars** |
| MNQ volume share | **1.44 bars** after detrending (5.29 raw) |

~6x the persistence, with autocorrelation still 0.428 at lag 60.

**So R02 chose the one observable on that pair that could not persist, and its mechanism was
never tested.** The retail-participation idea was not refuted - the instrument for measuring
it was incapable of carrying the signal. That is a direction left open, not closed:
participation measures on MNQ/NQ remain untested, and the observable that failed was the
wrong one for a structural reason that is now identified.

**Recorded because the R-series conclusion currently reads as though the angle was tested and
failed.** It was not.

### The detrending, recorded explicitly

| | phi | half-life |
|---|---|---|
| raw, 1-minute | 0.877 | 5.29 bars |
| minus time-of-day mean | 0.872 | 5.06 bars |
| **minus time-of-day AND yearly mean** | **0.617** | **1.44 bars** |

**MNQ's share of the pair rose from 0.292 in 2019 to 0.822 in 2026.** That is a secular
adoption trend. It is perfectly persistent and carries no information whatever.

**Reporting the raw 5.29-bar figure would have overstated persistence by about 4x, on
adoption rather than on signal.** The claim would have been "volume share has 21x the memory
of the basis" instead of the true ~6x.

**Same class as the `confirmed_break` defect (41) and the censored floor bound (45):** a
number that looked like a result was partly an artifact of not asking what produced it. The
recurring shape across all three is that the quantity measured and the quantity meant had
drifted apart, and only decomposing the measurement revealed it.

### N02's S6 PREDICTION, recorded BEFORE the measurement

N04/N05 died at S6 because a swing pivot is at-the-money when confirmed - 61.4% of levels at
zero distance from the reference, against 0.1-7.1% for every other level type (46). **Round
numbers should not have that property**, because a price grid exists independently of where
price currently is.

**Stated in advance so the measurement can disagree:**

- **median |level - ref| at `valid_from`: 8 to 30 MNQ points.** Distance to the nearest point
  of a 50-point grid is roughly uniform on [0, 25] for a single nearest level, and wider if
  the population includes further levels.
- **zero-distance share: BELOW 5%**, and in the same band as established level types
  (0.1-7.1%), not the pivot's 61.4%.
- **`verify` PASSES on both products**, distance ratio and touch ratio within +/-25%.

**If the match fails, N02 withdraws and the N-series closes with ZERO registrations from ten
candidates.** Said plainly now rather than looked for afterwards: there is no fix to reach
for, because 46 established that the `valid_from` convention is correct and a failure would
be a property of the level definition, exactly as it was for pivots and for L06.


## 49. N02's level population was circular; one corrected re-measurement, binding

### The defect, in its own terms

N02's first S6 attempt failed on both products with a TOUCH-RATE MISMATCH: real **100.0%**
against placebo 57.6% on MNQ, real 90.0% against 62.7% on MGC.

**The cause is a defect in the level population I built, not a property of round numbers.**
The construction admitted a grid level into the population **only when price came within 0.5
points of it**. So every real level was touched **by definition** - 100.0% is not a
measurement, it is the selection rule restated.

**The placebo was then asked to match an outcome the population had been selected on.** No
arbitrary region can match a 100% touch rate that was imposed rather than observed. Every
established level type in the catalogue - prior-day extremes, session extremes, opening
ranges - is defined independently of whether price ever reaches it, which is why their touch
rates are informative.

### Why this is a bug and not the N04/N05 outcome

The standing instruction rules out hunting for a fix after a hypothesis fails, and that is the
right rule. This is distinguished on evidence recorded BEFORE the measurement (48):

| pre-registered prediction | measured | |
|---|---|---|
| median distance 8-30 MNQ points | **10.5** | correct |
| zero-share below 5%, inside the 0.1-7.1% band | **2.4% MNQ / 3.7% MGC** | correct |
| `verify` passes | **failed on touch** | wrong |

**Distance and zero-share landed exactly as predicted.** Round numbers do NOT have the pivot
property - they are established at a distance, as claimed. The failure is on the one axis the
circular construction directly determines, at exactly 100.0%, which is the signature of
selecting on the outcome.

`verify` also returns a different failure KIND. N04/N05 got **DEGENERATE** - *"a property of
the level definition, not a tuning failure, and no scale or construction fixes it."* N02 got
**TOUCH-RATE MISMATCH**, which is what a mis-specified population produces.

**This is the N04/N05 precedent applied, not evaded.** There, `swing_pivots` had
`ref_price = price`, forcing distance to zero by definition. That bug was fixed, the level set
re-measured - **and the degeneracy was still there underneath**, because it was a real
property the bug had been hiding. Fixing a construction defect and re-measuring is what
distinguishes a bug from a property. It is not a rescue attempt, and it did not rescue pivots.

### The corrected definition, stated in full BEFORE it runs

**Population.** For each session, the **two nearest 50-point grid levels above and the two
below the session-open close** - four levels per session, deterministic, chosen without any
reference to where price subsequently goes.

**`valid_from`.** Session start. The levels exist from the open; nothing about them is
discovered later.

**`ref_price`.** The session-open close. Distance is then |grid level - session open|, which
measures reachability exactly as 46 requires.

**What this changes.** Touch rate becomes an OUTCOME rather than a selection criterion.
Expected real touch rate is high but well below 100% - the nearest level sits under 50 points
away and the second under 100, against typical MNQ session ranges of several hundred points.
Expected median distance is larger than the first attempt's 10.5, around 35-40 points, since
the population now includes far levels that the touch-based construction discarded.

**What this does NOT change.** The traded condition is unaltered: price trades through a level
by d points, enter in the break direction, exit at H=180 or 15:55 ET, d in {2,4,8}.

### One re-measurement, and it is binding

**This is the only re-measurement.** If S6 passes, N02 proceeds to S7 with this construction
correction recorded as part of its provenance. **If it fails, N02 withdraws and the N-series
closes with zero registrations from ten candidates** - no third attempt, no alternative band,
no re-scoping, and the closeout gets written rather than another option brought back.


### Outcome: S6 MATCHED on both products

| | MNQ | MGC |
|---|---|---|
| levels | 16,496 (4.0/session) | 16,020 (4.0/session) |
| real distance median | 50.00 | 50.00 |
| zero-share | 0.13% | 0.07% |
| touch real / placebo | 40.1% / 39.5%, **ratio 0.98** | 11.5% / 12.2%, **ratio 1.06** |
| distance ratio | 0.82 | 0.88 |
| **verdict** | **MATCHED** | **MATCHED** |

**The diagnosis in this entry was right, and the evidence is that touch rate now behaves like
a measurement.** It fell from an imposed 100.0% to an observed 40.1% (MNQ) and 11.5% (MGC) -
wildly different between products, which is what an outcome looks like and what a selection
rule cannot produce. The circularity was the whole failure.

### Two prediction misses, and one of them was avoidable

**The median distance is exactly 50.00, not the 35-40 predicted - and that was DERIVABLE, not
estimable.** Four levels drawn symmetrically around the session open put two at 0-50 points
and two at 50-100 on either side, so the median lands on the grid spacing by construction.
**A mechanical property of the population should be COMPUTED before it is stated, not guessed
at.** Predicting a number that follows deterministically from a definition I had just written
is the sloppier of the two misses, and the cheaper to have avoided.

**MGC's real touch rate is 11.5%, far below the "high but well below 100%" I implied.** Gold's
session range rarely spans two 50-point grid steps, so most of its level population is simply
unreachable within a session.

### MGC is unavailable to N02 as a robustness instrument

**This is a downstream constraint, not an observation.** S8 conventionally asks whether an
effect holds on another market. For N02 that route is **closed before it is tried**: at an
11.5% touch rate most of gold's population is out of reach within a session, so MGC cannot
supply a comparable event count no matter what the effect is.

The S6 match on MGC is genuine - the placebo is correctly matched to a mostly-unreachable
population - which makes this easy to misread as an open route. It is not one. **N02's S8
evidence will have to come from the era split alone**, and a later reader should find that
here rather than discover it when the cross-market check comes up empty.

### An ordering slip, caught and corrected

**S5 was validated on the OLD, circular population; S6 then passed on the CORRECTED one.** The
rule from 46 is S5 before S6, and changing the population invalidated the S5 evidence without
invalidating the rule. The corrected population is re-gated at S5 before S7 runs. Recorded
because it is the same ordering error as L11's in a subtler form: there the stages ran out of
order, here a stage's input changed underneath a passed gate.


## 50. N02 re-checked on the corrected population before S7 (S2-S5)

Recorded before any trial is spent, because the population change in 49 invalidated three
things that had already been written down as settled.

**S5 re-gated, not inherited.** The corrected population passed: d=2/4/8 fire 7,184 / 7,013 /
6,679 with entry-minute sd 412-416, up-share 0.51, and the identical-minute share falling as d
tightens (49.5% -> 31.4%), so d selects rather than offsets.

**S3 fell from 26,200 to ~7,000 events.** The circular population admitted every level price
touched; the corrected one holds four per session. Measured and routed to
`measured_rates.json` via a direct N02 dispatch - N-series rates are not in
`level_rates.json`, so they are measured, not routed from elsewhere. Independent counts at
H=180: 5,742 / 5,574 / 5,284.

**S2 moves from PROVABLE to STRADDLES.** DEFF measured on this population at 1.42-1.66 - lower
than the 2.19 measured at 7.68 events/session, as sparser events should be - giving BH bars of
2.21-2.46 at k=3 against a 2.0-5.0 prediction. The bottom ~5-10% of the range is unreachable;
eff/bar at the midpoint 1.42-1.58, eff/cost 7.3x. Same standing N05 had: registered under
surface-don't-reject, and a null near 2 bps is weak evidence.

**The cell count in the entry was wrong: three cells, not nine.** The grid is d in {2,4,8} at
H=180 only. BH rank-1 is computed at k=3.

**N02 is now schedulable and S7 runs next.** 3 trials, N 756 -> 759.


## 51. N02 retired at S7; fixed-point thresholds on a 14x price range (S7/S8)

3 trials. **N 756 -> 759, SR\* 0.1369.** Report: `reports/n02_stage1.md`.

**0 of 3 cells separate, 0 BH survivors.** Diffs +1.14 / +0.15 / -1.07 bps against a
registered +2.0 to +5.0; pooled ~+0.07. Retired on the pre-registered clause *positive mean,
no BH survivor*. **Power at the 3.5 bps midpoint was 68-78%**, so unlike L12 the significance
limb was reachable, and the magnitude limb refutes on its own.

### The era split looked striking; the defect behind it is programme-wide

Per 46's standing rule the striking number was hunted before any write-up. The era split
flipped sign - 2010-18 d=8 **-8.66 bps, p=0.0075**; 2024-26 d=2 **+4.43, p=0.033** - with both
CIs excluding zero.

**Cause: N02 is specified in index POINTS, and the index rose 14x over the sample.** Median
1,939 in 2010, 27,528 in 2026. The 50-point grid was 258 bps apart in 2010 and 18 bps in 2026;
d = 8 points was a **41 bps** breakout in 2010 and a **2.9 bps** one in 2026. Each cell is a
different condition in each era. The sign flip compares two different trades and says nothing
about decay or emergence; the 2024-26 positive is one of nine post-hoc era sub-tests with two
nominal hits in opposite directions.

**This is not confined to N02.** Every threshold in this programme specified in ticks or points
and run over the 2010-2026 spliced series carries the same non-stationarity. MNQ's 0.25-point
tick was ~1.3 bps in 2010 and ~0.09 bps in 2026. **L02, L03 and L04's m (ticks), L07's gap
width w (ticks), L12's m and the N04/N05 penetration depths are all denominated this way.** For
the L-series that means each cell pooled a threshold that was ~14x tighter in relative terms
early in the sample than late. **No status changes - report only** - but it means L07's
w-sweep, which the selectivity finding of 45 rests on, was sweeping a quantity that drifted by
an order of magnitude within each cell. The direction of the selectivity result is unlikely to
depend on it; its exponents may.

**S5 and S6 cannot catch this.** S5 checks that a condition selects events; S6 checks the
placebo is matched on distance and touch - both are computed on the pooled sample and both
passed. Scale stationarity is a property across TIME and no current gate looks there.

### Proposed standing S2 check

A registered threshold must be scale-invariant over the sample - bps, volatility units or ATR
multiples - or its registration must state the price range it spans and pre-register the era
split. Surface, don't reject, as with 45's magnitude check.

### The N-series closes

Ten candidates; **one tested, zero promoted.** N02 retired at S7; N04/N05 withdrawn at S6;
N01/N03/N06/N10 declined on arithmetic; N08 deferred; N07 closed as a conditioner with no
primary; N09 never a registration. 3 trials spent in total.


## 52. Scale invariance: a failure class with no gate, and L07's exponents re-measured (S2, S5-S8)

**A programme finding, recorded apart from N02** (51 was where it surfaced).

### The failure class

The spliced NQ/MNQ index rose **14x** over 2010-2026 (median 1,939 in 2010, 27,528 in 2026).
**Every threshold in ticks or points has therefore been running a different trade in each era,
pooled into one cell.** MNQ's 0.25-point tick was ~1.3 bps in 2010 and ~0.09 bps in 2026. N02's
8-point break was a 41 bps move early and a 2.9 bps move late.

**No gate could see it.** S5 checks that a condition selects events; S6 checks the placebo is
matched. Both are computed on the pooled sample, so both pass while the condition drifts by an
order of magnitude underneath them. Scale stationarity is a property across TIME, and nothing
in S1-S8 looked across time before S8's era split.

**It belongs with the other structural findings**, each a gap between the quantity measured
and the quantity meant:

| finding | what was measured | what was meant |
|---|---|---|
| `confirmed_break` (41) | a firing count | a selection of events |
| missing magnitude (45) | a null | a null against a stated effect |
| S5-before-S6 (44) | a matched placebo | a placebo for a valid treatment |
| **scale invariance (here)** | **one cell** | **one trade** |

### The S2 check, registered

`reports/STAGES.md` S2: a threshold must be scale-invariant over the sample (bps, volatility
or ATR units), **or** the registration must state the price range it spans and pre-register an
era split. **Surface, don't reject.** Round-number LEVELS are legitimately in price units; the
point is that the choice is declared.

`test_schedulable_entries_declare_threshold_units` enforces it. **No entry is schedulable
today, so the test currently checks nothing.** It gates the next registration without
rewriting entries that predate it, which is the intent.

### L07's selectivity exponents, re-measured with w scale-invariant

45's "selectivity, not firing rate" rests on L07's w sweep, and w was in ticks across the same
14x range. Re-measured with a new `w_bps` option on `fvg_zones_directed` (default behaviour
unchanged; the L07 tests still pass) - same arm, same bootstrap, both units, log-log fits
across the sweep. The first points cell reproduces L07's committed MNQ w=2/5m/g=10 cell
exactly (n 96,377, |eff| 3.777), so a difference could not be a harness artifact.

| | effect decay | bar fall | bar - effect |
|---|---|---|---|
| points, MNQ 5m | 0.385 | 0.689 | 0.304 |
| **bps, MNQ 5m** | **0.417** | **0.664** | **0.247** |
| 45 original, MGC 1m, endpoints | 0.412 | 0.624 | 0.212 |

**The exponents survive.** Changing units moves each by ~0.03; the bar falls faster than the
effect decays in both; the bps figures sit within 0.04 of 45's. **45's finding stands in
direction and approximate magnitude and is not restated.** Economics at the tight end also
hold: eff/cost 17.38 (points w=32t) against 16.67 (bps w=6.4).

**The drift was real and concentrated at the tight end:**

| zones/session | 2010-18 | 2019-23 | 2024-26 |
|---|---|---|---|
| points w=2t | 31.0 | 48.4 | 49.7 |
| points w=32t | **0.8** | 9.8 | **15.9** |
| bps w=0.4 | 41.3 | 46.9 | 45.3 |
| bps w=6.4 | 5.0 | 10.3 | 7.7 |

The tightest points cell was effectively a late-sample-only cell - 20x more zones per session
in 2024-26 than 2010-18. In bps the spread falls to ~2x and follows volatility regime rather
than price level. It left the exponents intact; it would not necessarily leave a per-cell
effect estimate intact, which is why the S2 check exists.

### Downstream uses, checked

- **Headroom estimates (45)** - rest on the decay/fall exponents, which survive. Hold.
- **Boundary sweep (45: eff/cost peak at w=24/tf=30m)** - run in points and on tf=5/15/30m.
  The 5m arm's exponents are confirmed in bps; **the peak's exact location was NOT re-measured
  in bps** and is unverified. The design principle (start tight, L/w is the cheap knob) holds.
- **N04/N05 parameters** - withdrawn at S6 (46) for an unrelated reason; nothing to revisit.
- **The x1.54 uplift, declined** - computed from the 0.412 decay exponent, now measured at 0.417
  in bps. The uplift would have been essentially the same, and it was declined on principle
  (a prediction should not be set by transfer from a refuted mechanism), which is untouched.

### The era split found something real by looking for something else

It was requested for N02 because R01 had decayed after 2024. It found no decay; it found a
mechanical scale artifact. **A check aimed at one failure surfaced a different, unguarded
one.** That is the argument for running it on every S7 result by default rather than on
suspicion, and STAGES.md S8 now says so.


## 53. The boundary peak does not survive in bps; the S2 scale check fault-injected

The two items 52 left open. No trial spent; N stays 759.

### The boundary peak (S8 design input)

45 placed the eff/cost optimum at **w=24 ticks / 30m, 18.41x**, turning down by w=32/30m
(15.59x). 52 confirmed the decay/fall exponents in bps but only on the 5m arm, leaving the peak
location - the specific parameter a future registration would inherit - unverified. Re-run on
the 15m and 30m arms in bps, same harness as `sweep_tight_l07.json`:

| tf | w_bps | f/sess | \|eff\| | eff/bar | eff/cost |
|---|---|---|---|---|---|
| 15 | 1.6 | 4.55 | 5.79 | 5.21 | 12.06 |
| 15 | 3.2 | 3.07 | 6.45 | 4.89 | 13.45 |
| 15 | 4.8 | 2.15 | 7.01 | 4.28 | 14.61 |
| 15 | 6.4 | 1.57 | 9.27 | 4.27 | 19.31 |
| 15 | 9.6 | 0.93 | 9.83 | 3.39 | 20.47 |
| **15** | **12.8** | **0.58** | **12.06** | **3.08** | **25.13** |
| 30 | 1.6 | 1.60 | 6.86 | 3.99 | 14.30 |
| 30 | 3.2 | 1.15 | 6.59 | 2.90 | 13.74 |
| 30 | 4.8 | 0.85 | 7.20 | 2.37 | 15.00 |
| 30 | 6.4 | 0.64 | 9.79 | 2.75 | 20.39 |
| 30 | 9.6 | 0.39 | 8.90 | 1.85 | 18.55 |
| 30 | 12.8 | 0.26 | 12.72 | 1.84 | 26.50 |

**The peak DISAPPEARS as an interior maximum.** In bps eff/cost keeps rising to the tightest
cell tested on both arms. The points "turn" at w=32/30m does not reproduce; the single
downward step in bps (30m, 6.4 -> 9.6) sits in cells of 1,075-2,629 events where the bar is up
to 6.93 bps, i.e. eff/cost uncertainty of roughly +/-10, so it is noise and the tight cells
cannot be ranked against each other.

**The points location w=24 ticks / 30m is SUPERSEDED.** `sweep_tight_l07.json` now carries
that note in every record, because a later reader opens the data file, not this entry.

**Operative bps setting, under 45's stated objective (maximise eff/cost subject to eff/bar
comfortably above 1): 15m / 12.8 bps** - eff/cost 25.1, eff/bar 3.08, 0.58 firings/session.
The 30m arm reaches the same economics (26.5) at eff/bar 1.84, which is not comfortably above
1.

**The tf-is-expensive rule holds in bps.** At the same w, 15m -> 30m moves eff/cost 25.1 ->
26.5 and collapses eff/bar 3.08 -> 1.84.

**The true optimum is UNRESOLVED** - at or beyond 12.8 bps, the grid edge once again. No
registration depends on it; it is recorded as an open design question, not a blocker, and a
future registration citing it must sweep past the edge first.

### The S2 scale-invariance check, fault-injected

52 registered the check and noted it enforced nothing, since no entry is schedulable. By 46's
own standard that made it an assumption. The check is now a function taking a registry, and
fed deliberately:

| injection | real check | sabotaged check (never fires) |
|---|---|---|
| point threshold | raises | **does not** - test fails |
| tick threshold | raises | **does not** - test fails |
| units undeclared | raises | **does not** - test fails |
| era split pre-registered, price range not stated | raises | **does not** - test fails |
| bps / BPS / volatility / ATR | passes | passes |
| points + stated price range + pre-registered era split | passes | passes |
| unschedulable point entry | passes (history not rewritten) | passes |

**Every raise-injection fails against a check that cannot fire**, so the tests detect a dead
check, not merely a live one. 42/42 pass on the real check. Recorded the same way as the DBN
loader's truncation injection and the 41 guard's discrimination test.

**The injection found a defect in the check as written in 52.** STAGES.md's escape hatch
requires BOTH a stated price range AND a pre-registered era split; the check tested only the
era split, and would have admitted the half-escape-hatch case. Fixed. **A check that had never
fired was also looser than its own specification**, and nothing would have shown it until an
entry depended on it.

### The bps result supersedes 45's conclusion, not just a data file

**Corrected claim.** 45 concluded that the eff/cost optimum sits at **0.65 firings/session**,
essentially where the L-series already operated (L12 1.46, L04 1.5), and therefore that
once-per-session conditions were near the economic optimum. That rested on the points-
denominated peak at w=24 ticks / 30m, which does not exist in bps. **The conclusion is
withdrawn.**

**What replaces it.** In bps the eff/cost curve rises monotonically to the tightest setting
tested on both arms. So:

- **the L-series was on the correct side of the curve but NOT at an optimum** - it operated
  near 1.5 firings/session, and eff/cost was still climbing well below that;
- **the optimum is tighter than anything this programme has swept**, at or beyond 12.8 bps;
- **selectivity as the design lever survives and is strengthened** - there is no interior
  point at which tightening stops paying economically within the range tested; the constraint
  that eventually binds is provability (eff/bar), not economics.

The historical text of 45 is left as written, per the decisions-log convention; this entry is
the correction and 45 should be read through it.

### The two-optima decision is orphaned

45 recorded the choice of a 3-6.5 firings/session operating band as a PREFERENCE between two
peaks an order of magnitude apart: eff/cost at w=24 ticks / 30m and eff/bar at w=12 ticks /
5m. **One of those peaks is gone**, so the trade-off it described no longer holds. Nothing
depended on it - the only registration it parameterised, N04, was withdrawn at S6 for an
unrelated reason - but the reasoning is invalid and marked ORPHANED in N04's registry entry so
it is not reused. (That entry's key also carried a stray non-ASCII character,
`two_optima_是_a_preference`, a typo from its registration; fixed.)

### 45 has now been revised three times, each time by measurement

1. **Premise** - the N-series draft selected for firing rate on the view that once-per-session
   conditions were the L-series' structural defect. Corrected by measuring the unit of
   observation (sessions, not events) and the decay exponents: selectivity, not firing rate,
   is the lever.
2. **Exponents** - re-measured with the gap threshold in bps after the 14x scale finding (52).
   **They held** (0.417/0.664 against 0.412/0.624); the revision was a verification, and it
   converted a points-denominated result into a scale-robust one.
3. **Optimum location** - the 0.65 firings/session peak was a points artifact; in bps the curve
   rises to the edge of the tested range.

**None of the three came from argument.** Each came from a measurement that someone chose to
run on a result already written down as a finding. **And each time the revised version was
more useful than the original**: the premise correction changed the design lever, the
exponent check made it scale-robust, and the optimum correction points the next sweep in the
right direction instead of anchoring it on a peak that was not there.

That is worth keeping as an observation in its own right: **a recorded finding in this
programme has been more reliable after it was re-measured than when it was first written, and
the cost of re-measuring was always lower than the cost of building on the unrevised version.**

### The programme, closed on measurements

**Four series. N = 759. SR\* 0.1369. Nothing promoted.**

| series | registered | trials | promoted | closed |
|---|---|---|---|---|
| F | 14 | 576 | 0 | futures_conclusion.md |
| R | 5 | (separate repo) | 0 | rseries_conclusion.md |
| L | 12 | 180 | 0 | level_conclusion.md |
| N | 1 of 10 candidates | 3 | 0 | 51 |

Every route is resolved or explicitly blocked. What remains open is recorded as open, not
dropped: the bps eff/cost optimum beyond the grid edge (here); L04's `sess_Asia` revival route
(43, 45); the `d` ATR reference period for L01/L06/L08 (a specification question, frozen);
participation measures on MNQ/NQ (48, reopened, untested); L07's direction-mix asymmetry (38);
and `f01_rates`' OOM on this laptop (CHECKPOINT).


## 54. P-series S1 draft reviewed: magnitudes, control design, corrections (S1, S2, S6)

The draft is saved as `P_SERIES_CANDIDATES.md` with corrections inserted as **[§54]**
blocks. **Nothing registered, no S5 or S6 run, no trial spent. N stays 759.**

### Data claims checked against disk, before any arithmetic

| claim in the draft | on disk |
|---|---|
| P02/P10: 672 spread files "on hand, unused" | present as raw `.csv.zst` only; **`parse.py` discarded them** before parquet |
| P09: ~40 years of COT usable | COT yes, but **GC is not on disk**; tradeable MGC starts 2010 (~830 weeks) |
| P12: MGC micro-share computable | **no** - needs GC volume, not on disk |
| P07: small-lot share needs `trades` | confirmed - the parquet `trades` column is 100% null |
| sample sizes | 4,125 spliced sessions; 4,006 MGC; **2,246 with both MNQ and NQ trading** |

### Task 1: a predicted magnitude for all thirteen

**Basis, and its limit.** These are PRIORS, not measurements, from three sources: the
programme's own observed effect range at 180m (maximum 5.0 bps, L07; typical 0.3-3.5), a
mechanistic bracket where one exists, and the direction of published results. **Literature
magnitudes are recalled, not verified in this session**, and are used for sign and order of
size only.

**Bar arithmetic** uses the repo's measured anchor (SE = 64.7 / sqrt(units) bps at 180m,
scaled by sqrt(horizon)), BH rank-1 at k=9, and effective units as a best/realistic bracket
built from session counts and the measured DEFF families of §45 (spread-out events 2.19;
clustered or persistent states higher). Cost floor 0.48 bps MNQ, 0.65 MGC.

| id | horizon | predicted bps | vs cost | units best/realistic | BH bar | verdict |
|---|---|---|---|---|---|---|
| **P03** | 180m | 1.0-4.0 | 2.1-8.3x | 13,185 / 5,775 | 1.56 / 2.36 | **above cost; straddles bar** |
| **P05** | 180m | 0.5-3.0 | 1.0-6.2x | 13,185 / 5,775 | 1.56 / 2.36 | at cost at low end; straddles (purchase) |
| **P04** | RTH | 2.0-8.0 | 4.2-16.7x | 2,062 / 825 | 5.81 / 9.19 | above cost; mostly below bar (conditioner) |
| P07 | 180m | 0.5-2.0 | 1.0-4.2x | 13,185 / 5,775 | 1.56 / 2.36 | at cost at low end; straddles (purchase) |
| P01 | 180m | 0.5-2.0 | 1.0-4.2x | 1,795 / 1,123 | 4.23 / 5.35 | at cost at low end; **below bar even best case** |
| P11 | 180m | 1.0-5.0 | 2.1-10.4x | 800 / 800 | 6.34 | above cost; below bar |
| P08 | daily | 2.0-10.0 | 4.2-20.8x | 2,062 / 1,031 | 10.9 / 15.5 | above cost; below bar |
| P09 | weekly | 5.0-20.0 | 7.7-30.8x | 332 / 166 | ~72 / ~102 | above cost; **below bar by 4-15x** |
| P02 | - | **cannot predict** | - | - | - | contamination differential; no live primary |
| P10 | - | **cannot predict** | - | - | - | exclusion test; no live primary |
| P06 | - | **cannot predict** | - | - | - | no trade rule |
| P12 | - | **cannot predict** | - | - | - | no trade rule; GC absent |
| P13 | - | **cannot predict** | - | - | - | conditioner; no direction |

**Reasoning for the predictable eight:**

- **P03 (1-4 bps).** A mechanistic bracket exists: a 5m MNQ move has sd ~11 bps, a two-sigma
  thin move is ~20 bps, and 5-20% excess reversal relative to a normally absorbed move gives
  1-4. The direction is consistent with the volume-reversal relationship in Campbell,
  Grossman and Wang (1993): low-volume price changes reverse more. The top of the range sits
  at the programme's observed maximum.
- **P05 (0.5-3).** OFI's price impact is overwhelmingly contemporaneous and its predictive
  component decays within minutes (Cont, Kukanov and Stoikov, 2014). Divergence cases are a
  minority. At 5-180m a small residual, and the draft rightly notes it is mined.
- **P04 (2-8, RTH hold).** Overnight moves on thin Globex books partially corrected when RTH
  liquidity arrives; larger in bps because the hold is session-length.
- **P01, P07 (0.5-2).** Boehmer et al. (2021) find no aggregate-level prediction from retail
  imbalance, and aggregate is where MNQ/NQ trades. Reduced to an information-content claim,
  both are noisier proxies for thin-book conditions than P03, so they are bounded below it.
- **P11 (1-5), P08 (2-10), P09 (5-20).** Longer or event-anchored horizons scale the bps up;
  the event counts do not scale with them.

### The findings from task 1, which matter more than the table

**No candidate is cleanly above both the cost floor and its BH bar.** The best, P03, clears
cost across its range and straddles its bar; nothing else does better without a purchase.

**Five of thirteen cannot state a magnitude at all** - P02, P06, P10, P12, P13. That is a
finding, not a gap in the review: an entry with no trade rule, or one whose only value is as
a differential on a primary, cannot pass the S2 magnitude check as that check is written.
Four of the five are conditioners or contamination tests, and **all four series are closed**,
so there is nothing for them to condition.

**Every "n: High" in the draft repeats the unit error §45 corrected.** The draft counts bars
that satisfy a quantile condition. The bootstrap unit is the session, holds overlap, and a
persistent state clusters into whole sessions. P01 is the sharpest case: "High" becomes
~1,100-1,800 effective units on a 7.3-year sample, and a BH bar of 4.2-5.4 bps against a
predicted 0.5-2.0.

### Task 2: control design - partly a category error, partly still open

**The location placebo is a category error for state conditions.** §37's null asks "is this
location special?" by building an arbitrary region at a matched distance. A state has no
location and nothing to displace - the same wall N04/N05 hit at S6 (§46) from a different
direction.

**The F14 pattern transfers only in part, and the part that matters already exists.**

1. **F14 as built is not rate-matched.** It fires at thirteen fixed RTH slot opens with a hash
   bit for direction, and its registered scope is harness validation at ~45,000 events. A hash
   control thresholded to the real condition's rate would be a new construction.
2. **A rate- and clustering-matched chance-alignment null is already inside every S7 run.**
   `signed_rotation_null` rotates the entire direction series circularly against returns: the
   firing count and its clustering are preserved exactly, and only the alignment with returns
   is destroyed. That is strictly stronger than a hash control fired at the same rate, which
   would preserve the count but not the clustering. **Building the proposed control would
   duplicate the rotation null with a weaker one.**
3. **F14 still transfers as a harness check** within its own scope, and §17's structural limit
   stands: conditions firing about once a session cannot have a real-data negative control of
   any construction.
4. **What neither covers is exposure.** A state condition that fires disproportionately in
   high-volatility regimes, at particular times of day or (for P01) in particular years can
   beat the rotation null because of WHEN it fires - rotation moves the signal into different
   regimes, so the confound is not held constant. **The S6 analogue for a state condition is a
   confound-matched comparison**: the same trade rule on entries drawn from outside the state,
   matched on time of day, trailing volatility and calendar year, with its own `verify`-style
   matching check.

**Decision recorded: the placebo question was MISFRAMED, not solved.** The alignment half was
answered long ago by the rotation null; the location half does not apply; the confound-matched
control is the genuinely open design question, and it must be built and fault-injected
before any state condition proceeds to S7. Recording "misframed rather than solved" without
the fourth point would have overclaimed.

### Task 3: corrections to the draft

- **P01: the sample bound is part of the entry.** MNQ launched 2019-05-06: **~7.3 years, 2,246
  sessions**, with the 0.292 -> 0.822 adoption curve dominating much of it. Not sixteen years.
- **P02: value is contingent.** A contamination conditioner improves a live primary; there is
  none. Kept, and not ranked first on a benefit that is not currently available. Its data also
  needs a parse change.
- **P03: the draft's scale note is wrong** (found in review, not in the brief). |return| per
  contract is not scale-invariant: the spliced series switches NQ -> MNQ on 2019-05-31 at one
  tenth the notional; measured median 1m bar volume falls from 83-140 (NQ, Mar-May 2019) to
  26-39 (MNQ, Jun-Jul 2019), so the ratio steps up ~3-5x at the splice, then trends within each
  segment (median 16 in 2010, 784 in 2026). Threshold relative
  to a trailing same-contract volume norm, or use `NQ.parquet` for the whole sample. **Ratio
  form is not scale invariance** - the same class of error §52 recorded.
- **P09: the 40 years are not available** without GC prices; MGC gives ~830 weeks.
- **P12: GC checked and absent**; the entry cannot proceed without a purchase.

### Recommended registration order, from the magnitudes rather than the draft

1. **P03** - the only candidate that clears cost across its predicted range and reaches its
   bar without a purchase. Register only after the volume normalisation is specified and the
   confound-matched control exists.
2. **Build the confound-matched control first.** It gates every state condition, including
   P03, and it is the open item.
3. **P05** - conditional on a purchase being justified on its own terms. Straddles its bar,
   at cost at the low end, and mined.
4. **P04, P08, P13 as conditioners, P02/P10 as contamination tests** - contingent on a primary
   surviving S7. Nothing to do until one does.
5. **Not registrable as specified:** P01 (below bar even best case), P07 (at cost at its low
   end, contested, purchase), P09 (4-15x below bar, no GC), P11 (below bar, N10 class),
   P06 and P12 (no trade rule; P12 also no GC).

On this arithmetic the honest summary is that **one of thirteen is worth registering first,
and only once a control that does not yet exist has been built.**

### The mode partition is a property of the control, not a P03 detail (added 2026-09-13)

§55 found the two exclusion modes while building P03's control, which makes them look like a
P03 implementation note. They are not. **The partition is a property of the control itself, and
every P-series candidate falls on one side of it:**

| | fires | control mode | failure mode of the WRONG choice |
|---|---|---|---|
| **frequent states** (P03, P05, P07, P13) | many times per session | **bar** — strict is structurally unavailable | strict leaves an unrepresentative residue of quiet years |
| **session-level states** (P01, P02, P04, P08, P09, P11) | about once per session | **strict** — bar mode has no meaning | bar mode would draw a "control" from inside the state |

**Neither mode is a preference and neither is always available.** A state firing several times
a session touches nearly every session — at P03's 7.81/session even a perfectly INDEPENDENT
state would touch ~99.9% of them — so the clean pool strict mode needs does not exist, and the
265 sessions that survive on NQ range from 0% of 2011 to 17.5% of 2025. A session-level state
has the opposite problem: the state IS the session, so excluding only the firing bars would
draw the control from inside the condition, and strict mode is the only meaningful one. But
strict mode is exactly the mode that fails when clean sessions are scarce, and scarcity is a
property of the state's base rate, not of the code.

**Therefore a CLEAN-POOL CHECK is a registration-time requirement, not a diagnostic to run
afterwards.** `session_clustering()` reports firings per session, share of sessions touched,
over-dispersion and clean-pool size; a session-level state whose clean pool is thin has no
valid control and is not registrable, in the same way L06 is not registrable because its levels
sit at the reference price (§37). Added to `STAGES.md` under S6 beside the placebo requirement,
because S6 is where a condition without a valid control must stop.

### The Int8 overflow, recorded in the truncated-read terms

`dt.hour() * 60` wrapped in polars — `dt.hour()` is Int8, so 18:00 ET evaluated to **56 instead
of 1080**. It was caught because the RTH filter then matched nothing and the run died on an
empty frame.

**That it failed loudly was a property of the window, not of the check.** The filter spanned
09:30–16:00, which the wrapped values miss entirely. A NARROWER window — or one whose wrapped
values happened to overlap it — would have returned a smaller, plausible, wrong set of bars,
and every downstream number would have been computed correctly on the wrong input.

**Same class as the zstd truncation the loader guards against** (`batch_ftp.py`): a truncated
`.zst` decompresses cleanly to a shorter file, which is why that path verifies SHA-256 and size
against the manifest rather than trusting a successful read. In both cases the defect produces
**a silent wrong answer indistinguishable from a right one**, and in both cases the only
protection is a check that does not depend on the operation appearing to succeed. The cast is
now explicit with the reason recorded at the line.

### P01's position, recorded honestly

P01 fails on **two independent grounds**, and it is worth separating them because the second
was not visible when §54's table was written:

1. **Below its bar.** Predicted 0.5–2.0 bps against a BH bar of 4.2–5.4 at 1,123–1,795
   effective units on the 7.3-year sample. Not close, and the best case does not reach it.
2. **It requires the mode that fails on its own sample shape.** Micro share is a session-level
   state, so it needs strict mode. Its base rate went 0.292 → 0.822 (§48), so in its late years
   there are almost no sessions where the state does not hold — exactly the scarce-clean-pool
   case above. The era fallback would then carry the comparison, which is the adoption curve
   being compared against itself.

**§48's persistence finding stands on its own and is not withdrawn.** Volume share persists at
1.44 bars detrended against the basis's 0.25, and that measurement is unaffected by anything
here. **What does not follow is that THIS TRADE RULE inherits it.** A persistent observable is
a necessary condition for a tradeable state, not a sufficient one: P01 additionally needs a
reachable magnitude and a constructible control, and it has neither. Recorded so that a later
reader does not treat §48 as having pre-cleared P01.

### Attribution, recorded on request 2026-09-13

Two items above were softened by passive phrasing in the first write-up. Corrected here in the
same terms as N06's ranking error (§45), because who made an error and when is part of what
makes the record usable.

1. **The unit error is the draft author's, and the draft was written AFTER §45.** Every
   "n: High" in `P_SERIES_CANDIDATES.md` counts BARS satisfying a quantile condition, not
   effective units. §45 had already recorded exactly this failure - N06's 18.8 firings/session,
   and the errors §41 and §45 themselves cite - and the P-series draft repeated it in a document
   written later. **Same shape as N06: a number that looked like an advantage was an artifact
   of not checking what the unit of observation actually was.** It is not a review finding that
   the draft happened to omit; it is a known error class recurring after its correction was
   written down, which is worse, and is why it is recorded here by name rather than folded into
   the table.

2. **P03's scale claim was the draft's, and the REVIEW caught it.** The draft asserted
   "Ratio-form observable, so §52's check passes natively." That assertion is wrong, and it was
   not corrected in the brief - it was found in this review by measuring the splice: median 1m
   bar volume falls from 83-140 (NQ, Mar-May 2019) to 26-39 (MNQ, Jun-Jul 2019), so the ratio
   steps up ~3-5x at a contract change that has nothing to do with liquidity. **A ratio is not
   automatically scale-invariant; it is scale-invariant only if its denominator is stationary,
   and contract size is not.** §52 exists because this class of error is invisible until
   measured, and the draft's sentence offered an assertion in place of the measurement.

Both corrections are in the entries themselves, marked **[§54]**.


### Decisions taken rather than resolved silently

1. **Predictions are priors and say so.** They set expectations for S2; they are not evidence
   and no entry's status depends on them.
2. **k = 9 throughout** for comparability with §45-§53; conditioners with fewer cells would get a
   modestly lower bar, which does not change any verdict above.
3. **The draft is saved with corrections inserted, not rewritten**, so proposal and correction
   remain distinguishable.
4. **CHECKPOINT's State section was stale** (N = 684, L11 unmeasured, L07 the latest run) and is
   corrected in the same commit - the failure mode §36 records.


## 55. The matched control for state conditions, built and fault-injected (S6)

Report: `reports/state_control.md`. Code: `signals/state_control.py`,
`reporting/state_control_feasibility.py`. Tests: `tests/test_state_control.py`, 17 passing.
**Nothing registered, no trial spent, no return series scored anywhere in this work.**

### What was built

§54 left one part of the placebo question genuinely open: a state condition can beat the
rotation null by firing in favourable REGIMES rather than by carrying information, because
rotation moves the firings into different times of day, volatility regimes and years instead
of holding them constant. The control transposes the level design — `make_region_placebo`
matched the nuisance (distance, which determines exposure) and varied the claim (real level
vs arbitrary region):

    matched      time-of-day bucket, volatility quantile, year
    varied       the state holds vs the state does not hold
    reported     era-fallback rate, control-bar reuse, unmatched share

Diagnostics follow §49's distance and touch ratios: a share-ratio test per axis, tolerances
fixed before the first run (0.10 on the two constructed axes, 0.25 on the year, 5% on the
fallback and unmatched shares), and a MATCHED/FAIL verdict that raises rather than returning a
caveat. The statistic is real-minus-control with a SESSION bootstrap, pinned by test against
`sweep_stage1.paired_stats` so the two cannot drift.

### The claim was verified rather than accepted, and that was the point

§54's claim — a condition cannot beat this control by firing in favourable regimes, because
the control fires in the same regimes by construction — is the same SHAPE of claim as the
P-series draft's "ratio-form, so the scale check passes natively", which §54 had just recorded
as false. So it was fault-injected:

1. a deliberately REGIME-LOADED fake condition, firing on even-numbered sessions inside a
   drifting high-volatility regime and carrying no information by construction, **does beat a
   rotation null**. The danger is real and not hypothetical.
2. the same condition **does not beat the matched control**.
3. a **genuine** state effect **does** beat it. Without (3), (2) would also pass for a control
   that is null against everything, which is the trivial way to look rigorous.

Plus the construction's guarantees: per-pair cell matching rather than on-average, determinism
across processes, DEGENERATE as its own failure kind (§49's distinction), and injected
corruption of each matched axis caught with the right failure kind.

### Two design changes forced by measurement

**The year is matched, not merely measured.** The first design left it free so that a trending
state would be blocked by a year-share ratio. Measured, that check has a NOISE FLOOR: a
condition with NO year trend deviates 0.37 (median, up to 0.55) at ~262 sessions/year over 16
years — the real sample's shape — against a 0.25 tolerance. **The check would have failed
well-behaved conditions at the sample size it was built for.** Widening the tolerance would
have been fitting the null to the test, so the construction changed: the draw is stratified by
year with fallback where a year holds none. Year deviation is then 0.000 at every realistic
size, and a trending P01-shaped state is still blocked at ~28% ERA FALLBACK. Both pinned.

**Whole-session exclusion is structurally unavailable to a frequent state.** Excluding every
session the state touches is right for a session-level state (volume share: 0.952
autocorrelation, §47) but presumes clean sessions exist. On real data they mostly do not, so a
`bar` mode was added: exclude the firing bars, still require a different session. Its control
bars are partly in-state, which **costs power, not validity** — the regimes are still matched
pair by pair, so a regime-loaded condition gains nothing, and contamination only shrinks a real
difference. The regime-loaded fake is run through bar mode too rather than assuming the
argument transfers.

### Feasibility measured on real data (matching only, no returns)

P03-shaped state on NQ — 5m RTH bars, |bps| / volume, trailing 90th percentile of the same
30-minute bucket over the previous 60 sessions:

    bars 272,970   sessions 3,559   firings 27,791   7.81/session
    sessions touched 92.6%   variance ratio vs Poisson 7.38   clean sessions 265

| exclusion | distinct control bars | reuse | era fallback | verdict |
|---|---|---|---|---|
| strict | 8,264 | 69.9% | 37.4% | **FAIL** |
| bar | 25,483 | 7.1% | 0.0% | **MATCHED** |

**Strict mode fails on arithmetic.** At 7.81 firings in a ~77-bar session, even a perfectly
INDEPENDENT state would touch ~99.9% of sessions; the 265 survivors range from 0% of 2011 to
17.5% of 2025, so the residue is an unrepresentative sample of quiet years. No bucketing fixes
it. Bar mode is clean on the same state, so a P03-shaped condition IS controllable.

### Decisions taken rather than resolved silently

1. **The exclusion mode is evidence-based, not a preference.** `session_clustering()` reports
   firings/session, sessions touched, over-dispersion and clean-pool size, and an entry cites
   them. Strict remains the default because it is the stronger control where it is available.
2. **A null under bar mode is weaker evidence than a null under strict mode**, because bar
   mode's contamination biases toward the null. Recorded now, before any entry can rely on it.
3. **§17's limit is untouched.** A condition firing about once a session still has too few
   events for any control to help — and strict mode, the one appropriate to session-level
   states like P01 and P04, is exactly the mode that fails on a frequent state. A session-level
   state must be checked for a clean pool BEFORE it is registered, not after.
4. **The P03 lookback is a parameter, not a detail.** 60 sessions, fixed a priori. It sets the
   warm-up (566 sessions lost of 4,125), how fast the threshold tracks the volume trend, and
   how much the state clusters. It must be carried in the entry and counted against its
   parameter budget — §45's point that the firing rate is a design lever, not a free choice.
5. **A silent Int8 overflow was found and fixed while building the feasibility check**:
   `dt.hour() * 60` wraps in polars, so 18:00 ET evaluated to 56 rather than 1080 and the RTH
   filter matched nothing. It failed loudly this time; a narrower window would have returned a
   wrong number instead of an empty frame. The cast is now explicit with the reason recorded at
   the line.

### What is still open

The control does not make P03 registrable by itself. Its threshold still needs the trailing
volume norm specified against a stationary denominator, its magnitude still straddles its BH
bar (§54), and no S2 has been run. Bar mode's power cost is unmeasured in size.

## 56. P03's S2: the denominator fixed, and a straddling magnitude (S2)

> **SUPERSEDED IN TWO PLACES BY §57, 2026-09-13.** Its bar arithmetic applied a sqrt(2) pairing inflation that **double-counts** - the SE anchor was already measured on a difference - and its horizon and magnitude were both assumed rather than measured. The denominator section stands. The text is left as written; §57 carries the corrections.

`reporting/p03_s2.py`, `reports/p03_s2.json`. **NOT REGISTERED. No trial spent, no S5, no S6,
no return scored.** S2 reads |return| only as the numerator of the state's own definition.

### The denominator, and why the draft's form could not work

§54 recorded that |return| per contract is not scale invariant. The two non-stationarities are
both large: the NQ→MNQ splice is a 10x notional change (measured median 1m bar volume 83-140
→ 26-39), and volume grows secularly besides. A fixed ratio threshold would fire almost never
early and almost always late — an era clock wearing a liquidity label.

**What is registered is not a level but a RANK.** The state is

    lambda_t > Q90( lambda over the SAME 30-minute bucket, previous 60 sessions )

which is dimensionless. Any rescaling common to a 60-session window — a contract change, a
tick-size change, secular growth — divides both sides of that comparison alike and leaves the
rank untouched. The bucket term does the same for the time-of-day shape, which the draft had
flagged as P03's largest confound. NQ-only is used, so the splice is avoided rather than
modelled; a spliced series would additionally have to drop the 60 sessions after the splice,
which is the one window a trailing denominator cannot absorb.

**The evidence is the firing rate, not the argument.** If the denominator were non-stationary
the rate would drift while the threshold sat still. Measured per year, 2012-2026: the rate
stays in **7.95%-12.10%** around its 10% design point while median bar volume runs 1,752 →
5,325. The rank construction holds across the eras it has to.

**Two caveats recorded rather than smoothed.** 2011 fires at 17.56% — it has 3,315 bars against
a full year's ~19,500, so the trailing bucket distribution is being built on sparse history.
NQ 1m coverage before 2013 is partial (2011: 5,313 bars, 2012: 8,060, 2013+: ~16-19k), so the
dense sample is really 2013-2026 and the early years contribute little n and more noise.

### The arithmetic

Post-warm-up sample **3,559 sessions** (566 of 4,125 spent on the 60-session lookback).
**27,437 firings across 3,238 sessions, 7.71 per session.** Bar from §45's anchor,
SE = 64.7/sqrt(effective units) at 180m, BH rank-1 at k=9.

| DEFF | effective units | bar, single mean | bar, paired difference |
|---|---|---|---|
| 2.19 (round-number family, measured) | 12,528 | 1.60 | **2.27** |
| 4.00 (deliberate pessimism) | 6,859 | 2.17 | **3.06** |

**The paired column is the one that applies.** The statistic is real-minus-control, a
difference of two event means, whose SE is inflated up to sqrt(2). That factor is the
conservative end: matching on regime correlates the two sides positively, which reduces the
variance of the difference, so the truth lies between the two columns. Reported both ways
rather than picked. **§54's table used the single-mean bar and therefore understated P03's
bar by up to 41%** — recorded here rather than silently corrected there.

### Verdict: STRADDLES

    predicted 1.0-4.0 bps    cost floor 0.48    bar 1.60-3.06

**Above the cost floor across its whole predicted range** (2.1x at the low end, 8.3x at the
high end). **Straddling its BH bar**: the top of the range clears even the pessimistic paired
bar, the bottom is below every version of it.

**Stopped here, deliberately.** A straddling S2 is registrable only with the significance limb
explicitly waived (§45's three legitimate responses, of which L12 should have been the first),
and that is a decision to take with the number in front of you rather than one to fold into a
registration. The number is 1.0-4.0 against 1.60-3.06.

### What a registration would still owe

1. **The horizon is a free parameter and 180m was assumed** for comparability with §45-§54. A
   thin-move reversion plausibly reverts faster; a shorter hold lowers the bar (sd scales as
   sqrt(h)) but also the effect. Fixing it a priori is part of S2, not S5.
2. **DEFF is bracketed, not measured.** P03's own design effect depends on the outcome, and
   measuring it now would be looking at the answer.
3. **The lookback (60 sessions) and the threshold (Q90) are parameters** and must be counted
   against the entry's budget, with k re-derived if the cell count changes.
4. **Bar mode is the only available control** (§55), so a null would be weaker evidence than a
   null under strict mode.

## 57. The sqrt(2) error was mine; P03's horizon and magnitude measured (S2)

`reporting/p03_mechanism.py`, `reports/p03_mechanism.json`, re-run `reports/p03_s2.json`.
**Still not registered. No trial spent, no forward return read anywhere in this work.**

### The sqrt(2) inflation: recorded as its own item, and it was an error in the CORRECTION

§56 claimed §54's table "used the single-mean bar for a difference-of-two-means statistic and
understated by up to 41%". **That claim is wrong, and checking it is what showed it.**

The anchor's provenance decides it. §45 set SE = 64.7/sqrt(units) from L12, and L12's number
was **"the test's own bootstrap SE of 1.016 bps"** on a table whose columns are
`real | placebo | diff` - a real-minus-placebo difference, at 4,052 pairs. 64.7/sqrt(4052) =
1.016. **The anchor is therefore ALREADY the SE of a difference of two means**, and inflating
it again double-counts the pairing. §54's table was right; §56's correction of it was wrong.

**Same class as the unit error and the scale error, one level up.** Each is a quantity computed
correctly for a DIFFERENT object than the one in hand - bars instead of sessions (§54), a ratio
whose denominator is not stationary (§52, §54), and here an SE for a single mean when the
constant already described a difference. The new instance is that it appeared **in a
correction**: the fix reproduced the error class it was fixing, by not checking the provenance
of the constant it was adjusting. A correction is not exempt from the check it applies.

**Swept the repo for the same mismatch.** The bar arithmetic exists in three places:

| where | statistic | anchor used correctly? |
|---|---|---|
| `p03_s2.py` | real-minus-control difference | now yes - the inflation is removed and the reason is at the function |
| §54's P-series table | real-minus-control differences throughout (every candidate needs a matched control, §55) | yes |
| §45's L01/L08/L09 blocks | paired real-minus-placebo, and the text says so | yes - and those used **per-case measured SEs** (4.45, 4.20, 2.44, 3.06-3.39), not the anchor |

**No other occurrence, and no occurrence of the mirror error** - the anchor is never applied to
a single-mean statistic, which would OVERSTATE a bar rather than understate one.

### P03's horizon, from the state's clock rather than from assumption

R01's precedent (r-series §17): the MNQ/MES deviation half-life was measured on the series, the
nearest grid horizon taken, and the choice recorded as data-informed rather than as an
out-of-sample prior. Followed here. The state variable is log(illiquidity / its own trailing
threshold); the decay is measured after each firing, within sessions, **using no forward
returns** - the quantity is a property of the state, and no signal, return series or statistic
exists when it runs.

| lag | 0 | 1 bar (5m) | 2 | 6 (30m) | 12 (60m) | 24 (120m) |
|---|---|---|---|---|---|---|
| elevation | 1.470 | 0.431 | 0.460 | 0.455 | 0.445 | 0.414 |
| vs lag 0 | 1.00 | **0.29** | 0.31 | 0.31 | 0.30 | 0.28 |

**Half-life 3.5 minutes -> H = 15, the nearest grid point.** Two things stated rather than
buried:

- **The half-life is below the 5-minute bar, so it is resolution-limited.** 3.5 min comes from
  interpolating inside the first bar. The choice is robust to that: any value under 5 minutes
  maps to 15, the grid's smallest point. What is NOT robust is the implication - P03's
  mechanism clock is faster than both the chosen bar and the tradeable grid, so H=15 is already
  ~4 half-lives past decay. R01 rejected H=60 for being 2-7 half-lives past restoration; P03
  cannot make the same choice because nothing shorter is on the grid.
- **The spike decays but a plateau remains**: elevation falls to 0.29 in one bar and then sits
  near 0.30 for two hours. The reverting claim is about the spike, so the spike's clock is the
  one used.

**The ordering is the safeguard and it is recorded deliberately.** Choosing the horizon after
seeing which one clears the bar would be selecting a specification on the outcome - the same
error as tuning a threshold until a result appears. Here the horizon was fixed by the state's
decay, the magnitude by the series' impact relation, and only then was the bar recomputed.
Neither measurement can see the bar: no forward return, no effect and no statistic exists when
they run. That ordering is what makes H=15 a specification rather than a selection.

### P03's magnitude, from measured impact rather than recalled literature

**The declined alternative, with its provenance.** §54 predicted 1.0-4.0 bps from a sketch (a 5m
MNQ move has sd ~11 bps, a two-sigma thin move ~20 bps, 5-20% excess reversal) whose direction
was attributed to Campbell, Grossman and Wang (1993). **Recalled from memory, never checked
against the paper**, and labelled as such in §54 at the time. **Superseded, not dropped** - the
same Amihud/Kyle mechanism is now measured on this series.

Within each (year, time-of-day bucket), log|return| = a + b log(volume) is fitted on all bars,
which absorbs the secular volume growth and the intraday shape. The fitted value is the move a
bar's own volume ordinarily buys; the residual is the excess displacement a thin move carries:

    median move at a firing        13.59 bps
    what its own volume buys        4.21 bps
    measured EXCESS                 9.18 bps   (IQR 4.88-16.37)

**The excess is a CEILING, not a prediction.** No reversion returns more than the move that was
made. The fraction that actually reverts is not measurable without forward returns, so it is
not guessed - and the ceiling is generous besides, because an unknown part of the excess is
permanent information rather than transitory impact.

### S2 re-run at H = 15: NOT BELOW, crossing at 6.8%

    bar 0.463-0.625 bps (DEFF 2.19-4.00, 12,528-6,859 effective units, no sqrt(2))
    cost floor 0.48 bps  ->  binding constraint 0.625 bps
    measured ceiling 9.18 bps  =  19.1x the cost floor, 15x the binding constraint

**P03 clears iff more than 6.8% of the measured excess reverts within 15 minutes.**

The bar fell from §56's 1.60-3.06 for two reasons that are worth separating: the horizon moved
from an assumed 180m to a measured 15m, which divides the bar by sqrt(12); and the spurious
sqrt(2) came out. The magnitude rose because 9.18 bps of measured excess replaced a recalled
1.0-4.0. **The cost floor now binds almost as hard as the BH bar** - 0.48 against 0.463-0.625 -
which is a different regime from every earlier P-series entry, where significance dominated.

**No verdict of CLEARS is recorded, and the reason is itself a correction.** The first draft of
the re-run declared CLEARS when the required fraction fell below a tenth - **a constant invented
in that file, with nothing behind it**, which is the same error as the recalled literature the
module exists to replace. Removed. The measurement can rule P03 OUT (a ceiling below the binding
constraint, which did not happen) but cannot rule it IN without a claim about the reversion
fraction - and that fraction is exactly what the test would measure. So the crossing point is
reported and the judgement is left where it belongs.

**P03 is therefore NOT below its bar, and the P-series does not close here.** The waiver
question §56 raised is no longer the live one: at H=15 the significance limb is nearly as cheap
as the cost limb, so a waiver would buy little. What a registration now turns on is whether
6.8% reversion within 15 minutes is a claim worth one trial.

## 58. P03 registered, run and retired at S7; the P-series closes (S5-S8)

`reports/p03_stage1.md`, `reports/p03_stage1.json`, `signals/p03.py`. **1 trial. N 759 -> 760,
SR\* 0.1368, chain verified.** First registration of the P-series and the only one.

| | |
|---|---|
| real - control | **+0.0794 bps** |
| pre-registered threshold | **+0.625 bps** - misses by **7.9x** |
| real leg net of the 0.48 floor | **-0.2796 bps** |
| separated | no - CI [-0.302, +0.451], p 0.691 |
| implied reversion fraction | **0.86%** of the measured excess, against 6.8% required |

### The three things pre-registered before the run, and why each mattered afterwards

1. **The refutation threshold, in the mechanism's own units.** "More than 6.8% of the measured
   9.18 bps excess reverts within 15 minutes." Because the threshold was in units the
   measurement produces, the result reads as a FRACTION - 0.86% against 6.8% - rather than as
   two bps numbers whose ratio has to be argued after the fact.
2. **That the prior was UNKNOWN, not high.** The 9.18 is a ceiling, part of it permanent
   information rather than transitory impact. Recording that first is what stops a null being
   written up as a surprise, and what makes it informative: **the null is informative because
   the threshold was low, not because the effect was expected.**
3. **That the binding limb is ECONOMICS, not significance.** Cost floor 0.48 against a bar of
   0.463-0.625 - the first P-series entry where the two are comparable. Every earlier one was
   significance-dominated (P01 needed 4.2-5.4 bps, P09 72-102). **That inverts what the null
   means**, and it had to be said beforehand or it would have read as an excuse: P03's null
   says the effect is small in bps, not that the test could not see it. The real leg is
   negative net of cost, so the economics limb refutes on its own and needs no power argument -
   the L12 shape (§45).

### The gates held, in order, and the trial was spent only after them

**S5 PASS**: entry-minute sd 110.2 over a 380-minute spread; neighbouring thresholds select
genuinely different events (Q85 Jaccard 0.67, Q95 0.50), so the parameter is not an offset.
Directional collapse is N/A by construction and says so rather than being skipped.

**S6 MATCHED** in `bar` mode: 27,437/27,437 paired, 7.0% reuse, time-of-day / volatility / year
deviations all **0.000**, era fallback **0.0%**. Bar mode was forced by the firing rate, not
chosen (§55), and its contamination costs power.

`stage1_run` is entered only after both pass, so an aborted run would have appended nothing.
**A run that never compared anything never had a chance to produce a false positive**, and the
accounting should say so.

**S8 era split, by default (§53)**: early +0.0140, late +0.1449, neither significant, no sign
flip. Unlike N02 - whose point thresholds ran a different trade in each era - P03's threshold is
a rank, so the split is interpretable, and it says the null is uniform rather than era-specific.

### The null was fault-injected before it was believed

§46 says to look for the bug when something CLEARS. Nothing cleared, but **the mirror risk
deserves the same treatment and nothing in the suite covered it**: a null manufactured by a sign
error or an off-by-one in the hold is indistinguishable from a real one.
`tests/test_p03_outcomes.py` pins four properties - a known injected +4.0 bps reversion is
recovered as **+3.45**, a pure random walk returns zero within noise, the hold never crosses a
session boundary, and a move that extends costs the fade rule money. **The machinery could have
seen an effect seven times smaller than the one it was looking for.** The null is a measurement.

### What the null does not settle, recorded before the run rather than after

The state's decay half-life is **3.5 minutes** and **H=15 is the shortest horizon the grid
carries**, so the test sits ~4 half-lives past the mechanism's clock. A null there is weak
evidence about thin-move reversion AT ITS OWN TIMESCALE. **Re-testing shorter is a new
registration with its own trial, not a re-reading of this one** - R01's rule (r-series §17):
running another horizon afterwards would invalidate the argument that chose this one.

### Two defects found while registering, both fixed rather than worked around

1. **`catalog_status` crashed on a legitimate status.** Its `closed_by` table was missing
   `stage1_inconclusive`, `stage1_passed` and `dead`, so the report died with a KeyError the
   moment an entry carried one. **The crash predates P03** - verified by stashing the
   registration and reproducing it. Completed the table, and kept the bare subscript rather
   than `.get` so an unknown status still fails loudly instead of rendering a blank cell.
2. **Two registry guards did not know the P-series existed.** The id pattern and the catalog
   regex both hard-coded `[FLN]`. Widened to `[FLNP]` - which the id check's own comment
   directs ("the pattern is widened deliberately when a series is opened"). This is coverage
   extended to a new series, **not a check loosened**: both assertions still bind exactly as
   before, and `found == set(REG)` is unchanged.

### The P-series closes

**Thirteen candidates, one registered, one tested, zero promoted, 1 trial spent.** §54 declined
the other twelve on arithmetic before any trial: five could not state a magnitude at all, four
sat below their BH bar, and the rest were conditioners with no live primary. P03 was the only
one that reached its bar, and it did so only after its horizon and magnitude were measured
rather than assumed (§57).

**The series' most reusable output is not a hypothesis.** It is the matched state control
(§55), its mode partition and clean-pool requirement now in `STAGES.md` under S6, and the
finding that a state condition's placebo question was three-quarters already answered and
one-quarter genuinely open.

## 59. Q-series S1 reviewed: a premise corrected, three re-registrations, and the filter (S1, S2)

Drafts saved as `Q_SERIES_FINAL.md` and `Q_SERIES_HANDOFF.md`, corrections inserted as **[§59]**.
Measurements: `reports/q09_drawdown.json`, `reports/q_series_s1.json`, `reports/q_series_s2.json`;
code in `reporting/q09_drawdown.py`, `q_series_s1.py`, `q_series_s2.py`. **Nothing registered, no
trial spent, no firing rate measured. N stays 760.** No forward mean is computed anywhere: the
data scripts read window SDs, counts and conditioner values only.

### A correction to a stated premise: the drawdown rule was assumed, not confirmed

**Confirmed with the firm.** The floor starts 4% below the starting balance and trails the running
equity peak. It becomes static when it reaches the starting balance - when the PEAK reaches +4% -
and then sits at breakeven permanently, so the cushion is the entire accumulated profit.

**The handoff's rule was assumed:** trailing until +10%, then static at +6%. Every Phase 1 / Phase 2
figure in the handoff was computed against it. **Same class as R04**, where a constraint was
assumed to have a lever it did not have: a number derived correctly from a rule nobody had checked.

**The handoff's own table is only partly reproducible, even under the rule it assumed.** For
X = mu t + sigma W with running maximum M, the maximum reached before the first drawdown of size d
is exponential (Taylor 1975; Lehoczky 1977): P(M reaches a first) = exp(-a/m), m = (e^(gd) - 1)/g,
g = 2mu/sigma^2. That formula reproduces **five of the nine cells within 2.3 points and one within
5, and misses three by 13-22 points**: Sharpe 1.5 at 0.5%/mo (67.5% vs 46%), 1.5 at 0.25% (96.3% vs
83%), 2.1 at 0.5% (96.0% vs 76%). A finite horizon was tested as the explanation and rejected: no
single horizon reproduces the set, the best (five years) still missing one cell by 24 points. **Its
provenance is recorded as unverified**, which matters because the demotion of Q01 rested on two of
its cells, one of them unreproduced.

**The baseline in the brief needed correcting too.** A driftless walk reaches +4% before a 4%
TRAILING drawdown with probability **exp(-1) = 36.8%**, not ~50%. 50% is the STATIC gambler's-ruin
answer; a trailing floor follows every new high up, which is exactly why the rule bites.

| P(peak +4% before a 4% trailing drawdown) | 1%/mo | 0.5%/mo | 0.25%/mo |
|---|---|---|---|
| Sharpe 1.0 | 49.5% | 62.0% | 81.9% |
| Sharpe 1.5 | 65.0% | 85.5% | 98.5% |
| Sharpe 2.1 | 84.9% | 98.4% | 100.0% |
| **no edge** | **36.8%** | **36.8%** | **36.8%** |

| superseded: P(+10% before 4% trailing), as printed | 1%/mo | 0.5%/mo | 0.25%/mo |
|---|---|---|---|
| Sharpe 1.0 | 17% | 30% | 61% |
| Sharpe 1.5 | 34% | 46% | 83% |
| Sharpe 2.1 | 64% | 76% | 95% |

**Verified, not trusted.** A trade-level Monte Carlo (20,000 paths, ~2,000 trades a year) agrees:
49.5% -> 52.3% Gaussian, 85.5% -> 86.5%, 36.8% -> 37.9%. The continuous formula is conservative by
1-3 points because trade-level monitoring misses breaches between steps. Student-t tails
(nu = 5 and 4.05, the latter at the programme's measured kurtosis) move every cell by under a
point. Median time to lock at Sharpe 1.5: **0.45 years at 0.5%/mo, 1.14 years at 0.25%/mo**,
against the handoff's ~3.3 years to +10%.

### Phase 2: the 3-4x step-up does not survive as a step

With the floor static at breakeven, fixed sizing breaches ever with probability exp(-g * cushion),
and k-times sizing divides the exponent by k. **At the moment of lock the cushion is 4% - LESS than
the handoff's ~6%:**

| lifetime breach at lock, cushion 4% | 1x | 2x | 3x | 4x |
|---|---|---|---|---|
| Sharpe 1.5, base 0.5%/mo | 5.0% | 22.3% | **36.8%** | **47.2%** |
| Sharpe 1.5, base 0.25%/mo | 0.2% | 5.0% | 13.5% | 22.3% |
| Sharpe 2.1, base 0.5%/mo | 0.3% | 5.3% | 14.1% | 23.0% |

**What survives is a destination, not a step.** Holding breach probability at its 1x-at-lock value
requires size proportional to the cushion, so 3x is earned at +12% and 4x at +16%. Under that rule a
breach needs a single trade to lose more than the whole cushion - 45 trade-SDs at Sharpe 1.5, 0.5%/mo
- which Student-t tails put at **1.65e-3 over five years** (nu 4.05) and 1.5e-4 (nu 5). **Not
modelled: intratrade adverse excursion**, which is larger than the trade-return distribution, and
whether the firm marks the floor on intraday equity. Both would raise these figures.

### Ordering: the demotion of edges does not hold

The handoff moved Q08/Q09 ahead of Q01 because "at Sharpe 1.5 the gap between 34% and 83% is entirely
a sizing choice." Corrected, the gap is **65.0% -> 98.5% (33.5 points, not 49)**, and at realistic
middle sizing survival is already 85.5%. The decisive number is the no-edge row: **36.8% at every
size.** At 4% annual volatility, moving from no edge to Sharpe 1.5 adds 48.7 points; no sizing adds
anything to a zero edge. **Sizing multiplies an edge and cannot substitute for one.** Q09 is complete
- it was a computation and cost nothing - and Q08 has nothing to act on until something survives.

### Three Q candidates were already in the registry

| Q | registry | status | what the Q draft missed |
|---|---|---|---|
| Q01 | **F02** order_imbalance_conditional_overnight_reversal | `stage1_uninformative`, **144 trials** | 87.1% of F02's (k=1) firings are Q01 firings |
| Q03 | **F12** pre_fomc_announcement_drift | `excluded` | ~128 events, and the 24h hold crosses 17:00 ET |
| Q04 | **F12's note** | - | "Do not register them individually" |
| (Q01's premise) | **F13** unconditional_overnight_drift | `excluded` | excluded on the same Liberty Street finding |

**F13's own entry says "recorded so it is not rediscovered"**, and the Q draft is that rediscovery.
The consequence for Q01 is not procedural. F02 recorded MNQ post-2021 `sell_imb` at +3.27 bps as "the
one directionally consistent result, and it is not evidence," so **the data on disk is not out of
sample for Q01**: a registration now would re-test the family F02 already looked at, on the same
data, after seeing it point the predicted way. NQ ends 2026-08-27 and F02 ran 2026-09-02. **A clean Q01
test needs data after 2026-08-27.** F02's 144 trials stay in N either way.

### Issue 1: Q01 and Q02 are one bet

Measured on NQ, no trial: Q01's conditioner (last-30m price change per unit volume) against Q02's
signal (last-30m price change) is **Spearman +0.972 full sample, +0.991 post-2021**. And **P(Q02 is
long | Q01 fires) = 100%** - an identity rather than an estimate, because Q01's trailing tercile
threshold is itself negative in 99.1% of sessions, so a Q01 firing implies a down close and fading a
down close is long. phi = +0.735 over 3,375 sessions.

**"Opposite sign" is wrong: both are long after a down close.** The windows are disjoint (16:00-16:59
against 01:45-03:15 the next night), so their P&L correlation is not forced to one - but it cannot be
assumed near zero, and both carry the same exposure on the same selloff days, which is where tails
cluster. **The first two candidates of a portfolio built on rho <= 0.1 share a conditioner, so the
recommended order was wrong and the portfolio needs different material.** Conditioner correlation is
necessary evidence rather than sufficient, and it cost nothing to measure before either was run.

### Issue 2: the sample period, and what extending it does not buy

**"~1,500 sessions over six years" and "~72 month-ends" are the MNQ/MES-from-May-2019 sample - and MES is
not on disk at all.** The NQ lineage carries these hypotheses instead, on one contract with no splice:

| window | sessions (NQ, 2010-2026) | pre-2021 | post-2021 |
|---|---|---|---|
| last 30m RTH (Q01 conditioner, Q02 signal) | 3,435 | 2,048 | 1,387 |
| 01:45-03:15 (Q01) | 3,559 | 2,120 | 1,439 |
| 18:00-16:00 session (Q05) | 3,428 / 195 months | 2,041 / 127 | 1,387 / 68 |

**The lineage more than doubles n - and none of the doubling lands where it matters.** Q10 makes
post-2021 decisive, and post-2021 is ~1,387-1,440 sessions and 68 months whatever the lineage. The
extension is entirely in the era Q10 discounts. **The 3,415 figure in the brief is not in the repo**;
the nearest measured count is 3,435 sessions with a complete last-30m window.

**Two venue findings, measured:** bars after 16:15 ET do not exist before 2015, and the 16:15-16:30
window holds 0-4 sessions a year before 2021 (128 in 2021, full thereafter) - consistent with the
former daily maintenance halt. And Q02's "hold into the Globex session" **crosses the 17:00 ET hard
exit**, so it is not executable as written; its compliant holds are 16:00-16:59 (continuous only
from mid-2021) or 16:00-16:14 (all eras). 2010-2012 are sparse in every window.

### Issue 3: Q01's proxy measures illiquidity, and P03 already measured its weakness

Price change per unit volume is P03's Amihud construction, signed. **It measures illiquidity, not
imbalance**: dividing by volume ranks a heavy-volume selloff - the largest imbalance - below a thin
one. Measured against a bulk-volume-classification order-flow imbalance ratio (Easley, Lopez de Prado
& O'Hara 2012; each bar's volume signed by its standardised return, sigma from that session's own
earlier RTH bars), **Spearman 0.792, against 0.774 for the raw return** - the division adds 0.02. It is
not scale invariant either: **median |dp/V| falls from 0.00070 (2010) to 0.00035 (2026)** while the
BVC ratio holds at 0.10-0.14 throughout.

**What P03 implies for it as a conditioner.** P03 traded the construction as a signal and found its
displacement mostly permanent at the mechanism's own clock - 0.86% of a 9.18 bps excess reverted
within 15 minutes. Q01 uses it to select nights for a window ~10 hours later, which P03 did not test,
so P03 does not refute Q01. But it removes the only reason to prefer the construction: it adds nothing
over the return it is built from, it drifts with volume, and the one property P03 measured - whether
what it flags reverts - came back weak. **Better on disk:** the BVC ratio, which is stationary, or the
return itself, F02's choice. True signed imbalance needs aggressor-side data: `trades` is null and no
`tbbo` is on disk, so that is a purchase.

### Issue 4: the two drafts disagreed on ordering

FINAL orders Q01, Q02, Q05, Q08, Q12. HANDOFF prints the same order and also labels Q08 and Q09 "now
primary", contradicting itself. **Resolved: edges lead** (the no-edge row above), **Q09 is complete,
Q08 waits for a survivor, Q12 waits for three, Q10/Q11 are gates.** But the filter below leaves no edge
registrable on data now on disk, so the resolved order has nothing in its first slot yet.

### The magnitude filter - ESTIMATES, NOT MEASUREMENTS

Bars use window SDs measured on NQ and the SE of the statistic each candidate tests - a
difference of two means for four of them (firing against non-firing nights, event against other
days), a single mean for Q02's all-session fade. No anchor is adjusted. DEFF bracketed 1.14-2.19.
k as written. **Post-2021 decides**, per Q10; every predicted range includes zero because decay
since publication is the stated prior.

| candidate | predicted post-2021 | n post (events/rest) | bar post-2021 | bar full | vs bar |
|---|---|---|---|---|---|
| Q01 | 0-3.0 | 478 / 908 | 2.81-3.89 | 1.78-2.47 | **STRADDLES** |
| Q02 16:00-16:59 | 0-0.96 | 1,387 | 1.44-1.99 | 1.02-1.42 | BELOW |
| Q02 16:00-16:14 | 0-0.96 | 1,387 | 1.04-1.43 | 0.59-0.82 | BELOW |
| Q03 (09:30-14:00) | 0-25 | ~46 / 1,394 | 30.6-42.5 | 17.0-23.5 | BELOW |
| Q05 | 0-10 | 476 / 911 | 16.4-22.7 | 9.2-12.8 | BELOW |
| Q06 Monday only | 0-3 | 273 / 1,167 | 10.6-14.7 | 5.9-8.2 | BELOW |
| Q06 as written, k=10 | 0-3 | 273 / 1,167 | 15.2-21.1 | 8.5-11.7 | BELOW |

**Cannot be predicted:** Q04 and Q07 (no direction), Q08-Q12 (not signals). Every predictable range
is at the 0.48 bps cost floor at its low end, and **the overnight spread for Q01 and Q06 is
unmeasured** - the 0.10 bps spread in the floor is itself an estimate for RTH.

**Provenance of each range:** Q01 - 3.6%/yr unconditional and ~0 since 2021 as CITED in F13 and the
draft, amplification after selloffs ESTIMATED at up to ~2x, and F02's +3.27 bps deliberately NOT
used. Q02 - P03's MEASURED reversal fraction up to P03's own 6.8% bar, times the MEASURED 14.1 bps
median last-30m move. Q03 - 49 bps over 24h as cited in F12, share inside 09:30-14:00 ESTIMATED at up to
half; the unconditional SD understates FOMC days and therefore the bar. Q05 and Q06 - RECALLED
literature with no bps figure in either document.

**The findings.** None clears both. **One straddles - Q01 - and it cannot be tested cleanly on disk
data.** Four sit below their post-2021 bars. Two cannot state a magnitude, five are not signals.
Q03's economics-only waiver rescues nothing: at ~46 events the economic estimate carries an interval
wider than the effect, N10's reasoning (§45).

### What this leaves, stated without taking the decision

**No Q candidate is registrable as a primary on data now on disk.** The portfolio route has no
material: the first pair shares a conditioner, four predictable candidates are below their decisive
bar, and the fifth is F02 re-tested on data F02 has seen. The handoff anticipated "if Q01, Q02 and Q05
all come back null"; **the filter reached most of that at S2 without spending a trial.** Whether to
write it up as the programme's finding, or to wait for data after 2026-08-27 and test Q01 once on
genuinely unseen data, is not decided here.

### Proposed, not adopted

1. **Q10 as a standing S8 requirement.** §53 already runs an era split by default; Q10 would fix the
   break at 2021 and make the post-2021 half decisive. It changes the method, so it is left for
   decision. The filter above applies it, so its effect is visible.
2. **Outcome fault-injection for nulls as standing in §46**, from the handoff. Also left for decision.
3. **Read `hypotheses.yaml` before drafting a series.** Three of twelve candidates were already
   registered and one had spent 144 trials.

### Decisions taken rather than resolved silently

1. **The trailing-drawdown formula was verified by Monte Carlo before it was used**, and checked
   against the handoff's table, which is why that table is recorded as partly unreproduced rather
   than silently replaced.
2. **The brief's ~50% baseline was corrected to 36.8%**, because the rule it describes is trailing.
3. **F02's +3.27 bps was not used as Q01's prior.** It is a previous look at the same data.
4. **Q02 and Q03 were assessed only at 17:00-compliant holds**, since the written versions are not
   executable on the account.
5. **No FOMC calendar is on disk**, so Q03's counts are eight a year rather than dates.
6. **Three bugs in the measurement script were found before any number was used, and one is the
   §54 class.** The imbalance ratio never joined (a datetime64 key against python dates), so every
   correlation printed NaN - loud. A rolling window demanding 60 values in 60 rows went undefined
   whenever one holiday fell inside it, leaving 64 sessions, on which P(Q02 long | Q01) = 100% and
   phi = +0.699 still printed as numbers. And the session open was taken as the last bar before
   midnight rather than the 18:00 reopen, which gave a "full session" SD of 130.5 bps - **almost
   exactly the programme's familiar ~130 bps daily figure, and therefore a wrong answer
   indistinguishable from a right one.** The corrected window gives 126.3.

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
- **[RESOLVED 2026-09-02] F05, F08, F10 and F11 firing rates are now measured** —
  `reports/firing_rates.md`. F05 and F11 open on both instruments, F08 on five of
  six, F10 on none. Superseded note follows:
- ~~**F05, F08, F10 and F11 are blocked on a MISSING MEASUREMENT, not a finding.**~~ Their
  conditions state no per-session firing rate and none was ever counted. An unmeasured
  rate used to fall through to the data ceiling — the most generous possible assumption,
  applied where least was known. It now blocks. **Counting those four firing rates is a
  data measurement, not a Stage 1 run, and it is the single highest-value unblocking
  task available.** F10 and F11 are the controls, so the catalog currently cannot say
  what its own controls are powered to detect.
- **[CORRECTED 2026-09-02] MNQ per-cell routes ARE open** — on F05, F08 and F11, opened
  by measuring the four firing rates. The earlier claim that every open per-cell route
  was on MGC was true when written and false within the day. F02, F04 and F06 remain
  MGC-only. See CLAUDE_FUTURES.md §5.9.
- **[RESOLVED 2026-09-02] `trials.jsonl` is wired into every runner and backfilled**,
  and F03's MGC cells are persisted. See §16. An unlogged run now raises.
- **[RESOLVED 2026-09-02] F14 registered AND run; the control passed.** See §17-19.
  Re-run it whenever the harness changes.
- **[F02 RESOLVED 2026-09-02] Run and recorded `stage1_uninformative`** - all 144 cells
  below the swept range; see §20-21 and `reports/f02_stage1.md`.
- **[RESOLVED 2026-09-02] Every hypothesis now has a MEASURED firing rate and declared
  rates no longer gate.** See §22. F06 MGC 120m/180m dropped RESOLVABLE to MIXED;
  F01's real worst-cell sample is 66 events, not the 4,125 the gate had been using.
- **F01, F02, F04, F06 and F09 have NO real-data control and cannot get one.** They
  fire once a session (~3,500 events vs MNQ's 19,722); F14 covers F03-like counts
  only. Any null from those five must say so rather than borrowing F14's assurance.
- **[RESOLVED] F05 corrected and schedulable** — the trigger references normal
  volatility, k discriminates, 5 of 6 routes open. See §27.
- **[RESOLVED] F06's vol_filter settled and schedulable** — but both remaining routes
  are MGC, where its mechanism is attenuated. See §28.
- **[RESOLVED] F08 retired on premise**, alongside F11. See §29.
- **[RESOLVED] Control runs no longer spend trials.** N 498 → 486. See §30.
- **F01's vol_filter gap is still open** and must be settled if F01 is ever revived.
- **[RESOLVED] F05 retired on an informative null** - the catalog's only retirement
  where the sample was demonstrably adequate. See §33.
- **[RESOLVED] F06 retired** - null on its only open routes, weaker than F05's. See
  §34. **The catalog is closed as registered**; see §35 and
  `reports/futures_conclusion.md`.
- **F01's vol_filter and F08's direction rule remain undefined** and would have to be
  settled before either could be revived.
- **No real-data control exists for the once-per-session regime.** Every verdict there
  - F02, F04, F06, F09 - carries synthetic assurance only.
- **F01's aggregate route is closed for the same reason as F07's**: its two entry times
  (15:00, 15:30) share a 15:55 exit, so the positions overlap and pooling adds almost
  nothing.
- **F04's confound control is owed if it is ever revived** — the same-clock-time
  random-day benchmark for the PM auction against 10:00 ET US liquidity.

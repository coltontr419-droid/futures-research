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

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
- **[PARTLY RESOLVED] F05's break deadline is derived (60 min) but the vacuity is NOT
  fixed** — it still fires on 79-91% of armings because sigma is measured on the
  compressed window itself. `schedulable: false` pending a decision. See §23.
- **F06 and F08 are `schedulable: false` on undefined terms** — F06's `vol_filter`,
  F08's volume-weighted move, and F08's note-only regime split. See §25.
- **Only F09 and F14 are schedulable, and F09 is closed on both routes.** In practice
  the catalog has nothing left to run that could produce evidence.
- **Unanswered: should control re-runs count toward N?** See §26.
- **F01's aggregate route is closed for the same reason as F07's**: its two entry times
  (15:00, 15:30) share a 15:55 exit, so the positions overlap and pooling adds almost
  nothing.
- **F04's confound control is owed if it is ever revived** — the same-clock-time
  random-day benchmark for the PM auction against 10:00 ET US liquidity.

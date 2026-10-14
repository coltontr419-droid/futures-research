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

## 60. Two standards adopted, the Q-series closed, and the programme ended (S8, all)

Terminal document: `reports/programme_conclusion.md`. **Nothing registered, no trial spent.
futures-research N stays 760 (SR\* 0.1368); the R-series log, kept separately, stays at 10.**

### Two standards adopted rather than left proposed

**1. S8: the era break is 2021-01-01 and the post-2021 half decides.** Standing, in `STAGES.md`,
and enforced for future entries by `check_post_2021_split`.

**2. A null is reportable only from a pipeline demonstrated to recover an injected effect of the
size being sought, at the run's own noise and n.** Standing, in `STAGES.md`, and enforced by
`check_null_reportability`, which refuses an injection LARGER than the effect sought or on a
LARGER sample than the run.

Both gates apply to entries registered after 2026-09-13 and are fault-injected (11 tests), because
nothing live is registered after adoption and a check never shown to fire proves nothing (§53).

### The caveat on prior findings, stated precisely - including where the brief overstated it

The instruction was to record that five series reported nulls before this standard existed.
**Checked against both repos, it is four, and none of them was uninjected:**

| series | nulls | injection that existed | why below the standard |
|---|---|---|---|
| F | F03, F05, F06; F02, F07 uninformative | planted ~90 bps edge in signed Stage 1; injected-effect detection floors | far above any sought effect; floors used a slow regime-flip construction |
| L | L02, L03, L12; L04 inconclusive | L07's paired statistic recovers +2.0 bps | noise 5 bps per event against ~65 real; `sweep_stage1` untested until §55 |
| N | N02 | the same | as above |
| P | P03 | +4.0 recovered as +3.45 | 6.4x the 0.625 threshold, at n = 400 |

**The R-series reported no null** - R01 separated, R02 closed on a measured half-life, R03 on
arithmetic, R04 on permission. R02's half-life estimator was validated on a 6.58-bar process, not
near the 0.25-bar reading that closed it, which is the nearest analogue.

**No verdict is reversed, and the reason is specific.** Most closures rest on economics or event
count, which need no power argument. What changes is the word "absent" wherever a null was the
reason: it now reads "not found by a pipeline never shown to see this size" - F05 included, the one
F-series test called adequately powered. **Saying "five series had no injection" would have been
the easier sentence and a false one.**

### The Q-series closed without registration

On grounds already measured in §59:

1. **Q01 is F02**, at 87.1% firing overlap. F02 has already looked at the post-2021 selloff family on
   this data, so the data on disk is not a fresh test.
2. **Q01 and Q02 are one bet.** Conditioners Spearman +0.972 (post-2021 +0.991); a Q01 firing implies
   Q02 is long on 100% of nights.
3. **Q02 crosses the 17:00 ET hard exit** as written.
4. **Q03 and Q04 are already excluded** under F12.
5. **Every predictable candidate sits below or straddling its post-2021 bar**: Q01 straddles; Q02,
   Q03, Q05 and Q06 are below. Q04 and Q07 state no direction; Q08-Q12 are not signals.

**The Q01 forward test was considered and rejected on arithmetic.** Matching the post-2021 bar's
power needs as many firings as the post-2021 sample holds: 478 at a 34.2% firing rate is **1,397
sessions**. Post-2021 NQ carries ~245 sessions a year with a usable window, so accumulating them
takes **5.7 years**. **The brief put the sessions available since the data ends at twelve; measured,
it is ten** (2026-08-28 to 2026-09-11, Labor Day excluded, the last RTH session on disk being
2026-08-27). Ten or twelve, the wait is 5.65 years. **That is a six-year wait, not a deferred
decision**, and it is recorded as rejected rather than pending.

### The programme ends

**No edge accessible at this cost structure and account size was found in intraday, calendar or
non-price futures signals, across six independently designed series.** 66 candidates drafted, 35
registered, 770 trials across two hash-chained logs, nothing promoted. `programme_conclusion.md`
states it for a reader who has seen none of this, and states what would have to change for the
question to be worth reopening. **Starting a seventh series is not on that list**: it would inherit
the same cost floor, the same 1-minute bars and the same account, which are the four constraints
that closed the first six.

### Provenance items recorded at close

1. **The handoff's Phase 1 table is only partly reproducible under its own rule.** Five cells within
   2.3 points, one within 5, three off by 13-22; no single finite horizon explains them (the best,
   five years, still misses one cell by 24 points). Source unverified.
2. **3,415 sessions: §59's "not in the repo" was itself wrong.** It checked futures-research only.
   The figure is **R03's measured usable-session ceiling in `r-series-research`**
   (`reports/r03_firing_rate.json`), which the brief attributed to the F-series. The nearest measured
   figure in futures-research is 3,435 sessions with a complete last-30m window. The correction is to
   the attribution, not to the existence of the number.
3. **N = 760 is one log.** It counts F (576), L (180), N (3) and P (1). The R-series trials (R01 9,
   R02 1) sit in their own chain in `r-series-research`. "Six series, N = 760" undercounts by ten;
   the programme total is 770 across two logs.

### Decisions taken rather than resolved silently

1. **The injection caveat was written from the tests, not from the brief.** Four series, and each had
   an injection - at the wrong size.
2. **The gates do not fail on history.** P03 is below the standard it helped motivate, and that is in
   `STAGES.md` where a reader sees it, not in a red test nobody can fix.
3. **The sessions-available figure was measured rather than copied.** Ten, not twelve; the conclusion
   does not depend on it.

## 61. A stopping rule, stated before a seventh series is designed (S2, S8)

**Nothing registered, no trial spent. N stays 760 (SR\* 0.1368); the R-series log stays at 10.**
Recorded in `reports/CHECKPOINT.md` as a gate on *designing*, not as a summary. Everything below
was computed 2026-09-29 from `trials.jsonl` in both repositories and from the figures in
`programme_conclusion.md`; nothing is transcribed from an earlier brief.

### Why a stopping rule now

The terminal report ends by arguing against a seventh series (§10). That argument is qualitative,
and a qualitative argument loses to persistence: it can be re-litigated every time someone has a
new idea. The programme has a trial log precisely because it does not trust that kind of judgement
about its own work. A stopping rule is the same instrument applied one level up — **a bar stated in
advance, so a seventh series is measured against it rather than argued for.**

### 1. The success condition, converted

**The account size follows from the number, and was not assumed.** $2,000 is 4% of $50,000, and 4%
is the account's own trailing floor (§1 of the terminal report), so the stated condition is a **4%
peak-to-trough excursion on a $50,000 account**. This is derived, not recalled, and it is the one
place where the drawdown figure in the old Q-series handoff (§8, provenance note 1, only partly
reproducible) is not relied on.

**Method, stated because the event definition decides the answer.** iid normal daily P&L,
arithmetic dollars on a fixed $50,000 base, 252 marks/year, 20,000 paths, bisection on Sharpe. An
event is counted once when an excursion first reaches $2,000 deep, and **a new equity high is
required before another can be counted** — distinct episodes, not days underwater. A simulation was
used rather than a closed form deliberately: the answer depends entirely on the counting
convention, and §6 of the terminal report is a list of constants that were correct for a different
object than the one in hand.

Required Sharpe is a **floor**; the volatility column is a **ceiling**. Verified monotone on a grid
(Sharpe 0.05 → 6.0, all three return targets), so each target has exactly one crossing.

| annual return | ≤3 events/yr | ≤5 events/yr |
|---|---|---|
| 10% | SR ≥ 0.59, vol ≤ 17.00% ($8,500) | SR ≥ 0.26, vol ≤ 38.23% ($19,114) |
| 15% | SR ≥ 0.95, vol ≤ 15.82% ($7,908) | SR ≥ 0.44, vol ≤ 34.24% ($17,119) |
| 20% | SR ≥ 1.31, vol ≤ 15.21% ($7,605) | SR ≥ 0.66, vol ≤ 30.51% ($15,255) |

### The ten-events row does not exist, and finding that out corrected a bug of mine

The first solver returned Sharpe 0.05 for all three ten-event cells — its own lower search bound, in
every case. **That is the signature of a bound being hit, not a solution**, and reporting those three
cells would have put four fabricated numbers into a rule about not fabricating numbers. Gridding the
function showed why: events/yr **saturates** as Sharpe → 0 rather than growing without limit.

Measured ceilings as Sharpe → 0 (R = 15%):

| marking | marks/yr | max attainable events/yr |
|---|---|---|
| daily | 252 | **8.76** |
| hourly | 1,638 | 20.81 |
| half-hourly | 3,276 | 28.52 |

≈ 0.5·√marks. The mechanism is the counting rule itself: **distinct episodes are bounded by the
number of new equity highs**, and for a near-driftless path the number of records in n steps grows
like √n. At daily marks that ceiling is 8.76, so **≤10 events/yr is not a constraint at all** — it
is satisfied by every strategy, including one with no edge. It cannot discriminate and must not be
used as a bar.

### OPEN DECISION 1 — the marking convention, which is load-bearing

Finer marking detects more excursions, so it **raises** the required Sharpe for the same event
budget. Measured at R = 15%:

| events/yr | daily (252) | hourly (1,638) |
|---|---|---|
| ≤3 | SR ≥ 0.95 | **SR ≥ 1.14** |
| ≤5 | SR ≥ 0.44 | **SR ≥ 0.66** |
| ≤10 | infeasible | SR ≥ 0.23 |

The table in `CHECKPOINT.md` uses **daily marks**. A prop trailing drawdown is commonly evaluated on
intraday equity, which would make the hourly column the right one and every bar ~20–50% stricter.
**The record does not settle which applies** — §8's provenance note already flags the old drawdown
table as only partly reproducible under its own rule. **Not resolved here.** Recorded so that
whoever registers against this bar states which convention they are held to, rather than inheriting
mine by accident.

### OPEN DECISION 2 — a $2,000 trailing drawdown is account-ending, not merely costly

Under the confirmed rule (floor 4% below start, trailing the peak until the peak reaches +4%, then
locked at breakeven), a **$2,000 drawdown from the peak is fatal until the peak exceeds $52,000**:
below that the floor *is* peak − $2,000, so reaching it breaches the floor. Once locked, a $2,000
drawdown from a peak of exactly $52,000 lands on $50,000, the floor, and is still fatal; it is
survivable only with a peak above $52,000.

So "experiencing a trailing $2,000 drawdown a few times per year" is **only coherent in the locked
regime with an equity cushion**. Taken literally against the account rule, the answer is that
**even one such event ends the account** in the first phase, and the relevant question is not a rate
but a ruin probability. The terminal report already states the no-edge case: the chance of reaching
the +4% lock before a 4% drawdown is exp(−1) = 36.8% **at every position size**.

**Not resolved here**, because the two readings imply different bars: a rate (the table above) or a
survival probability. The table is computed for the rate reading and is labelled as such.

### 2. Where the programme's own effects sit against the bar

**Not close, and precision is not what is missing.** The bar is a Sharpe floor; every measured effect
has a non-positive net edge, and a non-positive edge is Sharpe ≤ 0 at any volatility.

| | gross bps/event | net of 0.48 cost |
|---|---|---|
| R01, the largest effect measured anywhere | +0.452 | **−0.028** |
| L12 | +0.306 | −0.174 |
| P03 real leg | +0.200 | −0.280 |
| L07 | negative in 108/108 cells | wrong sign |

Inverted — the **gross** bps one MNQ contract ($48,000 notional) must earn per trade, against R01:

| trades/yr | gross @10% | gross @15% | gross @20% | ×R01 @15% |
|---|---|---|---|---|
| 245 | 4.732 | 6.858 | 8.983 | 15.2× |
| 1,000 | 1.522 | 2.042 | 2.563 | 4.5× |
| 5,000 | 0.688 | 0.792 | 0.897 | 1.8× |
| 25,000 | 0.522 | 0.542 | 0.563 | 1.2× |

**The ratio never reaches 1 at any trade frequency**; its floor as trades → ∞ is **1.062×**, because
the 0.48 cost floor alone exceeds the 0.452 best measured effect. **Trading more often cannot close
this gap** — only a larger effect or a lower cost can. That is the same conclusion §10 reaches about
full-size contracts, arrived at from the drawdown constraint instead.

SR\* = 0.1368 at N = 760 for scale: the weakest success bar in the table (SR ≥ 0.26) is **1.9× SR\***,
and the 15%/≤3 bar is **6.9×**.

### 3. The termination condition

**Base rate, measured in both logs:** 35 registered, **15 spent ≥1 trial** (13 here — F02, F03, F04,
F05, F06, F07, L02, L03, L04, L07, L12, N02, P03 — plus R01 and R02), **0 promoted**. Note F04 spent
36 trials and is absent from the terminal report's S7 discussion; the log is the authority.

Per registration, 0 in 35: exact 95% one-sided upper **0.0820**, rule of three 0.0857, Laplace
0.0270, Jeffreys 0.0139. Per series, 0 in 6: exact 95% upper **0.3930**, Laplace 0.1250, Jeffreys
0.0714.

At the measured mean of 5.83 registrations/series, P(a seventh series promotes ≥1):

| prior | P(promote) | a promotion must be worth |
|---|---|---|
| Jeffreys | **7.8%** | **12.8× one series' cost** |
| Laplace | 14.8% | 6.8× |
| rule of three | 40.7% | 2.5× |

The rule-of-three figure is a **95% upper bound on what 35 observations cannot exclude**, not an
estimate, and should not be quoted as one. The base rate is also **optimistic** for a seventh series,
because the six spent the best ideas first: R04, the strongest unexplored idea on record, is closed
by account permission rather than by evidence.

**Cost of one series:** trials, mean **128.3** / median **6.5** (F 576, L 180, R 10, N 3, P 1, Q 0 —
the mean is not a typical series); SR\* imposed permanently on all future work, **+0.0019** at the
mean 128 trials (+0.0002 at 10, +0.0026 at 180, +0.0069 at 576); calendar, **6 series in 16 days** of
repository history, ≈2.7 days/series.

The SR\* cost is the one that compounds: small per series, **permanent and shared**, and paid by
every future hypothesis *including the one that would have promoted*.

### 4. "We cannot think of new hypotheses" is not a valid termination condition

Recorded explicitly because it is the rule a closed programme drifts toward when it wants to stay
open. Hypothesis generation is **unbounded and cheap** — 66 candidates in 16 days, and 66 more
available for another 16 at no information gain. A condition that depends on exhausting ideas
**can never bind**, and a rule that cannot bind is not a rule.

The consequence is mechanical rather than rhetorical: stop only when ideas run out, and whatever
eventually survives has been selected by **how long the search continued** rather than by evidence.
N, SR\* and the trial log exist to prevent exactly that, and §10 of the terminal report names it in
its own last line.

Valid conditions are about cost and evidence — expected value below cost (above), or one of the four
binding constraints moving (information, permission, cost, time). Not imagination.

### What this section does NOT do

It does not design a seventh series, and it does not reopen anything. Both open decisions above are
left open on purpose. **The bar is stated so that a future series is checked against it rather than
argued for** — which is the only reason a stopping rule is worth writing before the next idea
arrives rather than after.

## 62. Both open decisions ruled; the operative bar is two objects, not one (S2, S8)

**No trial spent. N stays 760, SR\* 0.1368, chain intact.** §61 left two decisions open. Both are now
ruled, strictly, and both rulings move the bar **up**. Computed 2026-09-29; §61's tables are kept and
marked superseded rather than deleted.

### Ruling 1 — the marking convention is intraday

The firm evaluates its trailing floor continuously and the condition is stated as losing $2,000 from
any point, so **daily marks measure something nobody enforces.** §61's table was therefore too lenient.

**The bar converges, so the intraday figure is a limit rather than a grid choice.** Required Sharpe,
R = 15%, ≤3 events, single-phase: **0.95** daily → 1.13 hourly → 1.17 (30-min) → 1.19 (15-min) →
**1.20** (7.5-min). This mattered to check: had it diverged, "intraday" would have had no well-defined
answer and the ruling would have been unimplementable.

### Ruling 2 — two objects, and the stated condition describes only the second

**Phase 1 (pre-lock) is a ruin probability. A rate is not computable.** The floor *is* peak − $2,000
until the peak reaches $52,000, so the first 4% excursion is **terminal** — at most one occurrence, and
a frequency against a single absorbing barrier is undefined.

| Sharpe | P(lock) | P(ruin) |
|---|---|---|
| 0 | 0.384 | 0.616 |
| 0.95 | 0.482 | 0.518 |
| 1.31 | 0.564 | **0.436** |
| 2.00 | 0.766 | 0.234 |
| 3.00 | 0.965 | 0.035 |

**At Sharpe 1.31 — the top of §61's table — the account still fails to survive phase 1 43.6% of the
time.** The zero-edge row is the validation: it converges to **exp(−1) = 0.3679** as marking tightens
(0.4068 daily → 0.3843 at 30-min → 0.3720 at 52,416 marks), matching the figure already in §4 of the
terminal report. A simulator that reproduces a known analytic result on the same object is worth more
here than one that merely runs.

**Phase 2 (post-lock) is a rate, and "a few times per year" was stated against a regime the account
does not start in.** It applies only after the lock, and only once cushion exists — at the lock point
the floor sits **exactly one $2,000 drawdown below equity**, so early in phase 2 "experiencing a $2k
drawdown" *is* hitting the floor.

### A bug caught before publication: the rate must be conditioned on survival

The first post-lock solve returned **SR ≥ 0.25 for ≤3 events/yr at R = 10%**, and reported ≤5 events as
**INFEASIBLE while ≤3 was feasible** — backwards, since tolerating more events must lower the bar. The
column beside it gave the diagnosis: **P(floor) = 88.8%.** Those paths were not experiencing few
drawdowns; they were **dying before they could accumulate any**, and dead paths stop counting.

Gridded, the all-paths metric is non-monotone and the survivor-conditioned one is monotone (R = 15%):

| Sharpe | events (all paths) | events (survivors) | P(floor) |
|---|---|---|---|
| 0.05 | 3.21 | **47.30** | 98.0% |
| 0.50 | 3.02 | 9.10 | 81.4% |
| 1.00 | 2.56 | 4.02 | 53.2% |
| 1.50 | 1.78 | 2.04 | 27.8% |
| 2.50 | 0.39 | 0.37 | 3.3% |

**Bisecting the all-paths metric would have published a bar that rewards dying early** — the same
failure class as §6's list: a quantity computed correctly for a different object than the one in hand.
This one was caught by the monotonicity violation, not by inspection, which is an argument for always
reporting the shape rather than only the root.

### THE OPERATIVE BAR

Post-lock, intraday marks (3,276/yr), start $52,000, floor $50,000, events among survivors. Sharpe a
floor, volatility a ceiling:

| annual return | ≤3 events/yr | max vol | P(floor) yr1 | ≤5 events/yr | max vol | P(floor) yr1 |
|---|---|---|---|---|---|---|
| 10% | **SR ≥ 0.80** | 12.4% | 52.9% | SR ≥ 0.55 | 18.1% | 69.9% |
| 15% | **SR ≥ 1.21** | 12.4% | 42.0% | SR ≥ 0.85 | 17.7% | 62.5% |
| 20% | **SR ≥ 1.61** | 12.4% | 33.4% | SR ≥ 1.15 | 17.4% | 55.3% |

**The event rate alone is not a sufficient bar** — every cell satisfying it still ruins often. Sharpe to
hold first-year P(floor) down:

| annual return | P ≤ 20% | P ≤ 10% | P ≤ 5% |
|---|---|---|---|
| 10% | 1.36 | 1.66 | 1.90 |
| 15% | **1.71** | **2.06** | 2.34 |
| 20% | 1.99 | 2.39 | 2.72 |

**A registration is held to whichever is higher.** For 15% at ≤3 events with P(floor) ≤ 10% that is
**SR ≥ 2.06**, not 1.21.

### What both rulings do to the bar, and where it sits

The expectation was that the operative bar would land materially above §61's 0.95–1.31 daily range.
**It does.** At 15%, ≤3 events: **0.95 → 1.21** on the rate alone, and **→ 2.06** once first-year ruin
is held to 10%. At 20%: 1.31 → 1.61 → **2.39**.

Against the chance bar SR\* = 0.1368:

| bar | Sharpe | ×SR\* |
|---|---|---|
| 10%, ≤3 events | 0.80 | 5.8× |
| 15%, ≤3 events | 1.21 | 8.8× |
| 20%, ≤3 events | 1.61 | 11.8× |
| 15%, ≤3 ev **and** P(floor) ≤ 10% | **2.06** | **15.1×** |
| 20%, ≤3 ev **and** P(floor) ≤ 10% | 2.39 | 17.5× |

**Against every effect the programme measured, the comparison does not require precision.** R01,
+0.452 bps and the largest effect found anywhere in six series, is **−0.028 net** of the 0.48 cost
floor; L12 is −0.174; P03's real leg is −0.280; L07 is negative in 108 of 108 cells. **A non-positive
net edge is Sharpe ≤ 0 at any volatility.** So the operative bar is not a demanding target the
programme fell short of — it is a target nothing measured here is on the same side of zero as.

The sharpest statement of that is now promoted into the terminal report §9: **the required gross edge
per trade falls with trade count but converges to 1.062× the best effect ever measured**, because the
0.48 cost floor alone exceeds 0.452. Trading more often cannot close the gap; neither can sizing, which
multiplies an edge and cannot supply one.

### What this section does NOT do

No series designed, nothing registered, no trial spent. §61's tables are retained and labelled
superseded, including its two open-decision notes, because deleting them would hide that the bar moved
and in which direction.

## 63. The S-series designed and filtered at S2; nothing registered (S1, S2, S6, S7)

**NOTHING REGISTERED. NO TRIAL SPENT. N stays 760, SR\* 0.1368, both chains verify. S5, S6 and S7
not run.** `hypotheses.yaml` is untouched. Design in `reports/S_SERIES_DESIGN.md`; arithmetic in
`reports/s_series_s2.json` from `reporting/s_series_s2.py`.

A seventh series — retail indicators tested against a matched arbitrary reference, nine entries,
timeframes 5m/15m/30m/1h/4h, each indicator its own hypothesis rather than a combined signal. It
is accounted for in the ledger as a seventh series (§11 of the terminal report, `CHECKPOINT.md`),
not as a side investigation.

### The overlap was reported before anything was designed, and it is most of the finding

**Five of nine proposed entries are already in `hypotheses.yaml` under another series letter, and
three of the five have measured firing rates on disk.** Found by reading the registry, which is
§59's third unadopted proposal ("read `hypotheses.yaml` before drafting a series") applied for the
first time *before* the drafting rather than after it. Three of twelve Q candidates were already
registered and one had spent 144 trials; the cost of not looking is on record.

| S | indicator | prior entry | its status | this entry is |
|---|---|---|---|---|
| S01 | fair value gaps | **L07** | retired at S8, **108 trials spent** | repeat |
| S02 | RSI(14) | **F10** | retired unpowered, never run | timeframe extension |
| S03 | VWAP | **L01** | blocked at S4, 237 events | repeat |
| S04 | EMA(20/50/200) | **L08** (+ F11) | blocked at S4; F11 retired on premise | timeframe extension |
| S05 | volume profile POC/VAH/VAL | none | — | **new** |
| S06 | Bollinger bands | **L11** | **withdrawn at S5 — never tested** | repeat |
| S07 | MACD(12,26,9) | **F11** | **retired on premise**, never run | repeat |
| S08 | stochastic %K/%D | none; F10's family | — | **new** |
| S09 | classic floor pivots | none as specified | a deterministic function of **L03**'s H/L/C | **new** |

**For the repeats, re-running costs trials for information already on file in three of four
cases, and the exception is worth separating.** S01 would spend ~30 trials to re-derive §38's
measured −1.18 to −5.01 bps. S03 would re-measure 237 events. S07 inherits F11's **premise**
retirement, and a premise is not repaired by sample at any size. **S06 is the one genuine
information gain:** L11 was withdrawn before it was ever tested, and the `confirmed_break` defect
that withdrew it is fixed (§41), so there is no L11 result to repeat.

### L07 already answered this series' question at the only adequate event count

The brief's question — are these indicators distinguishable from a matched arbitrary reference —
is L07's question. L07 answered it for fair value gaps in **108 of 108 cells, negative in every
one, at 1.8–10.3× cost**, with the decomposition sharper than the difference: the real zone loses
while the matched region wins (§38). **"Distinguishable" was established and was not tradeable**,
and the mirror is not registrable because the sign came from this data. Every S-entry inherits
that bar.

### A design finding that precedes the arithmetic: the timeframe axis is not one axis

For the five **state** entries (FVG, RSI, Bollinger, MACD, stochastic) changing the timeframe
changes the object — a 4h RSI(14) reads 14 four-hour bars. For the three **level** entries (VWAP,
volume profile, pivots) it changes only the detection granularity: the session VWAP, the session
POC and the prior-session pivot are the same prices on any bars. So those three entries' five
timeframe cells re-enter on the same touches, which the L-series already measured as **97–100%
pairwise overlap for every substantive hypothesis** (the placebo control the only disjoint route).

**Both directions recorded, as §43 required for L04:** BH over 30 correlated cells is
conservative, *and* a raw count of separations overstates the evidence. **It buys nothing on
trials** — N counts comparisons appended, not independent ones, so five correlated cells spend
five trials and raise SR\* for everything after. Correlation makes a grid cheaper in evidence and
no cheaper in trials.

### The S4/S5 vise, which is why S03 and S04 have no setting that works

L01 fires 237 times and L08 659–950 because of a precondition: price must sit ≥ d ATR away for
15–30 minutes before a touch counts. **Remove it and the condition fires on nearly every bar**,
because price crosses a VWAP or an EMA constantly — that is the L11/L05/L02-sweep degenerate
condition that failed S5 at entry-minute sd 0.05 and 99.6% high/low collision (§41). **Keep it
and the count is 6–25× below the S4 floor.** There is no intermediate setting that passes both,
and looking for one is parameter selection. This is also the reason the open `d` ATR
reference-period decision must stay frozen: resolving it *in order to* schedule these is choosing
a parameter to get a result.

### DEFF was measured for these objects and it is 3–6× worse than the bracket in use

The Q-series bracketed DEFF at 1.14–2.19. `peak_bps_l07.json` **measures** it for an intrabar
indicator at two of this brief's own timeframes: **5.79 at 15m rising to 12.72 at 30m.** State
entries were given 5.8 — the measured bracket's low end, the generous choice. Recorded because
§45's unit error has now recurred twice after its correction was written down (§54), and the
defence against a third is to use a measurement where one exists.

### The filter validates against three measured results before it closes anything

§60's standard is about runs, but a filter about to close nine entries owes the same
demonstration. Checked on the programme's three measured effects with a known S7 outcome:

| case | effect | per-event sd | Sharpe | vs SR\* then | recorded outcome |
|---|---|---|---|---|---|
| L07 @ tf=15m, w=1.6bps | 5.790 | 22.8 | **0.2539** | 0.1357 | separated 108/108 ✓ |
| L04 best cell | 3.543 | 64.7 | 0.0548 | 0.1367 | nominal, 0 BH survivors ✓ |
| L12 | 0.306 | 64.7 | 0.0047 | 0.1367 | 0 of 9 separated ✓ |

**Three for three, and the discriminating case is the positive one** — a filter that only ever
said "below the bar" would reproduce L04 and L12 by accident but not L07's separation.

### The two multiplicity objects, kept apart

**Within an entry:** 30 cells (5 timeframes × 3 parameters × 2 instruments), BH rank-1 at FDR
0.05, z = 3.1440. Post-2021 decides, which multiplies every bar by 1/√0.337 = **1.72×**. Best-cell
bars, post-2021, H=180m: S01 3.56, S02 4.61, S03 33.68, S04 16.82, S05 6.90, S06 3.54, S07 3.44,
S08 2.91, S09 7.33. **Four of nine — S03, S04, S05, S09 — have a best-cell bar above 5.79 bps, the
largest effect the programme has ever measured anywhere.**

**Across the programme:** at 30 trials each, N runs 760 → **1,030** and SR\* 0.1368 → **0.1406**.
The last entry faces N = 1,030. **+270 trials is a 36% increase in N and +0.0038 of permanent
SR\*, about twice what one series costs at the measured mean of 128 trials** (§61). Projections
hold the trial-Sharpe variance fixed at 0.0018559; new trials would move it too, in an
unpredictable direction, and they are labelled projections for that reason.

### Where the two meet, which is the result

SR\* is a Sharpe and the bars are in bps, so they are not comparable until converted. An effect
*e* against per-event noise anchor(H) has per-observation Sharpe *e*/anchor(H), so the effect that
merely **reaches** SR\* is SR\* · anchor(H): at N = 1,030 that is **9.10 bps at H=180m and 3.71 bps
at H=30m.**

**Four entries clear their own BH bar at H=30m in their 5m cells — S02, S06, S07, S08, at
1.19–1.88 bps — and every one of them sits below the prevailing SR\* by about a factor of two.**
They pass the within-entry correction and fail the across-programme one. **The comparison does not
turn on the horizon:** nothing in the series predicts above 2.0 bps, against 9.10 at H=180m and
3.71 at H=30m. The only entry whose magnitude reaches SR\* in either column is S01 — whose
magnitude is **measured rather than predicted, and negative.**

### Both horizons are reported on purpose

The bar falls as √H while the cost floor does not, so H=30m opens four entries and H=180m closes
them. **Choosing the horizon that closes the series would be choosing a parameter to get a result,
and so would choosing the one that opens it.** §53 is the record of that error being made in the
other direction — a selectivity optimum that did not survive re-measurement in bps. Both columns
are shown and the SR\* comparison resolves it without depending on the choice.

### The filter's categories, against its two predecessors

| series | candidates | closed at S1–S2 | could not state a magnitude |
|---|---|---|---|
| P | 13 | 9 | 5 |
| Q | 12 | 12 | 7 |
| **S** | **9** | **9** | **0** |

**Every S-entry states a direction and a trade rule, so every one is predictable — and that is
worse, not better.** The P- and Q-series' unpredictable candidates survived their filters only in
the sense that the filter could not reach them. Nine of nine predictable and nine of nine below
the operative bar is a stronger closure than nine of thirteen.

### Dropped for discretion, with one dropped on a stronger ground

Fibonacci retracements (the swing is chosen by eye; mechanising it substitutes a free parameter
and a different indicator), order blocks and supply/demand zones, trendlines and chart patterns,
Elliott wave and harmonic patterns, Wyckoff phases. **Ichimoku** is specifiable but is five
components read jointly, which the brief excludes, and its one separable limb is a displaced MA
with a band — S04/S06 again. **Supertrend, Keltner and parabolic SAR** are specifiable and are all
the same object as S06, differing only in the volatility estimator; folded into S06 as a
pre-registered parameter rather than given three entries at 30 trials each. **OBV, Chaikin money
flow and the accumulation/distribution line** are specifiable but are non-price observables — the
P-series class, closed — and walk into §54's correction that a volume-derived ratio is not
scale-invariant because its denominator is not stationary.

**The stronger ground:** order blocks were already tried mechanically as **N04/N05** and
**withdrawn at S6** — median distance from price 0.000, 61.4% exactly zero, so no placebo can
match them (§46). That is structural, like L06, not a specification gap.

### Registration requirements not met by the design as drafted

Recorded as unmet rather than assumed, because §54's P-series draft was written *after* §45 and
§52 and repeated both errors.

- **S07's scale invariance fails as drafted.** A MACD sign change is unit-free, but any threshold
  on MACD *magnitude* is in price points — **the N02 error exactly**, where an 8-point break was
  41 bps in 2010 and 2.9 bps in 2026 on an index that rose 14×. Must be normalised by price or by
  a trailing rank.
- **S09's thresholds are price levels by construction** and are admissible only under S2's escape
  hatch: state the price range and pre-register the era split.
- **S03 and S04 carry the open `d` ATR reference-period decision**, which is not theirs to resolve.
- **Four state entries (S02, S06, S07, S08) need the §55 matched control in bar mode** plus a
  clean-pool check, not a location placebo — a state has no location.
- **Five collinearity pairs are unmeasured:** S02↔S08 (RSI and stochastic %K are both bounded
  position-in-range measures on the same bars), S04↔S06 (a Bollinger band *is* an MA ± kσ),
  S04↔S07 (MACD is the difference of two EMAs; F11 retired an MA crossover as "the same family as
  F01"), S03↔S05 (VWAP is the volume-weighted **mean**, POC the **mode** — two statistics of one
  distribution), S09↔L03 (PP = (H+L+C)/3 of the prior session). **Four of nine entries are at risk
  of being a second look at another entry in the same series** — the one multiplicity cost the
  trial log cannot price, since N counts comparisons and not whether two were the same bet. The
  Q01/Q02 precedent (+0.972, +0.991 post-2021, P(long|fires) = 100%) says measuring this costs
  nothing and can collapse four entries into two.

### Against the stopping rule

**Condition 1 (§62).** The operative bar is **SR ≥ 2.06** at 15% with ≤3 events and first-year
P(floor) ≤ 10% — **15.1× SR\*** — and phase 1 is a ruin probability, 43.6% even at Sharpe 1.31.
**No S-entry has a route to it.** Stated without overclaiming: the largest magnitude any entry
predicts is 2.0 bps, which the convergence argument does not by itself forbid at high trade
frequency — **but it is a prior with no measurement behind it, and the one entry with a
measurement behind it is negative.**

**Condition 2 (§61).** 0 promoted in 35 registrations; P(a seventh series promotes ≥1) is 7.8%
on Jeffreys and 14.8% on Laplace, so a promotion must be worth 6.8–12.8× one series' cost. **The
S-series costs 270 trials against a mean of 128 and a median of 6.5.** And the base rate is
optimistic here for a reason specific to this series: **five of nine entries are already in the
registry, so it is substantially re-drawing from the same urn rather than drawing from a new one.**

**Condition 3 (§61.4).** The S-series was generated from a list of popular indicators, which is
unbounded and cheap — §2's dropped list is longer than the kept one. A series assembled that way
is selected by **availability**, not evidence, which is the failure the terminal report names in
its last line.

### Recommended order, and it begins with things that cost no trial

1. **The five collinearity measurements.** No trial; logs to `measurements.jsonl` on the same
   reasoning that keeps firing rates out of N.
2. **Firing rates for S05, S06, S07, S08 and S09**, none of which has a measurement of its own
   at any timeframe. No trial (§22). These are the weakest numbers in the design, and three of the
   five straddle at H=30m on the strength of them.
3. **S06 only, if anything** — the one entry that is both a genuine information gain and plausibly
   above its own bar in its 5m cell. It would still need the §55 control in bar mode, a clean-pool
   check, and the acknowledgement that it sits ~2× below the prevailing SR\*.
4. **Not registrable as specified:** S01 (answered, 108 trials), S03 and S04 (the S4/S5 vise),
   S07 (premise), S09 (a function of a retired null's inputs), S02 and S08 (below SR\*, and
   probably one hypothesis).

### Decisions taken rather than resolved silently

1. **Nothing was added to `hypotheses.yaml`.** Registering is what that file means, and the brief
   withheld it. The design lives in a report and this section.
2. **Predicted magnitudes are priors and say so** (§54's rule), with one exception labelled as
   such: S01's is L07's measurement.
3. **The method was taken unchanged from §54 and §59** rather than re-derived, so the S-series
   filter is comparable to the P- and Q-series filters instead of freshly favourable.
4. **Firing counts are labelled MEASURED or EXTRAPOLATED per cell** in `s_series_s2.json`, with
   the extrapolation rule stated. Eleven of 45 cells are measured on MNQ; the rest are not.
5. **Both horizons are reported** rather than one chosen, for the reason above.
6. **The trial-Sharpe variance is held fixed in the SR\* projection** and that is stated as an
   assumption, not buried. New trials change the variance as well as N.
7. **The series is counted in the ledger as the seventh**, at 9 drafted / 0 registered / 0 trials,
   exactly as Q is counted at 12/0/0.

## 64. The S-series is closed, at design (S1, S2)

**CLOSED. Nothing registered, no trial spent, N stays 760, SR\* stays 0.1368, both chains verify.**
§63 is the arithmetic; this section is the close, and the two findings it produced that outlive the
series are promoted into `programme_conclusion.md` §5 as findings 9 and 10, in the same form as the
eight already there.

**The series was designed specifically so it would not be a seventh search, and it closed on
arithmetic anyway.** Every entry stated a direction and a mechanical trade rule before anything was
measured; the overlap with the existing registry was checked before any new cell was drafted, not
after; nothing discretionary was admitted, and what could not be made mechanical was dropped and the
reason recorded (§63, "dropped for discretion"). None of that changed the result. §10 of the terminal
report argued in advance that a seventh series inherits the same four constraints as the first six;
this is the series that tried hardest not to, and the argument held anyway.

**L07 had already answered the series' central question, at the only event count in the programme
adequate to answer it.** The question this series asks — is a retail indicator's behaviour
distinguishable from a matched arbitrary reference — is exactly L07's question, run at 23,545 to
655,490 firings per cell, an order of magnitude or more above anything else on file. It came back
**108 of 108 cells separating, negative in every one**, 1.8–10.3× the cost floor, with the real zone
losing while the matched placebo won. Designing eight more entries around the same question at
hundreds or thousands of firings per cell was not a fresh look at the question; it was a second
attempt at an answer the programme's largest sample had already given.

**Two findings are promoted rather than left in the design file, because they are general rather
than specific to retail indicators:**

1. **An entry can clear its own correction and still have established nothing** (§5 finding 9 of the
   terminal report). Four of the nine S-entries — RSI, Bollinger, MACD, stochastic, each in its
   shortest-timeframe cell — separated from their matched reference at 1.19–1.88 bps against a
   within-entry BH bar reachable at that size. Every one of the four sat roughly half the prevailing
   SR\* when the two were put in the same units. The within-entry bar and the across-programme bar
   answer different questions, and a design that reports only the first is reporting the easier one.
2. **A filter closing every candidate it can evaluate is a stronger result than one that closes most
   of them** (§5 finding 10). The P-series closed 9 of 13 at no trial cost, but five of the
   thirteen could not state a magnitude and were closed by being unreachable, not by being tested
   against a bar. The Q-series closed 12 of 12, seven of them the same way. **The S-series closed 9
   of 9, and all nine were predictable** — none escaped the filter by having no trade rule to check.
   Zero unpredictable candidates is not a weaker finding than nine of thirteen; an unpredictable
   candidate survives a filter by being outside its reach, not by passing through it.

**Three design weaknesses stand unmet, not resolved, and are not claimed otherwise:**

- **Five of the nine entries — S05, S06, S07, S08, S09 — have no firing rate of their own at any
  timeframe.** Their counts in `s_series_s2.json` are extrapolated from a stated rule, not measured,
  and three of them straddle their own bar at H=30m on the strength of that extrapolation alone.
- **S07's threshold, as drafted, is in price points rather than bps or a trailing rank** — any
  threshold on MACD's *magnitude* (as opposed to the sign of its crossing, which is unit-free) repeats
  the exact error that retired N02: an 8-point break was 41 bps in 2010 and 2.9 bps in 2026 on an
  index that rose 14×. Not fixed here; flagged so a later registration does not inherit it silently.
- **Five collinearity pairs are unmeasured** — S02↔S08, S04↔S06, S04↔S07, S03↔S05, S09↔L03 — any one
  of which could turn out to be the Q01/Q02 case (+0.972 Spearman, +0.991 post-2021,
  P(long | fires) = 100%, found at no trial cost). Measuring them is the cheapest open item in the
  design and was not done because nothing was registered to require it.

**What this section does not do.** It does not register anything, open S5/S6/S7, or revisit the
recommendation in §63 — collinearity measurements and the four unmeasured firing rates remain the
only items that cost no trial, and S06 remains the only entry both genuinely new and plausibly above
its own bar, still short of the prevailing SR\* by about 2×.

## 65. The T-series: T01 and T05 measured, T02–T07 closed at S2; nothing registered (S1–S6)

**NOTHING REGISTERED. NO TRIAL SPENT. N stays 760, SR\* 0.1368, both chains verify. S5, S6 and S7
not run.** `hypotheses.yaml` untouched. Measurements logged to `measurements.jsonl` here (T01 ×2,
T02/T04 ×2, T05 ×3) and in `r-series-research` (R01's T05 split ×1), none counted in N. The draft
is saved as `T_SERIES_CANDIDATES.md` with corrections inserted as **[§65]** blocks. Reports:
`t01_volume_clock.md`, `t05_sign_asymmetry.md`, `t02_t04_scale_collinearity.md`, `t_series_s2.md`.

An eighth series drafted against the same data: the statistical character of the price path —
volume clocks, jump/diffusion, realised skew, path efficiency, sign asymmetry, elapsed time since a
large move, variance ratio. It is counted in the ledger as the eighth, at 7 drafted / 0 registered.

### T01 — volume clock. Reopens nothing; two premises corrected, two cells withdrawn

- **There are no dead bars.** Zero `volume == 0` rows in either product; an untraded minute is
  absent, not forward-filled. The mechanism is unequal weighting of *traded* minutes (MGC: 1 to
  10,400 contracts a minute).
- **Effective n falls, it does not rise.** At the mean-minute threshold, 0.48× (MNQ) and 0.41×
  (MGC) as many bars as traded minutes. The draft's trap — "if n rises, check it is not
  manufactured" — is never reached.
- **Kurtosis at matched n** (volume vs a trade-minute clock): MNQ 86 vs 112, 39 vs 73, 20 vs 51.
  MGC's only valid cell goes the other way, 67 vs 30 — single-row absorption, measured: built from
  minutes, a volume clock can merge quiet minutes but never split a busy one.
- **The pre-stated validity check failed in two cells, and they are withdrawn.** Before any
  result, the module said realised variance should be close across partitions at matched n and
  that a large divergence would mean the construction is wrong. Raw ratios came back 0.69–0.96.
  A first draft of the write-up then *explained* that gap (bid-ask netting) instead of applying the
  criterion — the post-hoc move the trial log exists to prevent. It was replaced by a test: restore
  each session's dropped first leg, which differs by partition. Result 0.854–0.963 — a partial
  explanation (most of the gap on coarse bars, almost none on fine). **MGC k=1 and k=5 stay outside
  ±10%, so their kurtosis figures (164 vs 433, 65 vs 329) — the most striking numbers in T01 — are
  withdrawn, not interpreted.**
- **The three improvements the draft promised do not follow.** α: `calibration.md` §A already found
  coverage indistinguishable at γ₄ = 115 and 226. n_min: falls, but is tens of events against
  floors in thousands. Detection floor: a power floor on a mean, σ- and n-driven — not recalibrated
  here, argued and labelled so.
- **F01's "4,125 against 19,722" is the superseded ceiling.** §22 measured 3,523 (MNQ) / 3,449
  (MGC) at best, 66 / 115 at worst. The brief repeated the pre-§22 number; the measurement uses the
  measured one. **No S4-blocked entry crosses its floor; none qualifies for re-registration.**

### T05 — sign asymmetry. Every closed conclusion survives the split, at reportable power

Each split is of numbers first **reproduced exactly** from the record — all 108 L07 cells
(`l07_cells.json`, events exact, means to 1e-9), P03 (`p03_stage1.json`), all nine R01 cells
(`r01_checks.json`) — the §38 decision-2 practice. Gaps are tested with **sessions as the unit**;
R01 on non-overlapping entries, the independence its registered t already assumed.

| | sides | gap | verdict |
|---|---|---|---|
| L07 MNQ | both negative in 54/54; weaker side ≥ 2.31× cost | median +0.23 bps; BH 0/54 | survives |
| L07 MGC | both negative in 54/54; weaker side ≥ 1.76× cost | median +0.13 bps; BH 5/54 | survives |
| P03 | +0.133 / +0.025; neither clears +0.625; real legs net −0.32 / −0.24 | p = 0.81 | survives |
| R01 | +0.492 long / +0.411 short (best cell) | p 0.41–0.95, sign flips | survives |

**No closed entry was averaging a real effect with a null.** L07 carries one small, consistent lean —
down-created gaps (traded long) are the more negative side on both instruments, 5–9% of the effect,
surviving BH only on MGC in one overlapping family. That also **closes the open item in
`level_conclusion.md`**: a bullish/bearish mix difference cannot manufacture a sign that holds on
each side separately. R01's long side alone nominally clears the 0.48 single-leg floor by 0.012 bps;
selecting it would be choosing a subset by its result, the split is not significant, and R01 is a
two-leg trade against 0.96.

**§60 applied to T05's own nulls.** "No asymmetry" is a null, so the pipeline had to recover an
injected asymmetry *of the size sought* — one side carrying the whole effect, a gap of 2 × |pooled| —
*at each run's own noise and n*, by adding it to the real paired differences. Recovered exactly and
detected everywhere: L07's least-powered cell on both instruments (power 1.00), R01 (≥ 0.995 in
eight cells, **0.68** in W=120 k=2.5), **P03 at 0.82**. P03's null is reportable, narrowly.

### T02/T04 — not one hypothesis; each fails on its own; J is not scale-free

- **Collinearity (the brief's gate):** Spearman ρ(J, ER) **+0.047 to +0.073** on non-overlapping
  windows, both instruments, every W — the predicted direction, a tenth of the 0.6 threshold.
  Firing overlap, the test that decided Q01/Q02, agrees: below independence, Jaccard ≤ 0.0015.
  **Registering both would not be one bet counted twice.**
- **But T02's condition selects almost everything:** J < j_low in 57–94% of windows. **T04's
  almost nothing:** ER > 0.5 in 0.08–0.19% of windows, ER > 0.8 in none — a third of its grid empty.
- **J is not scale-invariant — the P03 failure class through a new channel.** A ratio of moments of
  one series is invariant to multiplicative scale, not to price *discreteness*: as price rises on a
  fixed tick, fewer 1-minute returns are exactly zero, and every zero removes two bipower terms
  against one RV term. J's median halves across eras (index 0.093 → 0.049, zero returns 18% → 3%;
  MGC 0.112 → 0.046), so a fixed j_low selects a different share each era. **This is a transferable
  finding and a candidate addition to finding 6 of the terminal report**; it is recorded here and not
  promoted, which is the user's call. ER and RSkew are stable.

### The S2 filter — every predictable entry fails, and SR\* binds twice

Method unchanged from §54/§59/§63 (k = 54, post-2021 decisive, DEFF 5.8), plus one sensitivity §63
lacked: SR\* converted to bps with the **outright** per-trade σ (lenient) as well as the paired-
difference anchor. Verdicts are stated under the lenient one.

| | prior | own BH bar | SR\* in bps | binds | |
|---|---|---|---|---|---|
| T02 | 0–0.5 | 0.85 | 2.95 | SR\* | below both |
| T03 | 0–1.0 | 0.85 | 2.96 | SR\* | **clears its bar, below SR\*** |
| T04 | 0–0.5 | 59–218 | 2.98 | BH bar | below both |
| T06 | — | | | | cannot predict; F05 restated |
| T07 | — | | | | cannot predict; no primary |

T02's draft range (2–5) cites R01's +0.452 as its anchor, which supports ~0.5; its measured
analogues (P03 +0.079, L12 +0.306, R01 +0.452) give 0–0.5. **T03 is the second instance of
finding 9**: an entry clearing its own correction while sitting below the programme's bar. T06's
draft distinguishes it from "L-series volatility compression"; that was F05 — tested at adequate
power and retired — and T06 arms the same trade.

### What the draft's closing paragraph may and may not say

The draft asked, if T02–T06 came back null at adequate power, to state that the statistical-character
axis is closed and is the last. **They did not come back null; they were not run** — closed at
S1–S2 by arithmetic and by measured properties of their own conditions. That is a stronger reason
not to run them and a weaker claim about the axis: **not shown empty by evidence, shown not worth
searching with these instruments on this data at this cost.** And the data limit is specific — a
true volume clock and a jump/diffusion split free of the tick grid both need trade-level data that
is not on disk. Per §61 that is a reason to stop, not a ninth series.

### Errors made and caught in this work, recorded because the record is the point

1. **Figures written before they were measured.** A first draft of the [§65] markup stated
   ρ(J, ER) ≈ −0.74 / −0.79, "exceeds 0.6, one hypothesis", and "J moves at most a few hundredths
   across eras" — none of it measured; the measurement says +0.05 to +0.07 and a ~2× drift. Caught
   and discarded before any commit. **The worst class of error this programme can make**, worse than
   any §6 entry: not a constant computed for the wrong object, but no computation at all.
2. **An event-level permutation test for T05's gap** — the §45 unit error recurring a fourth time
   after its correction was written. Replaced by a session bootstrap; a test now pins that it is
   wider than the event-level version under a shared session shock.
3. **A NaN-poisoned rolling sum** in the T02/T04 module: one boundary NaN made every later window
   NaN. The S2 filter had already consumed those NaN firing rates once; both were rerun. Pinned by
   test.
4. **`np.setdiff1d` inside a 10,000-iteration loop** — a multi-minute hang misread at first as data
   size.
5. **Memory, four times.** `definitions.load` (~626 MB) now OOMs alone on this machine with the
   editor open; T05 builds the same grid in year chunks (470 MB) and the FVG zones in row chunks,
   both pinned equal to the shared code by test and, at run time, by every one of 108 cells
   reproducing to 1e-9. R01's split OOM'd calling the evaluator eighteen times and was rewritten on
   the registered non-overlapping statistic. T02/T04 was rewritten per era. The first T01 loop was
   split one (product, k) per process.
6. **The T01 realised-variance criterion explained instead of applied** — above.
7. **A wrong figure given in conversation, not committed:** MGC's tick was described as ~8 bps in
   2010; it was 0.78 bps. The mechanism did not depend on it.

### Decisions taken rather than resolved silently

1. **Nothing added to `hypotheses.yaml`; S5–S7 not run.**
2. **Withdrawn cells stay in the tables, marked**, not dropped — a cell that vanishes is
   indistinguishable from one never computed.
3. **R01's p-value uses the normal tail**, not Student's t: `r-series-research` does not declare
   scipy, and at Welch df in the thousands the two agree beyond the precision reported.
4. **ρ(J, ER) on non-overlapping windows.** The first run used every rolling window (+0.05 to
   +0.08); windows sharing W−1 of W returns carry almost no independent information.
5. **T04's `|net| > k × ATR` clause omitted** — the draft fixes neither k nor which ATR.
6. **The discreteness finding is not promoted into the terminal report.** Finding 6 of
   `programme_conclusion.md` is the natural home; adding it is left to the user.

### Addendum, 2026-10-02, after `5b4e51d` — error 1 was model-dependent

*Appended after commit rather than edited into the list above, so the section reads as committed.*

**The figures in error 1 were written by a session running on Sonnet (`claude-sonnet-5`), selected by
mistake for this work.** The same work was then redone on Opus, which measured them, found them
contradicted, and discarded them before any commit. **This was not a rule failure.** The standing rule —
measure before asserting, and nothing enters the record unverified — held: the numbers never reached a
commit. What failed was the model, which wrote down results it had not computed. A rule that catches
that before commit is a backstop, not a reason to keep generating the error.

**Practical implication, recorded as a working rule: design and measurement tasks in this programme do
not route to Sonnet, even when they look routine.** The figures in question were exactly the kind that
look routine — a correlation and an era table, sitting in a markup block — which is what made them
dangerous.

**Scope, checked rather than assumed.** §64 and the terminal report's findings 9 and 10 were also
written in that Sonnet session. Their figures restate §63's computed output, and were re-verified
against `reports/s_series_s2.json` on 2026-10-02: the four 5m-cell bars (1.88, 1.45, 1.41, 1.19 bps),
SR\* in bps at the N each would face (3.64–3.70), and N 760 → 1,030 / SR\* 0.1368 → 0.1406 all
match. The incident does not extend to them.

## 66. The T-series is closed (S1, S2)

**CLOSED. Nothing registered, no trial spent; N 760, SR\* 0.1368, both chains verify.** Seven
measurement records in this repository (m00116–m00122) and one in `r-series-research` (m00003), none
counted in N. §65 is the measurement; this section is the close.

**T01 closes the methodological route.** A volume clock was the one T-series idea aimed at a binding
constraint rather than at a new effect, and it does not work here for a reason that is structural, not
a matter of tuning: **effective n falls under it rather than rising** (0.48× MNQ, 0.41× MGC), because
there are no dead bars to remove — the continuous series holds traded minutes only, and a volume clock
can merge right-skewed traded minutes but never split one. So the floor that blocked L01, L08 and F01
is a power floor that resampling does not move. That last step rests on the floor's construction (an
injection-recovery power sweep on a mean) and on `calibration.md`'s measurement that coverage does not
separate at γ₄ 115 against 226 — not on recalibrating the floor under a volume clock, which was not
done.

**T05 validates the programme's sign-symmetric design rather than exposing it.** Every hypothesis in
seven series was built the same way long and short; nobody had checked that choice. Split by the sign
of the conditioning move, L07 (all 108 cells), P03 and R01 each carry their effect on both sides, at
power §60 accepts. No closed entry was averaging a real effect with a null. **It also closes the L07
direction-mix item open since the L-series** (`level_conclusion.md`): a sign that holds separately for
bullish and bearish gaps cannot come from the mix between them.

**T02 and T04 are not collinear, and each fails independently.** Their conditioners correlate at
+0.05 to +0.07 and their firings overlap less than chance, so registering both would not have been one
bet counted twice. But T02's condition holds in 57–94% of windows — it selects almost nothing — and its
conditioner is not scale-free; T04's holds in under 0.2%. **T03 is the S-series finding repeating:** it
clears its own BH bar (0.85 bps) while sitting below the prevailing SR\* (2.96 bps). T06 restates F05;
T07 has no primary.

**The statistical-character axis is closed alongside level, state and time.** It was the fourth and last
structural dimension reachable from the data on disk — where price is, when, in what state the market
is, and how price arrived. The basis is the one the Q- and S-series closed on: arithmetic and measured
properties of each entry's own condition at S1–S2, not nulls at adequate power. **What remains requires
a data purchase or an account structure permitting constructions this one does not** (terminal report
§10, items 1 and 2); the T-series makes the data item concrete, since a true volume clock and a
jump/diffusion split free of the tick grid both need trade-level data.

**The discreteness finding is promoted** — as finding 11 of `programme_conclusion.md`, a new finding
and not an amendment to finding 6. Finding 6 covers a ratio whose denominator trends, as in P03. J is a
ratio built from one return series in which both terms scale together; it still drifts because the tick
grid underneath does not, and T02's jump fraction halved across eras for that reason. A reader applying
finding 6 to J would have concluded it was safe, so finding 6 does not cover it. This supersedes §65's
decision 6.

**Verification.** 19 of 20 test files pass, run one file at a time per CHECKPOINT. **`tests/test_roll.py`
was OOM-killed after 12 of its 18 tests and is unverified this session.** It covers `data/roll` code that
this change does not touch, and it is not claimed passing.

## 67. U01 registered and blocked on event count; the fill curve is arithmetic (S1–S4)

**A single hypothesis, not a series. Registered as U01, status `blocked_insufficient_events`. No
trial spent: N 760, SR\* 0.1368, chain intact. Two measurement records (m00123 MGC, m00124 the
index), not counted in N. S5, S6 and S7 not run.** Measurement in `reports/u01_gap_fill.md`
(`reporting/u01_gap_fill.py`); entry in `hypotheses.yaml` and `FUTURES_STRATEGY_HYPOTHESES.md`.

**The claim, and its weight.** "Large opening gaps — 0.4% or more at the open of a new day or week —
fill same-session only about 8% of the time." The source is a social media clip describing its
author's own backtest: no trial count, cost assumption or control visible, and no instrument or gap
definition stated. **It carries no prior weight and is registered on its own terms**, with the same
`provenance` block L11 carries.

### The condition, fixed before counting

In this programme's session convention: **daily** is the 18:00 ET reopen after the 17:00–18:00
maintenance break against the prior session's last price; **weekly** is the Sunday 18:00 ET reopen
against Friday's. The 09:30 RTH open against the 16:00 close is not used — index futures trade
through it, so it is a move in continuous trading, not a gap in the futures price. Choosing between
the two readings by which one fills less would have been selecting the condition by its result, so
the choice was made first and is recorded as a decision the user can overrule.

Validity rules, and when each was fixed:

1. **Same contract** for the open and the prior close (a roll is not a gap), and a **normal break**
   (< 6 h daily, < 3 days weekly). Fixed before counting.
2. **The open must be an open: first print within 5 minutes of the reopen.** Fixed after seeing the
   delay distribution — 87% of 2010 MGC sessions first traded more than 15 minutes late — and before
   any count of large gaps or any fill rate.
3. **The prior close must be a close: the prior session traded within 5 minutes of its own
   scheduled close** (that product-year's modal last-print time; the schedule moved — index bars
   after 16:15 ET do not exist before 2015, §59). **Fixed AFTER a first count and fill table had been
   seen**, and recorded as such. It was diagnosed from a coverage anomaly, not the fill rates: index
   "daily breaks" of ~21.5 hours in 2010–2012 traced to sessions holding ~110 bars that end around
   20:30 ET — the early NQ data is incomplete (median 113 bars a session in 2010 against 1,380 now),
   and MGC sessions before ~2016 are thin. **It can only remove sessions, so it cannot move the event
   count toward the floor**; the blocking verdict is robust to it in direction. First-run counts (127
   index, 54 MGC) are superseded by those below.

### Firing rate: blocked, like F01

| | daily opens | gaps ≥ 0.4% | weekly opens | gaps ≥ 0.4% | total (post-2021) | floor (180m proxy) |
|---|---|---|---|---|---|---|
| index (NQ→MNQ) | 2,634 | 41 | 484 | 63 | **104 (42)** | 5,884 |
| MGC | 2,236 | 3 | 607 | 43 | **46 (28)** | 2,862 |

**57× and 62× short on the full sample, more on the post-2021 half that decides.** A session-length
hold has no resolved floor at all; the 180-minute proxy is the most generous one that exists. The
brief anticipated "the low hundreds"; it is tens to one hundred. Nothing further is needed for the
verdict, and the entry's `blocked_reason` states the arithmetic, not a finding about the market.

### The fill curve: a smooth decline that tracks a random walk

Measured as the brief asked, a measurement and not a trial: same-session fill by gap size on a grid
fixed before measuring, daily and weekly, both instruments, against the reflection-principle
prediction 2(1 − Φ(g/σ)) for a driftless walk, σ the session's own realised volatility after the open
(and, as a check, the trailing 20-session median).

- **Shape: a smooth decline in all four panels, with no break at 0.4% or anywhere else.** 0.4% is a
  cut on a continuous relationship and has no special status.
- **Weekly opens — where most large gaps are — track the random walk.** Overall MGC 83.7% observed
  against 85.4% predicted (z −0.9); the index 76.6% against 81.9% (z −2.6, concentrated at
  0.1–0.2%). At and above 0.4% the bins agree within a few points (73 vs 72, 69 vs 71, 56 vs 59). One
  MGC bin (0.5–0.75%, n = 18) sits at z −3.6 with both neighbours on track: one of ~36 bins, not a
  break.
- **Daily opens fill MORE than the walk** (the index +7.9 points, z +7.4; MGC +4.0, z +3.5), at gaps of
  a few ticks (median gap/σ ≈ 0.1) — consistent with the reopen print itself reverting. That is a
  microstructure effect, in the direction opposite to the claim, far below 0.4%.
- **The "8%" is not what happens on these instruments.** Gaps of 0.4% or more fill 46.5% (MGC weekly)
  to 80.5% (index daily) of the time, and all three of MGC's daily ones — what arithmetic predicts. The clip may describe another
  instrument or definition; it does not say.

**By the brief's own test, U01 closes here twice over:** no effect beyond arithmetic at the stated
threshold, and too few events for any test of it to carry a verdict.

**No threshold was selected from the curve.** Picking the best-performing gap size would be a
search over thresholds and would have to be counted as one; the curve is reported, not mined.

### What the registration records, as the brief required

- **The 8% is descriptive and does not support a trade.** Non-fill includes drifting sideways,
  continuing away from the gap and partial retracement; only continuation pays. The S2 claim is
  stated as the same-session forward return in the gap's direction, real minus a matched control,
  against the cost floor in the post-2021 half. **Predicted magnitude 0 bps**: the only measured
  input matches the zero-drift walk, whose signed return has mean zero.
- **The control, chosen before any S6 work: state_control in strict (session) mode, matched on
  ex-ante volatility quantile, time of day and year.** The alternative — a 0.4% move at the same
  clock position with no gap — cannot be built at a reopen: any displacement at the open *is* a gap,
  so the comparison would be taken minutes or hours later and reintroduce L07's timing confound
  (§38), while holding displacement fixed and leaving the named confound, the volatility regime,
  free. Clean pool for strict mode: 2,233 / 564 (MGC daily / weekly), 2,593 / 421 (index) — ample.
- **Credit where due: 0.4% is a percentage, so the threshold passes §52 natively**, with no
  restatement and no era-split escape hatch — unusual here (N02's points, L07's ticks, P03's ratio
  and T02's "scale-free" J all needed correcting).

### Registry changes made to admit it

- **The ID and catalog checks accepted `[FLNP]\d\d`**, with a comment that the pattern widens
  "deliberately when a series is opened". U01 is not a series; the pattern is widened to
  `[FLNPU]` with a comment naming U as single hypotheses outside any series. Extended, not
  loosened — an unknown letter still fails.
- **The 8-hour hold check is stricter than the rule it stands in for.** A same-session hold from the
  18:00 reopen to 16:55 is ~23 hours, yet never crosses 17:00 and so satisfies the account. The check
  would reject U01 if it were untested; blocked, it does not bite. Recorded, not changed.

### The base rate moves trivially

Registrations go from 35 to **36**, still 0 promoted and 15 that spent a trial. §61's per-registration
exact 95% upper bound moves from 0.0820 to 0.0798. §61 is not rewritten; the figure is noted here.

### Decisions taken rather than resolved silently

1. **The CME reopen reading**, not the RTH open — above. The user can overrule it; doing so would be a
   new registration, not a re-cut of this one.
2. **The stale-close rule was added after results were seen**, and is recorded as such with its
   diagnosis and its one-directional effect.
3. **MGC's thin early years are excluded by the validity rules, not by year** (2011–2015 retain
   22–102 valid opens a year against ~238 from 2016).
4. **The session's own realised volatility is the primary random-walk scale**, because it absorbs the
   volatility-regime confound the brief names; the ex-ante scale is reported beside it and agrees.
   Realised volatility on 1-minute bars slightly overstates σ through microstructure noise, which
   biases the prediction toward MORE fill — the wrong direction to manufacture the daily excess.

## 68. U01: four rulings recorded (S1, S2)

**No trial spent; N 760, SR\* 0.1368. Nothing measured anew except a provenance check of the vendor
file.** §67 is the measurement; this section records how its open points were ruled.

1. **The CME reopen definition is settled, and recorded in the entry** (`definition_settled`), not
   left as a session decision. Index futures trade through 09:30, so a cash-open displacement is a
   move made in continuous trading rather than a gap in the futures price; the reopen is the only
   point where the futures price can gap. **A cash-open version would be a separate registration with
   a different mechanism** — cross-market price discovery at the equity open, not a discontinuity in
   the futures price.

2. **The daily-open observation is recorded as a measured property in its own right** — in the
   entry (`s1_measurement.reopen_microstructure`) and in `u01_gap_fill.md`, not discarded with the
   hypothesis. At daily reopens small gaps fill more often than a driftless walk predicts (the index
   +4.7, +8.8 and +15.1 points at 0.05–0.3%, z +3.1 to +4.3; MGC the same direction, smaller); weekly
   opens do not show it significantly. It was not what U01 registered and is not pursued.

   **A correction to how it was first described.** §67 and the session report placed the excess "at
   gaps of a few ticks". **They are 5–30 bps** — from about 6 ticks (MGC, 2010, smallest bin) to over
   200 (the index today) — small only relative to session volatility (gap/σ 0.07–0.22). That matters
   because "not tradeable at that magnitude" was ruled on the few-ticks description. On the corrected
   scale the record does not assert it: the excess is a touch-probability difference, not a measured
   return, so **tradeability is not established either way** — the same distinction U01's entry draws
   for the 8% — and the observation is recorded as not pursued rather than as untradeable. The
   reverting-reopen-print reading is an interpretation, not a test.

3. **The early-NQ session-length defect is added to the terminal report's error table (§6).**
   2010–2012 index sessions end in the evening — the 2010-06-08 session holds 119 rows ending 20:30
   ET with none in RTH — so each such "prior close" was an evening print and the next reopen showed a
   fake 21-hour break: every bar valid, no check failing, the count wrong downstream. **Provenance
   checked before it was recorded:** the same 119 rows, ending 00:30Z, are in the vendor's own
   `ohlcv-1m.NQM0.csv.zst`, the parsed parquet and the continuous series, so the defect is in the
   SOURCE DATA and the pipeline reproduced it faithfully. It was found through the break-length
   anomaly, not the fill rates, and the validity rule that fixed it can only remove sessions, so it
   cannot bias the count toward the floor. (The first lookup matched `MNQM0` for `NQM0` — a substring
   glob — and returned nothing; the exact file was then read.)

4. **The 8-hour hold check is left as noted, not loosened.** A check stricter than the account rule
   fails safe; relaxing it for a blocked entry would be fixing a test rather than an entry.

## 69. V01 registered and blocked at its ceiling; no forward return computed (S1–S4)

**A single hypothesis, registered post-hoc and marked so. Status `blocked_insufficient_events`. No
trial spent: N 760, SR\* 0.1368, chain intact. Two measurement records (m00125 MGC, m00126 the
index), not counted in N. No forward return was computed; S5, S6 and S7 not run.** Measurement in
`reports/v01_reopen_rate.md` (`reporting/v01_reopen_rate.py`).

**The mechanism**, as given: the first print after the CME maintenance break is set against thin
depth, so a displaced reopen is partly a liquidity artifact that corrects when real depth arrives;
the counterparty is whoever quoted into the thin book, and they persist because someone has to make
the first price.

**A citation corrected before it entered the record.** The brief called this "L03's absorption
mechanism". The absorption mechanism is **L02's** (its absorption arm: "whoever holds an overnight
position that must be adjusted once real depth arrives") — retired at S7 on a null, 0 of 27. L03's is
a stop sweep, forced flow beyond a reference point: a different counterparty. The entry cites L02.

**Provenance, marked rather than smoothed.** The observation came from U01's fill curve (§67–§68), so
the mechanism was written after the effect was seen, although it predicts the direction
independently. That is the shape §38 declined to register for L07's mirror; V01 is registered only
because it is blocked, with the order of events in its `provenance` block and the 36 looks (9 bins ×
2 open types × 2 instruments) that produced it.

### Two conflicts in the brief, and how they were resolved

1. **"Measure the forward return against the volatility-matched control" versus "do not run S6 and
   do not spend a trial".** A real-minus-control forward return IS the S6/S7 comparison, and by the
   programme's rule a comparison is a trial logged before it runs; the P- and Q-series reviews
   computed no forward mean before registering (§59). Measuring it unlogged would breach the trial
   log; logging it would breach the brief.
2. **"Whatever threshold defines the displacement range where the excess appears"** is a range chosen
   from U01's curve — the selection the U01 brief itself ruled out.

**Both dissolve on one costless measurement.** V01 fires at most once per daily reopen, so the count
of every valid daily reopen with a nonzero displacement is the largest any threshold could leave. If
that ceiling is below the floor, every threshold is blocked — none has to be chosen — and no return
could change the verdict, so the outcome look is moot rather than skipped.

### The ceiling

| | ceiling (every reopen fires) | post-2021 | floor 60m (the mechanism's scale) | floor 180m (most generous) |
|---|---|---|---|---|
| index (NQ→MNQ) | **2,469** | 1,015 | 19,722 — 8.0× short | 5,884 — 2.4× short |
| MGC | **1,926** | 901 | 5,620 — 2.9× short | 2,862 — 1.5× short |

On the post-2021 half that decides, 5.8× and 3.2× short of even the generous floor. Adding the Sunday
reopens — excluded by the mechanism's own wording, since they follow the weekend close rather than the
maintenance break — would give 2,942 and 2,499, still below; the exclusion does not decide the verdict.

### What else registration surfaced

- **Scale.** Median |displacement| is 2.55 bps (MGC) and 3.01 bps (index), 0.03 of trailing session
  volatility; p90 9.15 and 13.34 bps. Any threshold would be stated in volatility units. None was set.
- **The S2 magnitude ceiling does not close it.** A fade cannot return more than the displacement, and
  the median displacement sits above both cost floors. The event count closes it.
- **No valid control as specified.** With no threshold the condition fires on every valid daily
  reopen, so the volatility-matched control in strict mode has an empty clean pool — the L06
  disposition, and the registration-time clean-pool check fails. A threshold would create a pool, but
  the comparison would become large against small displacement, a dose-response design needing its
  own justification.
- **13.9% of MGC's valid daily reopens print exactly at the prior close** (zero displacement, no
  direction) — counted out, not faded.

### The base rate

Registrations 36 → **37**, 0 promoted, 15 that spent a trial. §61's per-registration exact 95% upper
bound moves to 0.0778. Not rewritten there; noted here.

### Decisions taken rather than resolved silently

1. **The forward return was not measured**, for the reasons above. If the economics number is still
   wanted, it is a trial: logged first, against the volatility-matched control, with a threshold and a
   horizon fixed beforehand. That is the user's decision, and it would not change the event-count
   verdict.
2. **No threshold was set**, rather than a curve-chosen one recorded as provisional.
3. **The Sunday reopen is out by the mechanism's wording**, and its inclusion is reported beside the
   verdict so the exclusion can be seen not to decide it.
4. **The 60-minute horizon** is the mechanism's own clock ("when real depth arrives"); the 180-minute
   proxy is reported beside it as the most generous floor.

## 70. The cost-floor audit, scoped but not yet quoted; V01's prior evidence corrected (S8)

**No trial spent; N 760, SR\* 0.1368. No market data downloaded, nothing purchased.**

### 1. Auditing the cost floor — what the record already settles

Every series closed against 0.48 bps (MNQ) and 0.65 (MGC), and the convergence result (§9 of the
terminal report) rests on 0.48 exceeding R01's +0.452 — a margin of **0.028 bps, about $0.13 per MNQ
round trip on $48,000**. The floor has never been checked. Its composition, from `CLAUDE_FUTURES.md`
§4, decides what a quote pull can and cannot do to it:

| | commission (fee table) | spread (one assumed tick) | floor |
|---|---|---|---|
| MNQ | 0.38 bps (≈ $1.82 round trip) | 0.10 | 0.48 |
| MGC | 0.53 | 0.12 | 0.65 |

- **About four-fifths of the floor is commission**, which no market data measures.
- **For a market-order round trip, quotes can only confirm or RAISE the spread component, never lower
  it.** A futures book cannot quote inside one tick, so crossing it costs at least the one tick the
  0.10 already assumes; wider spreads (overnight, thin reopens, event minutes) add to it.
- **So the convergence result inverts only through the commission or through passive execution.** At
  exactly one tick of spread it inverts if all-in commission is below 0.352 bps — **about $1.69 per
  round trip against the assumed $1.82**. Or if orders fill passively and EARN the spread, which is a
  question of fill probability. The first is a fee-schedule check; the second needs order-level data
  and the strategy's own order behaviour. **Neither is answered by mbp-1.**
- **An inversion would not rescue R01.** R01 is a two-leg trade against a 0.96 floor, and its effect is
  smaller than one tick of its coarser leg (0.569 bps on MES, `r01_checks.json` CHECK 2) — a spread
  that cannot be crossed for less than the effect. The convergence statement compares the best
  measured effect with a one-leg floor in the abstract; it is not R01's own economics.

### 2. The quote, and why it is not in this section yet

**There is no Databento API key on this machine.** `.env` holds FTP batch-delivery credentials (a
12-character password, not a `db-` key), and the historical metadata API accepts only a key. The cost
was not estimated from memory: pricing is usage-based and changes, and a remembered number in an audit
of an assumed number would be the wrong kind of error.

What exists instead, committed so the quote runs the moment a key does
(`reporting/cost_floor_quote.py`, endpoints and parameters confirmed from Databento's own client
source, metadata calls only — nothing downloaded or billed):

- **Front-month symbology** (`MNQ.v.0`, `MGC.v.0`, stype_in `continuous`) as the primary quote: the
  spread a strategy pays is the front month's. The ohlcv-1m pull (~$40, the scale reference) used
  `parent` symbology — every expiry and calendar spread — which in mbp-1 would price quotes nobody
  trades; parent is quoted beside it for the full and recent windows so the difference is visible.
- **Three windows per instrument:** full range (MNQ from 2019-05-06, when it began; MGC from 2010-06-06),
  the last two years, and the sample.
- **The sample is pre-registered** (`reports/spread_sample_sessions.json`): 30 full CME sessions per
  instrument (18:00–17:00 ET, so each spans the whole trading day), 10 per era, two per weekday, none
  on adjacent days, drawn once with a fixed seed from sessions on disk — **before any quote or any
  quote data exists**, so it cannot be chosen after seeing anything. It happens to include 2020-03-09
  and 2020-03-11 on MNQ, which is what an unselected draw should be allowed to do.

### 3. What a 30-session sample would and would not establish

**Would establish:** the quoted spread's distribution by hour of the CME day, typical (median) and
worst-case (p95, p99), in ticks and bps, per era; how often the spread exceeds the one tick the floor
assumes; top-of-book size, i.e. whether a one-lot fills at the touch; the 18:00 reopen specifically
(the thin-liquidity minute U01 and V01 concern). Those are most of what the spread component needs,
and they can only confirm or raise it.

**Would not establish:** slippage and fill probability, which depend on order type, latency and queue
position rather than on quotes; anything about passive execution — the one route by which spread cost
could fall below a tick; the commission, which is 79% of the floor; the spread on the specific minutes a
strategy would trade, conditional on its signal; and rare tails — thirty sessions resolve a typical hour
well and a news minute poorly.

### 4. V01: L02 is not prior evidence against it — corrected

**The V01 entry overstated the prior evidence.** It placed L02's absorption arm — same counterparty,
retired at S7 on a null, 0 of 27 — beside V01's mechanism as though that null bore on it. **It does
not.** L02 tested **only the 09:30 cash-open range** (`[09:30, 09:30 + W]` ET), **on MGC alone** at one
horizon; MNQ was excluded on event count. On MGC it measured cross-asset spillover from the equity open,
and its own note, written before it ran (§42), says the null "does not refute the mechanism, which was
never properly exposed." **It never tested the CME reopen.** The only registered entry that touches the
reopen at all is L06's `open_CME` level, which stopped at S6 — a magnitude-only condition with no valid
control — and was never tested. **V01's mechanism had no prior test.** Corrected in the entry and its
catalog section; §69 stands as written.

## 71. The cost-floor audit's premise corrected; a method finding on citing prior evidence (S2, S8)

**No trial spent; N 760, SR\* 0.1368. Nothing measured anew.** §70 is the analysis; this section
records it as a correction to the audit's own premise, and promotes one method finding.

### 1. The audit's premise was wrong, and the correction is recorded as such

The audit was framed as: the 0.48 / 0.65 floor has never been checked, and **if the real floor is
lower**, the convergence result inverts — so measure it with top-of-book quotes. **Quotes cannot lower
the floor.**

- **The floor is about 80% commission and 20% spread on both instruments** (MNQ 0.38 + 0.10, 79%
  commission; MGC 0.53 + 0.12, 82%).
- **The spread term already assumes exactly one tick, the minimum a futures book can quote.** For a
  round trip that crosses the spread, quote data can therefore only CONFIRM or RAISE that term.
- **The convergence result flips only if all-in commission is under about $1.69 per MNQ round trip
  against $1.82 assumed — a margin of $0.13 — or if orders fill passively and earn the spread rather
  than paying it.** Neither is measured by mbp-1.

### 2. The practical consequence

**The highest-value cost audit is confirming actual all-in commission (broker, exchange, clearing and
NFA fees, per side, at the account's actual tier) against the assumed $1.82 MNQ round trip** — a
fee-schedule check, not a data purchase. It addresses ~80% of the floor, where a $0.13 difference
decides the convergence result, and costs nothing but reading a schedule.

**`reporting/cost_floor_quote.py` stays committed and ready**, with its pre-registered 30-session
sample, **but it audits the smaller term.** It can show how often and by how much the spread exceeds
one tick — by hour, era, and at the thin 18:00 reopen — which can only add to the floor. It is worth
running before any strategy's economics turn on the spread; it is not the audit that could invert the
convergence result.

### 3. Passive fills: the route no quote data can reach

Of the two routes that could move the floor down, **passive execution is the only one that needs a
measurement this programme cannot make from quote data.** A resting order that fills earns the spread
instead of paying it — fully passive on both sides, the MNQ floor would fall from 0.48 to about 0.28
bps. But whether it fills, and what it is filled against, are the questions: **fill probability and
adverse selection require resting orders and a measured fill rate** — order-level data at minimum,
and properly the strategy's own orders on a live or demo account. Quote data describes the queue a
resting order would join; it cannot say whether the order would have been filled, or on which side of
the move.

**The other route, commission, is not a measurement problem.** It moves the floor by whatever the fee
schedule says — by more than the $0.13 margin if the real schedule differs materially (an all-in $1.20
round trip would put MNQ's floor near 0.35 bps) — and §2's check determines it exactly.

### 4. Method finding — promoted to the terminal report as finding 12

**An entry can be recorded as previously refuted by matching on counterparty description rather than
on what was actually tested.** V01's registration placed L02's absorption-arm null (retired at S7, 0
of 27) beside V01's mechanism because the two name the same counterparty — whoever is positioned
against thin depth when real liquidity arrives. **What L02 tested was different in every respect that
matters:** the 09:30 cash-open range, on MGC alone, where it measured spillover from the equity open
into gold — and a note written before it ran (§42) stated that its null could not refute its own
mechanism. **V01's mechanism had never been tested by anything** (§70).

**Two steps produced it, and both are recorded.** The brief named the prior entry by its mechanism
(and as L03, corrected to L02 in §69). The registration then carried that mechanism match through to
the prior entry's RESULT without checking its test — the session, the instrument, the horizon, and the
entry's own statement of what its null could establish. The second step is the one a rule can catch,
and it was mine.

**Rule:** before citing a prior entry as evidence for or against a new one, check what it TESTED —
session and clock, instrument, horizon, condition, and any pre-written limit on what its result can
establish — not what it is ABOUT. A shared counterparty is a mechanism match, not an evidence match.

## 72. The W-series: daily horizons were reachable all along; what binds there instead (S1, S2)

**Designed, not registered. No trial spent; N 760, SR\* 0.1368. Two measurement records (feasibility:
dispersions, granularity, correlation — no strategy return computed).** Draft: `W_SERIES_CANDIDATES.md`;
measurement: `reports/w_series_feasibility.md`.

Asked to find where the record's "end of the road" is wrong rather than to add another intraday search.

### The premise the record got wrong

**Daily horizons were filed as forbidden (terminal report §10) and are not.** The rule is flat by 17:00;
an 18:00-to-16:55 hold never crosses it, and chaining such holds re-creates daily exposure. Measured: the
excluded 16:55→reopen window carries 1.1–1.6% of a day's variance, the held part correlates 0.99 with the
full day, and one round trip is 0.34–0.56% of a day's SD (1.2%/yr MNQ, 1.6%/yr MGC traded every day).
**At a daily horizon the cost floor does not bind.** No series ever tested a daily-horizon strategy. The
firm's reading of an overnight hold inside one CME trading day is the load-bearing premise to confirm.

### What binds instead — corrected mid-design on the user's point

A first draft concluded that account size binds. **The user corrected it: a prop account permits 20–30
micros, so it is not margin-limited.** Correct, and the draft had framed a risk limit as a capacity limit.
What remains is the $2,000 trailing drawdown, and what it implies depends on the objective:

- **Under §62's ruled bar** (ruin ≤ 10%, max vol 12.4%): total risk ≈ $391/day of σ. One MNQ ($847/day at
  $59k notional) or one MGC ($538) exceeds it alone; diversifying inside it needs small contracts whose
  forced daily round trip drags Sharpe by several tenths.
- **Under prop-evaluation economics** (the fee as capital at risk): risk is set by EV per attempt, large
  size can be rational, standard micros fit, and cost drag stays at 0.04–0.09. The success condition
  becomes EV = P(pass) × payout − fee; R06's barrier machinery computes it once this account's terms are
  supplied (R06 itself used 10% structures).
- **Under both: evidence.** Sizing multiplies an edge and cannot supply one (§59: 36.8% pass at no edge, at
  every size).

### The multiple-testing bar for daily strategies — a decision to rule

SR\* has been one per-observation number (0.1368) built from mostly per-trade intraday Sharpes. Read on a
daily observation it is **2.17** annualised. The unit-consistent version — null variance of a daily Sharpe
at the strategy's own T, N unchanged — gives **0.96** (full sample) and **1.39** (post-2021, decisive).
Not resolved here. **Either way, the 760 trials already spent are now the main wall for daily strategies**
— the permanent shared cost §61 described, arriving where cost stopped binding.

### The candidates and the filter (priors sourced, arithmetic shown in the draft)

| | prior | vs 0.96 | vs 1.39 | vs 2.06 |
|---|---|---|---|---|
| W01 trend, MNQ + MGC | 0.41–0.64 | below | below | below |
| W02 trend, ~10 micros | 0.73–0.89 | below | below | below |
| W03 carry timing | 0.6–0.9 | below | below | below |
| **W04 trend + carry** | **0.77–1.27** | **straddles** | below | below |
| W05 vol-managed index | 0.4–0.5 | below | below | below |

Sources: Moskowitz, Ooi & Pedersen 2012 (0.3–0.5 per market, ~1.0 across 58); Koijen, Moskowitz, Pedersen
& Vrugt 2018 (carry timing 0.6 per class, 0.9 global — read from the manuscript text); Moreira & Muir 2017
with Cederburg et al. 2020 (no out-of-sample gain). W04's combination assumes a trend–carry correlation of
0–0.5, unsourced and labelled.

### What this overturns, stated no more strongly than it is

**Overturned:** cost binds everywhere (it does not at a daily horizon), and daily horizons are unreachable
(they are, subject to the firm). **W04 is the first candidate in nine series whose published prior reaches
a multiple-testing bar on this data.** **Not overturned:** no prior clears the post-2021 bar or §62's 2.06,
and nothing here is evidence of an edge — it is the first design whose prior makes a trial worth spending.

### Open, for the user

1. Confirm with the firm that an 18:00-to-16:55 hold is within "flat by 17:00".
2. Choose the objective: §62's bar or prop-evaluation EV — and for EV supply fee, target, payout split,
   reset cost, daily loss limit, contract limit.
3. Rule on the SR\* convention for daily strategies.
4. Buy ohlcv-1d for W02–W04's added markets (price once an API key exists).
5. If all four go the right way: register W04 alone, one portfolio-level trial.

## 73. W04 registered before its data; the prop-evaluation success condition computed (S1, S2, S8)

**One registration (W04), no trial spent; N 760, SR\* 0.1368. One computation logged to
`measurements.jsonl` (prop-evaluation EV, not counted in N).** Entry: `hypotheses.yaml` W04; EV:
`reports/w_prop_ev.md` (`reporting/w_prop_ev.py`).

### The rulings received (answers to §72's five open points)

1. **The firm confirmed** that an 18:00-to-16:55 hold is within "flat by 17:00". Daily horizons are open.
2. **Objective: prop-evaluation EV.** Terms supplied: $80 fee, +$3,000 target, a $2,000 buffer before
   payout, 90/10 split, no resets, $1,000 daily loss limit, 30 micros. Two terms were ambiguous and are
   modelled, not chosen: the daily loss limit is run both HARD (breach ends the account) and SOFT (flat
   for the day); "a $2k buffer before payout" is read as withdrawals only above $52,000, the lock point.
3. **SR\* convention left to the analyst; chosen: unit-consistent.** The single per-observation SR\*
   (2.17 read daily) compares a daily Sharpe with per-trade intraday Sharpes, which are not the same
   units. W04 is decided at the post-2021 unit-consistent bar, **≈1.39** at N = 761; the full-sample 0.96
   is reported beside it, not decisive.
4. **Data purchased by the user** (below).
5. **W04 registered alone, as one portfolio-level trial.**

### The data, and what changed because of it

**ohlcv-eod is not offered for GLBX.MDP3.** The settings given earlier named it from the schema enum
without checking it against the dataset; the error was the analyst's. ohlcv-1h costs ~10× ohlcv-1d, so
**ohlcv-1d was bought.** Its bars close at 00:00 UTC (19:00/20:00 ET): each misses the first 1–2 hours
of its own session and carries the first 1–2 hours of the next. Two consequences, both written into the
entry before any price was read:

- **Look-ahead, removed by construction.** A month-end close at 20:00 ET lies after the 18:00 reopen, so
  a signal traded at that reopen would use prices not yet seen. The entry now delays every position by
  one session; for a monthly signal this costs almost nothing.
- **Alignment, to be measured before use.** With positions constant between monthly rebalances, the
  shifted hours telescope within a holding period; what remains is day-level noise and the rebalance
  edges, unbiased in sign. It is MEASURED, not assumed: UTC-day against 18:00→16:55 session returns on
  the on-disk 1-minute MNQ and MGC, daily and 21-day correlation — price dispersions only, no strategy
  return.

**Received** (job GLBX-20261003-SDXCG4PTPA; three manifest SHA-256 hashes verified; parent symbology;
2010-06-06 to **2026-09-11**, three weeks short of today, ~15 of ~1,320 post-2021 sessions): every W04
product with all expiries — NQ, GC, HG, CL, ZN, 6E from 2010; micros M6E and MGC from 2010, MNQ 2019,
MCL and 10Y 2021, MHG 2022 (micros are used for costs only). **The file also holds ES and MES, which are
not in W04's universe and will not be used**, and calendar spreads and strips (about half the rows),
which are discarded.

**Amendments to the entry, made after the data arrived and before any price in it was read** (only the
symbol and date inventory above was looked at): ohlcv-1d and the one-session delay; carry from the
**same bar's** closes, with F2 the highest-volume outright expiring after F1, so a stale serial month
(gold lists every month, trades mainly the even ones) is never used; outright contracts only; ES/MES
excluded; weights netted per market; the economics row read at two sizes (below).

**One registry check changed.** `test_registry_consistency.py` capped holds at 8 hours; W04 holds 22.9.
§68 ruled it be left, not loosened, for U01: "a check stricter than the account rule fails safe;
relaxing it for a blocked entry would be fixing a test rather than an entry." It is now replaced by the account's own bound — a hold must fit inside one CME trading day — because W04
needs the longer hold and the firm has confirmed it. This departs from §68's letter for a live entry,
and is recorded as such; the 8-hour figure was a heuristic for "flat by 17:00", not the rule.

### The success condition, computed

Simulator: daily-horizon P&L marked 13 times a session, Student-t (ν = 5) innovations, the account's
trailing floor, lock, target, daily limit and monthly withdrawals; funded account followed two years;
an evaluation not passed in a year counts as failed. **Validated against the closed form first**: no
drift, no daily limit, P(pass) 0.260 against exp(−1)·2/3 = 0.245 — inside tolerance, but high by
~0.015 from discrete monitoring, so **every EV below is slightly optimistic.** 6,000 paths per cell.

EV per $80 evaluation (USD), HARD daily limit, selected cells:

| Sharpe | $100/day σ | $150 | $250 | $400 | $600 | $900 |
|---|---|---|---|---|---|---|
| 0 | −63 | +26 | +97 | +47 | −34 | −74 |
| 1.0 | +364 | +1,158 | +1,048 | +367 | +18 | −66 |
| 1.25 | +683 | +1,872 | +1,616 | +543 | +61 | −61 |
| 1.5 | +1,168 | +2,680 | +2,312 | +748 | +80 | −61 |

SOFT is close to HARD at small size and diverges above $400/day: at Sharpe 1.0, +720 at $400 and +431 at
$900 (HARD: +367, −66). Full grid in the report. Four findings:

1. **The edge, not the size, drives EV.** At $150/day, Sharpe 0 → +$26; Sharpe 1.0 → +$1,158; at the
   decision bar 1.39 (interpolated) ≈ **+$2,300 per evaluation**.
2. **EV is not evidence.** At zero edge it is positive at moderate size (+$97 HARD at $250; +$152 SOFT at
   $900): the firm absorbs losses beyond the fee. Matches §59 (sizing multiplies an edge, never supplies
   one). EV is therefore an economics row in W04's decision rule; the Sharpe bar decides.
3. **The optimum is small: ~$150–250/day of σ**, the opposite of R06's high-volatility optima under 10%
   structures. Below $150 the one-year evaluation cap binds (an assumed term; the firm's real time limit
   was not supplied). Above ~$400 the $1,000 daily limit and the $2,000 floor dominate.
4. **Granularity binds again, at this objective.** One MNQ is $847/day of σ and one MGC $538 (§72,
   measured). Under W04's registered equal-risk sizing, any integer book that holds MNQ at all holds every
   market near $847/day — on the order of $2,000/day with all six on. **That is above the grid's top
   size, where under the HARD reading EV is already −$66 at Sharpe 1.0 and −$47 at Sharpe 2.0; under SOFT
   it is +$431 at 1.0.** The
   trial's statistic (Sharpe) is scale-free and unaffected; its economics are not. The entry now requires
   the runner to report EV at both the EV-optimal (fractional) size and the smallest integer book.

**Not modelled:** consistency rules, minimum trading days, payout caps, funded-account time limits,
slippage beyond the assumed one tick, the firm's real evaluation time limit. The 30-micro cap does not
bind at any size the grid reaches.

### Open, for the user

1. **Ask the firm which reading of the $1,000 daily loss limit applies** — breach, or flat for the day.
   Under HARD, W04 as registered cannot be traded near its EV optimum; under SOFT it can be traded at
   positive EV if its edge is real.
2. If HARD: whether to register, BEFORE W04 runs, a variant whose book drops markets that cannot be held
   at under one contract at the target size. That would be a separate entry with its own trial, not an
   edit to W04.
3. W04 becomes schedulable once the alignment measurement is recorded and the runner passes outcome
   injection at Sharpe 1.39.

## 74. W04's daily bars measured against the sessions it trades: they stand in (S8)

**No trial spent; N 760. Two measurement records (correlations of price changes, no strategy return).**
`reports/w_daily_alignment.md` (`reporting/w_daily_alignment.py`). Owed by §73 before W04 could be
scheduled.

From the on-disk 1-minute data, UTC-day returns (last close before 00:00 UTC, Sunday bars dropped so
Monday runs from Friday, same contract only) against the 18:00-to-16:55 held session return:

| | era | days | corr, same session | corr, next session | SD ratio | corr, 21-day blocks |
|---|---|---|---|---|---|---|
| index | full | 3,166 | 0.966 | −0.065 | 1.016 | 0.981 |
| index | post-2021 | 1,384 | 0.972 | −0.068 | 1.020 | 0.990 |
| MGC | full | 3,131 | 0.972 | 0.012 | 1.022 | 0.987 |
| MGC | post-2021 | 1,381 | 0.969 | 0.010 | 1.025 | 0.989 |

**A UTC bar stands in for its session at 0.97 daily and 0.98–0.99 over 21-day blocks**, the span a
monthly rule lives on. The UTC series is 2% more volatile (it carries a few extra hours). The
next-session correlation is small; on the index it is negative, which the 1–2 hour overlap alone would
not produce, so it is not attributed here — the one-session delay removes it from W04 whatever its source.
**ohlcv-1d is adequate; ohlcv-1h is not needed.**

**What the vendor bar is, checked.** On the purchased file's MNQ and MGC rows, the 1d close equals the
1-minute last close before 00:00 UTC for the same contract and date on 99.4% and 98.7% of matched bars
(median difference 0 ticks). Matches cover only contracts the continuous file holds that day (2,233 of
7,572 MNQ bars; 4,879 of 28,813 MGC), since the purchased file carries every expiry.

**Two facts the W04 runner must handle, found here:**
- **Sunday-evening bars exist** (952 MNQ, 3,046 MGC): the Globex reopen falls on a Sunday UTC date.
  They are dropped, so Monday's return spans Friday's close to Monday's, as measured above.
- **The vendor names contracts with a one-digit year** (`MGCM9`). The decade is resolved from the bar's
  date; a wrong decade would splice unrelated contracts.

W04 now needs only its runner and the outcome-injection test at Sharpe 1.39 to be schedulable.

## 75. The daily loss limit is soft (ruling)

**Ruled by the user 2026-10-03, from the firm: hitting the $1,000 daily loss limit stops trading for that
day; it does not end the account.** §73's SOFT reading governs; the HARD columns in
`reports/w_prop_ev.md` stay as published, as the reading that was not adopted.

**What it settles.** §73's fourth finding was conditional on this. Under SOFT, W04's integer book —
about $2,000/day of σ once MNQ is held at equal risk — stays positive-EV if the edge is real: at the
grid's top size ($900/day) SOFT EV is +$431 at Sharpe 1.0 against −$66 under HARD, and +$1,120 at
Sharpe 2.0. That book still sits well above the ~$150–250/day optimum, so it gives up EV against the
fractional optimum; the runner reports both. **No reduced-universe variant is needed**, and none is
registered. W04's entry now names SOFT and computes the integer-book EV at that book's own σ (beyond the
grid) with the same simulator. No trial spent; N 760.

## 76. W04 run: it does not clear, gross or net; the daily-horizon cost premise corrected (S5–S8)

**One trial spent: t00767. N 760 → 761; SR\* 0.1368 (unchanged to four places).** Report:
`reports/w04_trial.md`. Runner committed before the run (`e5b62db`): `data/daily_bars.py`,
`signals/w04.py` (positions only), `signals/portfolio.py` (the evaluator, a new runner entry point in
the boundary test), `signals/w04_trial.py`; `tests/test_w04.py` (9, incl. no look-ahead).

### The bar, by the registered rule — lower than the number quoted

The entry fixes the bar as the unit-consistent SR\* "at the post-2021 sample's own T". The daily file
has **1,481** post-2021 bars (weekdays on the union of six markets' calendars), not the 1,320 sessions
of the 1-minute sample §72 used, so **the bar is 1.31, not the ≈1.39 quoted.** The registered rule is
applied; the quoted figure was an estimate of it. It decides nothing here.

### Outcome injection first (§60), synthetic only

A carry edge planted in six synthetic t(5) markets, calibrated so the pipeline's own long-sample Sharpe
is 1.29 (sought 1.31), recovered at n = 1,481 as 1.32 on average over 200 runs (bias 0.03, Monte Carlo
SE 0.034); SD of the estimate 0.48; **power at the bar 51%**, and a true Sharpe of 2.10 clears it 95% of
the time. `reports/w04_injection.json`.

### The result

| | T | gross | net | bar |
|---|---|---|---|---|
| **post-2021 (decides)** | 1,481 | 0.31 | **−0.42** | 1.31 |
| full | 3,972 | 0.37 | −0.49 | 0.80 |
| pre-2021 | 2,491 | 0.40 | −0.54 | — |

Sleeves, net post-2021: trend −0.60, carry −0.62. Rotation null (500): mean −0.81, 95th percentile
−0.15; 13.4% of rotations at or above the real — **the timing is not distinguishable from its own null.**

**W04 does not clear, and would not have cleared at zero cost:** gross 0.31 against 1.31. With the
estimate's SD of 0.48, the gross result's one-sided 95% upper bound is ≈1.10, so a true gross Sharpe at
the bar is itself unlikely (p ≈ 0.02) — this null is informative about the bar despite 51% power at it.
The published priors (0.7–1.2, pre-decay) were not met in either era: 0.40 gross before 2021, 0.31 after.

### What was wrong in the premise: cost DOES bind at a daily horizon, on low-volatility markets

§72 measured the chained round trip at 0.34–0.56% of a day's SD on MNQ and MGC and concluded **"at a
daily horizon the cost floor does not bind."** True of those two; **false as a portfolio statement.**
Measured here (post-2021, assumed $1.82 + one tick per micro round trip):

| micro | round trip / day's SD |
|---|---|
| MNQ | 0.5% |
| MGC | 1.2% |
| MCL | 1.5% |
| MHG | 1.7% |
| micro 10Y (ZN equivalent, DV01 assumed $70) | **4.7%** |
| M6E | **4.9%** |

Equal-risk sizing gives the two lowest-volatility markets the largest notional, and a daily re-entry
charges them every day: **the drag is 0.73 of Sharpe** (gross 0.31 → net −0.42). §72's wording stands
corrected by this section; its feasibility measurements were right for what they measured. The finding
generalises: **chained session holds cost one round trip per market per day, and in units of a day's
risk that is ~10× larger on FX and rates micros than on the index.**

### The economics row — defective as defined, and moot

The "smallest integer-micro book" was implemented as each held position rounding to at least one
micro. Netting the two sleeves leaves some markets with tiny weights, which forces the scale up: daily
$σ $7,173, median 39 micros, over the 30-micro cap on 61% of days — **not a tradable book.** Its soft-limit
EV (+$548) is the zero-edge lottery effect at huge size (P(pass) 38%, against §59's 36.8% with no edge),
not value. At the EV-optimal sizes with the measured Sharpe: −$51 ($150/day), −$5 ($250/day). The verdict
does not depend on this row; the definition is recorded as a defect, not repaired after the fact.

### Status

**W04 retired** (`hypotheses.yaml`), on an informative null. The W-series has no other registration.
W01–W03 and W05 were closed at S2 below every bar; **W04's result is no evidence for or against them, but
W02 and W03 share its universe and its daily re-entry, so they share its cost drag.**

## 77. X-series S1 reviewed: overlap with W, the flatten tax, the monthly floor — closed at X02 (S1, S2, S4)

**No trial spent; N 761, SR\* 0.1368 (r-series chain: 10, unchanged). Nothing registered. Two
measurement records (m00132 X01, m00133 X02).** Draft: `X_SERIES_CANDIDATES.md` (supplied by the user,
committed as received apart from a status banner). Measurement: `reports/x01_x02.md` (`reporting/x01_x02.py`).

### Step zero — the overlap with the W-series

The draft did not know the W-series' contents. They are: **W01** TSMOM on MNQ + MGC, **W02** TSMOM across
~10 micros, **W03** carry timing, **W05** volatility-managed index — all four closed at S2 below every bar
and never registered — and **W04** trend + carry across NQ, GC, HG, CL, ZN, 6E, **registered, run (t00767)
and retired**: post-2021 net −0.42 against 1.31 (§76). W04 reports each sleeve: **trend (12-month sign,
inverse-vol, monthly) gross 0.28 / net −0.60 post-2021, gross 0.54 full; carry gross 0.15 / net −0.62.**

| X | verdict | against |
|---|---|---|
| X01 flatten tax | **measurement, partly on file** — §72 measured MNQ and MGC, §76 all six W04 micros; extended here to fees, MES, and days-in-market | §72, §76 |
| X02 monthly floor | **new measurement** | — |
| X03 TSMOM | **repeat / parameter variation**: W02's rule, and W04's trend sleeve already ran it at L = 12 on six of X's seven markets; X03 adds ES and sweeps L ∈ {3, 6, 12}, vol window ∈ {20, 60} | W02, W04 trend sleeve |
| X04 selective TSMOM | **parameter variation** of X03 (a magnitude threshold on the same signal) | W02 / W04 |
| X05 long-horizon reversal | **new** — no entry in either registry tests 24–60-month reversal | — |
| X06 cross-asset lead-lag | **new** — R01 is intraday NQ/ES relative value, R04 cross-sectional ranking (closed on permission); neither is a daily lead-lag | — |
| X07 carry | **repeat**: W03's rule, and W04's carry sleeve ran it | W03, W04 carry sleeve |

Three of seven are repeats or variations of on-file work: X03 and X07 directly, X04 by construction on
X03. **Their information is on file at one trial already spent**, and re-running them would spend trials
on it. The draft's statement that carry is "likely blocked on data" because only the front month is on
disk is wrong — see X07 below.

### X01 — the flatten tax, measured

Post-2021 daily bars; one micro round trip per market per day held. **Fees:** exchange fees per side from
secondary sources, because CME's fee-schedule PDF refuses automated download (it returned a bot-block page
for both the CME and CBOT/NYMEX schedules dated 2026-02-01): equity micros $0.35 and MGC $0.60 (AMP's
notice of the 2025-02-01 change, $0.50 → $0.60) are corroborated; **MHG $0.62, MCL $0.52, M6E ~$0.43 and
10Y $0.30 are from search summaries and unverified.** NFA $0.02 per side. **The account's
broker/clearing charge is not known** and is assumed at $1.08 per round trip, the residual of the
programme's $1.82 MNQ assumption. **Spread: one tick per round trip, assumed** (no quote data on disk;
it can only be higher, §71).

| micro | round trip | bps of notional | / one day's $σ | Sharpe drag at d = 63 / 126 / 189 / 252 | verdict |
|---|---|---|---|---|---|
| MNQ | $2.32 | 0.71 | 0.51% | 0.04 / 0.06 / 0.07 / 0.08 | **eligible** |
| MES | $3.07 | 1.31 | 1.27% | 0.10 / 0.14 / 0.17 / 0.20 | marginal |
| MGC | $3.32 | 1.65 | 1.45% | 0.12 / 0.16 / 0.20 / 0.23 | marginal |
| MCL | $3.16 | 4.21 | 1.73% | 0.14 / 0.19 / 0.24 / 0.27 | marginal |
| MHG | $3.61 | 3.35 | 2.03% | 0.16 / 0.23 / 0.28 / 0.32 | **excluded** |
| 10Y | $2.72 | n/a (yield-quoted) | 3.72% | 0.30 / 0.42 / 0.51 / 0.59 | **excluded** |
| M6E | $3.23 | 2.34 | 5.12% | 0.41 / 0.57 / 0.70 / 0.81 | **excluded** |

Drag in Sharpe units is √d × (round trip / day's $σ) for a position at its own volatility; in % of
notional it is d × bps / 100. **The right unit is risk, not notional**: MCL costs the most per dollar of
notional (4.21 bps) but crude moves enough that it is only marginal; M6E costs about half as much per
notional and is excluded because the euro barely moves. The draft ranked by bps of notional and so had
MCL as the worst and M6E as middling — the reverse of the measured order. **Only MNQ is cost-eligible at
full time in market; MES, MGC and MCL are marginal; M6E, the micro 10Y and MHG are excluded before any
hypothesis names them** — the same mechanism that cost W04 0.73 of Sharpe (§76).

### X02 — the monthly floor, measured

Non-overlapping calendar-month returns of the seven front contracts; full months only. The test is the
programme's: clearing the unit-consistent SR\* at the sample's own T, so 80% power at a true monthly
Sharpe s needs s√T ≥ F_N + 0.84, with **F_N = 3.18 at N = 762**. Pooling: effective number of independent
instruments from the eigenvalues of the measured monthly correlation matrix, (Σλ)²/Σλ² — invariant to the
signs of the correlations, so "signed" and "absolute" agree.

**Measured correlation, post-2021:** NQ–ES **0.91**; ZN–6E 0.54, GC–6E 0.52, ES–ZN 0.51, HG–6E 0.51; mean
|ρ| 0.32. **M_eff: 3.75 of 7 post-2021 (4.17 full); 2.71 of the 4 cost survivors** (NQ, ES, GC, CL — NQ and
ES are almost one market).

| monthly Sharpe (annual) | SR\* floor | post-2021 pooled, all 7 | post-2021 pooled, cost survivors | full pooled, all 7 |
|---|---|---|---|---|
| 0.1 (0.35) | 1,615 | 255 — power 6% | 185 — 3% | 813 — 37% |
| **0.2 (0.69)** | **404** | **255 — power 51%** | **185 — 32%** | 813 — 99% |
| 0.3 (1.04) | 179 | 255 — 95% | 185 — 82% | 813 — 100% |

The single-test floor (one-sided 5%, no multiplicity) is 155 at 0.2; post-2021 clears it. **The SR\* floor
governs** (ruling 3 below).

**The draft's "~190 months, marginal" was right about the calendar and wrong about the decision.** It
counted the full sample; the post-2021 half decides (S8), and that half has **68 months**. Pooled across
all seven markets it carries 255 effective months, against 404 needed.

**By the brief's own rule, the series closes here:** post-2021 pooled effective n falls below the floor at
0.2 monthly Sharpe, on the full universe (255 < 404) and more so on the instruments X01 leaves (185).
**Nothing is registered.**

### Does this horizon clear the injection standard?

**The standard (§60) can be met at this horizon, and already has been: W04 recovered its sought effect at
its run's own n (§76), and its null is informative** — its gross Sharpe's one-sided 95% bound sits below
the bar. So the brief's "first horizon in nine series where a null means absence" was reached by W04,
not by this series. **What X02 adds is the size at which it holds:** post-2021, pooled across all seven
markets, a null means absence only for per-market monthly Sharpes of about **0.25 or more (≈0.87 a
year)** — 80% power needs s ≥ (3.18 + 0.84)/√255. On the cost survivors that rises to ≈0.30 (≈1.03 a year).
The literature's per-market TSMOM is 0.3–0.5 annual (MOP), so **a null at this horizon cannot speak to the
effect sizes the literature reports** — it can only rule out effects two to three times larger.

### X07 — data availability

**Not blocked.** The purchased file is parent symbology, every listed expiry, from 2010 (§73–§74); carry was
computed from it for six markets in W04, with F2 the highest-volume later outright on the same bar (ZN's
carry was undefined on 17% of bars, where no later ZN contract traded). Carry is on file as W04's sleeve
and closed as W03.

### X03 — two notes the brief asks to be carried into any entry

1. **The anti-hedging suppression rule must be fixed at registration.** It removes positions
   non-randomly (precisely the opposite-signed correlated pairs), so choosing it after seeing results
   would be a free parameter. Post-2021 NQ–ES is ρ 0.91: the pair the firm names would be in conflict
   whenever their 12-month signs differ.
2. **Prior refutation, cited by what it tested (finding 12).** Oliveira, Guzman & Firoozye (2025),
   *(Non-Parametric) Bootstrap Robust Optimization for Portfolios and Trading Strategies*, arXiv
   2510.12725: **on 21 ETFs, daily from 2006, 80/20 train/test, the in-sample-optimised TSMOM
   parameterisations' "test-period Sharpe ratios become negative for nearly all parameterizations"**
   (verbatim); on a futures dataset (commodities, bonds, currencies, equity indices) they report in-sample
   ~0.6 and "severe out-of-sample degradation". **What it tested is parameter selection, not MOP's fixed
   12-month rule** — so it bears directly on X03's sweep over L and vol window, and less on a single
   published parameterisation. The brief's "negative on both ETF and futures" is verbatim only for ETFs.

### Rulings made here, logged rather than resolved silently

1. **Fees from secondary sources**, four unverified; broker/clearing assumed at $1.08 per round trip;
   spread assumed one tick. The verdicts that could move: MHG sits at 0.32 (excluded) on a $0.62 fee that
   is unverified. The others are not close to a boundary.
2. **Eligibility thresholds**, Sharpe drag at full time in market: eligible ≤ 0.15, excluded > 0.30 —
   half and all of MOP's lower per-market estimate (0.3). A strategy in the market less of the time pays
   √(fraction) of that.
3. **The SR\* floor governs X02's closing rule, not the single-test floor.** Every registration since §73
   is decided by SR\* at its own T; a floor that ignores 761 trials would certify power against a bar
   no entry is judged by.
4. **Pooling assumes equal per-instrument Sharpe and equal risk weights.** Unequal Sharpes or the
   anti-hedging suppression would lower M_eff; this is the optimistic case.
5. **N at registration taken as 762** (the next trial).

### Status

**X-series closed at X02, nothing registered.** X05 and X06 are new and are the only candidates not
already on file. Neither changes the X02 arithmetic: X05 loses 24–60 months of the 68 to its lookback,
and X06 adds up to 56 ordered pairs of multiplicity. They are closed with the series.

## 78. The blocked-entry reconciliation: two superseded numbers corrected, no gap narrowed (S4, S8)

**No trial spent; N 761, SR\* 0.1368 (r-series chain: 10, unchanged). Nothing re-measured and nothing
logged.** Corrections to `hypotheses.yaml` (F01, L05), `reports/futures_conclusion.md` (F01 row),
`tests/test_registry_consistency.py` (pinned set) and the records named below.

**The §65 caveat applies to the source reconciliation.** It ran on Sonnet (`claude-sonnet-5-5`) at the
user's instruction, after the model rule was raised. It recomputed gaps from the record — each a recorded
count divided by a recorded floor — and measured nothing. The F01 counts it relies on are the §22
measurement carried forward: `f01_rates` is OOM-killed on this machine (CHECKPOINT) and could not be
re-run.

### What was reconciled

Every entry closed on an event count: the eight registry entries with status
`blocked_insufficient_events` (F01, L01, L05, L06, L08, L09, U01, V01), R03 (r-series), and F12
(`excluded`, "roughly 128" events, a declared estimate never measured). Counts as recorded at the time,
set against the current conventions: §13 (per cell, not per scan), §22 (measured, worst cell gates),
§41 and §45 (L05's count was sessions, not breaks, and is withdrawn), S4 (effective n), S8 (post-2021
decides), §65 (F01's 4,125 superseded), §67–§69 (U01's validity rule, V01's ceiling).

### The finding

**Every event-count block was re-derived under current conventions and no gap narrowed.** Two entries
carried superseded numbers; both corrections widen the gap.

| entry | as first recorded | under current conventions | gap |
|---|---|---|---|
| F01 | 4,125 MNQ / 4,006 MGC "events" — the pre-§22 declared ceiling | best cell 3,523 / 3,449; worst cell 66 / 115 (§22, carried forward) | 60m proxy: 4.8× / 1.4× → 5.6× / 1.63× at the best cell; 299× / 49× at the worst |
| L05 | MNQ best cell 4,669, worst 2,015; 0.794× of the 5,884 floor at 180m | **no valid count** — withdrawn (§41, §45) | the 1.26× short it implied does not stand |
| U01 | 54 MGC / 127 index (before the stale-prior-close rule, §67) | 46 / 104 (28 / 42 post-2021) | 180m proxy: 53× / 46× → 62× / 57×; post-2021 102× / 140× |

L01, L06, L08, L09, V01 and R03 are unchanged from their recorded counts. The L-series registry blocks
match the live `level_rates.json` cell for cell, except L05, which the cache no longer holds.

### V01's 1.15× is the narrowest live figure and is not a candidate

On MGC with the Sunday reopens added (2,499 events), V01 is **1.15× short** at the 180-minute proxy
(2,862), **2.25× short** at its own 60-minute horizon (5,620), and **4.9× short** on the post-2021 half
(1,150 events). It is not a candidate: it is a **ceiling count** — every valid reopen firing, no threshold
applied — so any real condition fires on fewer, and the 180-minute proxy is not V01's horizon. The Sunday
reopens are excluded by V01's own wording (§69); as defined, the same three figures are **1.49×, 2.92×
and 6.2×**. The one place the record shows a gap this narrow is a ceiling at the wrong horizon.

### Corrections made

1. **F01.** `blocked_reason` now carries the §22 figures, the widened gap, and the fact that the
   worst-cell counts use a volatility filter (`>median`, `>p66`) with no stated quantity or lookback, which
   §28 left open. The text first registered is preserved as `blocked_reason_as_registered`. The F01 row of
   `futures_conclusion.md` carries the correction inline, marked with its date, rather than replacing the
   old figure silently. Status stays `blocked_insufficient_events` — the block is real, only its number
   was stale.
2. **L05.** Status `blocked_insufficient_events` → **`excluded`**, with an `excluded_reason`; the old
   status is kept as `status_before_2026_10_09` and the old reason as `blocked_reason_superseded`. The
   `firing_rate` and `verdict_route_measured` blocks are kept as history and marked withdrawn.
   `condition_defect` already said the figure must not be inherited; the status now agrees with it.

### Decisions taken rather than resolved silently

1. **`excluded` is the status chosen for L05, and it reverses §41's "noted, not withdrawn".** §41's
   reason was that L05 was "already blocked, so nothing downstream changes". §45 then withdrew the S4
   count that block rested on, so the reason no longer held. The registry's vocabulary is closed (§36
   decision 3): `blocked_insufficient_events` is defined as arithmetic showing no route can carry a
   verdict, which is no longer true of L05; `untested` requires a live `test_order`; `retired` means
   closed on evidence. `excluded` is the existing status for a condition withdrawn as defective, and L11
   (the same `confirmed_break` defect) is the precedent. **The user can overrule it; doing so reopens the
   contradiction between L05's status and its own `stopped_at_reason`.**
2. **The pinned excluded set in the registry test now includes L05**, with the reason in the test's
   docstring as that test requires. `param_cap` is 0 as the excluded-entry test requires; the registered
   value, 3, is kept as `param_cap_registered`.
3. **As-registered text is preserved**, under a renamed key, as the registry does elsewhere
   (`verdict_route` beside `verdict_route_measured`).
4. **Not corrected here:** `reports/catalog_status.md` is a generated report last built 2026-09-13 and
   still shows L05 as blocked with an unmeasured rate; it is stale in more than this respect and
   regenerating it would bring unrelated changes. The L-series counts that are correct but conditional —
   L01, L06 and L08 on the open `d` ATR scale, L09 and L05 on tick thresholds (§52) — are unchanged.

## 79. The Y-series: the account's payoff structure, measured on real paths (S1, S2, S8)

**Designed, not registered. No trial spent; N 761, SR\* 0.1368. Two computation records (m00134 Y01,
m00135 its sensitivity).** Draft: `Y_SERIES_CANDIDATES.md`. Engine: `reporting/y01_structure_ev.py`;
sensitivity: `reporting/y01_sensitivity.py`.

Asked for a series with a high chance of producing something that performs in the prop account, after
the record had concluded that searching should stop. **The answer is not another market search.** At
N = 761 a new market claim needs a post-2021 Sharpe of ~1.3, and no published effect tested came close.
What the record had found and not followed up is §73's finding that the evaluation is worth more than its
fee at zero edge.

### What was measured

**Y01: zero-edge EV of one $80 evaluation on resampled real MNQ sessions**, drift removed per era, the
account's rules as supplied (§73, §75), the intraday trailing floor tested on each minute's low, the soft
daily limit, $2.32 round trip. 2,638 complete sessions 2015-11-20 to 2026-08-27 (the U01 completeness
rule excludes earlier, incomplete NQ sessions, so "pre-2021" here is 2015–2020).

- **Positive in every cell and both eras: +$5 to +$127 per $80** (post-2021: +$31 to +$127). RTH 2 MNQ:
  +$119 (2015–20), +$127 (post-2021). ±$10 Monte Carlo error per cell.
- **Robust:** RTH 2 MNQ stays at +$77 under an imposed long Sharpe of −0.3; doubling cost moves it by
  ~$18.
- **Extremely skewed:** 10 evaluations ($800) finish net positive 26% of the time with a median of −$800;
  40 evaluations ($3,200) 59%, median +$2,061, mean +$4,935.

### Why the number is a constant, not a tunable edge

At zero drift P(pass) ≈ e⁻¹·⅔ = 0.245 at any size (time-change invariance of a martingale), and the
funded account's expected withdrawals are bounded by the identity E[final equity] + E[withdrawals] =
$50,000: ≈ 0.632 × ($2,000 − $836) ≈ $736. **EV ≈ 0.245 × 0.9 × $736 − $80 ≈ +$82.** The measured cells sit
around it. Sizing and timing cannot move it much; drift, overshoot, the fee and the payout rules can.

### A validation failure that is itself a finding

The engine first failed its closed-form check (0.290 against 0.245). Not a code fault: a finite pool of
3,000 random-walk sessions carried a residual drift of ~$20/day, an annual Sharpe of ~0.5, which alone
moved P(pass) from 0.22 to 0.29 across seeds. Demeaned, it validates at 0.247–0.255. **Pass rates are
very sensitive to small drifts**, which is why cost and any real premium matter more than sizing, and
why the real paths are demeaned exactly before use.

### Decisions taken rather than resolved silently

1. **The Y entries are not market hypotheses and are not registered.** Y01 removes drift, so it makes no
   claim about direction; a forward demo test (Y05) uses new data and makes no predictive claim. Neither
   is a trial. **If a Y entry ever asserts a premium from this data, that assertion is a trial.**
2. **The long tilt (Y04) rests on an external prior (equity premium, Sharpe ~0.3), labelled and never
   estimated here.** The policy's EV is positive without it (zero drift) and at an imposed −0.3.
3. **The operating policy (Y03: RTH, 2 MNQ, long) was fixed from Y01's grid before the sensitivity run**
   and stated in that module's docstring, so it was not chosen from the sensitivity results.
4. **The account terms not supplied are assumed and listed** (evaluation cap 252 sessions, funded
   horizon 504, monthly unlimited withdrawals, intraday trailing floor). **Y02 — the firm's full
   rulebook — blocks any real-money use**; consistency rules and payout caps in particular could remove
   most of the EV.
5. **Cross-account opposite positions are excluded outright** as typically prohibited by the firm.

## 80. Y02: the evaluation under Tradeify's daily-account rules — still positive; the policy changes (S2, S8)

**No trial spent; N 761, SR\* 0.1368. One computation record (Y02).** `reports/y02_tradeify.md`
(`reporting/y02_tradeify.py`), on Y01's demeaned real MNQ sessions.

### The rules, supplied by the user 2026-10-09, and the readings taken

Firm: **Tradeify, daily accounts.** **40% consistency rule in the evaluation, none funded. Payouts capped
at $1,250 until live, no cap after; no maximum number of payouts. No evaluation time limit. End-of-day
floor.** Readings where the rule was not fully specified, each modelled rather than chosen:
- **Consistency:** pass needs profit ≥ $3,000 and the best day ≤ 40% of total profit, tested at a day's
  close; a failing ratio means trading on.
- **End-of-day floor:** set from the highest closing balance, $2,000 below it, fixed at $50,000 once that
  reaches $52,000. **Primary reading: falling to the day's floor intraday still fails**; the close-only
  reading is reported beside it.
- **Payout frequency was not supplied:** daily, weekly and monthly all run. **When the account goes live
  was not supplied:** the $1,250 cap is applied throughout (conservative), uncapped reported beside it.
- Unchanged: $80 fee, soft $1,000 daily limit, $2.32 round trip; funded account followed 504 sessions;
  evaluations capped at 2,000 sessions (none reached it).

Engine checked against Y01's validated engine where the two rules coincide (one bar per session):
identical, 0.3026 each.

### Result: still positive, and the consistency rule picks the size

| policy (primary reading) | P(pass) | EV per $80, 2015–20 | EV per $80, post-2021 |
|---|---|---|---|
| **RTH, 1 MNQ** | 21–22% | **+$93 to +$100** | **+$104 to +$145** |
| RTH, 2 MNQ | 16% | +$71 to +$100 | +$71 to +$73 |
| full session, 1 MNQ | 17–18% | +$39 to +$64 | +$37 to +$48 |
| full session, 2 MNQ | 11–12% | −$12 to +$16 | +$31 to +$53 |

(Ranges span the three payout frequencies; ±$15–25 Monte Carlo error.)

- **The consistency rule is what binds, and it binds hardest on large positions**: post-2021, RTH 2 MNQ
  passes 27% without it and 16% with it; RTH 1 MNQ 26% → 22%. A large position reaches $3,000 in a few
  big days, each too large a share of the profit. **The policy moves from RTH 2 MNQ (Y01) to RTH 1 MNQ.**
- **The payout cap and frequency barely matter** — differences sit inside the noise. Capping can even
  help: equity left in the account is cushion above the floor.
- **The close-only floor reading would raise RTH 1 MNQ to +$208.** Which reading Tradeify applies is
  worth confirming.
- **Robust to an adverse market:** RTH 1 MNQ under an imposed long Sharpe of −0.3 gives +$53 (19% pass);
  zero +$139; +0.3 +$265.
- **Budget, RTH 1 MNQ, monthly:** 10 evaluations net positive 35% (median −$800, mean +$1,480); 40
  evaluations 62% (median +$2,308, mean +$5,889).

### Decisions taken rather than resolved silently

1. **The primary floor reading is the stricter one** (intraday breach of the end-of-day floor fails);
   the gentler reading is reported, not used.
2. **The $1,250 cap is applied for the whole funded horizon**, because the point at which the account goes
   live was not supplied.
3. **The operating policy (Y03) is revised to RTH 09:30–16:00, 1 MNQ, long**, chosen as positive in both
   eras at every payout frequency and under the adverse drift. RTH 2 MNQ, Y01's choice, is set aside
   because the consistency rule cuts its pass rate by ~40%.

## 81. Tradeify's rules confirmed; the final-rules EV (S2, S8)

**No trial spent; N 761, SR\* 0.1368. One computation record (Y02, final rules).** Appended to
`reports/y02_tradeify.md` (`y02_tradeify.py --final`).

### The three open points of §80, answered by the user 2026-10-09

1. **Falling below the end-of-day floor intraday fails the account immediately** — the primary reading of
   §80, now confirmed; the gentler close-only reading (+$208) does not apply.
2. **Payouts are daily**, capped at $1,250 until the account goes **live, after 3 payouts on one account
   or 10 in total**; uncapped after. Modelled per account (live after 3 payouts on that account); the
   10-in-total route across accounts is not modelled, so this is the conservative case. **Assumed:** any
   nonzero withdrawal above the $52,000 buffer counts as a payout (no minimum payout size was supplied),
   and going live changes nothing but the cap.
3. **The fee is $80.**

### Result

| policy | P(pass) | EV per $80, 2015–20 | EV per $80, post-2021 |
|---|---|---|---|
| **RTH 09:30–16:00, 1 MNQ** | 21–22% | **+$85** | **+$125** |
| RTH, 2 MNQ | 16–18% | +$92 | +$79 |
| full session, 1 MNQ | 18% | +$60 | +$54 |

- **RTH, 1 MNQ under an imposed long Sharpe:** −0.3 → +$69; 0 → +$112; +0.3 → +$175 (the 0 cell repeats the
  table's +$125 on a fresh draw; the gap is Monte Carlo error, ±$15–25).
- **About 37% of funded accounts take at least one payout.** Daily payouts with the live rule make
  outcomes less lumpy than monthly: **10 evaluations ($800) finish net positive 46% of the time** (median
  −$333, mean +$1,268); **20, 61%** (median +$1,124); **40, 76%** (median +$3,707, mean +$5,010).
- **The operating policy stands: RTH, 1 MNQ, long.** RTH 2 MNQ is within noise of it before 2021 and well
  below it after; the full session is lower in both eras.

### What the figures still assume

The funded account is followed two years; going live changes only the cap; no minimum payout size; the
$2.32 round trip (commission assumed, §71). **The forward demo test (Y05) is the check on all of it.**

## 82. Correction: the evaluation's floor never locks; §80–§81's evaluation figures superseded (S2)

**No trial spent; N 761, SR\* 0.1368. One computation record (Y02, corrected final rules).**

### What was wrong

§79–§81 gave the evaluation the same floor rule as the funded account: trailing $2,000 below the peak,
**fixed at $50,000 once the peak reached $52,000**. That rule came from the account as first described
(§62, §73) and was carried into the Tradeify model without being checked. **The user corrected it
2026-10-09: Tradeify's evaluation floor starts at $48,000 and keeps trailing the end-of-day balance with
no lock — at $52,999 the floor is $50,999.** The funded account's floor is as modelled: fixed at $50,000
once the end-of-day balance reaches $52,000. Also confirmed: passing needs $53,000, and the funded
account must build the $2,000 buffer to $52,000 before anything is withdrawable — both as modelled.

Without the lock the evaluation is a single trailing-drawdown race to +$3,000: at zero drift, continuous
monitoring, P(pass) = exp(−3,000/2,000) = 0.223, against 0.245 with the lock. Checked on the engine with
one Gaussian bar a day: 0.245, which is what the discrete-monitoring correction (≈0.58σ on each barrier)
predicts, exp(−2,913/2,087) ≈ 0.248.

### Corrected result (Tradeify as confirmed)

| policy | P(pass) | EV per $80, 2015–20 | EV per $80, post-2021 |
|---|---|---|---|
| **RTH 09:30–16:00, 1 MNQ** | 18–19% | **+$62** | **+$78** |
| full session, 1 MNQ | 13–16% | +$29 | +$44 |
| RTH, 2 MNQ | 11% | +$22 | +$23 |

- RTH, 1 MNQ under an imposed long Sharpe: −0.3 → **+$45**; 0 → +$87; +0.3 → +$138.
- Budget, RTH 1 MNQ: 10 evaluations net positive **40%** (median −$657, mean +$796); 20, **53%** (median
  +$280); 40, **67%** (median +$1,981, mean +$3,140).
- **The policy stands: RTH, 1 MNQ, long** — best in both eras, positive under the adverse drift. Larger
  positions lose more to the unlocked floor and the consistency rule together.

### What is superseded, and what is not

- **§80's evaluation figures and §81's results table are superseded** for Tradeify by the table above.
  They are left as written, with this section as the correction.
- **Y01 (§79) is not wrong for the account it modelled** — the lock rule as first described — but that is
  not Tradeify's evaluation. Its martingale argument still holds; its constant becomes
  0.223 × 0.9 × E[withdrawals] − $80.
- The method point, recorded because it is the same shape as finding 12: **a rule carried from an
  earlier account description into a new firm's model, without being re-checked against the new firm's
  terms.**

## 83. Y03: session, direction and instrument under Tradeify's rules — two stable policies (S2, S8)

**No trial spent; N 761, SR\* 0.1368. Two computation records (Y03, MNQ and MGC).**
`reports/y03_sessions.md` (`reporting/y03_sessions.py`), on Tradeify's confirmed rules (§81–§82) and
demeaned real sessions; one contract.

### Fixed before running

Windows: **Asia 19:00–03:00 ET and London 03:00–11:30 ET, the repo's own definitions**
(`levels/definitions.py`; London overlaps the US morning by two hours, as defined); RTH 09:30–16:00 and
its halves, 09:30–12:00 and 12:00–16:00 (the shorter-window check §82 proposed). Long and short. 1 MNQ
($2.32 round trip) and 1 MGC ($3.32). **Selection rule: per instrument, the highest 2015–20 EV is the
pick and its post-2021 EV the confirmation.** MGC's complete sessions run from 2011-02-01 (2,863); MNQ's
from 2015-11-20 (2,638).

### Result

- **The pre-registered pick failed for MNQ:** Asia long, +$97 in 2015–20, fell to **+$17** post-2021
  (+$74 → +$22 at 16,000 accounts). **For MGC it held:** London long, +$74 → **+$75**.
- **Across the 4,000-account grid, most MNQ cells moved between eras by more than the ±$15–25 Monte Carlo
  error.** At zero edge, choosing among windows and directions is mostly choosing noise and regime;
  **the finding is how little the choice matters once one stable cell is in hand**, not which cell wins.
- **Shorter windows do not help systematically.** MGC's 12:00–16:00 window is slightly negative (−$7 to
  +$6): its small daily swing makes the fixed round trip a larger share and slows resolution.
- **Long and short show no consistent difference with drift removed**, as expected; a real equity
  premium can only favour long on MNQ.

**Contenders re-run at 16,000 accounts** (chosen after the grid; precision, not a new selection; the
quoted ± is Monte Carlo error given the historical pool, and is smaller than the real uncertainty the
era-to-era difference shows):

| policy | EV 2015–20 | EV post-2021 | 10 evaluations net positive | 40 |
|---|---|---|---|---|
| **MNQ 09:30–16:00, long** | **+$67** | **+$82** | 40% | 67% |
| **MGC London 03:00–11:30, long** | **+$68** | **+$70** | 41% | 67% |
| MNQ 09:30–16:00, short | +$13 | +$62 | 37% | 62% |
| MNQ Asia 19:00–03:00, long | +$74 | +$22 | 33% | 50% |

### Decisions taken rather than resolved silently

1. **Two operating policies, both stable across eras: MNQ 09:30–16:00 long (Y03's original) and MGC
   London 03:00–11:30 long.** They are on different instruments with a low measured correlation
   (post-2021 monthly NQ–GC ρ 0.16, §77), so evaluations run on both are closer to independent than two
   on one — a budget split across them should be less lumpy. **Not computed jointly**; stated as a
   direction, not a figure.
2. **The MNQ Asia cell is not adopted** despite winning its selection: it failed its own confirmation.
3. **The contender re-run was chosen after seeing the grid** and is labelled so; it refines estimates,
   it does not add a selection.

## 84. Y04: MNQ New York and MGC London on one account — worse than each on its own (S2)

**No trial spent; N 761, SR\* 0.1368. One computation record (Y04).** `reports/y04_combined.md`
(`reporting/y04_combined.py`), Tradeify's confirmed rules, drift removed, 16,000 accounts.

Asked by the user: trade both stable policies (§83) on the same account. Built by pairing the two
instruments' sessions BY DATE (2,499 dates both have complete, 2016-01-27 to 2026-08-27), so their real
co-movement is kept: MGC long 03:00–11:30, MNQ long 09:30–16:00, one floor, one soft daily limit, the 40%
consistency rule on the combined daily P&L, both round trips ($5.64). The combined minute low is the sum
of the two legs' lows — conservative, it can only overstate an excursion.

| | daily $σ | EV per $80, 2016–20 | EV per $80, post-2021 | 40 evaluations net positive, post-2021 |
|---|---|---|---|---|
| **both, one account** | 712 / 817 | **+$65** | **+$46** | 56% |
| MNQ New York alone | 618 / 699 | +$71 | +$82 | 66% |
| MGC London alone | 318 / 386 | +$45 | +$74 | 69% |

**One account holding both is worse than either alone after 2021, and worse than MNQ alone in both
eras.** The legs are nearly uncorrelated (daily P&L ρ +0.06), so combining them raises the day's swing
(to $817 after 2021) — and with it the share of profit a single good day carries against the 40%
consistency rule — and doubles the daily cost, without changing the structural value per account. Per
dollar of fees, **two separate accounts, one per instrument, return about +$156 per $160 post-2021 (+$82
and +$74) against +$46 per $80 combined.**

### Decisions taken rather than resolved silently

1. **Recommended: separate accounts per instrument, not both on one.** Whether Tradeify permits one
   trader several evaluations or funded accounts at once, and on what terms, was not supplied and must be
   checked.
2. **MGC London's 2016–20 figure here (+$45) is below §83's 2015–20 (+$68)** because the paired sample
   starts in 2016 rather than 2011 and uses only dates MNQ also has; §83's single-instrument figure stands
   for MGC alone.

## 85. Y05 historical replay: real order weakens and widens the structure value (S8)

**No trial spent; N 761, SR\* 0.1368. Two computation records (Y05 replay, MNQ and MGC, block bootstrap
included).** `reports/y05_replay.md` (`reporting/y05_replay.py`).

Asked by the user: instead of months of demo accounts, start accounts on many historical dates and see
how they would have done. Done exhaustively rather than at random: **an account started on every
complete session that leaves room for an evaluation and a two-year funded period** (MNQ 2,038 start
dates, 2015-11-20 to 2024-03-14; MGC 2,263, 2011-02-01 to 2024-03-13), walking forward through the
sessions **in their real order** under Tradeify's confirmed rules, with the two policies fixed in §83.

### Result

| | P(pass) | median days to pass | EV per $80, drift removed | EV per $80, actual history | share of accounts net positive (actual) |
|---|---|---|---|---|---|
| MNQ 09:30–16:00 long | 23% (actual 32%) | 31 | **+$1** | +$119 | 14% |
| MGC London long | 22% (actual 24%) | 58 | **+$44** | +$115 | 12% |

**"Actual history" includes the market's real moves** — for long MNQ, the 2016–2026 rise; for long gold,
the 2024–25 rally. It is descriptive only, asserts no premium and is not counted as evidence (§79
decision 1). **The drift-removed replay is the rule structure alone, and it is far below the resampled
simulation** (§83: +$67 / +$82 MNQ, +$68 / +$70 MGC).

**By start year the outcome is dominated by when the account starts.** MNQ drift-removed: −$80 to
+$408 (2023 starts); MGC: −$80 to +$1,803 (2015 starts). Accounts started near each other share their
fate, so 2,000 start dates hold only a few dozen independent episodes.

### Why — a block bootstrap separates clustering from noise

Accounts built from random runs of consecutive real sessions (8,000 per cell, drift removed): runs of
one day are the resampling of Y01–Y04; longer runs keep real clustering and trends inside each run.

| EV per $80 | 1 day | 21 days | 63 days | 252 days |
|---|---|---|---|---|
| MNQ, 2015–20 | +$56 | +$2 | +$10 | −$61 |
| MNQ, post-2021 | +$99 | +$55 | +$84 | +$49 |
| MGC, 2011–20 | +$72 | +$72 | +$116 | +$162 |
| MGC, post-2021 | +$64 | +$49 | +$13 | +$42 |

- **Runs of one day reproduce the resampled simulation** (+$56 to +$99) — the wiring is consistent.
- **With real runs kept, EV ranges from −$61 to +$162 with no consistent direction.** Removing each era's
  mean drift leaves the multi-month trends inside it, and those decide much of an account's fate. Long
  runs have few distinct episodes, so they describe particular years more than a law.
- **The resampled simulation's ±$3–5 was the error of a model that assumed independent days. The real
  uncertainty is an order of magnitude larger.**

### What changes in the Y-series' claims

1. **The zero-edge value is now stated as "positive in most estimates, roughly $0 to $80 per $80 fee
   with real-order uncertainty of the same size", not as +$70–80.** MNQ's real-order replay is at zero.
2. **Accounts started at the same time are not diversified against each other.** A budget should be
   spread over time, not spent at once; the earlier budget tables (§79–§84) assumed independent
   evaluations and overstate how quickly a budget converges.
3. **The forward demo test (Y05) is not replaced** by this replay: the replay checks real-order dynamics
   on old data, not current fills, current rules or the next regime. It does shorten what the demo test
   must answer.

## 86. The Z-series: decide on external out-of-sample evidence; Z01, front-running rebalancers (S1, S2)

**Designed, not registered. No trial spent; N 761, SR\* 0.1368. Nothing measured on our data.**
Draft: `Z_SERIES_CANDIDATES.md`.

The user closed the Y-series' practical use: the account structure is worth too little to build income
on (§85). Asked for a different basis.

### The basis

Income needs a real edge, and a modest one is worth a lot in this account (§73: Sharpe 0.4 ≈ +$250 per
evaluation, 1.0 ≈ +$1,100). This programme can no longer discover one on its own searched history (SR\*
≈1.3 at N = 761). **The Z-series takes its evidence from outside**: an effect published by others,
replicated exactly as published, tested only on data AFTER the authors' sample ends.

### The literature, checked before choosing (web sources in the draft)

Turn-of-the-month faded after 1990; the Treasury auction cycle reportedly reversed after 2010; the
pre-FOMC drift disappeared after 2015. **Calendar and event anomalies decay once published.** The one
candidate with a forced counterparty and no post-publication record: **Harvey, Mazzoleni & Melone (NBER
w33554, 2025/2026), front-running pension and balanced-fund rebalancing** — read from the paper itself:
next-day equity returns 17 bps lower when equities are overweight; long S&P / short 10-year futures by
the signal, 1997-09-10 to 2023-03-17: 10.2% a year, 9.2% volatility, **Sharpe 1.11 (≈1 net)**, alphas
t > 4, **skewness +5.2**; Sharpe 0.90 excluding the 2008–09 and 2020 crises; weaker in calm markets.

### Z01 and Z02, specified before any data is touched

The construction is copied from the paper's Appendix B and Section 4 (60/40 drift simulation; Threshold
signal averaged over δ = 0–2.5%; Calendar signal with the last-week and first-day rules; weight = mean of
−Threshold/1.5% and the modified Calendar). **Z01**: the published long/short ES–ZN spread. **Z02**: the
equity leg alone, on MES. **Test window: 2023-03-18 to 2026-09-11**, about 880 daily observations the
authors never saw; signals from the purchased ES and ZN daily bars; entry at 20:00 ET after bar D's
close, exit 16:55 ET on D+1.

### Rulings needed before anything runs

1. **The decision rule.** SR\* at N = 762 and this test's length is ≈1.7 — a bar for claims found by
   searching our data, which Z01 was not. Proposed: confirm if the post-2023 Sharpe is > 0 with the
   published sign and the prop EV at the posterior Sharpe (prior 0.5 ± 0.35, the published ~1.0 halved
   for decay) is positive; reject if ≤ 0. **This departs from every earlier registration's rule and is
   the user's to make.**
2. **Tradeify's rule on opposite positions** in correlated products, for long-equity / short-bond (Z01).
   Z02 avoids the question.
3. **Optional data:** ES and ZN 1-hour bars would replace the UTC-close approximation of the entry.

### Decisions taken rather than resolved silently

- **Z01 was chosen among four literature candidates by their post-publication record**, not by any
  result on our data; that selection is recorded here and does not touch our history.
- **The 2010–2023 construction check is not evidence**: the paper already used those years, and it
  compares signal properties only.
- **Honest odds:** a realistic prior after decay is Sharpe ~0.5; the post-2023 test (SE ≈ 0.54) can catch
  a dead effect but only weakly confirm a live one.

## 87. Z02 registered: rulings, two readings, construction check and injection — before the trial (S1–S5)

**One registration (Z02). No trial spent yet; N 761, SR\* 0.1368.** Entry: `hypotheses.yaml` Z02;
construction `signals/z02.py`; runner `signals/z02_trial.py`; tests `tests/test_z02.py` (5, including
the paper's own worked example: a +10% equity day moves both signals by +2.26%).

### Rulings received (§86's three open points), user 2026-10-09

1. **The decision rule is accepted**: confirm if the post-2023-03-17 Sharpe is > 0 with the published
   sign AND the Tradeify EV at the posterior Sharpe (prior Normal(0.5, 0.35)) is positive; reject if ≤ 0.
   It replaces the SR\* bar for this externally specified hypothesis.
2. **Long equity with short bonds counts as hedging and is not allowed.** Z01, the paper's long/short
   spread, is therefore untradeable and **is not run** (it would spend a trial on information that
   cannot change what is traded). **Z02, the S&P leg alone on MES, is the one test.**
3. **Daily bars first**; hourly ES/ZN only if needed.

### Two readings, both fixed before any return was computed

- **The Threshold reset (B.1).** The PDF text loses the notation, leaving it open whether a breach is
  judged on the previous day's weight or on the day's drifted weight. **Calibrated against the paper's
  own published signal property** (Table C.1: Threshold AR(1) 0.61) on 2010–2023, signals only:
  previous-day reading **0.78** (0.80 and 0.77 in the two halves — not an era effect); drifted-weight
  reading **0.65**. **The drifted-weight reading is used.** The construction check had been set at ±0.10
  before running; the literal reading failed it, and this is recorded rather than smoothed over. Matching
  a published, non-return statistic is a construction choice, not result-fishing — no strategy return
  existed when it was made.
- **"Four business days before month-end"** = the 4th-from-last business day, the last being −1 (the
  paper's Figure D.2 axis).

### Construction check — passed (signals only, 2010-06-07 to 2023-03-17)

| | ours | paper (1997–2023) |
|---|---|---|
| Threshold AR(1) | 0.65 | 0.61 |
| Calendar AR(1) | 0.92 | 0.91 |
| correlation Threshold–Calendar | 0.63 | 0.605 |

The correlation was not used to calibrate and moved closer under the chosen reading.

### Outcome injection — passed (§60)

Real post-2023 weights, real ES noise with its alignment destroyed, Sharpe 0.5 planted (the prior
mean): **recovered 0.52 at n = 908**, SD of the estimate **0.49**, P(estimate > 0) **86%**. The SD is the
standard error the posterior will use.

### Registry changes made to admit it

- The ID and catalog patterns accept `Z`.
- **`SINGLE_MARKET_INSTRUMENTS = {MES}`**: an entry that claims no two-instrument confirmation
  (`stage4_reachable: false`) may name MES as its mechanism's primary instrument. The mechanism is the
  S&P leg of 60/40 portfolios; naming MNQ would misstate where it holds. MES never counts as Stage 4
  evidence. Every other entry is checked exactly as before.
- `schedulable: false` as for W04: the event-rate gate does not apply to a position held most days; the
  runner refuses to run without the check and the injection.

## 88. Z02 run: the rebalancing effect survives out of sample — confirmed (S6–S8)

**One trial spent: t00768. N 761 → 762.** Report: `reports/z02_trial.md`; full results
`reports/z02_trial.json` (including the corrected EV and the sizing comparison).

### The test — 2023-03-18 to 2026-09-11, after the paper's sample

| | T | Sharpe gross | Sharpe net |
|---|---|---|---|
| **test window** | 908 | +0.66 | **+0.51** |
| 2010–2023-03-17 (inside the paper's sample; context, not evidence) | 3,312 | +0.68 | +0.37 |

- **Rotation null (500): the real result beats 98.4% of rotations** (mean −0.51, 95th percentile +0.25).
  The null mean is negative because the signal leans short (equities were mostly "overweight" in a rising
  market); the strategy earned +0.51 against that lean, not because of it.
- Outcome injection (before the run): Sharpe 0.5 recovered as 0.52 at this n, SD 0.49.
- **Posterior Sharpe 0.50 ± 0.28** (prior Normal(0.5, 0.35), test 0.51, SE 0.49).

**By the user's rule (§86–§87): CONFIRM** — the test Sharpe is positive with the published sign, and the
Tradeify EV at the posterior is positive. **The first rebalancing-effect result on data after its
publication sample, and the first hypothesis in twelve series to pass its own pre-registered rule.**

### A correction to the decision's EV component, made in the open

The trial's record (t00768) carries an EV at the posterior of +$27. **That figure charged the MES cost
twice**: the posterior is a Sharpe NET of cost, and the EV code subtracted the cost again. Corrected
(`z02_trial._prop_ev`), with the same sizing: **+$93 at the posterior** (−$18 at zero edge; +$15 and +$202
at ±1 SD). The decision does not change; the trial log is append-only and keeps the first figure, and
this section is the correction.

### Sizing — an economics choice, compared on shape, not on realised returns

The EV simulation imposes the drift, so comparing sizings compares the SHAPE of the returns (variance,
skew, the consistency rule) and does not re-test the edge. Four rules fixed before the comparison, EV per
$80 at Sharpe 0 / 0.22 / **0.50** / 0.79:

| sizing | daily $σ | EV |
|---|---|---|
| the paper's proportional weights, capped at 5 MES | 369 | −18 / +15 / **+93** / +202 |
| proportional, capped at 2 | 258 | +25 / +91 / **+226** / +453 |
| **sign of the signal, 1 MES** | **175** | **+50 / +161 / +410 / +836** (P(pass) 36% at 0.50) |
| sign of the signal, 2 MES | 350 | +25 / +75 / +173 / +319 |

**One MES in the signal's direction is the best fit for this account by a wide margin**: small, steady
daily swings sit well inside the trailing floor and the 40% consistency rule, and the edge does the work.

### What is NOT established, stated plainly

1. **The posterior is the PROPORTIONAL construction's Sharpe.** That the sign-only version keeps it is
   plausible (same direction, same days) but unverified. Checking it on the test window now would be a
   second look at data already seen. **The check is forward data.**
2. **908 days is a short test**: the posterior's ±0.28 spans +$161 to +$836 per evaluation for the
   sign-only sizing.
3. **Daily bars, not settlement**: entry at 20:00 ET after the UTC close is an approximation of the
   paper's close-to-close return.
4. **Publication** (2025) may yet erode it; the test window is mostly before wide circulation.

### A second record correction

t00768's note reads `provenance=external (...)`. That field records who wrote the RECORD (`native` or
`reconstructed`), and was misused for the hypothesis's source. **The record is native** — written by
`z02_trial.py` as it ran. The log cannot be edited; `tests/test_trial_logging.py` lists t00768 in a
documented `MISLABELLED_NATIVE` set, and the runner now writes `provenance=native; source=external`.
SR\* at N = 762: 0.1367.

### Next

A forward demo of **Z02, sign-only, 1 MES** under Tradeify's rules from 2026-09-12 on: new data, the
sizing's Sharpe measured as it accrues, the fills and the 20:00 ET entry checked in practice.

## 89. Z02 in the account: the replay is break-even, a sizing error corrected, closed for this account (S8)

**No trial spent; N 762, SR\* 0.1367. One computation record (replay and corrected EV).**
`reports/z02_replay.json`, `reports/z02_ev_today.json`.

### A correction to §88's account figures

§88's EV used each day's HISTORICAL contract value. A 2010 MES was ~$5.5k of exposure against ~$38k today,
so the simulated daily swing ($175) was about half of today's ($380), and **+$410 per evaluation was
overstated.** On today's contract value:

| one MES by the signal's sign, EV per $80 at Sharpe | 0 | 0.20 | **0.41** | 0.50 | 0.78 |
|---|---|---|---|---|---|
| | +$25 | +$59 | **+$110** | +$142 | +$258 |

0.41 is the one-MES sizing's own realised net Sharpe in the test window (the paper's proportional sizing:
+0.50; in 2010–2023, +0.20 against +0.58 — the sign-only sizing keeps less of the edge). That realised
figure is a second look at data already seen, and is reported as description, not confirmation.

### The every-start-date replay (requested by the user; realised returns, real order, today's contract)

| start dates | accounts | P(pass) | payout given pass | EV per $80 |
|---|---|---|---|---|
| all, 2010–2025 | 3,920 | 16% | 42% | **−$5** |
| 2010–2022 | 3,312 | 17% | 45% | +$8 |
| **2023 on (the test window)** | 608 | 8% | 8% | **−$78** |

Days (2010–2022 starts, trading days): to pass median 41 (mean 47); to fail median 43 (mean 56); from the
start of an evaluation to the first payout median 84; a funded account that fails does so at a median 43
days in (22 for 2023 starts).

### What it means

**The rebalancing effect is real out of sample (§88), and it does not carry this account.** A Sharpe of
~0.4 at one MES's ~$380 daily swing is an expected ~$10 a day; the account's +$3,000 target and $2,000
trailing floor are reached by noise long before the drift matters. The modelled EV (+$110) and the
real-order replay (≈ $0) differ in the same direction the Y-series found (§85). **Z02 is closed for this
account** at the user's decision 2026-10-09; the finding stands. Lesson carried forward: **in this
account an edge must be large relative to the daily swing on the days it is held — a high Sharpe per
day in the market — or the barriers decide.**

## 90. Z03 designed: the Treasury end-of-month effect, account-checked before any test (S1, S2)

**Designed, not registered. No trial spent; N 762, SR\* 0.1367.** Draft: `Z_SERIES_CANDIDATES.md` (Z03).

The user asked for another hypothesis on the same path. **Z02's lesson made the criteria sharper**: in
this account the edge must be large relative to the daily swing **on the days it is held**, so the search
was for event-concentrated forced flows. Rejected after reading: Hartzmark & Solomon (AER 2025, dividend
reinvestment; ~6 bps on large payout days — too small, and needs CRSP dates); intraday gamma momentum
(weakened in the 0DTE era; needs options positioning).

**Chosen: Hartley & Schwarz (2019), the Treasury end-of-month effect** — index-duration extension and
insurer buying at month-end; 10-year note last-2-days Sharpe 0.87, 10-year futures +0.14% a month
(1990–2018), nothing at other times. **Specification fixed before any return on our data**: long ZN the
last 2 business days of each month (the window the paper's figures and tables mostly use — not the
table's best cell); test window 2019-01-01 to 2026-09-11, after the paper's sample; Z02's decision-rule
form with prior Normal(0.44, 0.35).

**Account check first, as Z02 taught:** real ZN event-day returns, drift removed, the drift imposed —
one ZN gives P(pass) 49% and EV +$202 per $80 at the prior (75% and +$760 at the published Sharpe;
−$22 with no edge), but a median of ~490 trading days to pass; two ZN pass in ~170. The effect's
concentration fixes Z02's problem; the cost is time.

**Open with the user:** whether Tradeify allows ZN or the micro 10-year; go-ahead for the one trial.

## 91. The user's timeline — a payout within 1–2 months — needs an edge of about Sharpe 5 (S2, S8)

**No trial spent; N 762, SR\* 0.1367. One computation record (m00145).** `reports/z_speed_frontier.json`
(`reporting/z_speed_frontier.py`). Z03 not run: the user requires passing and a first payout within 1–2
months, and Z03 (§90) would take ~8–24 months to pass.

### What the requirement implies, computed

Tradeify's confirmed rules, resampled real MNQ 09:30–16:00 sessions (post-2021) with drift removed and an
edge imposed; a funded account starting the day after the pass, which must clear the $2,000 buffer.
**P(a first payout within 42 trading days of starting the evaluation):**

| annual Sharpe | 1 MNQ | 2 MNQ | 3 MNQ |
|---|---|---|---|
| 0 | 7% | 4% | 2% |
| 1 | 12% | 6% | 3% |
| 2 | 20% | 9% | 5% |
| 3 | 30% | 13% | 6% |
| 5 | **51%** | 23% | 10% |

(P(pass within 42 days), 1 MNQ: 20% / 27% / 38% / 48% / 66%.)

### What it means

- **A coin-flip chance of a payout within two months needs an annual Sharpe of about 5** at one MNQ.
  Larger positions make it worse: the trailing floor and the 40% consistency rule punish large days
  more than they reward them.
- **Nothing in twelve series approaches that.** The one effect confirmed out of sample (Z02, §88) is
  ~0.5; the best published, account-tradeable effects found (§86, §90) are ~0.9–1.1 before decay.
  Daily-horizon Sharpes of ~5 in index futures belong to infrastructure-heavy market-making, not to
  anything this programme can find or a retail account can run.
- **At the edges actually available, a 1–2 month payout is a ~7–12% outcome per evaluation** — luck,
  not strategy.

### What would change the arithmetic

The frontier is set by the account's geometry as much as by the edge: a $3,000 target against a $2,000
trailing floor that never locks during the evaluation, a 40% consistency rule, and a $2,000 funded buffer.
Account types with a static or end-of-evaluation-locked floor, a lower target relative to the drawdown, or
no consistency rule move the frontier; the engine (`y02_tradeify`, `z_speed_frontier`) can price any
firm's terms in minutes.

## 92. Eleven prop-firm account types priced against the strategies: none makes a 4-month payout likely (S8)

**No trial spent; N 762, SR\* 0.1367. One computation record (firm comparison).** `reports/z_firms.md`
(`reporting/z_firms.py`). The user relaxed the requirement to **a first payout within 4 months (84
trading days)** and asked for Tradeify's other account types plus Apex, Lucid, Take Profit Trader, Alpha
Futures and Topstep.

### Rules — gathered 2026-10-09, third-party summaries, several conflicting

50K accounts: Tradeify Select Daily (the user's confirmed terms), Select Flex, Growth, Lightning; Apex
EOD; Topstep (standard path); Lucid Flex, Lucid Pro; Take Profit Trader; Alpha Futures Zero, Advanced.
**None could be confirmed on the firms' own pages** (Tradeify's help centre refused automated access);
each assumption is written into its spec (`note`) and the report. Sources: Prop Data Lab (Tradeify,
verified against its help centre 2026-08-26), and guides from QuantVPS, Prop Trading Vibes, Tradecovex,
Phidias, Tradetanto, LuxAlgo, PropScope and Alpha Futures' own comparison page — listed in the session.

### The engine, checked first

One general engine (floor trailing at end of day or intraday, stopping at the start or never; soft daily
limits; consistency that raises the target; minimum days; time limits; subscriptions and activation fees;
payouts by buffer or share of profit, qualifying days, caps and ladders). **It reproduces §82** (Tradeify,
user's terms, 1 MNQ RTH, no edge: P(pass) 0.189 vs 0.193, two-year EV +$78 vs +$78) — after a bug was
caught: "uncapped after going live" had been written as an empty value, which numpy turned into NaN and
which silently blocked every payout after the third. Funded payouts then matched the validated engine
exactly ($868 each). Run one strategy per process; the first attempts were killed for memory.

### Result — P(a first payout within 84 trading days)

| account | no edge (1 MNQ RTH) | Sharpe 1 (1 MNQ RTH) | MGC London, no edge | Z02, Sharpe 0.41 |
|---|---|---|---|---|
| Tradeify Select Daily (user's) | 7% | 12% | 7% | 5% |
| Tradeify Select Flex | 8% | 15% | 13% | 14% |
| Topstep | 9% | 17% | 13% | 14% |
| **Lucid Flex** (close-only drawdown) | **13%** | **21%** | 11% | 14% |
| Lucid Flex (intraday breach) | 8% | 13% | — | — |
| all others | 1–7% | 8–15% | 1–11% | 2–8% |

EV per attempt within the 84 days, no edge / Sharpe 1: Lucid Flex +$117 / +$453, Topstep +$79 / +$295,
Tradeify Select Daily +$89 / +$282; Apex, Alpha, Take Profit Trader, Tradeify Growth and Lightning are
negative at no edge (fees, time limits, monthly subscriptions, higher buffers).

### What it means

- **No account type makes a payout within 4 months likely.** The best is ~13% at no edge and ~21% with a
  Sharpe-1 edge — and that best (Lucid Flex) depends on its drawdown being checked at the close only;
  with intraday breach it falls to 8% / 13%, level with Topstep and Tradeify.
- **The structure, not the firm, binds:** a ~$3,000 target, a ~$2,000 trailing drawdown and a buffer
  before payout appear in every firm's 50K account in some form.
- **Within that, the cheapest accounts with no time limit and no monthly subscription do best**
  (Tradeify Select Daily at the user's $80, Lucid Flex, Topstep); time limits (Apex), subscriptions (Take
  Profit Trader, Alpha) and high buffers (Lucid Pro, Growth) do worst.
- **Strategies:** the Sharpe-1 column is the best published effect found, assumed rather than measured;
  Z02's confirmed edge (0.41) gives 2–14%.

## 93. The A-series: the account played optimally — a payout within 4 months in ~60% of runs (S8)

**No trial spent; N 762, SR\* 0.1367. No market claim (zero edge throughout). One computation record.**
`A_SERIES.md`; `reporting/a01_game.py`, `reporting/a02_real.py`; `reports/a01_game.json`,
`a02_real.json`, `a02_sequential.json`.

The user asked for strategies built around prop-firm rules. Noted first, plainly: most quick prop-firm
successes are the visible tail of very many attempts — the lottery measured in §91–§92 — and software
cannot create a market edge. **What had never been tried was optimising the STAKING within the rules.**

### A01 — solved exactly (fair odds)

Daily bracket choice (+W / −L), dynamic programming on Tradeify's evaluation and funded rules. **Max
P(pass) 30% within ~10 trading days** (vs ~19% passive); funded P(first payout) 48%; whole path P(payout
within 84 days) 14.5%, EV +$245 per attempt. Three defects found and fixed on the way, each recorded in
code: odds priced on a stop beyond the floor (gave 41%, above the 40% fair ceiling); a free "wait" action
that tied with trading once values settled and left 4,602 reachable states idle; orders not netted for
cost, which left the deciding day $7 short of the target.

### A02 — real MNQ minute paths

Engine checked on fair synthetic paths (26.4% with costs, vs 30% without). On real paths, drift removed:
2 MNQ — P(pass) 23%, P(payout within 84 days) 8%, EV +$123 per $80; median 7 days to pass, 12 to a
first payout. **Real intraday behaviour erases most of the single-attempt gain; the speed remains.**

### A03 — back-to-back attempts over 84 trading days

**Solved policy, 2 MNQ, real history replayed from every start date: P(at least one payout) 61%, median
first payout on day 38, ~10 attempts ($824 in fees), mean net +$675, P(net > 0) 45%** (resampled: 53%,
+$763). Passive 1 MNQ, the same way: 32%, +$84. 3 MNQ replayed: −$51.

### Decisions taken rather than resolved silently

1. **"Wait" is not an action** in the solved game: in a fair game it never raises the objective, and as a
   tie-break it stranded accounts.
2. **The evaluation policy is the one solved for P(pass within 21 days); the funded policy maximises
   expected dollars within 21 days** — applied as stationary tables.
3. **No market claim**: every path is demeaned; the result is a property of the rules plus real intraday
   path shape and costs.
4. **Open, for the user:** whether Tradeify's terms allow this bracket behaviour; real commission; a
   forward demo of the exact policy before money.

## 94. Route 1 — a portfolio of parallel accounts, payouts reinvested — mostly goes bust (S8)

**No trial spent; N 762, SR\* 0.1367. Zero edge. One computation record.** `reports/a04_portfolio.md`
(`reporting/a04_portfolio.py`).

The user's point: one account at a time does not scale, and a policy that burns accounts is not a
business. Recorded first, as the user was told: **with zero edge every funded account eventually dies,
and its expected lifetime payouts are capped near 90% of the $2,000 cushion (~$1,800) whatever the
policy** — the martingale identity of §79. So without an edge, scaling can only mean more parallel
attempts. The user chose that route ("route 1").

### The lanes

The solved policy (A01) on four instrument-sessions, contracts sized to ~2 MNQ New York's daily swing:
MNQ 09:30–16:00 (2), MNQ 19:00–03:00 (5), MGC 03:00–11:30 (4), MGC 12:00–16:00 (7). Sessions paired by
date (2016-01-27 to 2026-08-27) and replayed in real order. **Daily correlations between lanes +0.02 to
+0.08** — they diversify. Each alone, back-to-back for 84 days: P(≥1 payout) 36–50%, mean net +$100 to
+$546 (MNQ New York here +$329, below A03's +$675 because this sample includes 2016–2020).

### The portfolio — 12 months, every 5th start date (450), payouts reinvested

| budget, max accounts | busted by month 4 | busted by month 12 | mean net, 12 months | 90th pct bankroll | bankroll above start |
|---|---|---|---|---|---|
| $800, 4 | 62% | **69%** | +$2,043 | $11,949 | 28% |
| $800, 8 | 79% | 84% | +$1,932 | $12,287 | 14% |
| $1,600, 8 | 59% | **68%** | +$4,230 | $24,375 | 28% |
| $1,600, 12 | 72% | 78% | +$4,379 | — | 20% |

**A positive average carried by ~3 runs in 10; ~7 in 10 lose the whole budget.** More concurrent
accounts make it worse.

### Why — the bet's shape

Each attempt risks $80 for a ~8% chance at a payout of roughly $1,000–1,500: long odds, thin edge. The
Kelly fraction for such a bet is ~2% of bankroll, so each concurrent account wants a reserve of roughly
$4,000–8,000; the budgets tested bet 5–10× too much, and ruin arrives before the long shots do. At a
Kelly-safe size the bankroll grows slowly. **Route 1 does not scale into a business at zero edge.**

### What this closes and what it leaves

- Closes: scaling the zero-edge structure by parallel accounts, as an income route.
- Leaves: the A-series staking solver as a TOOL — the right way to stake any real edge once one exists
  (route 2), since a modest edge staked the solved way pays far more than the same edge traded passively.

## 95. Route 2's bar: the edge needed for a payout within 4 months; three literature candidates rejected (S1, S2)

**No trial spent; N 762, SR\* 0.1367. One computation record.** `reports/b_event_frontier.json`
(`reporting/b_event_frontier.py`). The user chose route 2 — find an edge, stake it with the A01 solver.

### Candidates read and rejected before any test

- **End-of-day reversal** (Baltussen, Da & Soebhag 2024): a cross-section of individual stocks, 3–4 bps a
  day long-short; not an index effect.
- **Option-expiration week** (Stivers & Sun 2013): S&P 100 stocks against the equal-weighted index, to 2010;
  index-level ~0.2% a week — about 4 bps a day.
- **Dash for cash** (Etula et al., RFS 2020): forced pension cash needs at month-end; ~25 bps over T−3..T−1
  and 48 bps over T−3..T+3 (working-paper figures) — about 7–8 bps a held day against ~100 bps of daily
  swing.

### The bar, computed (Tradeify Select Daily, user's terms; synthetic held-day returns)

| per-held-day Sharpe × days a month (annual) | P(payout within 84 days) | EV per $80, 84 days |
|---|---|---|
| 0.10 × 10 (1.1) | 11% | +$155 |
| 0.10 × 21 (1.6) | 20% | +$326 |
| 0.15 × 21 (2.4) | 28% | +$595 |
| 0.20 × 10 (2.2) | 21% | +$450 |
| 0.20 × 21 (3.2) | **43%** | +$1,181 |
| 0.30 × 10 (3.3) | **39%** | +$588 |
| 0.30 × 21 (4.8) | 72% | +$3,620 |

(Simple sizing, best of four daily swings; the A01 solver would add to these.)

### What it means

- **A coin-flip chance of a payout within 4 months needs an annual Sharpe of ~3**, however the edge is spread
  across days: concentration helps against the barriers but costs time.
- **No published, surviving, account-tradeable futures effect found is near 3**; the best are ~1 before
  decay, and Z02 is ~0.4–0.5 confirmed.
- **Expected value per attempt rises steeply from Sharpe ~1** (+$155 to +$326 vs +$89 at zero edge), which
  shrinks the bankroll problem that closed route 1 (§94). **Route 2's realistic target: a portfolio of
  modest, independently confirmed edges reaching ~1–1.5 combined, staked with the A01 solver.**

## 96. Z03 dropped (ZN not tradable); Z04 — the macro-announcement premium — registered before its trial (S1–S5)

**One registration (Z04). No trial spent yet; N 762, SR\* 0.1367.**

### The user's constraints, 2026-10-09

- **ZN is not supported at the user's firms.** Z03 (Treasury month-end) is dropped. The micro 10-year
  yield contract is assumed unsupported as well.
- **A Sharpe of ~0.5 is acceptable for now; the aim is to add independent pieces to a strategy portfolio**
  (§95's target: several modest confirmed edges, ~1–1.5 combined, staked with A01).

### Candidates rejected before testing (web sources in the session)

- **Turn-of-the-month** (Maberly & Waggoner 2000): disappeared after 1990 in S&P futures; a third-party
  reconstruction 1990–2026 shows Sharpe ~0.28.
- **Month-end FX hedge rebalancing at the London fix** (Melvin & Prins 2015): ~14 bps per 10% relative
  equity outperformance, in one hour, once a month; EUR/USD (the only micro FX pair at Tradeify) not
  statistically reliable.

### Z04, specified before any return on the event days was computed

Savor & Wilson (2013, 1958–2009): **11.4 bps on FOMC, employment and inflation announcement days vs
1.1 bps otherwise**; Ai, Bansal & Guo (2023) report it persisting to 2023 (10.68 vs 0.93); its FOMC part was
low in 2016–2019. A risk premium, not a flow.

- **Calendar built and checked** (`reports/z_macro_calendar.json`): FOMC decision days parsed from the
  Federal Reserve's own pages (8 a year; 7 in 2020); Employment Situation and CPI release dates from BLS
  archive pages read through a page reader (BLS refuses direct downloads) — **checked mechanically**: 12 a
  year each, every non-Friday jobs report a known exception (2013 and 2025 shutdowns, July 4 weeks, a 2026
  delay), the missing months the 2025 shutdown. ~31 event days a year.
- **Position:** long MES on each event date's UTC-day bar (20:00 ET the evening before to the 16:55 exit).
- **Test window 2010-01-01 to 2026-09-11** — after the original sample, but NOT wholly independent: the
  2023 extension covered most of it.
- **Decision (the Z rule, extended before the run):** confirm only if (1) event-day mean > other-day mean
  (Welch t > 1.645 — the paper's claim, so a rising market alone cannot pass), (2) net Sharpe > 0, (3)
  Tradeify EV at the posterior > 0 with 1 MES; prior Normal(0.25, 0.35).
- **Outcome injection passed:** Sharpe 0.25 planted on the 506 event days, recovered 0.24 (SD 0.24);
  P(estimate > 0) 84%.

## 97. Z04 run and retired: no announcement premium in ES since 2010 (S6–S8)

**One trial spent: t00769. N 762 → 763.** `reports/z04_trial.md`.

| 2010-06-07 → 2026-09-11 | value |
|---|---|
| mean ES return, 506 event days | **+3.4 bps** |
| mean ES return, other days | +5.7 bps |
| Welch t (needed > 1.645) | **−0.43** |
| strategy net Sharpe (gross) | +0.04 (+0.16) |
| calendar-shift control: share at or above the real | 0.67 |
| posterior Sharpe | 0.11 ± 0.20 |
| Tradeify EV at the posterior, 1 MES, 2 years | −$17 (zero edge −$27) |

**Rejected on every condition.** Event days earned LESS than other days. The injection had shown 84% power
for a Sharpe of 0.25 at this n, so this is an informative null for the effect size sought — not a
statement about the pre-2010 premium, and not independent of the UTC-day bar approximation (§74).

**For the portfolio search:** a published risk premium reported to persist to 2023 in broad-market
studies does not appear in S&P futures, this way, since 2010. Two Z tests: Z02 confirmed (~0.4–0.5),
Z04 rejected.

## 98. Four more candidates screened out before testing; the Goldman roll needs a tradability ruling (S1, S2)

**No trial spent; N 763, SR\* 0.1367.** Literature only (sources in the session).

| candidate | published | after publication | verdict |
|---|---|---|---|
| Buyback blackout windows (MES/MNQ) | industry commentary | State Street 1994–2018: no significant negative return; 10b5-1 plans keep buying | **rejected** |
| Oil predicts stocks with a lag (Driesprong, Jacobsen & Maat, JFE 2008) | 12 of 18 markets | a 2026 study of 44 markets: "present only up to the global financial crisis and has largely disappeared ever since" | **rejected** |
| Gold autumn effect (Sept, Nov; 1980–2010) | in-sample only | no post-2010 test; a recent study finds commodity seasonals do not beat buy-and-hold out of sample; 2 months a year | **rejected** |
| **Goldman roll front-running** (Mou 2011) | **Sharpe up to 4.39, 2000–Mar 2010**; index funds roll on business days 5–9 | mixed: traders roll early/late (Irwin, Sanders & Yan); a CFTC study finds small roll-day effects | **open — needs a ruling** |

**The Goldman roll is the strongest candidate found in route 2**: a forced flow on a published schedule,
and testable after its sample on the purchased data (every CL expiry from 2010, including CME's own
calendar-spread instruments). **But the trade is a calendar spread — long one CL expiry, short the next —
which may count as hedging under the user's firm's rules.** No test until the user rules on it.

## 99. Goldman roll out (a spread is long and short at once); Z05 — gold overnight/day — registered (S1–S5)

**One registration (Z05). No trial spent yet; N 763, SR\* 0.1367.**

**User's ruling, 2026-10-09:** the firm allows anything that is never long and short at the same time.
**The Goldman roll (§98) is therefore out** — a calendar spread is long one expiry and short another at once.
An outright version is not viable: the roll moves the gap between expiries by a fraction of a percent over
several days, against crude's ~2% daily swing.

**Z05**, from Blose, Gondhalekar & Kort (2018, J. Econ. & Finance): COMEX gold earns significantly positive
returns overnight and significantly negative returns in the day session, in up and down markets, 1985–2012.
The paper's tables could not be read (Springer and ResearchGate refuse automated access), so the
specification follows the stated claim and **the prior, Normal(0.25, 0.35), is an assumption**.
- **Position:** 1 MGC long 18:00–08:20 ET, short 08:20–13:30 ET (the COMEX day session), long 13:30–16:55,
  flat 16:55–18:00 — sequential, never simultaneous. Three round trips a day at $3.32.
- **Test window 2013-01-01 to 2026-08-27**, after the paper's sample; MGC minute data, complete sessions.
- **Confirm only if** overnight minus day > 0 (Welch t > 1.645) with the published signs, net Sharpe > 0,
  and Tradeify EV at the posterior > 0 with 1 MGC.
- **Outcome injection:** the first version used a permutation, which leaves the sample mean and SD
  unchanged and so reported zero uncertainty — corrected to a bootstrap: Sharpe 0.25 planted, 0.25
  recovered, SD 0.30, P(estimate > 0) 80%, n = 2,736 sessions.
- Registry: MGC admitted as a single-market primary alongside MES (§87's rule).

## 100. Z05 run: confirmed under the rule, marginally — and possibly gold's rally (S6–S8)

**One trial spent: t00770. N 763 → 764.** `reports/z05_trial.md`.

| 2013-01-02 → 2026-08-27, 2,736 sessions | value |
|---|---|
| mean overnight / New York day return | +2.9 / −0.7 bps |
| Welch t, overnight − day (needed > 1.645) | **+1.82** |
| net Sharpe, three round trips a day (gross) | **+0.22** (+0.56) |
| long-overnight leg alone / short-day leg alone | +0.30 / **0.00** |
| by period: 2013–16 / 2017–20 / 2021–26 | −0.20 / −0.06 / **+0.52** |
| posterior Sharpe | 0.24 ± 0.23 |
| Tradeify EV at the posterior, 1 MGC, 2 years | +$47 (zero edge +$5) |

**CONFIRMED under the user's rule (§86), marginally.** Three reasons to discount it:
1. **The short New York leg earns nothing**; the result is the long-overnight leg, net of three round trips.
2. **It appears only in 2021–2026**, the period of gold's large rally; a long position held ~18 hours a day
   collects much of any drift, and the overnight−day test only partly separates drift from the published
   asymmetry.
3. **t = 1.82** against a 1.645 bar.

**Not done, deliberately:** switching to "long overnight only" after seeing the legs would be fitting the
result; it would need a forward test of its own. **Portfolio so far:** Z02 (~0.4–0.5, MES) and Z05 (~0.24,
MGC) — about 0.5 combined if independent.

## 101. The edge portfolio (Z02 + Z05) in the account: worse than zero-edge solved staking (S8)

**No trial spent; N 764, SR\* 0.1367. One computation record.** `reports/zp_portfolio.md`
(`reporting/zp_portfolio.py`). Realised returns, real order — descriptive, partly a second look.

Z02 (1 MES by the rebalancing signal's sign) + Z05 (1 MGC, gold long overnight / short the NY day) in one
Tradeify account (different products; never long and short in one), 2,736 days 2013–2026; the day's worst
point counted as the sum of both legs' worst points (conservative).

| strategy | realised Sharpe | 4 months back-to-back: P(≥1 payout) | mean net | P(net > 0) |
|---|---|---|---|---|
| Z02 + Z05, 1 unit | +0.21 | 15% | −$230 | 8% |
| Z02 + Z05, 2 units | +0.21 | 13% | −$832 | 6% |
| Z05 alone, 1 MGC | +0.22 | 18% | +$191 | 17% |
| Z02 alone, 1 MES | +0.06 | 3% | −$193 | 2% |
| **A03, zero-edge solved staking, 2 MNQ** | 0 | **61%** | **+$675** | 45% |

**Two findings.**
1. **The edges are weaker over the full period than in their tests**: Z02's one-MES version earns +0.06 over
   2013–2026 (its +0.41 was the 2023–2026 test window; 2013–2023 lies inside the paper's sample).
2. **In this account, staking dominates a weak edge**: passive daily holding of ~0.2-Sharpe edges loses to
   the zero-edge solved policy. A 0.2–0.4 Sharpe edge shifts a ~±1% daily bracket's odds by a fraction of a
   percent, so weak edges add almost nothing to the solver either.

**Verdict (the user's own condition): not good enough — keep searching.** What a candidate must now beat is
not zero but A03: it needs an edge large enough to move the solver's bracket odds, i.e. several bps a day
on MNQ/MES/MGC, consistently, after costs.

## 102. A05: re-solving the staking with real bracket odds makes it worse (S8)

**No trial spent; N 764, SR\* 0.1367. Zero edge. One computation record.** `reports/a05_empirical.json`
(`reporting/a05_empirical.py`).

A01 priced every bracket as a fair coin. A05 measured each bracket's real NET outcome distribution (2 MNQ,
09:30–16:00, cost netted as in A02) on **2015-11 to 2020-12** sessions (drift removed), re-solved both games
with those distributions (on a reduced 21-bracket menu; A01 keeps its full grid), and ran A03's test on
**2021–2026**, the same real-history back-to-back replay:

| 84 trading days, 2021–2026 replay | A01 fair-odds policy | A05 real-odds policy |
|---|---|---|
| P(≥1 payout) | **61%** | 43% |
| mean net | **+$675** | −$8 |
| P(net > 0) | 45% | 38% |

**Why:** in the training years, a +$1,200 / −$1,000 bracket on 2 MNQ hit its target 17% of the time, its
stop 26%, and **ended at the close with neither 57% of the time** — calmer markets relative to today's
contract value. The learned policy fitted that regime and transferred badly. **The fair-odds policy
assumes no regime and is the more robust one.** A vol-normalised version (sizing contracts to a constant
daily swing) might transfer, but it is a further refinement on a single historical regime split, and is not
pursued now. A03 stands as the bar.

## 103. Option 2 — edges big enough to move the solver: two screened out on size or survival (S1, S2)

**No trial spent; N 764, SR\* 0.1367. One computation record (m00152).** `reports/z_screen_intramom.json`
(`reporting/z_screen_intramom.py`). The user approved option 2 after §102: look only for edges of **several
bps per held day**, reliably, on MNQ / MES / MGC, and screen on size before spending a trial.

### Market intraday momentum (Baltussen, Da, Lammers & Martens, JFE 2021)

The return from the previous close to 30 minutes before today's close (r_ROD) predicts the last half hour,
across 60+ futures, 1974–May 2020; the stated mechanism is forced hedging by short-gamma option dealers and
leveraged ETFs. Published: NQ β 6.36 (t 7.97), R² 4.1%; the equity 1/N timing strategy earns 6.86% a year at
Sharpe 1.73 — **~2.7 bps a day, gross, for a diversified portfolio**; no costs (the authors say it may not be
exploitable after costs except at a tick). Already marginal against the bar, so the size was measured **on
our data inside the paper's own sample** (to 2020-04-30; the script asserts nothing later is read, so the
2020-05 → 2026 test window stays clean):

| paper's sample, our data | days | corr(r_ROD, r_LH) | timing, gross bps/day (t) | gross Sharpe | net $/day, 1 contract | net Sharpe |
|---|---|---|---|---|---|---|
| MNQ (NQ), last half hour 15:30–16:00 | 1,841 | +0.09 | **+1.1** (1.55) | +0.57 | −0.88 | −0.34 |
| MGC (gold), last half hour 13:00–13:30 | 897 | +0.20 | **+1.2** (2.03) | +1.07 | −1.61 | −0.98 |

(Days whose signal spans a contract roll, or missing a bar at either time, are dropped.) **About 1 bp a day
before costs, inside the sample that made the claim** — real for gold, but a dollar or two a day on today's
contract, eaten by the round trip. **Rejected on size; no registration, no trial.** A test on 2020-05 →
2026 would be well powered for the published size but cannot reach the bar even if the effect survived.

### Pre-holiday effect (Ariel 1990; Lakonishok & Smidt 1988)

Large per held day in the original samples (~20–30 bps on the day before a US market holiday, ~9 days a
year). **The one peer-reviewed post-publication test** (Ko & Yang, *Critical Finance Review* 2024, 1983–2019)
finds it **now exists only among small firms; for large firms the difference became insignificant,
especially after 1990.** Supportive recent sources are a short conference sample and a practitioner blog
(~0.15% over three days since 2005). **Rejected on survival; no trial.**

### Where option 2 stands

The bar (§95) is a combined annual Sharpe of ~3 for a coin-flip payout within 4 months, or several bps a held
day for the A01 solver's brackets to move. Every candidate read across §95–§103 is either ≲1–1.5 bps a
held day before decay or failed its post-publication record; the two that passed tests (Z02 ~0.5, Z05
~0.2) do not move the account (§101). **No published, surviving, account-tradeable effect of the required
size has been found.** The search can continue, but the expected yield per candidate is now low; the
alternative on the table is a demo forward test of the A01/A03 solved policy, which is the bar.

## 104. A06: the solved policy as a daily ticket for the demo forward test; the search continues alongside (S8)

**No trial spent; N 764.** `reporting/a06_playbook.py`; lookup tables `reports/a06_playbook_{eval,funded}.csv`;
log template `reports/a06_demo_log.csv`. The user will run A03 on a demo account and wants the edge search to
continue meanwhile rather than wait four months on it.

**The ticket is A03's replay rule, nothing added:** at 09:30 ET buy 2 MNQ at market; one OCO bracket on the
fill — take-profit +W, stop −L (net dollars; the order offsets add the $4.64 round trip, as A02); close at
16:00 ET if neither fills. W and L come from the 21-day-horizon A01 policy at yesterday's end-of-day state
(evaluation: balance, EOD peak, best day; funded: balance, peak, payouts), with the stop capped one dollar
above the floor — the same rounding and cap as `a02_real.sequential`. Examples: a fresh evaluation is
+$1,200 / −$1,000 (301.25 / 248.75 points); a fresh funded account +$3,000 / −$1,000.

**What the demo can and cannot show.** The policy has zero edge; its value is the rules' asymmetry. One
four-month run is one draw from a distribution in which **P(net > 0) is 45% even if everything works**
(A03), so the demo's P&L cannot confirm or refute it. What the demo *can* check, day by day, is the
assumptions the replay makes: fills at the 09:30 open, the bracket executing at its prices, stop slippage on
gaps, the firm marking the floor and consistency rule as modelled, and costs. Judge the demo on those, by
comparing each logged day against the replay's outcome for that day's bars, not on whether it pays out.

## 105. A07: volatility-scaled size does not help; 4 MNQ beats A03's 2 on both histories — the demo runs 4 (S8)

**No trial spent; N 764. Zero edge. Computation record m00154** (`reports/a07_volscaled.json`,
`reporting/a07_volscaled.py`). **m00153 is superseded:** its `--log` re-read the JSON left by the first,
vol-only run instead of the full grid (the log is append-only; the record stays, this note corrects it).

A05 showed the fixed 2-MNQ bracket behaves differently by regime (in calm years most brackets end at the
close). A07 tested a rule fixed before the run — contracts = clip(round(2 × σ_ref / σ̂₂₀), 1, 15) on a
trailing 20-session σ̂ — and, as controls, the same A01 policy at **fixed** sizes 1–8 MNQ. Two independent
histories (2021–26, A03's; 2015–20, A05's; drift removed within each, today's contract value), each by
in-order replay from every start date and by a 21-session block bootstrap (new `a02_real` mode `block`,
2 × 6,000 paths). 84 trading days of back-to-back $80 attempts.

| P(≥1 payout) / mean net | 2021–26 replay | 2021–26 block | 2015–20 replay | 2015–20 block |
|---|---|---|---|---|
| fixed 2 (A03) | 61% / +$675 | 55% / +$509 | 35% / +$180 | 40% / +$95 |
| fixed 3 | 53% / −$51 | 54% / +$234 | 56% / +$269 | 55% / +$624 |
| **fixed 4** | **72% / +$1,053** | **69% / +$1,043** | **78% / +$1,527** | **65% / +$1,324** |
| fixed 5 | 74% / +$1,416 | 67% / +$1,111 | 46% / +$389 | 56% / +$525 |
| fixed 6 | 83% / +$1,905 | 73% / +$1,390 | 58% / −$9 | 61% / +$401 |
| fixed 8 | 48% / +$150 | 54% / +$261 | 65% / +$432 | 67% / +$527 |

- **Vol scaling: no reliable gain** over a fixed size of the same average (2021–26 levels 0.75–2.0: 49–93%,
  non-monotone; 2015–20: 46–71%). The 93% at 1.5× is a spike between 72% and 74%. Dropped.
- **Size: 4 MNQ beats 2 MNQ on every measure in all four tests**, and is the only size near the top in both
  histories. 2 MNQ was A03's choice against 3 on one history (§93), where 3 happens to be a dip.
  Mechanism, plausibly: at 2 MNQ many days end at the close with neither level hit, so the account moves
  less like the solver's fair coin; at 4 the brackets resolve. The response is not smooth (3 and 8 dip) and
  4 was picked by looking — mild selection, partly answered by its holding in both histories and both
  methods. **Effective samples are small** (~16 independent 84-day windows per history).
- **The demo runs 4 MNQ** (`a06_playbook` default; tables regenerated). Typical tickets: evaluation start
  +$1,200 / −$1,000 = +151.25 / −123.75 points; funded +$3,000 / −$1,000.

**Two literature leads screened out, no trial:** a gold trend preprint (arXiv 2511.08571: Sharpe 2.88, 43%
a year at 15% volatility with a 0.52% maximum drawdown — internally inconsistent, spot gold, signal not
specifiable) and the same-half-hour periodicity (Heston, Korajczyk & Sadka 2010; a cross-sectional stock
effect with no index-futures evidence).

**Memory note:** the 2.7 GB machine now has ~1 GB free with the editor open; loading the full NQ minute
series was OOM-killed. `a07_volscaled` streams each era to a subset file and caches the paths under
`data/cache` (gitignored); results matched the earlier full-series load exactly (sessions, σ).

## 106. A08: the same staking on gold — 8 MGC London long, a second, near-independent account (S8)

**No trial spent; N 764. Zero edge. Computation record m00155** (`reports/a08_gold.json`,
`reporting/a08_gold.py`). The A01 policy on **MGC, London 03:00–11:30 ET, long — the gold cell fixed in Y03
(§83) before any of this**, at fixed sizes 2–15; A07's tests (2011–20 and 2021–26 histories, drift removed
within each, today's contract value; in-order replay and 21-session block bootstrap; 84 trading days of
back-to-back $80 attempts). One MGC's daily window swing: $362 (2011–20), $386 (2021–26).

| P(≥1 payout) / mean net | 2011–20 replay | 2011–20 block | 2021–26 replay | 2021–26 block |
|---|---|---|---|---|
| 2 MGC | 17% / +$46 | 22% / +$13 | 35% / −$66 | 33% / +$64 |
| 4 | 40% / −$112 | 47% / +$313 | 60% / +$858 | 51% / +$575 |
| 6 | 52% / +$433 | 60% / +$586 | 62% / +$1,594 | 58% / +$1,073 |
| **8** | **60% / +$1,352** | **64% / +$1,353** | **48% / +$1,299** | **54% / +$692** |
| 10 | 78% / +$2,710 | 74% / +$2,395 | 48% / +$829 | 49% / +$521 |
| 12 | 77% / +$3,274 | 77% / +$2,892 | 55% / +$571 | 53% / +$394 |
| 15 | 77% / +$2,591 | 77% / +$2,467 | 55% / +$265 | 55% / +$129 |

- **The best size differs by era** (10–12 in 2011–20, 6 in 2021–26), so the best cell is not taken.
  **8 MGC is chosen by matching risk, not by its row:** its daily $ swing (~$3,100) is close to 4 MNQ's
  (~$2,800). Across both products the plan does best when the position's daily swing is roughly 2.5–4× the
  $1,000 stop — enough for brackets to resolve rather than end at the close (an observation from two
  products' grids, not a fitted rule).
- **Correlation of daily results with the MNQ account: +0.06 (2021–26) and +0.06 (2011–20).** Two accounts
  are close to independent attempts.
- Playbook: `a06_playbook ... --product MGC` (8 MGC, buy at 03:00 ET, flat at 11:30 ET); tables
  `reports/a06_playbook_{eval,funded}_mgc.csv`. The 03:00 entry needs a time-triggered order.

## 107. A09: both demo plans survive the user's slippage; neither holds through the 17:00–18:00 break (S8)

**No trial spent; N 764. Computation record m00156** (`reports/a09_slippage.json`, `reporting/a09_slippage.py`).

**Hours, confirmed against the user's rule** (no position held through the 17:00–18:00 ET daily close): the
MNQ plan holds 09:30–16:00 ET; the gold plan **03:00–11:30 ET (3 AM to 11:30 AM;** London window = minutes
540–1050 after the 18:00 open). Both open and close inside one trading day.

**Slippage.** The user reports fills within ~$10 a trade. Added to commissions per day's trade (the
same $ on take, stop and close outcomes):

| P(payout in 4 months) / mean net | slip $0 | slip $10 | slip $20 |
|---|---|---|---|
| 4 MNQ, 2021–26 (replay · block) | 72% +$1,053 · 69% +$1,043 | 80% +$1,230 · 66% +$879 | 63% +$308 · 61% +$487 |
| 4 MNQ, 2015–20 | 78% +$1,527 · 65% +$1,324 | 76% +$1,267 · 63% +$1,107 | 56% +$478 · 56% +$739 |
| 8 MGC, 2021–26 | 48% +$1,299 · 54% +$692 | 51% +$1,076 · 55% +$790 | 43% +$653 · 54% +$578 |
| 8 MGC, 2011–20 | 60% +$1,352 · 64% +$1,353 | 68% +$1,800 · 69% +$1,411 | 63% +$1,730 · 64% +$1,366 |

At **$10 a trade the plans are essentially unchanged** (block-bootstrap net −$160 to +$100; in-order replays
move both ways, which is path noise). At $20, MNQ falls to 56–63% and +$300–740; gold holds. With fills
confirmed, the demo's execution purpose is largely answered; what remains is the firm's rule enforcement.

## 108. A10: six weeks of unseen data, and the stop-fill assumption corrected — both plans better than reported (S8)

**No trial spent; N 764. Computation records m00157 (forward, first run; superseded), m00158 (84-day, stop
fills) and m00159 (forward, final).** `reports/a10_forward.{json,md}`, `reports/a10_levelfill_84d.json`
(`reporting/a10_forward.py`, `reporting/a10_levelfill.py`).

**New data.** Batch `GLBX-20261010-3KALFURKDJ` (GLBX.MDP3, ohlcv-1m, `MNQ.FUT` + `MGC.FUT`, parent,
2026-08-28 → 2026-10-10 UTC exclusive, CSV/zstd, the original job's settings; NQ not needed after 2019),
fetched over FTP and verified against its manifest (47 files): 16 outright contracts, 28 spreads discarded.
Parsed to `data/parquet_update`, rolled by `roll.py`'s rule to `data/continuous_update` (MNQ U6→Z6 on
2026-09-15, that session dropped; MGC Z6 throughout); the 2026-08-28 session, split by the two purchases at
00:00 UTC, completed from the existing series (same contract, 120 + 1,260 = 1,380 bars). The canonical
`data/` series are untouched. (`parse.py` overwrote `reports/batch_contents.md`; restored from git.)

**The stop-fill assumption.** A02–A09 filled a stop at the LOW of the first minute bar touching it. On
tight stops at 09:30 that doubled the loss (planned −$200, booked −$221 to −$485 in the forward log). The
user reports fills within ~$10, so `a02_real.STOP_FILL = "level"` (fill at the stop price) is added; the
default stays `bar_low` so every earlier record reproduces.

**84 days, stop-price fills** (P(payout) / mean net; replay · block):

| | 2021–26 | 2015–20 (MNQ) / 2011–20 (MGC) |
|---|---|---|
| 4 MNQ, bar-low (A07) | 72% +$1,053 · 69% +$1,043 | 78% +$1,527 · 65% +$1,324 |
| **4 MNQ, stop price** | **79% +$1,143 · 71% +$1,317** | **72% +$1,833 · 65% +$1,685** |
| 5 MNQ, stop price | 77% +$1,940 · 76% +$1,998 | 69% +$2,358 · 71% +$1,759 |
| 8 MGC, bar-low (A08) | 48% +$1,299 · 54% +$692 | 60% +$1,352 · 64% +$1,353 |
| **8 MGC, stop price** | **77% +$2,210 · 76% +$2,031** | **74% +$2,396 · 76% +$2,419** |

Under realistic fills the size curves are smoother (part of A07/A08's noise was the fill artifact) and **8 MGC
is strong in both eras**. 5 MNQ edges 4 in both eras; the playbook stays at 4 (no re-selection on a further
look) — noted as the option.

**Forward, 2026-08-28 → 2026-10-09, real prices and drift, stop-price fills:** 4 MNQ — 2 evaluations bought,
one passed-free run to a funded account (ends funded at $49,288), no payout yet, net −$160; 8 MGC — 7
evaluations, one passed (funded failed in 3 days), net −$560. **Both sit at the historical median for a
29–31-session stretch** (MNQ −$320, MGC −$400; P(net > 0) at that length 29% / 38%). Six weeks can neither
confirm nor refute a plan whose value shows over four months.

## 109. A11: the edge bar for the staking plans — Sharpe 0.25–0.5 on the window's direction now pays (S2, S8)

**No trial spent; N 764. Computation record m00160** (`reports/a11_edge_bar.json`, `reporting/a11_edge_bar.py`).
Route 2's bar (§95) asked an edge to win the account on its own: annual Sharpe ~3. The plans now earn from the
account's structure (§105–§108), so an edge only has to **tilt each day's bracket** — pick its direction, or
make the long side likelier. Planted as a drift of S/√252 × σ_window per session on the drift-free paths,
stops filling at the stop price, 84 trading days (P(payout) / mean net, block bootstrap; replay similar):

| annual Sharpe on the window | 4 MNQ 2021–26 | 4 MNQ 2015–20 | 8 MGC 2021–26 | 8 MGC 2011–20 |
|---|---|---|---|---|
| 0 | 71% +$1,317 | 65% +$1,685 | 76% +$2,031 | 76% +$2,419 |
| 0.25 | 72% +$1,475 | 65% +$1,789 | 80% +$2,556 | 81% +$2,872 |
| 0.5 | 73% +$1,574 | 70% +$1,966 | 81% +$3,251 | 81% +$3,196 |
| 1.0 | 78% +$1,935 | 76% +$2,651 | 83% +$3,708 | 85% +$4,078 |
| 2.0 | 82% +$2,816 | 85% +$4,493 | 90% +$5,439 | 91% +$6,994 |

**The new screening bar: a directional effect of annual Sharpe ≥ ~0.25 on the traded window (≈1.5 bps a
day), surviving after publication, is worth +$100–600 per 4 months — most on gold.** Candidates rejected in
§95–§103 only for SIZE (not for decay) are reopened against it; those rejected for not surviving publication
stay out. The window matters: an effect must act inside 09:30–16:00 (MNQ) or 03:00–11:30 ET (MGC).

## 110. Z06 registered — the 12-month trend sign as the bracket's direction; a follow-on to W04 (S1–S5)

**No trial spent at registration; N 764.** Screening against §109's bar: the only candidate with strong
post-publication evidence that acts inside the plans' windows and fits a direction tilt is **time-series
momentum** (Moskowitz, Ooi & Pedersen 2012: sign of the past 12-month return, all 58 futures, 1985–2009;
replicated over a century and in live trend funds). **It is not new to the programme:** W04 (§72–§76) held
the same signal daily in a trend-plus-carry book and failed — mostly on cost (round trips 0.5–4.7% of a day's
SD) against a Sharpe-1.31 bar, with the trend sleeve −0.60 net post-2021; W04 never reported the trend sleeve
gross or per market. Here the sign only sets a bracket the plans pay for anyway, so cost does not enter,
and the question W04 did not answer is asked: does the sign predict the DIRECTION of these windows?

**Fixed before any return** (`hypotheses.yaml` Z06; `signals/z06.py`, `signals/z06_trial.py`): sign of the
roll-correct held return over the 12 calendar months ending at each month end (NQ, GC daily bars), applied to
every session of the next month (no leakage: the month-end bar closes 00:00 UTC, before any later window
opens); windows MNQ 09:30–16:00 and MGC 03:00–11:30 ET; real window returns; sessions 2011-07 → 2026-08-27
(MNQ's complete sessions begin 2015-11-20). Per product, CONFIRM only if (1) Sharpe(sign × r) > 0, (2)
mean(sign × r) > mean(r) — it must beat the plans' current always-long — and (3) posterior > 0. Prior
Normal(0.2, 0.3), an assumption (the paper charts per-instrument Sharpes, 0 to ~1.2). One trial, both products.

**Outcome injection** (`reports/z06_injection.json`): Sharpe 0.2 planted by bootstrap, recovered 0.197 (MNQ,
2,638 sessions, SD 0.31) and 0.201 (MGC, 2,846, SD 0.30); P(estimate > 0) 72% / 74%.

### Z06 run: rejected on both products — the plans stay always-long (S6–S8)

**One trial spent: t00771. N 764 → 765.** `reports/z06_trial.{json,md}`.

| | MNQ 09:30–16:00 (2015-11 → 2026-08) | MGC 03:00–11:30 (2011-07 → 2026-08) |
|---|---|---|
| sessions; share short | 2,638; 12% | 2,846; 34% |
| **Sharpe, sign × window** (needs > 0) | **−0.17** | **−0.25** |
| Sharpe, always long | +0.35 | +0.13 |
| window mean on short-signal sessions | **+14.8 bps** | +2.9 bps |
| posterior | +0.02 ± 0.22 | −0.03 ± 0.21 |
| by period, signal / long | 2016–20 −0.15 / +0.44; 2021–26 −0.16 / +0.32 | 2011–15 −0.86 / −1.16; 2016–20 −0.18 / +0.68; 2021–26 −0.14 / +0.11 |

**REJECTED on both:** conditions (1) and (2) fail for each, (3) also for MGC. The months the trend said "short"
were UP in both windows; in every period the signal trails always-long except gold's 2011–15 bear market,
where both were negative. Z06 retired.

**A by-product, descriptive:** with real drift, always-long earned Sharpe +0.35 in the MNQ window (2.5 bps a
session) and +0.13 in the MGC window over these years. The zero-edge backtests remove it; by §109's table a
realised drift of this size adds roughly +$100–300 per 4 months to MNQ. It is the equity premium inside the
window, not an edge to count on.

## 111. Z07 registered — index-level reversal (MAC(5)) as the MNQ bracket's direction (S1–S5)

**No trial spent at registration; N 765.** Baltussen, van Bekkum & Da (2019, JFE 132(1)): across 20 indexes,
daily index returns turned negatively autocorrelated after ~1999 as index futures and ETFs grew — a forced
flow (index arbitrage price pressure that reverses). Trading against MAC(5) earned Sharpe 0.67 on the S&P 500
after March 1999; Nasdaq 100 MAC(5) after 1999 −0.111 (t −3.84); sample to 2016-12-31. Not previously in the
registry (F02/Q01 condition on the overnight gap, a different and intraday signal).

**Fixed before any return** (`hypotheses.yaml` Z07; `signals/z07.py`, `signals/z07_trial.py`): S = 4r1 + 3r2 +
2r3 + r4 on the four roll-correct NQ daily returns dated before the session; SHORT the 09:30–16:00 window if
S > 0, LONG otherwise; real window returns; sessions 2017-01-01 → 2026-08-27. CONFIRM only if (1) Sharpe > 0,
(2) it beats always-long, (3) posterior > 0. Prior Normal(0.3, 0.3), an assumption. **A named risk:** the paper
measures close-to-close; a reversal that happens overnight or at the open is not in the 09:30–16:00 window. The
same rule on the close-to-close return is reported beside it (not decisive).

**Outcome injection** (`reports/z07_injection.json`): 0.3 planted, recovered 0.305 (SD 0.34, 2,366 sessions);
P(estimate > 0) 81%.

### Z07 run: rejected — the reversal leans the right way but does not beat always-long (S6–S8)

**One trial spent: t00772. N 765 → 766.** `reports/z07_trial.{json,md}`.

| 2017-01 → 2026-08, 2,366 sessions | |
|---|---|
| **Sharpe, direction × 09:30–16:00** (needs > 0) | **+0.09** |
| Sharpe, always long (must beat) | +0.35 |
| window mean: long sessions / short sessions (59% short) | +3.88 / **+1.58 bps** |
| by period, signal / long | 2017–20 +0.46 / +0.39; 2021–26 **−0.15** / +0.32 |
| same rule, close-to-close (the paper's basis; not decisive) | +0.25 (published 0.67 to 2016) |
| posterior | +0.21 ± 0.22 |

**REJECTED** on condition (2). The ranking is right — windows after down weeks rose more than after up weeks —
but even the "short" sessions rose, so shorting them gives up the drift; and the effect faded after 2020.
**Not done, deliberately:** a "long or flat" variant (skip instead of short) would be a new specification chosen
after seeing these numbers; it is not run. Z07 retired.

**Where the screen stands.** Against §109's bar, the two strongest documented candidates acting inside the
windows (trend, index reversal) failed against always-long; the remaining literature is either decayed, outside
the windows, cross-sectional, or second looks at Z02/Z05's already-used test data. The plans run always-long.

## 112. A12: the two accounts together — a payout within 4 months from 93–97% of start dates (S8)

**No trial spent; N 766. Zero edge (drift removed). Computation record m00161** (`reports/a12_joint.json`,
`reporting/a12_joint.py`; `a02_real.sequential` gains an opt-in `per_trader` output, default unchanged).
4 MNQ (09:30–16:00) and 8 MGC (03:00–11:30 ET) started on the same date, each run back-to-back through real
history in order for 84 trading days, stops at the stop price; paired on common start dates.

| 84 trading days, both accounts | 2021-01 → 2026-04 starts (1,276) | 2016-01 → 2020-08 starts (1,056) |
|---|---|---|
| P(at least one payout) — measured | **97%** | **93%** |
| — if independent (§106's estimate) | 95% | 93% |
| P(both pay out) | 59% | 54% |
| median trading days to the first payout | 25 | 22 |
| mean net / median net | +$3,356 / +$2,787 | +$4,361 / +$1,945 |
| P(net > 0) | 79% | 72% |
| net 10th / 90th percentile; worst start | −$1,020 / +$8,256; −$2,560 | −$1,440 / +$13,105; −$2,160 |
| mean fees | $2,105 | $1,768 |
| correlation of the two accounts' net | −0.18 | +0.26 |

**The independence estimate held.** With both accounts the chance of no payout in four months is 3–7%; a bad
four months costs ~$1,000–1,500 at the 10th percentile and ~$2,600 at worst. Caveats as before: start dates
overlap heavily (~16 independent windows per history), the edge is zero, and the real drift (§110: MNQ window
+0.35) is not counted.

## 113. A13: size as part of the policy fails everywhere; a stuck-account defect found and fixed (S8)

**No trial spent; N 766. Computation record m00162** (`reports/a13_size_policy.json`,
`reporting/a13_size_policy.py`).

**Design, fixed before running:** the staking game re-solved over (take, stop, contracts) — MNQ 2–6, MGC 4–12;
W ∈ {1,2,3,4,6,8,10,12,15,20,30}, L ∈ {2,4,5,6,8,10} ($100) — with each action's net outcome distribution
measured on real sessions (stops at the stop price), learned on one history and tested on the other in both
directions; adopted only if it beats the fixed-size fair-odds policy on mean net AND P(payout) in both.

| learned → tested (84 days, replay) | fixed size, fair odds | size-aware | size-aware, in sample |
|---|---|---|---|
| MNQ 2015–20 → 2021–26 | 79% +$1,148 | 44% +$934 | 56% +$1,011 |
| MNQ 2021–26 → 2015–20 | 70% +$1,627 | 46% +$339 | 55% +$937 |
| MGC 2011–20 → 2021–26 | 77% +$2,016 | 24% −$81 | 55% +$2,225 |
| MGC 2021–26 → 2011–20 | 73% +$2,392 | 42% +$325 | 52% +$943 |

**Not adopted on either product.** It is worse even in sample, so the fault is the approach, not only the regime:
as in A05 (§102), outcome tables measured from 1-minute bars mislead the solver — a tight bracket whose levels
are both touched inside one fast minute is booked as a stop (W=1/L=2 at 4 MNQ: take 53% vs ~64% fair), so it
avoids the small end-game brackets the fair-odds policy depends on. **The fair-coin policy at a fixed,
risk-matched size (4 MNQ, 8 MGC) stays.**

**A defect found on the way, and its reach.** With stops filling exactly at their price, a stop capped one dollar
above the floor leaves the account at floor + $1 — a state the A13 solver gives no action, so its replay held
the account untraded for ever (no fail, no new evaluation). Fixed in `a02_real.sequential` and A13 (an
untradable account is finished and replaced, the playbook's rule, §108) and in `a10_forward.walk`. **Reach:
none on recorded results** — A03 reproduces exactly (60.6%, +$674.7), and A10b, A11 and A12 rerun to
byte-identical reports (the fair-odds policy always has an action); A10's forward log changes only in labels
(five "FAILED on a $9–27 trade" days become "FINISHED at the floor", same outcomes and nets).

## 114. Scaling: parallel streams on one market multiply the bet, not the odds — breadth is the lever (S8)

**No trial spent; N 766. Computation record m00163** (`reports/a12_joint.json` → `parallel_pairs`;
`a12_joint.scale`). The user needs more than one payout in four months; Tradeify does not limit evaluation
purchases. k parallel pairs (1 MNQ + 1 MGC stream each), pair i started i trading days after the first, each
run back-to-back in real order for 84 trading days; the sum over pairs, from every first start date:

| k pairs | fees | mean net | P(net > 0) | 10th pct | worst |
|---|---|---|---|---|---|
| 1 | $1.8–2.1k | +$3.4–4.4k | 72–80% | −$1.0–1.4k | −$2.6k |
| 5 | $8.8–10.5k | +$16.8–21.7k | 74–82% | −$4.9–6.6k | −$12.6k |
| 10 | $17.7–21.0k | +$33.7–43.1k | 75–82% | −$8.9–11.3k | −$23.7k |
| 20 | $35.4–42.0k | +$67.7–85.1k | 75–83% | −$14.2–17.4k | −$45.2k |

(ranges: 2021–26 and 2016–20 histories.) **Expected net scales linearly; the odds do not move.** Streams on the
same market trade the same days with similar brackets, so they win and lose together: k pairs is one bet k
times larger, and the worst case grows with it. **Breadth — the same staking on markets that do not move
together (MNQ–MGC daily correlation +0.06) — is what raises P(net > 0).** Candidate micros (each needs 1-minute
data and its own window check, as gold had): MCL, MHG, M6E, SIL, M2K (partly correlated with MNQ). Open with
the user: Tradeify's cap on simultaneous FUNDED accounts, and whether copying one plan across accounts is allowed.

## 115. Breadth on a budget: crude is the third market; hourly candles are enough with the OHLC rule (S2, S8)

**No trial spent; N 766.** The user can hold 5 funded Tradeify accounts at once and may copy one plan across
accounts; the tradable list is broad (CME equity, FX, energy, metals, grains, livestock; Eurex). Minute data for
six candidates was quoted at $668, and for two continuous series still $549 — too expensive.

**Correlations from data already owned** (`data/raw_daily`, roll-correct daily returns, 2021–26 / 2016–20):
crude vs Nasdaq **+0.04** / +0.23, vs gold **+0.06** / +0.01; copper +0.35 / +0.43 against Nasdaq / gold
(2021–26); the euro +0.41 against gold. **Crude is the clear third account** (one CL ≈ $2,500 daily SD, so ~2 CL
or 15–20 MCL); copper and the euro add little; natural gas (not in the file) is the likely fourth.

**Hourly candles, tested on MNQ and MGC** (`reporting/a14_coarse_bars.py`): minute paths rebuilt as 30-minute
and 1-hour candles. A plain tie rule spans $500–$5,000 of mean net (pessimistic vs optimistic) — unusable. With
the **OHLC path rule** (open nearer the high → high first; open = previous bar's close):

| mean net, block bootstrap | 1-minute | 30-minute | 1-hour |
|---|---|---|---|
| MNQ 2021–26 / 2015–20 | +$1,317 / +$1,685 | +$1,116 / +$1,508 | +$1,422 / +$1,523 |
| MGC 2021–26 / 2011–20 | +$2,031 / +$2,419 | +$1,870 / +$2,112 | +$1,819 / +$2,074 |

**Hourly is within ~10–15% of the minute answer, slightly conservative in 3 of 4** — enough to decide whether a
market works and at what size. Databento has 1-hour but no 30-minute schema. Proposed order: `ohlcv-1h`,
`CL.v.0` and `NG.v.0`, continuous symbology, 2010-06-06 → 2026-10-10.

## 116. A15: crude from owned daily bars — a weak but independent third account; the 5-funded cap bounds scale (S8)

**No trial spent; N 766. Computation record m00164** (`reports/a15_crude.json`, `reporting/a15_crude.py`).
Hourly crude data still cost >$100 (Databento's per-GB price for 1h exceeds 1m's), so crude is built from the
**owned** ohlcv-1d file: one bar per session, the OHLC path rule for a bar touching both levels, window the whole
session (18:00→16:55, permitted). **Checked first** on MNQ and MGC full sessions against 1-minute paths: one bar a
day lands within ~±30% on mean net and ~5 points on P(payout) (hourly ~10–15%) — a go/no-go tool, not a precise one.
Further approximation: UTC-day bars, not exact sessions (0.97, §74).

**Crude alone** (P(payout) / mean net, replay; 2016–20 · 2021–26): 5 MCL 18% −$235 · 26% −$11; **10 MCL 55% +$545 ·
45% +$397**; 15 MCL 61% +$1,105 · 50% +$487; 20 MCL 74% +$1,188 · 50% +$518; 30 MCL 81% +$3,513 · 60% +$775.
The size was fixed by the risk-matching rule before looking (one MCL's daily SD ≈ $250 → 10 MCL ≈ 4 MNQ's $2,800).
Larger looks better in both histories, but that is seen after the fact and within the method's error; not adopted.

**Three accounts together** (4 MNQ RTH + 8 MGC London + 10 MCL session; same start dates, real order, 84 days):

| | 2016-01 → 2020-08 (997 starts) | 2021-01 → 2026-04 (1,214) |
|---|---|---|
| P(at least one payout) | 98.6% | 99.9% |
| streams with a payout, mean | 2.0 of 3 | 2.0 of 3 |
| mean / median net | +$4,910 / +$3,491 | +$3,739 / +$2,977 |
| P(net > 0) — three markets (two) | **81%** (72%) | **78%** (79%) |
| 10th percentile / worst | −$1,000 / −$3,360 | −$1,300 / −$3,120 |
| fees | $2,539 | $3,001 |
| net correlations MNQ–MGC, MNQ–CL, MGC–CL | +0.25, −0.12, −0.31 | −0.17, −0.02, −0.19 |

**What scale is available.** Each stream holds at most one funded account, and the user's firm allows five funded
at once — so parallel copies (§114) are capped too: **about five streams in total**. At zero edge that bounds the
plan near five streams × ~$1–2k per four months. Raising it needs a real edge (none found), funded accounts that
survive to uncapped "live" payouts (the policy already maximises this), or **more firms**: each firm has its own
cap, and §92 priced eleven account types — the same staking, re-solved per firm's rules, multiplies the slots.

## 117. Z08 registered — commercial hedgers' weekly flow (CFTC COT) as the commodity brackets' direction (S1–S5)

**No trial spent at registration; N 766.** The user stays with Tradeify and wants a real edge (#3). Lesson of
Z06/Z07: on MNQ a signal must beat a drift-earning long; on gold and crude the long earns little, and §109 shows
gold gains most per unit of edge — so the search turns to commodity direction. Not previously tested (the
X-series cites hedging pressure only as trend/carry's mechanism).

**Source:** Kang, Rouwenhorst & Tang (2020, JF 75(1)), 26 commodities incl. gold and crude, 1994-01 → 2014-11:
weekly position changes are driven by impatient speculators; commercials supply liquidity, and prices rise the
week after hedgers BUY (a typical change moves next week's expected return ~0.17%; t 4–5 in both halves). A 2023
retest (Maréchal, J. Futures Markets 43(5)) exists; its findings could not be read.

**Size screen inside the paper's sample only** (2010-06 → 2014-11, owned daily bars; COT legacy files from the
CFTC, free, `data/cot/`): crude Sharpe **+0.70** (always-long +0.04; +7.6 bps after hedger buying, −6.5 after
selling); gold +0.24 (always-long −0.06). MGC minute sessions are sparse before 2016 (56–86 a year), so gold's
screen used daily GC.

**Fixed before any post-2014 return** (`hypotheses.yaml` Z08; `data/cot.py`, `signals/z08.py`,
`signals/z08_trial.py`): Q = weekly change in commercial net long / previous open interest; the five sessions
of the week after the Friday release take sign(Q). Crude: the full session (daily CL bars, the window of §116);
gold: London 03:00–11:30 (MGC minute, real returns). 2015-01-01 → 2026-08-27. Per product, CONFIRM only if
Sharpe > 0, it beats always-long, and posterior > 0. Prior Normal(0.3, 0.3), an assumption.

**Outcome injection** (`reports/z08_injection.json`): 0.3 planted, recovered 0.301 for both (crude 2,864
sessions, SD 0.29; gold 2,578, SD 0.30); P(estimate > 0) 84%.

### Z08 run: gold confirmed, marginally and unstably; crude rejected (S6–S8)

**One trial spent: t00773. N 766 → 767.** `reports/z08_trial.{json,md}`.

| 2015 → 2026-08 | MGC, London 03:00–11:30 (2,578 sessions) | MCL, session (2,864) |
|---|---|---|
| **Sharpe, hedger-flow sign × window** | **+0.42** | +0.17 |
| Sharpe, always long (must beat) | +0.36 | +0.23 |
| mean after hedger buying / selling | +3.77 / −0.30 bps | +6.79 / +1.14 bps |
| by period, signal / long | 2015–20 −0.08 / +0.74; 2021–26 **+0.79** / +0.09 | 2015–20 +0.03 / −0.13; 2021–26 +0.36 / +0.71 |
| posterior | +0.36 ± 0.21 | +0.23 ± 0.21 |
| decision | **CONFIRM** | REJECT (condition 2) |

**Gold is confirmed under the user's rule but should be read as marginal:** it beats always-long by 0.3 bps a
session overall, the two eras disagree in sign, and the full-session daily check (not decisive) does not beat
always-long (+0.39 vs +0.59). Its value to the plan, by §109, is of order +$500–900 per four months at the
posterior against a zero-drift long — and roughly nothing against a gold that keeps rallying. **Crude repeats
Z06/Z07's pattern:** the ranking is right, but the "sell" weeks still rose, so shorting them gives up the drift.

**Adopted:** the gold account takes the weekly COT direction — `python -m futuresres.signals.z08 --direction`
(refreshes this year's CFTC file; prints the side for the coming week) then `a06_playbook --product MGC --side
long|short` (a mirrored bracket; the policy is symmetric at zero edge). Crude and MNQ stay long. First reading:
positions of 2026-10-06 (released 10-09), commercials +1.58% of open interest → long gold, sessions 10-12 → 10-16.

## 118. A16: the portfolio with gold's COT direction — P(net > 0) 85–87%, bad case roughly halved (S8)

**No trial spent; N 767.** `reporting/a16_portfolio.py` (prints; figures here). Three Tradeify accounts — 4 MNQ
09:30–16:00 long, 8 MGC London with Z08's weekly direction, 10 MCL session long — with gold's edge planted at Z08's
**posterior** Sharpe 0.36 (as A11; not the in-sample result), real order, stops at the stop price, 84 days:

| 2021–26 / 2016–20 | gold always long, zero edge | **gold with COT direction (posterior 0.36)** |
|---|---|---|
| gold alone: P(payout) / mean net | 77% +$2,210 / 76% +$2,662 | **81% +$3,261 / 88% +$3,182** |
| three accounts: P(≥1 payout) | 99.9% / 98.6% | 99.9% / 100% |
| streams paying, mean | 2.01 / 2.02 | 2.05 / 2.14 |
| paid out / fees | $6,740 / $3,001 · $7,449 / $2,539 | $7,755 / $2,966 · $7,932 / $2,502 |
| mean / median net | +$3,739 / +$2,977 · +$4,910 / +$3,491 | **+$4,789 / +$4,240 · +$5,431 / +$4,119** |
| P(net > 0) | 78% / 81% | **87% / 85%** |
| 10th percentile / worst | −$1,300 / −$3,120 · −$1,000 / −$3,360 | **−$470 / −$3,120 · −$785 / −$2,364** |

The gain is +$520–1,050 per four months on the mean and, more usefully, a bad four months roughly halved.
Caveats: the edge is Z08's marginal, era-unstable confirmation (§117); MCL rests on one-bar-a-day estimates (±30%);
the starts overlap (~16 independent windows per history).

## 119. The strict Z rule, adopted before any further candidate; Z08's gold result does not survive it (S2, S8)

**No trial spent; N 767.** `signals/z_strict.py`, `reports/z_strict_review.json` (descriptive re-reading of used
test data — no new trial). The user asked whether the Z-series ran "as vigorously as before". It did not: the Z
rule (§86) confirms on test-window Sharpe > 0 and a positive posterior — a bar a null signal clears roughly a
quarter to half the time — with no multiple-testing deflation (it replaced SR\*), few placebo nulls and no
second-instrument confirmation. **At the user's direction, from here on a direction signal confirms for a market
only if ALL hold:** (1) it beats the plan's current always-long with one-sided **t > 1.645** on the per-session
difference d = s·r − r; (2) mean(d) exceeds the **95th percentile** of the same statistic with the signal circularly
shifted (≥ 20 sessions, every 5th); (3) posterior > 0 under the registered prior, reported beside a zero-mean
prior; (4) the result is reported against the running count of Z market-tests (8 so far; 0.4 chance passes
expected at 5%).

**Z06–Z08 re-read under it:**

| test | t, beats long (> 1.645) | placebo pct (≥ 95) | Sharpe | posterior: registered / zero prior | strict |
|---|---|---|---|---|---|
| Z06 MNQ | -1.98 | 0 | -0.17 | +0.02 / -0.08 | no |
| Z06 MGC | -1.22 | 14 | -0.25 | -0.03 / -0.13 | no |
| Z07 MNQ | -0.60 | 68 | +0.09 | +0.20 / +0.04 | no |
| Z08 MCL | -0.14 | 68 | +0.17 | +0.24 / +0.09 | no |
| Z08 MGC | +0.15 | 89 | +0.42 | +0.36 / +0.20 | no |

**Z08's gold "confirmation" does not survive:** its +0.42 was gold's drift (always-long +0.36), not the signal —
the advantage over always-long has t +0.15. **Z08 retired; the gold account returns to always-long** (playbook
default; the weekly `--direction` step is dropped). **§118's improvement is withdrawn**: it planted Z08's posterior
as an edge over a zero-drift long, which the evidence does not support. **The portfolio stands at its zero-edge
figures (§116): +$3.7–4.9k mean net per four months, P(net > 0) 78–81%.** Z02 (98.4% of its rotation null) is the
one prior confirmation of placebo strength; Z05 (Welch t 1.82, 2021–26 only) predates the rule and is not used.

## 120. Searching under the strict rule: Z02 as MNQ direction (descriptive); Z09 — index roll selling — registered (S1–S5)

**No trial spent at registration; N 767.** Recent literature on daily predictability of crude and gold is thin and
mostly negative (oil predictability largely an averaging artefact — Conlon, Cotter & Eyiah-Donkor; gold: weak
or preprint-only); nothing new for index futures beyond intraday momentum (§103).

**Z02 as the MNQ bracket's direction — descriptive, a second look, no trial.** The one programme result of placebo
strength. Its sign set the 09:30–16:00 direction (long when the weight is ≥ 0): in the paper's sample (2015-11 →
2023-03) Sharpe +0.57 vs always-long +0.40, placebo 100th pct, **t(beats long) +0.32**; in Z02's own test window
(2023-03 → 2026-08, already used) +0.83 vs +0.25, placebo 99th, **t +0.72**. Its timing is real against shifted
versions, but it is short 75–79% of days against an equity drift, so its advantage over always-long is too noisy
to pass the strict rule. Not adopted.

**Z09 registered** (`hypotheses.yaml` Z09; `signals/z09.py`, `signals/z09_trial.py`). Mou (2011): GSCI funds sell
the next-to-expire crude contract on the 5th–9th business days; set aside in §98–§99 only as a SPREAD. The outright
is allowed: the crude plan shorts on trading days 5–9 and is long otherwise. **Construction check before any
return:** on 99.5% of roll days the volume-front contract our daily series holds is the one the GSCI sells (100%
every year but 2020's 92%). All owned data (2010-06 on) postdates the paper. Strict rule; prior Normal(0.2, 0.3), an
assumption. `tests/test_registry_consistency.py`: MCL added to the single-market primaries (crude is a plan
instrument since §116).

**Outcome injection** (`reports/z09_injection.json`): the first run FAILED — the plant had the wrong sign (roll days
higher); caught by recovery (−0.04 for +0.2) and fixed to e = noise + s·μ. Rerun: 0.2 planted, recovered 0.208
(SD 0.24, 3,993 sessions). **Power under the strict rule at the prior's size is only 10%** (P(Sharpe > 0) 79%): this
test can confirm a large roll effect, not a small one — recorded before the run.

### Z09 run: rejected — the roll effect held to 2020 and reversed after (S6–S8)

**One trial spent: t00774. N 767 → 768.** `reports/z09_trial.{json,md}`. Strict rule, 9th Z market-test (0.45 chance
passes expected at 5%).

| 2010-06 → 2026-08 (3,993 sessions; 970 on roll days) | |
|---|---|
| crude, roll days (5th–9th) / other days | +1.59 / +2.33 bps |
| **t, advantage over always-long** (> 1.645) | **−0.20** |
| **placebo percentile** (≥ 95) | **52.5** |
| posterior (registered / zero prior) | +0.13 / +0.05 |
| by period, roll / other bps (t) | 2010–15 −15.8 / −2.4 (+1.66); 2016–20 −20.9 / +7.9 (+1.28); 2021–26 **+38.2** / +2.1 (**−2.63**) |

**REJECTED.** The roll pressure was visible through 2020 — near the bar in each half-decade — and reversed sharply
after 2021, the signature of an effect that has been front-run. No shifted-window variant is run after seeing this.

## 121. A power screen before registering, and four more candidates screened out under the strict rule (S1, S2)

**No trial spent; N 768.** `signals/z_strict.power` — the strict rule's chance of passing condition (1) if a
candidate's published effect is exactly right (the placebo and posterior can only lower it). Run on the plans'
own scales (MNQ 09:30–16:00: always-long +2.5 bps, SD ~120 bps, ~2,600 sessions; gold: SD ~100 bps, ~2,500):

| case | expected t | power |
|---|---|---|
| MNQ short on 1/4 of days averaging −1.3 bps | 0.28 | 8% |
| ... averaging −10 bps | 2.08 | 66% |
| ... averaging −20 bps | 4.11 | ~100% |
| gold 50/50 signal at ±3 bps | 1.06 | 28% |
| gold 50/50 signal at ±5 bps | 1.76 | 55% |

**A candidate is registered only if its published effect gives meaningful power** — in practice ~5–10 bps a day or
more on the days it acts. This keeps trials off candidates that cannot pass even if the paper is right.

**Screened out:**
- **Dash for cash** (Etula, Rinne, Suominen & Vaittinen, RFS 33(1) 2020; working paper 1980–2014): institutions sell
  T−8..T−4 before the last month-end settlement day (T = last trading day; the window would shift with the US move to
  T+2 in 2017 and T+1 in 2024). The selling window earns −3.4% annualised on the S&P (−1.3 bps a day) against +28.6%
  over T−3..T+3: as MNQ's short days, **power 8%**. Out on size.
- **Rebalancing pressure** (EDHEC-hosted SSRN 5122748: −17 bps next day when funds are overweight equities): the same
  work as Z02 (§120 covers Z02 as MNQ direction).
- **Gold ETF flow pressure:** only a thesis (short-lag VAR, reversing at 3–5 days); no peer-reviewed effect to fix.
- **Post-options-expiration weakness ("vanna/charm"):** practitioner commentary only; the peer-reviewed findings are
  expiration-week strength (Johnson & So 2013) and pinning (Ni, Pearson & Poteshman 2005).

## 122. Z10 registered — gotobi importers' dollar buying into the Tokyo fix, on free spot data (S1–S5)

**No trial spent at registration; N 768.** The user chose to keep screening (option 1), then asked for yen data. The
Databento portal refused every yen request (continuous symbology "no data"; parent symbology not found in the UI),
so the test uses **free USD/JPY spot 1-minute bars** (HistData.com, 2016-01 → 2026-09, `data/fx_histdata/`, gitignored;
`data/fx.py` keeps only the three minutes needed, one file at a time). 6J futures mirror the spot rate inversely.

**Source and mechanism:** arXiv 2301.13204 (Suzuki group; 2018–2020, building on their earlier study) — USD/JPY rises
into the 9:55 JST TTM fix on days divisible by five, as banks pre-buy dollars for importers' "goto-barai" settlements;
the Tokyo fixing is studied in Ito & Yamada (2017, J. International Economics). **Evidence is thinner than the
programme's usual** (a 4-page preprint), and the preprint itself says the effect is widely known.

**The account constraint fixes the window:** the paper enters at 03:00 JST (13:00–14:00 ET), which holds through the
17:00–18:00 ET CME break the account forbids. The tradable part — the 18:00 ET reopen to 9:55 JST — is fixed here.

**Screen inside the paper's sample only** (and before it): 2018–20, the paper's window +2.68 bps (SD 18.9, t 1.91, win
63%; 181 events vs the paper's 185); **the tradable window +2.67 bps (SD 12.4, t 2.88, win 64%)**; non-gotobi days −1.1
to −1.6. **2016–17: −0.94 bps (t −0.56)** — absent before the paper's sample; a warning recorded before the run.
Dollar scale: one 6J ≈ $84k notional, so +2.7 bps ≈ $22 gross, ~$14 after the 1 bp cost; at 3 contracts ~$40 per event,
~70 events a year — a small, high-consistency add-on, not a new engine.

**Fixed before any 2021–2026 return** (`hypotheses.yaml` Z10; `signals/z10.py`, `signals/z10_trial.py`): long USD/JPY
18:00 ET → 9:55 JST on gotobi days (the 5th…30th or the last business day before a weekend one; Tue–Fri JST),
net of 1.0 bp; 2021-01-01 → 2026-09-30. **The strict rule for a standalone trade:** net mean t > 1.645; at or above the
95th percentile of BOTH the calendar shifted ±1–4 business days and random same-size non-gotobi sets; posterior > 0
(prior Normal(+0.8 bp, 1.0), an assumption); reported as the 10th Z market-test. 6J added to the registry's
single-market primaries.

**Outcome injection** (`reports/z10_injection.json`): +0.8 bp planted, recovered 0.81 (SD 0.84, 316 events); **power of the
strict t at the prior's size 24.5%** (roughly 70% if the full in-sample size holds).

### Z10 run: rejected — half the in-sample size, then gone (S6–S8)

**One trial spent: t00775. N 768 → 769.** `reports/z10_trial.{json,md}`. 10th Z market-test.

| 2021-01 → 2026-09, 316 gotobi events, 18:00 ET → 9:55 JST | |
|---|---|
| gross / net mean (SD) | +1.49 / **+0.49 bps** (13.0) |
| **t, net** (> 1.645) | **+0.67** |
| placebo: random non-gotobi sets / calendar shifted ±1–4 days (≥ 95) | 92.8th / 50th |
| net, 2021–23 / 2024–26 | +0.87 (t 0.88) / **+0.10** (t 0.09) |
| non-gotobi days, same window; the paper's 03:00 JST window (not tradable) | +0.56; +2.15 bps gross |

**REJECTED.** The effect came in at about half its 2018–20 size and has been near zero since 2024: a well-known flow
anomaly competed away, as Z09's roll was. Data cost: nothing (free spot data).

**Ten Z market-tests under the strict rule (Z02–Z10), none passing it.** The pattern across Z04, Z06–Z10: published
effects are either too small for the strict bar at our sample sizes (§121's power screen) or front-run after
publication (Z09, Z10). Z02 alone has placebo-strength timing, and it cannot beat an always-long equity plan.

## 123. A Discord bot for the demo: scheduled tickets, account bookkeeping, the demo log (S8)

**No trial spent; N 769.** `bot/` (`futures_bot.py`, `ticket.py`, `accounts.py`, `policy.json`, systemd unit, README);
`a06_playbook export` writes `bot/policy.json`; `tests/test_bot_ticket.py`. The user wants callouts in Discord from a
DigitalOcean droplet already running another bot, without keeping the laptop on.

- **Light by design:** the solved policy is exported once (271 KB JSON) and `ticket.py` reproduces
  `a06_playbook.ticket` in plain Python — no numpy or solver on the droplet; `discord.py` only; systemd caps it at 200 MB.
- **Checked:** the bot's ticket equals the playbook's on 3,000 random states (eval and funded, all three products,
  stops near the floor, finished accounts); the bookkeeping (pass with the 40% rule, funded lock and payout cap, floor
  breach, new evaluation) is unit-tested.
- **Schedule (New York time):** MGC 02:55 Mon–Fri, MNQ 09:25 Mon–Fri, MCL 17:55 Sun–Thu, end-of-day reminder 17:05.
  The user reports closing balances with `!eod`; payouts, new evaluations and corrections by command; every event is
  appended to `demo_log.csv` for the backtest comparison.
- **Not automated:** orders are still placed by hand (automated execution needs the firm's permission first).

## 124. A 9 PM schedule: entering everything at 9 PM ET is clearly weaker than the current windows (S8)

**No trial spent; N 769.** Scratch computations (`a01`/`a02`/`a08`/`a12`/`a15` machinery; figures here). The user's work
schedule allows notifications only around 9 PM ET. Two routes: keep the windows and pre-place time-triggered orders
(platform-dependent), or move every entry to 9 PM ET, held to 16:55 the next day (bracket or flatten).

**The 9 PM window (21:00 → 16:55), zero edge, stops at the stop price, risk-matched sizes** (swing ≈ $2.8–3.1k → 3 MNQ,
6 MGC; crude unchanged, its daily-bar estimate already covers the session):

| 84 days, block bootstrap (replay similar) | current window | 9 PM entry |
|---|---|---|
| MNQ, 2021–26 / 2015–20 | 4 MNQ 71% +$1,317 / 65% +$1,685 | 3 MNQ 62% +$1,471 / 50% +$468 |
| MGC, 2021–26 / 2011–20 | 8 MGC 76% +$2,031 / 76% +$2,419 | 6 MGC 68% +$1,998 / 64% +$1,847 |

| three accounts together | current (2021–26 · 2016–20) | all at 9 PM |
|---|---|---|
| P(≥1 payout) | 99.9% · 98.6% | 89.0% · 86.4% |
| mean / median net | +$3,739 / +$2,977 · +$4,910 / +$3,491 | +$4,158 / +$2,983 · +$2,422 / +$1,599 |
| P(net > 0) | 78% · 81% | **67% · 64%** |
| 10th percentile / worst | −$1,300 / −$3,120 · −$1,000 / −$3,360 | **−$2,960 / −$3,520 · −$2,160 / −$3,440** |

**Weaker, chiefly in the tail:** P(net > 0) falls ~13–17 points and the 10th percentile roughly doubles — plausibly
because three long windows sharing the same overnight move are more correlated than the current staggered ones.
Preferred: keep the current windows with time-triggered entries and exits, if the user's platform supports them;
otherwise the 9 PM plan at these figures. Awaiting the user's platform.

## 125. The bot on the user's schedule: one 17:30 ET alert, manual trading, every ticket shadow-tracked (S8)

**No trial spent; N 769.** `bot/schedule.py`, `bot/shadow.py`, `bot/futures_bot.py` rewritten; tests extended. Tradovate has
no scheduled market entry and TradingView only SENDS webhooks (a bridge with Tradovate access would be needed to place
orders); the user chose manual trading with one alert at 17:30 ET, which lets crude keep its 18:00 entry (§116) — an
interim move of crude to 21:00 was reverted before anything used it.

- **The 17:30 alert (Sun–Thu):** results of finished tickets; any closing balance not yet recorded (a balance sent later
  reissues that ticket); then crude 18:00 tonight → 16:55, gold 03:00 → 11:30 and MNQ 09:30 → 16:00 tomorrow. Friday:
  results only. The alert date is persisted, so a restart cannot post twice.
- **Shadow tracking:** every ticket, traded or not, is simulated after its window on free Yahoo 1-minute bars (NQ=F,
  GC=F, CL=F) by the backtests' rules (entry at the entry minute's open; take/stop at their prices; a minute touching
  both = stop; else the exit-time close; commissions) and appended to `shadow_log.csv`; `!took` / `!skipped` mark it.
  **Validated** against the programme's Databento data for 2026-10-06..09: all 8 MNQ and MGC outcomes identical (take,
  stop, time exit), P&L equal but for one tick on a time exit, entry prices within 1–3 ticks.
- Tests: the schedule's windows (a Sunday alert yields MCL Sun 18:00 → Mon 16:55, MGC Mon 03:00 → 11:30, MNQ Mon
  09:30 → 16:00), tracking with a fake feed, results reported once, Friday without tickets.

## 126. A18: the demo checker — and the six unseen weeks already match the backtest's outcome mix (S8)

**No trial spent; N 769.** `reporting/a18_demo_check.py`. The bot is deployed on the user's droplet (34 MB, systemd,
clock synced) and the demo starts 2026-10-11. For every finished ticket in the bot's shadow log the checker computes,
on 2021–26 history (A07/A08 paths, drift removed, stops at the stop price, a minute touching both = stop; crude by the
one-bar approximation), the probability that THAT bracket ends in a take, a stop or a time exit and its expected net
P&L; it then compares the live counts (chi-square, three cells) and P&L (z against the summed expectation), and with
`demo_log.csv` measures the execution gap on traded tickets (closing-balance change vs shadow P&L).

**First run, on the forward check's 55 MNQ and MGC tickets (2026-08-28 → 10-09, data no backtest had seen):**
observed take / stop / time exit **26 / 27 / 2 against 23.9 / 29.0 / 2.1 expected** (chi-square 0.32, p ≈ 0.85); shadow P&L
−$4,177 against −$1,543 ± $7,015 (z −0.38). The live outcome mix is what history predicts.

## 127. Z11 registered — month-end FX hedge rebalancing at the London 4 p.m. fix (EUR/USD), on free data (S1–S5)

**No trial spent at registration; N 769.** The user asked to keep searching and, when the literature runs out, to build
hypotheses from data. This one is from the literature: Melvin & Prins (2015, Journal of Financial Markets 22; 10
currencies, 2004-04 to 2012-12) — international equity managers reset currency hedges at the month-end WM/Reuters 4 p.m.
fix, so a country's equity outperformance over the month predicts its currency's fall in the hour before the fix
(panel slope −0.0142: 10% → 14 bps; R² 0.03). A forced, scheduled flow, like Z02's.

**Data, free** (HistData 1-minute; `data/fx_fix.py`, one file at a time): EUR/USD and GBP/USD spot; S&P 500, FTSE 100 and
DAX index CFDs (the DAX stands in for the Eurozone market; HistData's Euro Stoxx 50 stops in 2019).

**Screen inside the paper's sample only** (2010-11 → 2012-12, 26 month-ends each): **EUR/USD +11.09 bps per event, t +3.19,
win 81%** (slope +1.90 bps per 1% of S&P − DAX, the predicted sign); **GBP/USD −5.68 bps, t −1.41, win 31%** — the wrong
sign; GBP is dropped and not tested (recorded; it counts against the strict rule's running total).

**Fixed before any 2013–2026 return** (`hypotheses.yaml` Z11; `signals/z11.py`, `signals/z11_trial.py`): on the last weekday
of each month, 15:00 → 16:00 London (10:00–11:00 ET most of the year), long EUR/USD (6E) if the S&P 500 beat the DAX from
the first to the second-last trading day, short otherwise; net of 1.0 bp; 2013-01 → 2026-09. Strict rule: net t > 1.645;
at or above the 95th percentile of BOTH the same signed trade on the 5 weekdays before month-end and the signal permuted
across months; posterior > 0 (prior Normal(+3, 3) bps, an assumption, shaded for the 2015 fix reform); 11th Z test.

**Outcome injection** (`reports/z11_injection.json`): +3 bps planted, recovered 3.03 (SD 1.16, 158 events); power of the
strict t at that size 82%.

### Z11 run: rejected — strong in 2010–12, gone since 2013 (S6–S8)

**One trial spent: t00776. N 769 → 770.** `reports/z11_trial.{json,md}`. 11th Z market-test; power 82% at the prior's size.

| 2013-01 → 2026-09, 158 month-ends | |
|---|---|
| gross / net per event (SD) | **−0.92 / −1.92 bps** (17.9) |
| t, net (> 1.645) | −1.34 |
| slope on S&P − DAX | +0.05 bps per 1% (in-sample 2010–12: +1.90) |
| placebos: 5 weekdays before / permuted signal (≥ 95) | 20th / 30th pct |
| 2013–19 / 2020–26 net | −0.19 / −3.88 bps |

**REJECTED.** The hedging-channel effect was clear in the paper's years and our 2010–12 slice and has been absent since —
published in 2013 (working paper), and the WM/Reuters fix window was widened from one minute to five in February 2015.
Data cost: nothing.

## 128. Z12 registered — the euro weakens in European hours and strengthens in US hours (S1–S5)

**No trial spent at registration; N 770.** One more documented FX effect before building our own hypotheses, chosen
because it acts every day (≈ 4,200 observations, not ≈ 160): Breedon & Ranaldo (2013, JMCB; EBS 1997-01 → 2007-06; also
Cornett et al. 1995, Ranaldo 2009) — currencies depreciate in their own trading hours, as local participants are net buyers
of foreign currency then; for EUR/USD a simple short-in-European-hours / long-in-US-hours strategy earned **after-cost
Sharpe ratios of 1.3 (morning short) and 0.9 (afternoon long)**. Sessions per their Table 1: Europe 07:00–15:00 London,
US 08:00–16:00 New York.

**Fixed before any return** (`hypotheses.yaml` Z12; `signals/z12.py`, `signals/z12_trial.py`; `data/fx_fix.hourly_utc`,
102,744 hourly EUR/USD prices 2010–2026): every New York weekday, SHORT 07:00 London → 08:00 New York, LONG 08:00 → 16:00
New York — the paper's "open-to-open / open-to-close" read without the 08:00–10:00 overlap (the account cannot be long and
short at once; a READING fixed in advance); 0.8 bp per leg; 2010-01-04 → 2026-09-30 (entirely after the paper). No
in-sample screen is possible (the free data starts in 2010). Strict rule: daily net t > 1.645; at or above the 95th
percentile of the same schedule shifted by each of the other 23 hours; posterior > 0 (prior annual net Sharpe
Normal(0.6, 0.4), an assumption); 12th Z test.

**Outcome injection** (`reports/z12_injection.json`): net Sharpe 0.6 planted, recovered 0.599 (SD 0.24, 4,231 days); power of
the strict t 80%.

### Z12 run: rejected — real gross, eaten by costs, decayed after 2017 (S6–S8)

**One trial spent: t00777. N 770 → 771.** `reports/z12_trial.{json,md}`. 12th Z market-test; power 80%.

| 2010-01 → 2026-09, 4,231 weekdays | |
|---|---|
| morning short / afternoon long, gross | +1.26 / +0.40 bps |
| day net of 1.6 bps (SD) | **+0.06 bps** (47.6) |
| t / annual net Sharpe | **+0.09** / +0.02 |
| placebo: schedule shifted by each other hour | 87th pct |
| 2010–17 / 2018–26 net (Sharpe) | +1.40 (+0.41) / **−1.18 (−0.45)** |

**REJECTED.** The direction the paper found still shows gross, but two round trips a day absorb it, and it has reversed
since 2018.

**Twelve strict-rule market-tests (Z02–Z12), none passing.** Every forced-flow and calendar effect tested since §86 was
stronger in its paper's years than after: the shared failure is publication and arbitrage, not the tests. The literature
route is now exhausted for the user's markets; the next step is hypotheses of our own on untouched data (§129).

## 129. The D-series protocol: hypotheses of our own, discovered on 2010–17, validated once on sealed 2018–26 (S1)

**No trial spent; N 771. Written and committed BEFORE any discovery scan.** The literature route is exhausted for the
user's markets (§128: twelve strict-rule tests, none passing). At the user's direction, hypotheses are now generated from
data. The programme's earlier data-driven series (F, L, N, P, Q; ~760 trials) found nothing, and the common failure of
data-driven search is testing ideas on the data that suggested them. This protocol prevents that:

1. **Universe — markets this programme has not examined**, free HistData 1-minute, each tradable in the user's account:
   GBP/USD (6B), AUD/USD (6A), USD/CAD (6C), USD/CHF (6S), DAX (FDAX), Nikkei 225 (NKD), silver (SI). Excluded: EUR/USD
   and USD/JPY (seen in Z10–Z12), and the S&P/Nasdaq/gold/crude futures this programme has searched since 2026-08.
2. **Discovery window 2010-01-01 → 2017-12-31 only.** The discovery code asserts that no row after 2017-12-31 is read.
3. **Two pattern families, fixed now:** (D-a) each UTC hour of the day, mean 1-hour return over all weekdays — 7 × 24 = 168
   tests; (D-b) each UTC hour on each weekday — 7 × 24 × 5 = 840 tests. 1,008 in all.
4. **Selection:** two-sided |t| > 4.1 (Bonferroni, 0.05 / 1,008) AND |mean| > 2 × the instrument's round-trip cost (FX
   0.8 bp; DAX and Nikkei 1.0 bp; silver 1.5 bp). **At most 5 candidates carried forward**, by |t|; a D-b candidate inside a
   carried D-a hour of the same instrument is dropped as a duplicate.
5. **Validation window 2018-01-01 → 2026-09-30, sealed until each candidate is registered.** One trial per candidate,
   STRICT rule for a standalone trade: net one-sided t > 1.645 in the discovered direction; at or above the 95th percentile of
   the same instrument's other 23 hours (D-a) or other hour-weekday cells (D-b); posterior > 0 with prior = the discovery
   mean halved; reported against the running count (Z and D market-tests together).
6. **If nothing passes selection, nothing is carried forward**, and that is the result.

## 130. D-series discovery (2010–17): seven cells pass, four carried, three dropped as untradable; D01 registered (S1–S5)

**No trial spent at registration; N 771.** `reporting/d_discovery.py`, `reports/d_discovery.json`. Seven markets (GBP/USD,
AUD/USD, USD/CAD, USD/CHF, DAX, Nikkei, silver; free HistData, whole-hour prices), 2010-01 → 2017-12 only (asserted).
**912 testable cells** (of 1,008: cells with fewer than 30 hours — closed index hours — drop out); **7 pass**
|t| > 4.1 and |mean| > 2 × cost; the protocol carries four:

| carried | discovery mean (SD), t |
|---|---|
| USD/CHF 21:00–22:00 UTC, all weekdays | −1.90 bps (10.8), −7.88 |
| **silver 11:00–12:00 UTC, all weekdays** | **−5.53 bps (33.7), −7.27** |
| AUD/USD 22:00–23:00 UTC, all weekdays | −1.62 bps (9.7), −6.56 |
| USD/CAD 22:00–23:00 UTC, Thursdays | +1.63 bps (5.6), +5.52 |

**Three dropped before any validation data was read — untradable, and probably not real.** 21:00–23:00 UTC is 17:00–19:00
New York (16:00–18:00 in winter): it covers CME's 17:00–18:00 ET daily break, when 6S / 6A / 6C do not trade and the account
may not hold, and it is the FX rollover, when spreads widen sharply. HistData's quotes are BID prices, so a spread blow-out
reads as a fall in the bid and its normalisation as a rise — the signs found (negative into rollover, positive out of it)
fit that artefact. **The protocol (§129) should have excluded the CME break window; it is added to it now** for any later
D-series scan. The decision used no 2018–2026 data.

**D01 registered** (`hypotheses.yaml` D01; `signals/d01.py`): short silver (SI) 11:00 → 12:00 UTC every weekday — the hour
ending at the 12:00 London silver fix in both summer and winter (an electronic auction since August 2014; the fix-dip
pattern is documented for the manipulation era); net of 1.5 bp (2.0 bp reported: SI's tick is ~1.7 bp). Validation 2018-01 →
2026-09, sealed until now; strict rule against silver's other 23 hours; prior Normal(+1.3, 1.5) bps net; 13th Z+D test.
The registry gains the D series and SI (`tests/test_registry_consistency.py`).

**Outcome injection** (`reports/d01_injection.json`, noise from silver's other hours only): +1.3 bps planted, recovered 1.34
(SD 0.94, 2,169 events); power of the strict t 39% at the prior's size, near 100% at the discovery size.

### D01 validation: rejected — the hour is still unusual, but too small after costs and fading (S6–S8)

**One trial spent: t00778. N 771 → 772.** `reports/d01_trial.{json,md}`. 13th Z+D market-test; power 39% at the prior's size.

| sealed 2018-01 → 2026-09, 2,169 weekdays | |
|---|---|
| short 11:00 → 12:00 UTC, gross (SD) | **+2.25 bps** (36.8) — discovery −5.53 for the long, i.e. +5.53 for the short |
| net at 1.5 bp / at 2.0 bp (t) | **+0.75 (t +0.95)** / +0.25 (t +0.32) |
| placebo: silver's other hours | **95th pct** (passes) |
| 2018–21 / 2022–26 net (t) | +2.04 (+1.91) / −0.38 (−0.33) |

**REJECTED** on condition (1). Unlike every Z test, the pattern itself survived out of sample — the hour into the London silver
fix is still silver's weakest — but at ~40% of its discovery size it does not cover SI's costs, and it was near zero after
2021. The D-series scan produced one genuine, out-of-sample-persistent pattern; it is not tradable at a profit.

**Running total: thirteen strict-rule market-tests (Z02–Z12, D01), none passing.** With the user's markets and the free data
examined, the next lever is the account structure itself: the user has asked about forex prop firms, whose static drawdowns
may be worth several times Tradeify's per attempt at zero edge (to be priced, §131).

## 131. Forex prop firms considered and set aside by the user — evaluation fees too high (S2)

**No trial spent; N 772.** The user asked whether forex prop firms (FTMO, FundedNext, Alpha Capital, The5ers, FundingPips, E8
Markets) are worth pursuing. Third-party rule summaries were gathered for all six and FundedNext's official help centre was
read (Stellar 2-Step $100k: $549.99 fee refunded with the first payout; 8% / 5% targets, ≥ 5 trading days per phase; 5% daily
loss on the initial balance, raised by the day's profits; **10% static maximum loss**; funded: ≤ 3% risk at any time, first
payout after 21 days then every 14, 80% split, news profits counted at 40%; "account rolling", "breaching several accounts in a
short span" and "one-sided betting" treated as gambling). The static 10% cushion would let a funded account pay up to ~$8,000
at zero edge (vs ~$1,800 at Tradeify), but the plan would have to change (≤ 3% risk a day, one account at a time, mixed
direction). **The user declined: evaluation fees of ~$500 are too high; stay with Tradeify.** Not to be re-proposed unless the
user raises it.

## 132. D-series family 2 protocol: 30-minute windows around fixings, opens and closes (S1)

**No trial spent; N 772. Written and committed BEFORE the scan.** The user asked for a second discovery family. Lesson of
§130: the only pattern that persisted out of sample (silver into the London fix, 95th-percentile placebo in 2018–26) sat on a
SCHEDULED flow. Family 2 therefore scans the 30 minutes before and after each scheduled fixing, open or close in the same
seven markets — a small, mechanism-led family, so the multiple-testing bar is lower and moderate effects can pass.

1. **Windows (local time; 30 minutes before the event, then 30 minutes after):**
   - GBP/USD, AUD/USD, USD/CAD, USD/CHF: the WM/Reuters 16:00 London fix; the Tokyo 09:55 JST fix (window ends / starts at 09:55);
     USD/CAD also the Bank of Canada 16:30 New York rate. (26 windows: 4 × 2 × 2 + 1 × 2 + DST-robust local definitions.)
   - Silver (XAG/USD): COMEX settlement 13:25 New York, before and after; the London fix 12:00 London AFTER only (the
     before-window is D01's, already validated). (3 windows)
   - DAX: Xetra open 09:00 Frankfurt (after); US open 15:30 Frankfurt (after); Xetra closing auction 17:30 Frankfurt (before,
     after). (4 windows)
   - Nikkei: Tokyo open 09:00 JST (after); morning close 11:30 JST (before); afternoon open 12:30 JST (after); close 15:00 JST
     (before) — the 2010–17 schedule. (4 windows)
2. **Two day-sets per window:** all weekdays; the last weekday of the month. Total ≈ 2 × 29 = 58 tests (the exact count is
   reported; cells under 30 observations drop out).
3. **Discovery 2010-01 → 2017-12 only** (asserted). **Selection:** two-sided |t| > Bonferroni at 0.05 over the tests run (≈ 3.2
   for 58) AND |mean| > 2 × cost (FX 0.8 bp; DAX, Nikkei 1.0; silver 1.5). At most 5 carried, by |t|; a month-end cell is a
   duplicate if its all-weekday cell is carried.
4. **Exclusion (added after §130):** any window overlapping 17:00–18:00 New York (the CME break) is not scanned.
5. **Validation 2018-01 → 2026-09, sealed until registration;** one trial each; the strict rule for a standalone trade (net t >
   1.645 in the discovered direction; ≥ 95th percentile of the same instrument's other family-2 windows of the same day-set;
   posterior > 0 with prior = discovery mean halved less cost); reported against the running count.

## 133. Amendment before the family-2 scan (user): no multiple-testing cut in discovery; a watchlist tier for forward testing (S1)

**No trial spent; N 772. Committed BEFORE the scan.** The user directs that candidates not be discarded for failing a
multiple-testing penalty: "I want to know if something works ... then we can forward test to see if it's still viable." §132
is amended:

1. **Discovery selection:** two-sided |t| > 1.96 (uncorrected) AND |mean| > 2 × cost. **All** passing cells are carried (a
   month-end cell remains a duplicate of a carried all-weekday cell). The number of tests run and carried is reported, so the
   expected count of chance passes (~5% of tests) is visible beside the result.
2. **Validation unchanged:** one trial per candidate on the sealed 2018-01 → 2026-09 window.
3. **Three outcomes:** **CONFIRM** — the strict rule (§119/§132) holds; **WATCHLIST** — the strict rule fails but the net mean
   in validation is > 0 in the discovered direction; **REJECT** — net mean ≤ 0. Watchlist items are forward-tested live by the
   demo bot (shadow-tracked, no capital) until they either meet the strict rule on the combined out-of-sample record or fade.
   Only CONFIRM counts as an edge for the plan and its projections; the strict rule itself is not relaxed.

## 134. D-series family 2 discovery: one cell beats twice its cost; D02 registered (S1–S5)

**No trial spent at registration; N 772.** `reporting/d2_discovery.py`, `reports/d2_discovery.json`; price marks at :00/:25/:30/:55
(`data/fx_fix.quarter_marks`). **56 tests on 2010–17** (no window touched the CME break); about 2.8 would clear |t| > 1.96 by
chance and **6 did**; **one also beats 2 × cost and is carried (amendment §133: no multiple-testing cut):**

| cell (2010–17) | mean (SD), t, n |
|---|---|
| **AUD/USD, 30 min before the 09:55 JST Tokyo fix, month-end** | **+2.88 bps (8.3), +3.25, 88** — carried |
| USD/CHF, 30 min before the Tokyo fix, all weekdays | +0.52 (5.8), +3.92 — below 2 × cost (0.8 bp) |
| USD/CAD, 30 min after the Bank of Canada 16:30 rate | −0.51 (7.5), −3.01 — below cost |
| GBP/USD, before the Tokyo fix, month-end | +1.24 (4.0), +2.89 — below 2 × cost |
| USD/CAD, before the Tokyo fix | +0.30 (4.6), +2.65 — below cost |
| USD/CHF, before the WM/R 16:00 fix | −0.79 (13.7), −2.62 — below 2 × cost |

The Tokyo-fix pre-window is where most of the signal sits (four of six), consistent with the dollar-buying flow behind
the gotobi effect (Z10) — but mostly too small for CME futures costs.

**D02 registered** (`hypotheses.yaml` D02, `signals/d02.py`): long AUD/USD (6A) 09:25 → 09:55 JST on the month's last weekday
(20:25 / 19:25 New York the evening before), net of 0.8 bp; sealed validation 2018-01 → 2026-09; CONFIRM / WATCHLIST / REJECT
per §133; prior Normal(+0.64, 1.0) bp; 14th Z+D test. 6A added to the registry's single-market primaries.
**Injection** (`reports/d02_injection.json`): +0.64 bp planted, recovered 0.63 (SD 0.88, 100 month-ends); power of the strict t
22% at the prior's size.

### D02 validation: REJECT — the discovery did not recur (S6–S8)

**One trial spent: t00779. N 772 → 773.** `reports/d02_trial.{json,md}`.

| sealed 2018-01 → 2026-09, 100 month-ends | |
|---|---|
| long AUD/USD 09:25 → 09:55 JST, gross / net (SD) | **−0.33 / −1.13 bps** (8.2) |
| t / placebo (other month-end windows) | −1.38 / 0th pct |
| 2018–21 / 2022–26 net | +0.01 / −2.06 bps |

**REJECT tier** (net ≤ 0; nothing to forward-test). The one cell family 2 carried was a chance pass of the uncorrected scan —
the outcome the expected-chance-pass count (2.8 of 56) warned of, and the reason every carried cell still gets the sealed
check. Fourteen Z+D market-tests, none confirmed; the watchlist is empty.

## 135. A19: planning further ahead makes the plan worse — the cost-blind solver buys tiny stops (S8)

**No trial spent; N 773. Computation record (A19)** (`reports/a19_horizon.json`, `reporting/a19_horizon.py`). The user approved
re-solving the policy for lifetime value (a zero-edge funded account can be worth up to its cushion). Evaluation solved for
P(pass within He days), funded for E[payouts within Hf days]; He ∈ {21, 42, 84}, Hf ∈ {21, 63, 126, 252}; 4 MNQ + 8 MGC, drift
removed, stops at the stop price; block-bootstrap mean net, MNQ + MGC:

| He / Hf | 84 days: 2021–26 / 2015–20 | 252 days: 2021–26 / 2015–20 |
|---|---|---|
| **21 / 21 (the plan)** | **+$3,346 / +$4,035** | **+$11,079 / +$13,131** |
| 42 / 21 | +$1,739 / +$2,625 | +$5,646 / +$8,473 |
| 21 / 63 | +$312 / +$408 | +$1,152 / +$1,461 |
| 21 / 126–252 | −$722 / −$499 | −$1,829 / −$1,086 |
| 84 / any | −$420 to −$439 / −$270 to −$385 | about −$1,100 / −$630 to −$940 |

**Why:** the A01 solver prices every bracket as a fair coin and ignores commissions. Planning further ahead raises the value of
surviving, so it chooses tight stops — funded +$3,000 / −$200 instead of +$3,000 / −$1,000; evaluation +$600 / −$200 instead of
+$1,200 / −$1,000. On real paths a $200 stop on 4 MNQ is a few ticks wide, resolves within minutes (often against, under the
one-minute both-touched rule) and pays commissions every day: 84-day P(payout) falls from 70–77% to 12–15% (Hf 252) and to
0–1% (He 84). The 21-day horizon is what keeps the solver away from brackets that only work on paper; it stays.
**Next (A20):** the long horizons again with a menu restricted to stops ≥ $500, where costs and tick noise are small.

## 136. A20: stops of at least $500 improve the plan slightly in both histories; longer horizons still lose — adopted (S8)

**No trial spent; N 773. Computation record m00166** (`reports/a20_menu.json`, `reporting/a20_menu.py`). Block-bootstrap mean
net, MNQ + MGC, stops at the stop price:

| menu, He / Hf | 84 days: 2021–26 / 2015–20 | 252 days | 84-day P(payout) MNQ / MGC, 2021–26 · 2015–20 |
|---|---|---|---|
| full (A01), 21 / 21 | +$3,346 / +$4,035 | +$11,079 / +$13,131 | 70% / 77% · 64% / 76% |
| **stops ≥ $500, 21 / 21** | **+$3,412 / +$4,191** | **+$11,297 / +$13,830** | **71% / 77% · 68% / 77%** |
| stops ≥ $500, 21 / 63 | +$1,079 / +$1,039 | +$3,866 / +$3,732 | 71% / 77% · 68% / 77% |
| stops ≥ $500, 21 / 126 | +$20 / +$131 | +$709 / +$1,024 | 32–40% |
| stops ≥ $500, 42 / 21 | +$2,296 / +$2,918 | +$7,860 / +$9,791 | 57% / 57–67% |
| stops ≥ $500, 42 / 63 | +$523 / +$848 | +$2,273 / +$3,184 | 57% / 57–67% |

Crude (10 MCL, one-bar approximation), full → restricted: replay 45% +$397 → 52% +$820 (2021–26), 55% +$545 → 49% +$418
(2016–20); block +$254 → +$295, +$649 → +$684 — neutral to slightly better.

- **Removing stops under $500 helps in both histories** (+2–4%: +$66–156 per four months, +$218–699 a year; MNQ's 2015–20
  P(payout) 64% → 68%). The tight brackets were losing to tick noise, the one-minute both-touched rule and commissions.
- **Longer horizons still lose** even without tight stops: the funded policy planned over 63+ days plays for survival and
  withdraws far less within any realistic window. The 21-day horizon stays.
- **Adopted for the live plan only:** `a06_playbook.PLAN_L_SET = (5, 6, 8, 10)`; the solver's default menu (A01's) is unchanged so
  every earlier record reproduces. `bot/policy.json` re-exported; tables regenerated; `tests/test_bot_ticket.py` passes. Example
  end-game ticket (MNQ eval at $52,700, best day $1,100): +$300 / −$500 (was +$100 / −$200-type). The droplet needs the new
  `policy.json` (copy and restart).

## 137. A21: Nikkei (1 NKD) and DAX (2 FDXM) fill the two unused funded slots — five accounts, ends ahead 85–96% (S8)

**No trial spent; N 773.** `reporting/a21_more_accounts.py`; `reports/a21_{market}.json`, `a21_corr.json`, `a21_portfolio.json`. The user
chose to improve what works rather than search for new edges; Tradeify allows 5 funded accounts and the plan used 3. Candidates with
free HistData 1-minute data, windows fixed in advance from each main session: DAX (FDXM, €5/pt) Xetra 09:00–17:30 Frankfurt; Nikkei
(NKD, $5/pt) 09:00–15:00 Tokyo; EUR/GBP/AUD/JPY (6E/6B/6A/6J) 08:00–16:00 London; silver (SI) COMEX 08:25–13:25 New York. Zero edge,
drift removed per era, today's contract values, stops at the stop price, the live policy (stops ≥ $500, §136); assumed ≤ 3 full-size
contracts and round trips FDXM/NKD $4, FX/SI $4.5 (estimates). Bid-quote CFD/spot data — an approximation of the futures.

**Alone, at the risk-matched size (daily swing ≈ $2,900; 84 days, replay · block, P(payout) and mean net):**

| market (size) | 2010–20 | 2021–26 | daily correlation with MNQ / MGC / MCL (2021–26) |
|---|---|---|---|
| **Nikkei, 1 NKD** (swing $2.9–3.5k) | 71% +$1,117 · 80% +$2,020 | 75% +$1,855 · 79% +$2,135 | **+0.01 / +0.01 / +0.03** |
| **DAX, 2 FDXM** ($2.4–2.8k) | 75% +$1,724 · 74% +$1,888 | 85% +$3,621 · 79% +$3,023 | +0.19 / +0.16 / −0.05 |
| silver, 1 SI ($3.7–4.6k, cannot go smaller) | 75% +$2,058 · 75% +$2,388 | 86% +$2,605 · 81% +$2,394 | +0.14 / **+0.58** / +0.07 |
| euro, 3 6E (undersized, $1.4–1.8k) | 66% +$2,236 · 72% +$2,024 | 75% +$1,657 · 71% +$1,626 | +0.05 / +0.32 / −0.05 |
| pound / aussie / yen, 3 (undersized, < $1.1k) | 27–43% | 35–51% | gold +0.29–0.40 |

**Portfolio (joint replay on common start dates; 3 = MNQ 4, MGC 8, MCL 10):**

| per four months | 3 accounts | + NKD | + NKD + DAX | + NKD + DAX, extra slippage (NKD +$25, DAX +$10 a trade) |
|---|---|---|---|---|
| 2021–26 mean / median | +$4,712 / +$3,224 | +$6,785 / +$6,200 | **+$10,475 / +$9,422** | +$10,034 / +$9,013 |
| 2021–26 P(net > 0); 10th pct | 80%; −$1,060 | 90%; +$25 | **96%; +$1,374** | 96%; +$1,194 |
| 2010–20 mean / median | +$5,363 / +$4,346 | +$6,115 / +$5,212 | **+$6,833 / +$5,831** | +$6,392 / +$5,482 |
| 2010–20 P(net > 0); 10th pct | 80%; −$899 | 79%; −$1,895 | **87%; −$1,505** | 85%; −$1,880 |
| fees | $2.6–3.0k | $3.7–4.1k | $4.7–5.1k | |

**Recommended: add Nikkei (1 NKD, 09:00–15:00 Tokyo = 20:00–02:00 New York) and DAX (2 FDXM, 09:00–17:30 Frankfurt = 03:00–11:30
New York) as accounts 4 and 5** — Nikkei is uncorrelated with everything; DAX nearly so. Silver duplicates gold; the FX contracts are
too small within a 3-contract cap. Open with the user before the bot is changed: that their Tradeify account type permits NKD and FDXM
and how FDXM counts against the contract cap; the extra $2.1k of evaluation fees per four months.

## 138. Nikkei and DAX added to the demo — forward test first; evaluations bought only if it comes back positive (S8)

**No trial spent; N 773.** The user confirmed: Tradeify permits NKD and FDXM; the per-account cap is taken as 3 minis / 30 micros
(Tradeify states no separate rule for them); the two extra evaluations will be bought **only if the forward test is positive**.

- **Playbook** (`a06_playbook.PRODUCTS`): NKD 1 contract, $5 a point, tick 5, rt $4, 09:00–15:00 Tokyo; FDXM 2 contracts, €5 a point at
  EUR/USD 1.12 ($5.60), tick 1, rt $4, 09:00–17:30 Frankfurt. Fresh-evaluation tickets: NKD +240 / −200 points, FDXM +108 / −89 points
  (≈ +$1,200 / −$1,000 net). `bot/policy.json` re-exported.
- **Bot:** windows defined in each exchange's own time zone and converted per date (NKD 20:00 → 02:00 New York in summer, 19:00 →
  01:00 in winter; FDXM 03:00 → 11:30, shifting an hour in the weeks when Europe and the US change clocks on different dates); the
  17:30 alert now carries five tickets (MCL, NKD, MGC, FDXM, MNQ). Shadow tracking from Yahoo: NKD=F; FDXM on the DAX index (^GDAXI,
  Xetra hours). Bookkeeping for five accounts; an existing three-account `state.json` is kept and the two new accounts start fresh.
- **Demo checker** (A18): expected outcome rates for NKD and FDXM from A21's 2021–26 paths.
- Tests: tickets equal the playbook on 3,000 random states over all five products; the schedule's NKD/FDXM windows; state migration.

## 139. The bot shows ticks and posts a weekly check against the backtest (S8)

**No trial spent; N 773.** At the user's request, while the demo runs: (1) every ticket shows its take and stop in **ticks** beside
points (TradingView's bracket fields take ticks; tick sizes MNQ 0.25, MGC 0.10, MCL 0.01, NKD 5, FDXM 1); (2) the Friday 17:30 alert
carries a **weekly check** — the week's shadow-tracked outcomes (take / stop / time exit) and P&L against the backtest's expectation
for the same brackets, flagged UNUSUAL if |z| ≥ 2 on P&L or the outcome mix's chi-square ≥ 6. Expectations are precomputed from
2021–26 paths for every bracket the live policy can choose (W_SET × the plan's stop menu, 76 per product) into `bot/expected.json`
(`a18_demo_check --export-expected`), so the droplet needs no history; a stop capped near the floor maps to the nearest menu
bracket. Tests extended. Deployed to the droplet with the user's go-ahead.

## 140. Accounts 4–5 re-checked on real prices — a clock bug in all HistData work, fixed; soybeans is the sixth market (S8)

**No trial spent; N 773.** `reporting/a22_more_markets.py`; `reports/a22_*.json`; A21 re-run (`reports/a21_*.json` overwritten
with corrected values). At the user's request: re-check the NKD/DAX backtest, then look for a sixth and seventh market.

**A clock bug, found by the re-check.** HistData's ASCII M1 timestamps are **New York local time with daylight saving**, not
"EST without DST (UTC−5)" as `data/fx.py`, `data/fx_fix.py` and A21 assumed — so every HistData window ran **one hour late from
March to November**. Shown three ways: A21's Nikkei proxy vs real NKD futures (window-return correlation 0.996 in US summer only
when shifted an hour; 0.994 in winter unshifted); HistData S&P (spxusd) vs Databento NQ 1-minute returns, 2024 (summer 0.895 at
−60 min, 0.012 at 0; winter 0.894 at 0); silver (xagusd) vs Databento MGC (0.708 / 0.010; 0.673 at 0 in winter). All three
loaders now read the stamps as America/New_York; caches built the old way are in `data/cache/stale_utc5/`.
**Affected and not re-run: Z10 (gotobi), Z11 (month-end fix), Z12 (EUR time of day), D01 (silver fix), D02 (AUD Tokyo fix) —
trials t00775–t00779 — and both D-series discovery scans (§130, §134).** Their windows were an hour off for ~8 months a year;
their REJECT verdicts are unsafe until re-run. Records stay as written (append-only).

**Accounts 4–5, corrected** (A21 re-run; 84 days; replay):

| | 2010–20 old → corrected | 2021–26 old → corrected |
|---|---|---|
| 1 NKD alone | 71% +$1,117 → 67% +$1,189 | 75% +$1,855 → 74% +$2,763 |
| 2 FDXM alone | 75% +$1,724 → 73% +$2,072 | 85% +$3,621 → 83% +$1,879 |
| five accounts: mean / P(net > 0) / 10th pct | +$6,833 / 87% / −$1,505 → **+$8,109 / 84% / −$654** | +$10,475 / 96% / +$1,374 → **+$9,448 / 94% / +$1,300** |

**Real prices.** Yahoo hourly bars (NKD=F, 2024-05 → 2026-09; the official DAX index ^GDAXI for DAX — Yahoo has no Eurex
futures), same dates, both as hourly bars with the OHLC path rule. Corrected proxy vs real: NKD correlation 0.98, SD ratio ~0.99,
range ~0.97; 1 NKD replay +$3,600 real vs +$3,008 proxy (block +$2,586 / +$2,445). DAX correlation 0.94 (the index opens on a
Xetra auction with stale prints; the CFD, like FDXM, trades before 09:00), +$3,906 index vs +$2,023 proxy — the proxy is the
closer and more conservative guide for FDXM. NKD window volume: median ~1,250 contracts. **Accounts 4–5 stand.** `bot/expected.json`
regenerated (NKD/FDXM outcome rates move ≤ 5 points; MNQ/MGC/MCL unchanged) — not yet deployed.

**Sixth and seventh market.** Candidates fixed before any result, each market's whole session: natural gas (MNG), platinum (PL),
copper (MHG), corn/soybeans/wheat (ZC/ZS/ZW), live cattle/lean hogs (LE/HE), bitcoin (MBT, not on Tradeify's stated list). Free
Yahoo data: hourly ~730 days for all; daily since 2010 only where Yahoo's daily bar matched the hourly-built session (NG, BTC,
grains), copper from the owned Databento file. **Yahoo's continuous hourly series interleaves two contract months around rolls**
(corn June 2024, hogs Sept–Oct 2025 and March 2026, swings of 4–25%); sessions with an internal open/close jump > 0.8% or a
one-hour move > max(5%, 15× the median) are dropped (NG 32, PL 12, HG 20, ZC 63, ZS 33, ZW 68, LE 34, HE 112, BTC 21 of ~560; the
rule also drops a few real extremes, e.g. copper 2025-07-30). Sizes by the daily-swing rule ($2,900) within 3 full / 30 micro:
27 MNG, 1 PL, 10 MHG, 3 ZC/ZS/ZW/LE/HE (corn and hogs reach only ~$1k), 13 MBT.

Alone (replay P(payout), mean net; 2024–26 hourly · 2010–20 · 2021–26): **ZS 83% +$5,299 · 68% +$3,324 · 74% +$2,891**; LE 88%
+$3,367 (hourly only); NG 84% +$2,025 · 48% +$900 · 75% +$1,364; BTC 73% +$1,429 · 71% +$3,483 (2017–20) · 54% +$1,496; HG 48%
−$509 · 39% +$493 · 66% +$1,594; PL 60% +$606; ZW 42% +$2,194 · 59% +$3,161 · 56% +$858; HE 52% +$1,077; ZC 37% +$271.
Correlation with the five live accounts ≤ 0.2 for NG, ZS, LE, HE; copper +0.26–0.38 (Nasdaq, gold), platinum +0.44 (gold), bitcoin
+0.31 (Nasdaq); the grains +0.4–0.6 with each other.

**Portfolio** (joint replay, common start dates, one run without bitcoin — `a22_portfolio.json`; with bitcoin in
`a22_portfolio_with_btc.json`; per four months, mean / P(net > 0) / 10th pct):

| | 2024–26 hourly (229 starts) | 2016–20 (669) | 2021–26 (1,019) |
|---|---|---|---|
| five live | +$8,329 / 99% / +$1,380 | +$8,117 / 84% / −$679 | +$9,446 / 94% / +$1,300 |
| **+ soybeans (6)** | **+$14,327 / 100% / +$3,773** | **+$9,524 / 87% / −$968** | **+$12,586 / 96% / +$2,768** |
| + natural gas (6) | +$9,673 / 94% / +$547 | +$9,095 / 93% / +$1,280 | +$10,860 / 96% / +$1,376 |
| + cattle (6) | +$10,437 / 100% / +$1,403 | — | — |
| + soybeans + natural gas (7) | +$15,671 / 100% / +$5,685 | +$10,503 / 94% / +$1,322 | +$14,000 / 97% / +$3,873 |
| + soybeans + cattle (7) | +$16,436 / 100% / +$5,014 | — | — |
| soybeans in place of crude (5) | +$12,593 / 100% / +$3,688 | +$9,119 / 86% / −$408 | +$11,495 / 97% / +$2,778 |

**Stress — stops filled at the bar's extreme** (an upper bound on gap slippage; soybeans and cattle pause overnight / trade one
session): ZS hourly +$5,299 → +$2,586, daily +$3,324 → −$320 and +$2,891 → −$162; LE hourly +$3,367 → +$2,794; NG hourly
+$2,025 → −$292. On daily bars the bound is extreme (a whole day's low as the fill); on hourly bars soybeans and cattle keep most
of their result and natural gas does not. Soybeans bar-to-bar gaps > 0.25%: 2.8% of hours.

**Reading.** Soybeans (3 ZS) is the best sixth market in all three histories and the best swap for crude if the plan stays at
five accounts; natural gas (27 MNG) is the better-tested seventh (long history, the best 10th percentile in 2016–20), cattle (3 LE)
the stronger one on two years of data only. All on free Yahoo bars (hourly within ~10–15%, daily ~30% of the minute answer) —
a go/no-go, not a forecast. **Open with the user:** Tradeify's 5-funded cap (a sixth or seventh account needs it lifted — or a
swap); shadow-tracking ZS and NG/LE in the bot before buying anything; deploying the regenerated `expected.json`; re-running
Z10–Z12, D01–D02 and the D-series scans on the corrected clock.

## 141. Soybeans added to the demo bot as a sixth ticket (S8)

**No trial spent; N 773.** The user: "since it's a demo just add soybeans to the bot." 3 ZS, the whole CBOT session — enter at the
19:00 Chicago open (20:00 New York), flat by 13:15 Chicago (14:15 New York; the close is 13:20); prices in cents a bushel, $50 a
cent, tick ¼ cent ($12.50), round trip $4.50 (estimate). Fresh-evaluation ticket: +8.00 / −6.50 cents = 32 / 26 ticks (≈ +$1,200 /
−$1,000 net). Playbook (`a06_playbook.PRODUCTS["ZS"]`), `bot/policy.json` and `bot/expected.json` re-exported (ZS expectations
from A22's cleaned 2024–26 hourly sessions — coarser than the minute-based products); bot: accounts, schedule (Chicago clock),
shadow tracking on Yahoo `ZS=F` (checked on the 2026-10-08 session: 964 minute bars, bracket resolved). The corrected
`expected.json` of §140 was deployed 2026-10-11 and this change 2026-10-12, with the user's go-ahead; previous files kept in
`/opt/futures-bot/backup-2026-10-12/`. Demo only — under Tradeify's 5-funded cap a soybean account would replace one of the five.
Caveat: Yahoo's continuous series can mix two contract months near a roll (§140), so a shadow result there may be wrong.

## 142. The five HistData tests re-run on the corrected clock — Z12 confirms but fails the post-2021 gate; discovery re-scanned (S1–S8)

**Five trials spent: t00780–t00784, each written through `TrialLog.supersede` naming t00775–t00779. N 773 → 778.** Each module's
own `--inject` then `--run`, code unchanged; only the loaders' clock changed (§140). Old reports kept in the session scratch.

| test (old → new) | net | t | placebo pct | posterior > 0 | decision |
|---|---|---|---|---|---|
| Z10 gotobi, 18:00 ET → 09:55 JST | +0.49 → +0.46 bps | +0.67 → +0.54 | 93 / 50 → 39 / 50 | yes → yes | REJECT → REJECT |
| Z11 month-end EUR/USD London fix | −1.92 → −0.17 bps | −1.34 → −0.09 | 30 → 63 | no → yes | REJECT → REJECT |
| **Z12 EUR/USD short Europe, long US** | **+0.06 → +1.46 bps/day** | **+0.09 → +2.00** | **87 → 100** | yes → yes | **REJECT → CONFIRM** |
| D01 silver short 11:00–12:00 UTC (sealed 2018–26) | +0.75 → −2.23 bps | +0.95 → −2.52 | 95 → 26 | yes → no | REJECT → REJECT |
| D02 AUD long into the Tokyo fix, month-end (sealed) | −1.13 → −4.72 bps | −1.38 → −2.75 | 0 → 0 | no → no | REJECT → REJECT |

**Z12 confirms on its registered statistic and window (2010–26; injection power 79%) — and fails S8, the post-2021 gate.**
By period, net bps a day (t, annual Sharpe): 2010–17 +2.72 (+2.31, 0.81); 2018–20 +0.28 (+0.20, 0.11); **2021–26 +0.28 (+0.25,
0.10)**; morning leg alone 2021–26 +0.40 (Sharpe 0.25), afternoon −0.12. By year the edge lives in 2012–2017 (Sharpe +1.0 to +3.0)
and is flat since 2018. The strength after the paper (2013) and the fade since 2018 are both in the data; the registered test
pools them. **Not adopted** (S8; and 6E at ≤ 3 contracts carries ~$60 a day of edge). Net > 0 out of sample, so it goes to the
**watchlist** (§133), the programme's first entry there; a forward test would read the 2026–27 days as they come.

**D01 and D02 now point the other way on sealed data** (silver rises 11:00–12:00 UTC, t −2.52 for the short; AUD falls into the
Tokyo fix at month-end, t −2.75 for the long). Reversed signs found on sealed data are not hypotheses — recorded, not acted on.

**Discovery re-scanned on 2010–17 with the corrected clock** (`reports/d_discovery.json`, `d2_discovery.json`; rules unchanged).
Family 1 (|t| > 4.1, 926 tests): carried USD/CHF 20:00 UTC Fridays (t −6.07), USD/CHF 21:00 UTC Fridays (−4.47; inside the CME
break — excluded under §130's amendment), silver 10:00 UTC all weekdays (−4.22; replaces the 11:00 UTC cell D01 was built on, old
t −7.27). Family 2 (|t| > 1.96 and 2× cost, 58 tests, ~2.9 by chance): **8 carried, was 1** — GBP/USD into the 16:00 London fix at
month-end (+2.84), DAX after the Xetra open at month-end (−2.64), Nikkei into the Tokyo morning close (−2.60), AUD/USD into the Tokyo
fix at month-end (+2.57, D02's cell), AUD/USD after the London fix at month-end (−2.41), USD/CHF after the London fix at month-end
(+2.34), AUD/USD into the London fix at month-end (+2.04), DAX after the Xetra close at month-end (+1.97). **None registered yet —
open with the user** (each would be one validation trial on the sealed 2018–26 window; the Friday USD/CHF cell sits in the
Friday-close bid-spread pattern §130 described). The trial log's chain verifies (778 records).

## 143. D03–D11 registered — the nine cells of the corrected-clock re-scan, each to be validated once (S1–S5)

**No trial spent at registration; N 778. Committed BEFORE any validation data is read.** The user: "test those 9." From §142's
re-scan, the cells carried that were never validated (D02's cell was; USD/CHF 21:00 UTC Fridays is excluded as inside the CME
break, §130). One module, `signals/d_cells.py`; `hypotheses.yaml` D03–D11; catalog sections; 6S, 6B, FDXM, NKD added to the
registry's single-market primaries.

| id | cell (discovery 2010–17: mean, t, n) | trade | prior net (bp) |
|---|---|---|---|
| D03 | USD/CHF 20:00–21:00 UTC, Fridays (−2.88, −6.07, 403) | short USD/CHF (long 6S) | N(+0.64, 1.0) |
| D04 | silver 10:00–11:00 UTC, all weekdays (−3.14, −4.22, 1,949) | short SI | N(+0.07, 1.5) |
| D05 | GBP/USD 30 min into the 16:00 London fix, month-end (+5.63, +2.84, 96) | long 6B | N(+2.02, 1.0) |
| D06 | DAX 30 min after the Xetra open, month-end (−8.71, −2.64, 79) | short FDXM | N(+3.36, 1.0) |
| D07 | Nikkei 30 min into the Tokyo morning close, all weekdays (−2.35, −2.60, 1,153) | short NKD | N(+0.18, 1.0) |
| D08 | AUD/USD 30 min after the London fix, month-end (−3.45, −2.41, 96) | short 6A | N(+0.93, 1.0) |
| D09 | USD/CHF 30 min after the London fix, month-end (+3.18, +2.34, 96) | long USD/CHF (short 6S) | N(+0.79, 1.0) |
| D10 | AUD/USD 30 min into the London fix, month-end (+4.23, +2.04, 96) | long 6A | N(+1.32, 1.0) |
| D11 | DAX 30 min after the Xetra closing auction, month-end (+4.25, +1.97, 78) | long FDXM | N(+1.13, 1.0) |

**Fixed now:** direction = the discovery sign; costs as the scans (FX 0.8, DAX/Nikkei 1.0, silver 1.5 bp); prior mean per §132
(discovery mean halved less cost), prior SD max(1.0, cost) — the rule D01 (1.5) and D02 (1.0) used without stating it; placebo =
the same trade in the instrument's other cells of its family and day-set; tiers per §133; Z and D market-tests 15–23; outcome
injection from the placebo cells' demeaned returns (family 1) or the same window on all weekdays (family 2), the runner refusing
without it. Caveats on record before the run: D03 sits in the Friday-close bid-spread pattern §130 described; D04's prior is
nearly zero (the discovery mean is barely twice the cost); D05–D11 come from an uncorrected scan where ~2.9 of 58 cells pass by
chance and 8 did; D08 and D10 are one pair's before/after windows on the same days.

## 144. D03–D11 validated: one artefact, five watchlist cells, three rejects — still no tradable edge (S6–S8)

**Nine trials spent: t00785–t00793. N 778 → 787.** `reports/d0{3..9}_trial.*`, `d10_trial.*`, `d11_trial.*`; injections all
recovered (power of the strict t at the prior's size 7–52%). The trial log's chain verifies (787 records).

| id, trial | cell | events | net bps | t | placebo pct | 2018–21 / 2022–26 net | tier |
|---|---|---|---|---|---|---|---|
| D03 t00785 | USD/CHF falls in the last New York hour on Fridays (20:00-21:00 UTC) | 401 | +1.81 | +5.12 | 95 | +1.70 / +1.90 | **INVALIDATED (quote artefact)** |
| D04 t00786 | silver falls 10:00-11:00 UTC | 2171 | +0.43 | +0.56 | 91 | +1.21 / -0.25 | **WATCHLIST** |
| D05 t00787 | GBP rises into the London 4 pm fix at month-end | 102 | +1.54 | +0.69 | 100 | -2.20 / +4.61 | **WATCHLIST** |
| D06 t00788 | DAX falls in the first half hour of Xetra at month-end | 100 | -5.42 | -1.88 | 0 | -7.38 / -3.88 | **REJECT** |
| D07 t00789 | Nikkei falls into the Tokyo morning close | 2161 | -1.00 | -2.35 | 33 | -0.68 / -1.26 | **REJECT** |
| D08 t00790 | AUD falls after the London 4 pm fix at month-end | 97 | +2.33 | +1.68 | 67 | +2.36 / +2.30 | **WATCHLIST** |
| D09 t00791 | USD/CHF rises after the London 4 pm fix at month-end | 97 | +2.03 | +1.44 | 100 | +3.19 / +1.03 | **WATCHLIST** |
| D10 t00792 | AUD rises into the London 4 pm fix at month-end | 99 | +0.11 | +0.06 | 67 | -3.49 / +3.24 | **WATCHLIST** |
| D11 t00793 | DAX rises after the Xetra closing auction at month-end | 94 | -1.45 | -0.60 | 67 | -4.84 / +1.53 | **REJECT** |

**D03 passes the strict rule as registered (t +5.12, both halves t +3.63) and is not real.** Checked after the run, as §143 said
it would need: on HistData the drop lives only in the last hour before the weekend close, 16:00–17:00 New York, in both seasons
(US summer, 20:00 UTC: −4.20 bps, t −9.4; winter, 21:00 UTC: −4.63, t −8.4) and is absent the hour before (+0.14). On **CME 6S
futures trades** (Yahoo 6S=F hourly, 117 Fridays 2024–26) the same hour is **−0.06 bps, t −0.10**; on a quote feed (CHF=X) it is
−4.41, t −8.6. The bid falls as the spread widens into the close — §130's artefact, now shown on traded prices. Recorded as
INVALIDATED; not adopted and not watchlisted. Lesson for the protocol: any cell adjacent to a market close is checked against
traded futures prices before validation.

**Watchlist** (§133; with Z12, §142): D04, D05, D08, D09, D10. None is tradable as it stands: net 0.1–2.3 bps a trade, 12 events a
year for the month-end cells. Years of forward data the strict t would need at the validated size (one-sided 1.645, same SD):
D04 ~75, D05 ~48, D08 ~8, D09 ~11, D10 ~7122. A forward test in the bot would not decide any of them within the user's
horizon; recommended instead: re-read them from free data once a year. **Rejected:** D06, D07, D11. Running count: 23 Z and D
market-tests; 0 tradable confirmations.

## 145. A23: Tradeify's 100K and 150K accounts lose to the 50K over four months — stay at 50K; 50% consistency is worth ≤ $12–27 (S8)

**No trial spent; N 787.** `reporting/a23_account_sizes.py`; `reports/a23_check.json`, `a23_solve.json`, `a23_book.json`.
The user's rules (2026-10-12; in the module's docstring): 100K / 150K evaluations, target $6k / $9k, EOD drawdown $3k / $4.5k, no
daily loss limit, consistency 40% (50% for an add-on, price unknown), fees $185.50 / $258.30 after the standing 30% sale; funded
Daily (drawdown $2.5k / $3.5k locking at the start, daily loss $1,250 / $1,750, $1,750 / $2,500 a payout) and Flex (drawdown $3k /
$4.5k, no daily limit, $3,500 / $4,500 every 5 winning days of ≥ $200 / $250); payouts above the lock point, capped until the 3rd,
90%, no funded consistency on any size; 5 accounts in total. The A01 game re-solved per spec (take menu scaled by target, stop
menu by drawdown and capped by the daily limit, Flex with a winning-day state), contracts × evaluation-drawdown ratio. **Check:**
the 50K spec reproduces the live engine — MNQ +$1,265.35 vs +$1,265.53, MGC +$2,248 vs +$2,229, identical payout rates — after
implementing the playbook's FINISHED rule (§113; the live engine reaches nearly the same end through its fixed 2.32 cost).

**Game values** (zero edge; P(pass within 21 days) / funded E[$] in 21 days): 50K 0.300 / $1,080; 100K Daily 0.220 / $1,588; 150K
Daily 0.220 / $2,266; 100K Flex 0.220 / $1,631; 150K Flex 0.220 / $2,376. At 50% consistency the passes rise to 0.327 / 0.250.

**Five-account books, 84 days, real order, every size per market (5⁵ = 3,125 books per era):**

| per four months (40% consistency) | 2016–20, crude | 2016–20, soybeans | 2021–26, crude | 2021–26, soybeans |
|---|---|---|---|---|
| **all 50K Daily** | **+$7,852, 93%, p10 +$419** | **+$8,907, 88%** | **+$8,807, 93%, p10 +$1,133** | **+$12,499, 98%, p10 +$3,941** |
| all 100K Daily | +$504, 49% | +$2,460, 59% | +$2,497, 46% | +$6,159, 68% |
| all 150K Daily | +$2,656, 57% | +$4,352, 56% | +$2,917, 55% | +$5,512, 68% |
| all 100K Flex | −$516, 40% | +$377, 50% | +$3,277, 66% | +$8,433, 82% |
| all 150K Flex | −$250, 43% | +$1,368, 44% | +$518, 47% | +$3,163, 58% |
| fees, all 50K / all larger | ~$5.0k / $11–14k | | ~$5.2–5.4k / $11–14k | |

The larger accounts pass less often within the window (more evaluations bought at 2.3–3.2× the price) and their larger payouts
mostly fall after four months. The best mixed books beat all-50K by at most ~$0.7–1.4k on the mean, at a lower P(net > 0) and 10th
percentile, and the winning mix differs by history (gold on a 150K in 2016–20; MNQ on a 100K Flex in 2021–26) — chosen after the
fact. **Recommendation: stay with five 50K Daily accounts** for the four-month goal.

**50% consistency on the 50K:** +$999 / +$737 (2016–20) and +$1,668 / +$1,754 (2021–26) per four months on ~62–68 evaluations;
P(net > 0) ±2–4 points. **Worth it if the add-on costs less than ~$12–27 per evaluation** (break-even by history); the price is
open with the user.

**Decided (user, 2026-10-12):** the add-on costs more than $27 per evaluation — not bought; the plan stays at 40% consistency.

**Corrected 2026-10-13 (§146):** A23's replay summed float32 P&L, so an account landing exactly on the target (e.g. +$600 on a
$33.20 round trip read as $599.99) failed to pass. Fixed (P&L to the cent; ½-cent tolerance on the target) and re-run: all-50K books
**+$8,023, 92%** (2016–20, crude) and **+$9,468, 93%, p10 +$1,748** (2021–26, crude); soybean books unchanged; the 100K / 150K books
unchanged to the dollar. The conclusion stands.

## 146. A24: pricing commissions into the solver does not improve the plan — not adopted; a float-precision bug in A23 fixed (S8)

**No trial spent; N 787.** `reporting/a24_cost_aware.py`, `reports/a24_book.json`. A01 prices a bracket +W / −L (net) as a fair
coin, L / (W + L); with the round trip c the gross levels are W + c and L − c, so on a fair market P(win) = (L − c) / (W + L).
A24 adds only that known term (A05's measured odds fitted one regime, §102) and re-tries the longer horizons that the cost-blind
solver spoiled (§135–136). Variants fixed before any result, one rule for every market; live sizes; 84-day replay from every start.

**Engine fix first.** A24's first pass showed crude far below the live engine (+$242 vs +$820): A23's replay summed float32
paths, so an evaluation landing exactly on +$3,000 read $2,999.99 and never passed. Fixed (P&L rounded to the cent, ½-cent
tolerance on target and consistency); A23 and A24 re-run. Against the live engine: MNQ +$1,265.3 vs +$1,265.5, MGC +$2,248 vs
+$2,229, MCL +$834 vs +$820 (payout rate 60% vs 52%: on days within one round trip of the floor A23 retires the account, as the
playbook and bot do, §113, while the live engine trades on with a $1 stop through its fixed 2.32 cost offset).

| five accounts, per four months (mean / P(net > 0) / 10th pct) | 2016–20, crude | 2016–20, soybeans | 2021–26, crude | 2021–26, soybeans |
|---|---|---|---|---|
| **plan (fair coin, 21 / 21)** | **+$8,023 / 92% / +$259** | +$8,907 / 88% / −$752 | **+$9,468 / 93% / +$1,748** | **+$12,499 / 98% / +$3,941** |
| cost-aware, 21 / 21 | +$8,105 / 85% / −$910 | +$8,648 / 81% / −$1,447 | +$8,219 / 90% / +$17 | +$11,608 / 96% / +$1,847 |
| cost-aware, 42 / 21 | +$8,708 / 85% / −$1,359 | +$9,902 / 89% / −$369 | +$8,225 / 85% / −$723 | +$10,362 / 95% / +$1,681 |
| cost-aware, 21 / 63 and 42 / 63 | = 21 / 21 and 42 / 21 (the funded policy does not change) | | | |

By market (2021–26 / 2016–20 mean net, plan → cost-aware): MNQ +$1,265 → +$1,741 / +$1,960 → +$2,050; MGC +$2,248 → +$1,408 /
+$2,075 → +$2,477; MCL +$834 → +$636 / +$678 → +$771; NKD +$2,763 → +$1,694 / +$1,189 → +$1,655; FDXM +$1,879 → +$1,991 /
+$2,071 → +$2,037; ZS +$3,727 → +$3,859 / +$3,024 → +$3,922.

**Reading.** Pricing the commission in shifts brackets slightly and moves single markets by ±$1k either way, with no sign
that holds across both histories except MNQ's small gain; the books lose P(net > 0) and the 10th percentile in every case, and
the mean in three of four. Picking the variant per market would be choosing after the fact. **Not adopted; the plan's fair-coin
solver stays.** With the ≥ $500 stop menu (§136) the commission is already small against the brackets (c / (W + L) ≈ 0.2–1.5%),
so there was little left to fix — the cost-blind failure of §135 lived in the tiny stops that menu removed.

## 147. The demo review in one command; the bot files `!eod` under the right trading day (S8)

**No trial spent; N 787.** While the demo runs, so the ~2026-10-25 review takes minutes:

- **`python -m futuresres.reporting.a18_demo_check --review`** pulls `shadow_log.csv`, `demo_log.csv`, `state.json` and `tickets.json`
  from the droplet (read-only; copies in `data/cache/demo/`, gitignored) and prints, and saves as `review_<date>.md`: outcomes and
  shadow P&L against the backtest for the same brackets (overall and per product, soybeans included); each recorded close against
  the shadow P&L of the ticket that was running when it was sent (the latest started ticket from `tickets.json`; closes sent
  while a ticket is still open are skipped until it is tracked; tickets marked skipped are excluded, unmarked ones counted and
  flagged — `!took` is not always sent); and each account's phase, balance, evaluations bought, passes, payouts and fees.
- **Bot defect found by the first run.** `!eod` filed a balance under today only after 17:00 New York, else the previous trading
  day — but the user sends it as each bracket resolves (02:48, 11:21, 16:24), so every close of the first two days was filed a day
  early (DAX under 2026-10-09) and the 17:30 alert would list balances as missing. Now `schedule.eod_day`: the New York date of
  the exit of the product's latest started ticket (every ticket of one alert exits on the next alert's date); the old rule only
  when no ticket has started. Test added. The bot's log now writes New York time with its offset (the droplet runs on UTC; earlier
  rows are naive UTC, which the checker converts). Help text and README updated. **Deployed 2026-10-13 with the user's go-ahead** (previous files in `/opt/futures-bot/backup-2026-10-13/`).

**First reading (2026-10-13, 9 finished tickets):** take / stop / time exit 2 / 7 / 0 against 3.8 / 4.7 / 0.4 expected (chi-square
2.4, p ≈ 0.30); shadow P&L −$4,601 against −$261 ± $3,147 (z −1.38) — within normal range at nine tickets. Recorded closes match
the shadow within $4 (soybeans −$11.50), but are round ±$1,000 / ±$1,200: the demo appears to charge no commission (or balances are
rounded) — live accounts will pay $2.56–$33 a ticket that the demo does not show.

**How the demo is run (the user, 2026-10-13):** the tickets are NOT placed — the user cannot be at the screen at each entry time —
the user reads each ticket's take or stop after the fact and records it with `!eod`, without commissions. So the demo is a
paper forward test of the plan's brackets: the review's "execution" section checks the user's reading against the shadow
tracker (it agrees within commission and tick rounding), not real fills; slippage and commissions are untested until live.

## 148. A25: holding payouts back does not help — the plan's "take everything allowed, every day" stays (S8)

**No trial spent; N 787.** `reporting/a25_payout_timing.py`; `reports/a25_book.json`; A23's engine gains a `withdraw` option
("all" reproduces the live engine: MNQ +$1,265.3 vs +$1,265.5). The funded game chooses, at each day's end, to withdraw none, half
or all of what the rules allow (above $52,000; $1,250 a payout until the third). Variants fixed before any result, one rule for
every market: the plan (all, funded horizon 21), choose at 21, 63 and 126 days. Six markets, both histories, 84-day replay.

| five accounts, per four months (mean / P(net > 0) / 10th pct) | 2016–20, crude | 2016–20, soybeans | 2021–26, crude | 2021–26, soybeans |
|---|---|---|---|---|
| **plan (take all)** | **+$8,023 / 92% / +$259** | **+$8,907 / 88% / −$752** | **+$9,468 / 93% / +$1,748** | **+$12,499 / 98% / +$3,941** |
| choose, 21 days | +$8,013 / 92% / +$253 | +$8,874 / 88% / −$673 | +$9,592 / 93% / +$1,719 | +$12,632 / 97% / +$3,970 |
| choose, 63 days | +$8,540 / 94% / +$2,237 | +$8,398 / 94% / +$1,813 | +$8,151 / 93% / +$1,351 | +$9,869 / 96% / +$2,490 |
| choose, 126 days | −$2,972 / 0% | −$2,751 / 0% | −$3,139 / 0% | −$2,936 / 0% |

- **At the plan's 21-day horizon the choice changes nothing** (±$130): the solver would hold back only in states the replay rarely
  reaches.
- **At 63 days it holds back in ~60–85% of payable states** — better in 2016–20 (mean +$517 / −$509; 10th percentile up ~$2k),
  worse in 2021–26 (−$1,317 / −$2,630). No consistent sign; adopting it would mean choosing a history.
- **At 126 days it never withdraws before the cap lifts**, so nothing is paid within four months — the solver plays for
  uncapped payouts later, which a four-month goal cannot use.
- **Not adopted.** Taking everything allowed every day remains the plan; with no edge, money in the account is only exposed.

## 149. D-series family 3 protocol: the session relay — does a finished window predict the direction of the next one? (S1)

**No trial spent; N 787. Written and committed BEFORE any data is built or scanned.** The user: keep searching; published effects
are likely gone — find something from what the programme has seen. Everything tested so far was a published effect or a scan of
clock patterns; the plan itself trades six windows that hand over from Tokyo to Europe to New York. If a window that has fully
closed predicts the DIRECTION of a later one, the bot can choose long or short for that ticket at no extra cost (one trade a day
either way) — direction is the one lever the zero-edge plan leaves open. Not covered before: Z06/Z07 used a market's own long
history (rejected), F08 same-hour MNQ/gold divergence (premise failure), Z05 gold day/night (marginal). Nothing tested the relay.

1. **Windows and returns** (each from the start of the window to its end, the plan's windows; ET unless stated):
   NKD 09:00–15:00 Tokyo (= 20:00/19:00 → 02:00/01:00 New York); DAX 09:00–17:30 Frankfurt; MGC 03:00–11:30; MNQ 09:30–16:00;
   MCL the CME session (owned daily bars, roll-correct, bar dated D ≈ 20:00 D−1 → 20:00 D New York — an approximation);
   ZS the CBOT session (Yahoo daily, open → settlement; §140 checked it against hourly sessions). Plus pre-window moves:
   NKD Tokyo 15:00 → next 09:00; DAX 17:30 → next 09:00; MGC 11:30 → next 03:00; MNQ 16:00 → next 09:30; and the morning so far at
   MNQ's entry: DAX and MGC 03:00 → 09:30.
2. **Sources:** MNQ (NQ/MNQ spliced) and MGC 1-minute Databento TRADES (owned); NKD, DAX free HistData CFD minute bars on the
   corrected clock (§140) — window opens and closes only, none at a session close where §144's quote artefact lived; prices are the
   close of the last minute bar before each time; a window or move whose two prices come from different contracts is dropped.
3. **Tests (40 target × predictor pairs; every predictor has FINISHED before the target's entry):**
   - NKD (entry 20:00 D): MNQ, DAX, MGC, MCL, ZS windows of D; NKD's own window of D; NKD's pre-window move (to 09:00 Tokyo D+1).
   - ZS (entry 20:00 D): MNQ, DAX, MGC, MCL windows of D; NKD of D; ZS's own session of D.
   - MCL (entry 18:00 D): MNQ, DAX, MGC, ZS windows of D; NKD of D; MCL's own session of D.
   - DAX (entry 03:00 D): NKD of D (closed 02:00); MNQ, MGC, MCL, ZS of D−1; DAX's own window of D−1; DAX's pre-window move.
   - MGC (entry 03:00 D): NKD of D; MNQ, DAX, MCL, ZS of D−1; MGC's own window of D−1; MGC's pre-window move.
   - MNQ (entry 09:30 D): NKD of D; DAX and MGC 03:00 → 09:30 of D; MCL, ZS of D−1; MNQ's own window of D−1; MNQ's overnight move.
   Two forms each: every day (direction = sign of the predictor), and strong days only (|predictor| above its 2010–17 median).
   **80 tests**; at |t| > 1.96 about 4 pass by chance.
4. **Discovery 2010-06 → 2017-12 only** (asserted). Statistic: mean of sign(predictor) × target, the target demeaned within the
   period (directional skill beyond drift), two-sided t. **Carried: every test with |t| > 1.96** (§133: no multiple-testing cut);
   its sign fixes the rule — momentum (follow the predictor) or reversal (fade it). No cost filter: the direction is chosen for a
   trade the plan makes anyway.
5. **Validation 2018-01 → 2026-08, sealed until registration; one trial per carried test.** CONFIRM only if all hold:
   (a) **against always-long** (§119): the daily difference (rule direction − always long) × the target's RAW return has t > 1.645;
   (b) placebo: the real rule's mean at or above the 95th percentile of the same rule with the predictor shifted ±2…±11 trading
   days (20 shifts); (c) posterior > 0, prior Normal(discovery mean / 2, |discovery mean| / 2) on the demeaned statistic;
   (d) **S8: the demeaned statistic is positive on 2021–2026 alone**; reported against the running count (Z and D market-tests
   from 24). WATCHLIST if the validation mean (demeaned) > 0 but a condition fails; REJECT otherwise.
6. **Use, if any confirms:** the direction rule is put into the plan's replay (A23 engine, the confirmed market only) and the
   effect on P(payout) and net per four months reported before anything changes in the bot.
7. **Addendum before the scan (data checks, no outcome read):** values more than 15 robust SDs from a series' median are dropped
   as bad prints (two DAX CFD overnight values, +27,100 and −7,423 bps); the owned NQ minute data is sparse before 2013 (33 days in
   2010, 72 in 2011, 107 in 2012), so MNQ's discovery sample is ~1,300 days, not ~1,900.

## 150. Family-3 discovery: ten tests carried (≈4 by chance); D12–D21 registered before validation (S1–S5)

**No trial spent at registration; N 787. Committed BEFORE any validation data is read.** `reporting/d3_relay.py` (`--build`,
`--scan`), `reports/d3_discovery.json`; `signals/d_relay.py`; `hypotheses.yaml` D12–D21; catalog sections; MNQ and ZS added to the
registry's single-market primaries. 80 tests on 2010-06 → 2017-12 (asserted); |t| > 1.96 expected ~4 by chance; **10 carried**:

| id | target | rule | predictor | form | discovery (bps beyond drift a day) | prior |
|---|---|---|---|---|---|---|
| D12 | NKD_win | fade | NKD_pre (same) | all | -6.52, t -3.10, n 1812 | N(+3.26, 3.26) |
| D13 | MGC_win | follow | MGC_pre (same) | all | +6.10, t +2.89, n 1349 | N(+3.05, 3.05) |
| D14 | MNQ_win | fade | MNQ_win (prev) | all | -6.15, t -2.74, n 1047 | N(+3.07, 3.07) |
| D15 | NKD_win | fade | NKD_pre (same) | strong | -8.44, t -2.51, n 906 | N(+4.22, 4.22) |
| D16 | MGC_win | follow | MGC_pre (same) | strong | +8.20, t +2.46, n 674 | N(+4.10, 4.10) |
| D17 | MCL | fade | MGC_win (prev) | strong | -17.88, t -2.31, n 653 | N(+8.94, 8.94) |
| D18 | MCL | fade | MNQ_win (prev) | all | -12.54, t -2.26, n 1234 | N(+6.27, 6.27) |
| D19 | MGC_win | fade | MGC_win (prev) | strong | -7.95, t -2.24, n 592 | N(+3.97, 3.97) |
| D20 | MNQ_win | fade | ZS (prev) | strong | -6.72, t -2.11, n 625 | N(+3.36, 3.36) |
| D21 | ZS | fade | MGC_win (prev) | all | -6.97, t -2.01, n 1337 | N(+3.49, 3.49) |

Seven distinct relationships (D12/D15 and D13/D16 are one pair's every-day and strong-day forms). **Noted before the run:** D12/D15's
predictor ends at the price the Nikkei window starts from, so a noisy CFD quote at 09:00 Tokyo would make the two look negatively
related — a fade could be partly measurement; D13/D16 (gold) runs the opposite way to that artefact. Validation per §149, 5;
Z and D market-tests 24–33.

## 151. D12–D21 validated: no confirmation; gold following its overnight move (D16) passes everything but always-long (S6–S8)

**Ten trials spent: t00794–t00803. N 787 → 797.** Injections all recovered. Z and D market-tests 24–33.

| id, trial | rule | days | beyond drift, bps a day | vs always-long | placebo pct | 2021–26 | tier |
|---|---|---|---|---|---|---|---|
| D12 t00794 | NKD_win fades NKD_pre (same, all) | 2153 | -2.24 (t -1.25) | -1.85 (t -0.72) | 5 | -0.02 | **REJECT** |
| D13 t00795 | MGC_win follows MGC_pre (same, all) | 2139 | +1.17 (t +0.71) | +0.06 (t +0.02) | 85 | +3.15 | **WATCHLIST** |
| D14 t00796 | MNQ_win fades MNQ_win (prev, all) | 2000 | +2.82 (t +1.09) | +0.51 (t +0.14) | 85 | -0.43 | **WATCHLIST** |
| D15 t00797 | NKD_win fades NKD_pre (same, strong) | 1099 | -0.33 (t -0.12) | +0.96 (t +0.24) | 40 | +1.98 | **REJECT** |
| D16 t00798 | MGC_win follows MGC_pre (same, strong) | 962 | +6.27 (t +2.34) | +5.18 (t +1.28) | 100 | +8.91 | **WATCHLIST** |
| D17 t00799 | MCL fades MGC_win (prev, strong) | 1050 | -11.30 (t -1.27) | -26.91 (t -2.20) | 5 | -10.77 | **REJECT** |
| D18 t00800 | MCL fades MNQ_win (prev, all) | 1999 | -4.37 (t -0.71) | -18.18 (t -1.98) | 30 | -7.06 | **REJECT** |
| D19 t00801 | MGC_win fades MGC_win (prev, strong) | 1066 | +2.95 (t +1.18) | +0.87 (t +0.26) | 80 | +2.42 | **WATCHLIST** |
| D20 t00802 | MNQ_win fades ZS (prev, strong) | 954 | -0.01 (t -0.00) | -3.76 (t -0.65) | 40 | +2.21 | **REJECT** |
| D21 t00803 | ZS fades MGC_win (prev, all) | 2107 | -2.74 (t -1.09) | -2.86 (t -0.83) | 15 | -3.71 | **REJECT** |

**D16 — gold, follow its own move since the last London window (11:30 → 03:00 ET), on strong days** — is the closest the programme
has come: beyond drift +6.27 bps a day (t +2.34), placebo 100th percentile, posterior > 0, and **stronger in 2021–26** (+8.91,
t +2.68). It fails only (a): against always-long it adds +5.18 bps a day (t +1.28), because shorting gold costs its 2018–26 drift
(2018–20 against always-long −6.21; 2021–26 +10.19). Its every-day form D13 is weaker (+1.17, t 0.71; 2021–26 +3.15). The nearest
variants of the Nikkei fade (D12, D15) failed outright — the 09:00 CFD-quote concern of §150 is moot.

**Reading.** The relay holds nothing that beats always-long under the strict rule. One candidate is worth watching: D16 on the
watchlist with D13, D14, D19. D16 is the only one with a placebo at the 100th percentile and a stronger second half; it is also the
kind of rule (a bracket direction chosen by a move that has already happened) the plan could use at no cost.

## 152. D-series family 4 protocol: the overnight state at the open (MNQ, gold), from traded futures data with volume (S1)

**No trial spent; N 797. Written and committed BEFORE any data is built or scanned.** The user: keep searching. Family 3 used
window returns only; the owned Databento data also carries **volume and the path** of the hours before each entry, which free
quote data cannot. Question: does the state of the market just before the plan's entry — where it sits in its overnight range,
how busy and how volatile the night was, the last half hour, how the previous window ended — predict the window's direction?

1. **Targets:** MNQ 09:30–16:00 and MGC 03:00–11:30 New York (the plan's windows), from 1-minute TRADES (owned; MNQ = NQ/MNQ
   spliced, sparse before 2013, §149 addendum). A day whose segment spans two contracts is dropped.
2. **Segments** (New York time; Globex break 17:00–18:00 excluded by the data):
   - MNQ: overnight = 18:00 (previous day) → 09:30; pre-open = 09:00 → 09:30; previous window = 09:30 → 16:00 of the previous
     day, its last hour 15:00 → 16:00.
   - MGC: overnight = 11:30 (previous day) → 03:00; pre-open = 02:30 → 03:00; previous window 03:00 → 11:30, last hour 10:30 → 11:30.
   For each: return, high, low, last price, volume, realised variance (sum of squared 1-minute log returns).
3. **Predictors, all known at entry; 12 tests per market, 24 in all:**
   (1) overnight close location = (last − low) / (high − low) − ½, every day; (2) the same, strong days (|value| above its
   2010–17 median); (3) overnight return, days with overnight volume above its 2010–17 median (volume as the ratio to the
   previous 20 days' mean); (4) overnight return, days with overnight realised variance above its median (same ratio form);
   (5) pre-open return, every day; (6) pre-open return, strong days; (7) pre-open return, days with pre-open volume above median
   (ratio form); (8) previous window close location, every day; (9) the same, strong days; (10) previous window's last-hour
   return, every day; (11) the same, strong days; (12) the overnight return on days the entry price lies OUTSIDE the previous
   window's high–low range (a gap beyond it).
   ~1.2 of 24 pass |t| > 1.96 by chance. D16 (§151) used gold's 11:30 → 03:00 return on strong days; (3) and (4) condition the
   same return on volume and variance instead — related, recorded.
4. **Discovery 2010-06 → 2017-12 only** (asserted); statistic and selection exactly as §149, 4 (sign of the predictor × the
   target demeaned within the period; carried at |t| > 1.96; follow or fade fixed by the sign).
5. **Validation exactly as §149, 5** (sealed 2018-01 → 2026-08; one trial each; (a) against always-long t > 1.645, (b) placebo with
   the predictor shifted ±2…±11 days ≥ 95th pct, (c) posterior > 0 with prior Normal(discovery/2, |discovery|/2), (d) 2021–26
   > 0; CONFIRM / WATCHLIST / REJECT); Z and D market-tests from 34. Bad-print rule of §149 addendum applies.

## 153. Family-4 discovery: six gold tests carried (≈1.2 by chance), all "follow the overnight move"; D22–D27 registered (S1–S5)

**No trial spent at registration; N 797. Committed BEFORE any validation data is read.** `reporting/d4_overnight.py`,
`reports/d4_discovery.json`; `signals/d_overnight.py`; `hypotheses.yaml` D22–D27; catalog. 24 tests, 2010-06 → 2017-12; **all six
carried tests are gold, all follow the overnight move** into the London window; MNQ none (best |t| 1.53).

| id | test | gate | discovery (bps beyond drift a day) | prior |
|---|---|---|---|---|
| D22 | ON_loc | strong | +7.89, t +3.39, n 885 | N(+3.95, 3.95) |
| D23 | ON_ret|vol | ['ON', 'vratio'] | +7.22, t +2.75, n 882 | N(+3.61, 3.61) |
| D24 | ON_loc | None | +4.60, t +2.57, n 1770 | N(+2.30, 2.30) |
| D25 | PRE_ret | strong | +6.68, t +2.29, n 777 | N(+3.34, 3.34) |
| D26 | ON_ret|outside | outside | +6.65, t +2.28, n 757 | N(+3.32, 3.32) |
| D27 | ON_ret|rv | ['ON', 'rvratio'] | +5.53, t +2.04, n 882 | N(+2.77, 2.77) |

**Recorded before the run:** these six are one phenomenon measured six ways, so their validations are strongly correlated —
six passes would be one finding, not six. And D16 (§151) already read gold's 11:30 → 03:00 move on 2018–2026; the sealed window is
not independent of that look. Data: the owned NQ file has full day sessions on only ~72 days of 2011 (an artefact of the original
pull; overnight complete). Z and D market-tests 34–39.

## 154. D22–D27 validated: all six on the watchlist — gold's overnight continuation is real but smaller than gold's drift (S6–S8)

**Six trials spent: t00804–t00809. N 797 → 803.** Injections all recovered. Z and D market-tests 34–39.

| id, trial | rule | days | beyond drift, bps a day | vs always-long | placebo pct | 2018–20 / 2021–26 | tier |
|---|---|---|---|---|---|---|---|
| D22 t00804 | MGC follows ON_loc (strong days) | 1117 | +2.93 (t +1.32) | +0.55 (t +0.17) | 95 | -0.58 / +4.77 | **WATCHLIST** |
| D23 t00805 | MGC follows ON_ret (ON vratio above median) | 1281 | +1.61 (t +0.71) | +4.21 (t +1.31) | 80 | -3.11 / +4.09 | **WATCHLIST** |
| D24 t00806 | MGC follows ON_loc (every day) | 2188 | +3.18 (t +1.92) | +1.90 (t +0.77) | 100 | +1.27 / +4.20 | **WATCHLIST** |
| D25 t00807 | MGC follows PRE_ret (strong days) | 1218 | +0.74 (t +0.30) | -0.88 (t -0.27) | 55 | -5.97 / +3.99 | **WATCHLIST** |
| D26 t00808 | MGC follows ON_ret (entry outside the previous window's range) | 839 | +4.97 (t +1.84) | +3.79 (t +0.95) | 100 | -1.54 / +8.35 | **WATCHLIST** |
| D27 t00809 | MGC follows ON_ret (ON rvratio above median) | 1235 | +0.89 (t +0.38) | +2.22 (t +0.64) | 70 | -1.08 / +1.96 | **WATCHLIST** |

**Reading.** Every measurement of the phenomenon is positive beyond drift on the sealed window (+0.7 to +5.0 bps a day), every
one is positive on 2021–26 alone (+2.0 to +8.4), and three of six place the real rule at the 95th–100th percentile of its
shifted placebos (D22, D24, D26; D24, every day, t +1.92). With D16 (§151) that is seven correlated looks pointing one way:
**gold continues its overnight move into the London window.** None beats always-long (best t +1.31): over 2018–26 gold's drift
(+2.6 bps a day in this window, far more in 2024–26) costs a direction rule its short days. Effect size ~3 bps against a window
SD of ~77 bps — about $10–15 a day on the plan's 8 MGC. **Not adopted** (the strict rule is not met); watchlisted. The
watchlist now holds a coherent family (D13, D16, D22–D27); the bot could shadow-track it as a forward test (§133) at no cost.

## 155. D-series family 5 protocol: the calendar — does the day's place in the week, month or year set a window's direction? (S1)

**No trial spent; N 803. Written and committed BEFORE any calendar statistic is computed.** The user: continue. Families 3–4
asked what the market did before a window; family 5 asks when the window falls. Calendar effects are documented for stock indices
(close to close); not for the plan's six windows, which include Tokyo traded from New York, the London gold window, crude's and
soybeans' sessions. Data: the family-3 window returns (§149; owned Databento for MNQ / MGC, corrected HistData for NKD / DAX,
owned daily bars for MCL, Yahoo daily for ZS), bad-print rule as §149.

1. **Targets:** the six windows, each dated by its New York trading date D as in §149 (NKD by its Tokyo date).
2. **Calendar cells, from the dates alone** (US trading days = weekdays on which MNQ or MCL has a window; a weekday with
   neither is a US holiday): (1)–(5) Monday … Friday; (6) the last trading day of the month; (7) the first three trading days
   of the month; (8) the trading day before a US holiday; (9) the trading day after a US holiday (or after a long weekend);
   (10) the third Friday of the month (equity options expiry); (11) the Monday–Thursday before it (expiry week);
   (12) the last five trading days of a quarter. **12 cells × 6 windows = 72 tests**; ~3.6 pass |t| > 1.96 by chance.
3. **Statistic:** on the cell's days, the target demeaned by its own mean over ALL days in the period (so the cell is measured
   against the market's ordinary day); a rule trades the cell's days LONG if the mean is positive, SHORT if negative, and
   leaves the plan unchanged (always long) on other days. Two-sided t; carried at |t| > 1.96 (§133). Discovery 2010-06 → 2017-12.
4. **Validation exactly as §149, 5** — for a long-cell rule the comparison with always-long is trivially zero, so (a) is read as:
   the cell's raw mean exceeds the market's raw mean on other days, Welch t > 1.645 (a short-cell rule: the direction rule's
   daily difference against always-long, t > 1.645, as before); (b) placebo: the same statistic on the same number of randomly
   drawn days of the same weekday mix, 2,000 draws, real ≥ 95th pct; (c) posterior with prior Normal(discovery/2,
   |discovery|/2); (d) 2021–26 alone in the discovered direction > 0. Z and D market-tests from 40.

## 156. Family-5 discovery: one cell of 72 (fewer than chance) — the calendar sets no direction; D28 registered (S1–S5)

**No trial spent at registration; N 803. Committed BEFORE validation data is read.** `reporting/d5_calendar.py`,
`reports/d5_discovery.json`. 72 tests (12 calendar cells × 6 windows), 2010-06 → 2017-12: **one carried against ~3.6 expected by
chance** — crude's bar dated Monday −23.4 bps against an ordinary day (t −2.33, n 371). Next: MGC Wednesday −8.4 (t −1.82), MCL
quarter's last 5 days +26.4 (t +1.75), ZS month's last day +28.2 (t +1.74). **As a family the calendar holds nothing for these
windows** (the scan found fewer passes than chance).

**Addendum to §155, 4 before validation:** for a WEEKDAY cell the "random days of the same weekday mix" placebo is the cell itself;
(b) becomes: the cell's demeaned mean beats each of the other four weekdays' (D01's other-hours logic). **Flag recorded:** the owned
crude bar dated Monday runs from Friday's close (`data/daily_bars.py`: Sunday bars dropped), so it includes the weekend gap that the
plan, entering Sunday 18:00, does not hold — a Monday effect here may not be tradable even if real. D28 registered (Z and D test 40).

## 157. D28 validated: crude's Monday weakness did not recur — the calendar family closes empty (S6–S8)

**One trial spent: t00810. N 803 → 804.** 431 Mondays, 2018-01 → 2026-08: short-Monday +4.10 bps against an
ordinary day (t +0.28); against always-long t -0.40; Monday does not beat the other weekdays (Tue +15.8, Wed −3.3,
Thu −16.1, Fri −1.1); 2018–20 +21.42, **2021–26 -5.14**. Fails (a), (b) and (d); WATCHLIST only in
form (the pooled mean is above zero). The discovery's −23.4 bps (t −2.33) was the scan's chance pass; family 5 found nothing.
Z and D market-tests: 40.

## 158. D-series family 6 protocol: the opening drive — does a window's first 30 or 60 minutes set the rest of it? (S1)

**No trial spent; N 804. Written and committed BEFORE any data is built.** The user: continue. Families 3–5 asked about information
before a window; this asks about the window's own start. If its first stretch predicts the remainder, the ticket would enter at
the end of that stretch in the predicted direction and close at the window's usual end — the same bracket logic, a later start.
F06 (cash_open_drive_continuation, MNQ, retired) tested a published version for MNQ only; gold's London window, Tokyo and Xetra
are untested.

1. **Windows with intraday data:** MNQ 09:30–16:00 and MGC 03:00–11:30 New York (owned Databento trades; a move whose two prices
   are from different contracts is dropped); NKD 09:00–15:00 Tokyo and DAX 09:00–17:30 Frankfurt (corrected HistData CFD minute
   bars — mid-session prices only; no session close is used except the window's end, as in §149). Crude and soybeans have no
   minute history here and are not tested.
2. **Predictor and target:** prices at the window's start, +30, +60 minutes and end (close of the last 1-minute bar before each
   time). Predictor = start → +k; target = +k → end; k ∈ {30, 60}. Forms: every day; strong days (|predictor| above its 2010–17
   median). **4 markets × 2 k × 2 forms = 16 tests**; ~0.8 pass |t| > 1.96 by chance.
3. **Discovery 2010-06 → 2017-12;** statistic, selection and follow / fade exactly as §149, 4 (target demeaned within period).
4. **Validation exactly as §149, 5** (sealed 2018-01 → 2026-08; one trial each; the always-long baseline is a long position over
   the same remainder +k → end); Z and D market-tests from 41.

## 159. Family-6 discovery: three carried (≈0.8 by chance) — DAX and Nikkei continue their first half hour; D29–D31 registered (S1–S5)

**No trial spent at registration; N 804. Committed BEFORE validation data is read.** `reporting/d6_drive.py`,
`reports/d6_discovery.json`; `signals/d_drive.py`. 16 tests, 2010-06 → 2017-12; **3 carried**, all "follow the first 30 minutes",
in the two non-US windows; MNQ nothing (best |t| 0.75), gold +1.59 at best.

| id | market | predictor | form | discovery (bps beyond drift a day) | prior |
|---|---|---|---|---|---|
| D29 | DAX | first 30 min | all | +5.98, t +2.64, n 1797 | N(+2.99, 2.99) |
| D30 | NKD | first 30 min | strong | +6.00, t +2.16, n 906 | N(+3.00, 3.00) |
| D31 | DAX | first 30 min | strong | +7.67, t +2.11, n 898 | N(+3.84, 3.84) |

D29 and D31 are one effect (every day / strong days). Data: corrected HistData CFD minute bars, mid-session prices plus the
window's end as in §149. Z and D market-tests 41–43.

## 160. D29–D31 validated: the opening drive faded after 2020 — no confirmation (S6–S8)

**Three trials spent: t00811–t00813. N 804 → 807.** Z and D market-tests 41–43.

| id, trial | rule | days | beyond drift, bps a day | vs always-long | placebo pct | 2018–20 / 2021–26 | tier |
|---|---|---|---|---|---|---|---|
| D29 t00811 | DAX follows its first 30 minutes (every day) | 2154 | -0.20 (t -0.11) | -1.48 (t -0.56) | 20 | +2.25 / -1.55 | **REJECT** |
| D30 t00812 | NKD follows its first 30 minutes (strong days) | 1256 | +2.61 (t +1.28) | +3.55 (t +1.26) | 95 | +8.12 / +0.17 | **WATCHLIST** |
| D31 t00813 | DAX follows its first 30 minutes (strong days) | 1023 | +1.19 (t +0.40) | +0.30 (t +0.07) | 35 | +4.16 / -0.44 | **WATCHLIST** |

The opening-drive continuation held in 2018–20 (Nikkei strong days +8.1 bps, t +2.04; DAX +2.3) and is gone in 2021–26 (Nikkei
+0.2, DAX −1.6). D30 keeps a 95th-percentile placebo on the pooled window but fails (a) and stands on its first three years.
Watchlist for D30 and D31 in form; nothing to adopt.

## 161. D-series family 7 protocol: London continuation beyond gold — silver and the major currencies (S1)

**No trial spent; N 807. Written and committed BEFORE any data is built.** The user: continue. Six families found one
phenomenon that held in every look and grew stronger after 2021 — gold continues its overnight move (11:30 → 03:00 New York)
into the London window (03:00 → 11:30) (D16, D22–D27; §151, §154) — and failed only against gold's own drift. **A hypothesis
generated from the programme's own data:** the same London continuation in markets without gold's drift, where a direction rule
does not have to beat a rally.

1. **Markets** (free HistData minute bars, corrected clock §140; prices at 11:30 and 03:00 New York only — neither is a session
   close for these markets; the 17:00 rollover falls inside the predictor's span and is never used as a price): silver XAG/USD
   (SI / SIL), EUR/USD (6E / M6E), GBP/USD (6B), AUD/USD (6A / M6A), USD/JPY (6J), USD/CHF (6S), USD/CAD (6C). All tradable as CME
   futures in the account (decisions.md 115).
2. **Target:** the window 03:00 → 11:30 New York (the plan's gold window). **Predictors:** (i) the market's own overnight move,
   11:30 (previous day) → 03:00; (ii) gold's overnight move (MGC_pre, owned Databento trades, §149). Forms: every day; strong days
   (|predictor| above its 2010–17 median). **7 markets × 2 predictors × 2 forms = 28 tests**; ~1.4 pass |t| > 1.96 by chance.
3. **Discovery 2010-06 → 2017-12;** statistic and selection exactly as §149, 4. **Validation exactly as §149, 5;** Z and D
   market-tests from 44. Note: families 1–2 (§130, §134) scanned these pairs' hours and fix windows on 2010–17 and validated
   single cells on 2018–26; the statistic here (a window's direction set by the preceding move) was not computed there.

## 162. Family-7 discovery: silver continues its own and gold's overnight move — five carried (≈1.4 by chance); D32–D36 registered (S1–S5)

**No trial spent at registration; N 807. Committed BEFORE validation data is read.** `reporting/d7_london.py`,
`reports/d7_discovery.json`; `signals/d_london.py`. 28 tests, 2010-06 → 2017-12; **5 carried, 4 of them silver** — the gold finding
reappears in silver at two to three times its size relative to the window (silver's window SD ~141 bps):

| id | market | rule | form | discovery (bps beyond drift a day) | prior |
|---|---|---|---|---|---|
| D32 | xagusd (SI) | follow own overnight | strong | +17.40, t +3.60, n 977 | N(+8.70, 8.70) |
| D33 | xagusd (SI) | follow gold overnight | all | +12.37, t +3.34, n 1364 | N(+6.18, 6.18) |
| D34 | xagusd (SI) | follow gold overnight | strong | +18.47, t +3.19, n 682 | N(+9.23, 9.23) |
| D35 | usdchf (6S) | fade gold overnight | all | -2.83, t -2.21, n 1363 | N(+1.41, 1.41) |
| D36 | xagusd (SI) | follow own overnight | all | +6.67, t +2.20, n 1954 | N(+3.34, 3.34) |

The currencies show nothing but USD/CHF fading gold's move (t −2.21). Silver's four tests are one phenomenon; correlated. USD/JPY data
here start 2016. Z and D market-tests 44–48.

## 163. D32 CONFIRMS: silver's London window follows its own strong overnight move (S6–S8)

**Five trials spent: t00814–t00818. N 807 → 812.** Z and D market-tests 44–48.

| id, trial | rule | days | beyond drift, bps a day | vs always-long | placebo pct | 2018–20 / 2021–26 | tier |
|---|---|---|---|---|---|---|---|
| D32 t00814 | xagusd London window follows its own overnight move (strong days) | 1132 | +9.07 (t +1.93) | +14.07 (t +2.06) | 100 | +6.55 / +10.08 | **CONFIRM** |
| D33 t00815 | xagusd London window follows gold's overnight move (every day) | 2088 | +2.57 (t +0.82) | +3.97 (t +0.87) | 85 | +2.57 / +2.57 | **WATCHLIST** |
| D34 t00816 | xagusd London window follows gold's overnight move (strong days) | 944 | +11.50 (t +2.27) | +12.27 (t +1.60) | 100 | +6.94 / +13.57 | **WATCHLIST** |
| D35 t00817 | usdchf London window fades gold's overnight move (every day) | 2083 | -0.12 (t -0.14) | +0.58 (t +0.46) | 40 | -1.65 / +0.72 | **REJECT** |
| D36 t00818 | xagusd London window follows its own overnight move (every day) | 2181 | +6.63 (t +2.16) | +7.23 (t +1.64) | 100 | +2.38 / +8.96 | **WATCHLIST** |

**D32 meets the strict rule on sealed data** — silver (XAG/USD), 03:00 → 11:30 New York, in the direction of its own move from the
previous 11:30, on days that move exceeds its 2010–17 median (≈ half of days): against always-long +14.07 bps a day (t +2.06);
placebo 100th percentile; posterior +8.99; 2018–20 +6.55, **2021–26 +10.08**. Reported against the running count: the 48th Z and D
market-test, with no multiple-testing cut (the user's rule, §133). Its siblings: D36 (every day) t +1.64 against always-long,
D34 (gold's move, strong days) t +1.60 — both short of 1.645 by a hair, placebo 100th, stronger after 2021; D33 weaker; USD/CHF
(D35) rejected.

**Not yet adopted. Before any use:** (1) the validation used free bid quotes — the effect must be checked on traded silver futures
(D03's lesson, §144); (2) silver is not one of the plan's accounts — its value in the plan (a silver account in place of the
weakest, at the risk-matched size, the rule on strong days and long otherwise) must be replayed before anything changes.

## 164. D32 checked on real silver futures and replayed in the plan: real, but too small to move the brackets (S8)

**No trial spent; N 812.** `reporting/a26_silver.py`, `reports/a26_silver.json`.

**Real futures.** COMEX silver (Yahoo SI=F hourly, 2024-05 → 2026-10, contract-switch hours dropped; the window ends at 11:00 or
12:00 as hourly bars allow): the D32 rule earns **+15.9 bps a day beyond drift (t +1.59)** to 11:00 and **+24.0 (t +2.17)** to 12:00;
against always-long +14.7 (t +0.98) / +19.7 (t +1.18). The free bid-quote series on the same span: +18.5 (t +1.95). Same sign and
size on traded prices — **not a quote artefact** (contrast D03, §144).

**In the plan** (A23 engine; a silver London-window account, 3 SIL — one SIL $61k, window SD $958, swing $2,874; drift removed so
only skill beyond drift is credited; the rule short on 23–26% of days, acting on 48–57%):

| 84 days, per account | 2010–20 (rule in sample) | 2021–26 (out of sample) |
|---|---|---|
| silver, always long | 60%, +$1,440, P(net > 0) 49% | 80%, **+$1,865**, 71% |
| silver with D32 | 63%, +$1,574, 53% | 77%, +$1,684, 63% |

| five accounts, per four months | 2010–20 | 2021–26 |
|---|---|---|
| 5 live (crude) | +$8,023, 92% | +$9,468, 93% |
| silver always long for crude | **+$9,563, 91%** | **+$10,375, 96%** |
| silver with D32 for crude | +$8,361, 87% | +$10,179, 94% |
| 5 with soybeans for crude (§140) | +$8,907, 88% | +$12,499, 98% |

**Reading.** D32 adds ~9–14 bps a day on the days it acts — about $15–20 a day on 3 SIL — against brackets of ±$1,000–1,200 that
resolve within hours. The bracket's take-or-stop is decided by the path, the rule predicts the window's end-to-end drift, and at this
size the drift does not move the hit rates (Z02's lesson, §89: an edge must be large against the daily swing on the days it is
held). **D32 stands as a confirmed edge; it is not adopted into the plan.** Side finding: silver's London window, always long, beat
crude as the fifth account in both histories (+$0.9–1.5k per four months), but its window correlates +0.77–0.81 with gold's, and
soybeans in crude's place remains the better swap in 2021–26.

## 165. A27: D32 as a standalone strategy cannot carry a Tradeify account — what "standalone" has to mean here (S8)

**No trial spent; N 812.** `reporting/a27_standalone.py`, `reports/a27_standalone.json`; A23's replay gains `skip` (days the
strategy sits out: no cost, no breach) and `fixed` (net brackets every traded day; defaults reproduce the live engine). The user:
standalone strategies count too, not only overlays on the plan. D32 on its own 50K Daily account, 3 SIL, 84-day replay:

| 2021–26 (out of sample), drift removed / real | P(payout) | mean net | P(net > 0) |
|---|---|---|---|
| S1 D32 days only, the plan's solver brackets | 53% / 53% | +$1,551 / +$1,625 | 53% |
| S2 D32 days only, hold to 11:30, stop $1,000 | 1% / 1% | −$917 / −$921 | 1% |
| S3 D32 days only, hold to 11:30, stop $600 | 5% / 4% | −$435 / −$462 | 4–5% |
| B same days ALWAYS LONG, hold, stop $1,000 | 5% / 5% | −$697 / −$711 | 5% |
| S4 every day, D36's direction, hold, $1,000 | 12% / 12% | −$1,283 / −$1,288 | 6% |

(2010–20: the same pattern; S1 +$1,018 / +$871.) Holding the window to capture the drift fails the evaluation over and over —
a position swinging ±$2,900 a day meets the $2,000 trailing floor long before a +$3,000 target; the rule improves the hold variants
only marginally over the no-skill baseline (B). Only the staking brackets (S1) make the account pay, and they do so at the
zero-edge plan's rate.

**What "standalone" has to mean in this account.** §91: a payout within one to two months needs a strategy Sharpe of ~5 a year; D32
is ~0.7–1 (about 0.06–0.09 standard deviations per traded day). A strategy carries a Tradeify account on its own only if its edge
per day is large against its own daily swing — which, at ~one trade a day, means a Sharpe several times anything this programme
has measured. Sharpe grows with the square root of the number of independent trades, so a standalone search should look for
**many small, independent trades a day** (intraday, minute-level, owned trade data), each with a modest edge — not one daily hold.

## 166. D-series family 8 protocol: short-horizon reactions to large intraday moves — many trades a day, for standalone use (S1)

**No trial spent; N 812. Written and committed BEFORE any data is built.** §165: a standalone strategy needs many independent
trades a day, each with an edge after costs. The programme's one robust finding is CONTINUATION after information arrives
(gold and silver into London); this family asks the same at minutes: after an unusually large move, does the market continue or
reverse over the next minutes, and does it depend on volume?

1. **Data:** owned Databento 1-minute TRADES, MNQ (NQ/MNQ spliced) and MGC; a return is used only if its bars are of one contract
   and consecutive in time. Discovery **2013-01 → 2017-12** (MNQ's day sessions are complete from 2013, §153); validation
   **2018-01 → 2026-08**, sealed.
2. **Sessions:** MNQ day 09:30–16:00 and night 18:00–09:30; MGC London 03:00–11:30 and Asia 18:00–03:00 (New York time).
3. **Event at a minute's close t:** |r_k(t)| > 2 σ_k, where r_k is the k-minute return (k ∈ {5, 15, 30}) and σ_k the standard
   deviation of k-minute returns in the same session over the previous 20 sessions. **Volume condition:** the k minutes' volume
   relative to the mean k-minute volume of the same session over the previous 20 sessions — high (> 1) or low (≤ 1).
4. **Trade:** enter at t's close in the direction of the move (follow) or against it (fade), exit after h ∈ {5, 15, 30} minutes or at
   the session's end if sooner; **no overlap** (events during an open trade are ignored). Cost per round trip: MNQ $2.32 + one tick
   ($0.50) = 1.41 points; MGC $3.32 + one tick ($1.00) = 0.432 points.
5. **Tests:** 2 markets × 2 sessions × 3 k × 2 volume conditions × 3 h = **72**; ~3.6 pass by chance. Statistic: net points per
   trade, follow direction (a fade is its negative before costs — computed separately, net of costs, so each test is follow OR fade
   by the sign of the GROSS follow mean); t from day-clustered sums. **Carried:** |t| > 1.96 AND net mean > 0 after costs.
6. **Validation (one trial each):** CONFIRM if (a) net mean per trade > 0 with day-clustered t > 1.645; (b) placebo: real net mean
   at or above the 95th percentile of 1,000 draws of the same number of trades entered at random minutes of the same sessions, same
   h and direction rule (direction = the random minute's own k-move sign); (c) posterior > 0, prior Normal(discovery/2,
   |discovery|/2); (d) 2021–26 alone > 0. WATCHLIST if net > 0 otherwise; REJECT. Any CONFIRM is then replayed as its own 50K
   Daily account (A27's engine) before it counts as usable.

## 167. Family-8 discovery: no short-horizon reaction beats its costs — 0 of 72 carried (S1)

**No trial spent; N 812.** `reporting/d8_intraday.py` (minute grids per session, 2010–2026, cached), `reports/d8_discovery.json`.
72 tests, 2013-01 → 2017-12: **none carried** (|t| > 1.96 with net > 0 after costs). The largest gross effects are reversals after
LOW-volume moves in gold — 0.2–0.37 points before costs against 0.432 points a round trip — and every MNQ cell loses about its
cost (e.g. after a 5-minute 2σ move on high volume, 10,421 trades, net −1.37 points, t −23). **At one-minute resolution, price
and volume reactions in MNQ and gold are smaller than a tick plus commission;** a many-trades-a-day standalone strategy would need
information this data does not carry (the order book, order flow). Nothing to validate; no trial spent.

## 168. D-series family 9 protocol: drift after scheduled releases — does the first reaction predict the rest of the day? (S1)

**No trial spent; N 812. Written and committed BEFORE any event or return is computed.** §165–167: a standalone strategy needs
moves that are large on the days it trades; minute reactions on ordinary days are below costs. The largest information events
in these markets are scheduled: US releases at 08:30 New York (CPI, payrolls, PPI, retail sales, claims) and Fed decisions at
14:00. Question: does the first 5 or 15 minutes after the release predict the move over the rest of the session?

1. **Data:** the family-8 minute grids (owned Databento trades): MNQ night (to 09:30) and day (09:30–16:00); MGC London
   (03:00–11:30). Discovery **2013-01 → 2017-12**; validation **2018-01 → 2026-08**, sealed.
2. **Release days, from the data alone:** an 08:30 day is one whose 08:30–08:35 volume exceeds 3× the median volume of those
   five minutes over the previous 20 sessions — in MNQ for the MNQ tests, in MGC for the MGC tests. A 14:00 day: MNQ's 14:00–14:05
   volume over 3× its 20-session median. (Detected, not looked up; recorded counts are reported.)
3. **Tests:** predictor = the move from the release minute to +k, k ∈ {5, 15}; target = +k → session end — MNQ 08:30: to 16:00
   (night and day grids joined; one contract required); MGC 08:30: to 11:30; MNQ 14:00: to 16:00. Forms: every release day; strong
   (|predictor| above its 2013–17 median). **3 event types × 2 k × 2 forms = 12 tests**; ~0.6 pass by chance.
4. **Statistic and selection:** sign(predictor) × target in points, demeaned within period; follow / fade by sign; carried at
   |t| > 1.96 AND the rule's mean minus a round-trip cost (MNQ 1.41 pts, MGC 0.432 pts) > 0.
5. **Validation (one trial each):** CONFIRM if (a) the rule's net mean per trade (after cost) > 0, t > 1.645; (b) placebo: real
   at or above the 95th percentile of the same rule on 1,000 random draws of non-release days at the same clock times; (c) posterior
   > 0, prior Normal(discovery/2, |discovery|/2); (d) 2021–26 alone > 0. Any CONFIRM is then replayed as its own 50K Daily
   account (A27 engine) before it counts as usable. Z and D market-tests from 49.

## 169. Family-9 discovery: gold fades its first reaction to 08:30 releases — two carried (≈0.6 by chance); D37–D38 registered (S1–S5)

**No trial spent at registration; N 812. Committed BEFORE validation data is read.** `reporting/d9_events.py`,
`reports/d9_discovery.json`; `signals/d_events.py`. **Bug found and fixed before any result was used:** the family-8 grids numbered
contracts separately in each session file, so the MNQ 08:30 test (night and day grids joined) saw false contract changes and kept 18
of 187 release days; contracts are now coded year × 12 + month in every grid (`d8_intraday.build`), grids rebuilt, scan re-run
(family 8's single-grid tests are unaffected). Release days detected 2013–17: MNQ 08:30 189, MGC 08:30 239, MNQ 14:00 107.

| id | event | predictor | form | rule | discovery | prior |
|---|---|---|---|---|---|---|
| D37 | MGC 08:30 | first 15 min | all | fade | -0.93 pts, t -2.07, n 239; net +0.50 | N(+0.46, 0.46) |
| D38 | MGC 08:30 | first 5 min | all | fade | -0.97 pts, t -1.99, n 239; net +0.54 | N(+0.49, 0.49) |

MNQ shows nothing at 08:30 or 14:00 (best t +1.18). D37 and D38 are one effect. Economics are thin: ~0.5 points net a trade is
~$40 on 8 MGC, ~48 release days a year. Z and D market-tests 49–50.

## 170. D37–D38 validated: gold's release-day fade did not recur — rejected (S6–S8)

**Two trials spent: t00819–t00820. N 812 → 814.** Z and D market-tests 49–50.

| id, trial | rule | release days | net pts a trade (t) | placebo pct | 2018–20 / 2021–26 | tier |
|---|---|---|---|---|---|---|
| D37 t00819 | MGC 08:30: MGC fades its first 15 minutes to the session end (every release day) | 278 | -0.27 (t -0.37) | 56 | -1.26 / +0.35 | **REJECT** |
| D38 t00820 | MGC 08:30: MGC fades its first 5 minutes to the session end (every release day) | 278 | -0.76 (t -0.98) | 48 | -1.63 / -0.22 | **REJECT** |

The discovery's fade (t −2.07 / −1.99, ~0.5 points net) was a chance pass; on 2018–26 the rule loses after costs and sits mid-pack
among random non-release days. Family 9 is empty.

## 171. D-series family 10 protocol: the cross-market daily universe — does yesterday's session in one market set today's direction in another? (S1)

**No trial spent; N 814. Written and committed BEFORE any data is fetched.** The user: continue; and a strategy that keeps an
account for a few months and pays out before it fails is a win — the 84-day back-to-back replay (payouts minus every fee, failed
accounts replaced) already measures exactly that. Family 3 tested hand-offs between the plan's six windows; this widens the net
to 14 CME futures, every pair.

1. **Universe** (Yahoo daily bars, 2010 → 2026; the session's open → settlement return within one bar, so a roll never enters):
   ES, NQ (indices); GC, SI, HG (metals); CL, NG (energy); ZN (10-year notes); 6E, 6J (currencies); ZC, ZS, ZW (grains); and RTY.
   Every Globex session closes before the next one opens, so the predictor (the previous trading day's session) has finished.
   Bad prints: the §149 15-robust-SD rule per series. Yahoo daily bars for some metals are day-session bars (§140); a session is
   whatever Yahoo's bar spans, used consistently as both predictor and target.
2. **Tests:** every ordered pair (target ≠ predictor): **14 × 13 = 182**, every day (no strong form — the family is wide);
   ~9 pass |t| > 1.96 by chance. Statistic as §149, 4 (sign of the predictor × the target demeaned within the period; follow or fade
   by the sign); **carried at |t| > 1.96**. Discovery 2010-01 → 2017-12.
3. **Validation exactly as §149, 5** (sealed 2018-01 → 2026-08; against always-long t > 1.645; placebo with the predictor shifted
   ±2…±11 days ≥ 95th pct; posterior > 0; 2021–26 > 0). Any CONFIRM is replayed as its own 50K Daily account (one-bar paths,
   §116) before it counts. Z and D market-tests from 51.

## 172. Family-10 discovery: 7 of 182 pairs carried — fewer than chance (~9); D39–D45 registered anyway, per protocol (S1–S5)

**No trial spent at registration; N 814. Committed BEFORE validation data is read.** `reporting/d10_universe.py`,
`reports/d10_discovery.json`; `signals/d_universe.py`. 182 ordered pairs, 2010-01 → 2017-12; **7 carried against ~9.1 expected by
chance** — as a family the daily cross-market universe shows no excess signal. Validated per §171 regardless:

| id | target | rule | previous session of | discovery (bps beyond drift a day) | prior |
|---|---|---|---|---|---|
| D39 | ZN | follow | ES | +2.09, t +3.04, n 1935 | N(+1.04, 1.04) |
| D40 | HG | fade | NG | -7.35, t -2.84, n 1937 | N(+3.68, 3.68) |
| D41 | ZN | fade | 6J | -1.65, t -2.41, n 1935 | N(+0.83, 0.83) |
| D42 | NG | follow | SI | +10.71, t +2.24, n 1936 | N(+5.36, 5.36) |
| D43 | ZS | follow | ES | +5.77, t +2.01, n 1937 | N(+2.89, 2.89) |
| D44 | GC | follow | ZN | +3.98, t +1.99, n 1935 | N(+1.99, 1.99) |
| D45 | RTY | fade | ES | -11.72, t -1.98, n 119 | N(+5.86, 5.86) |

RTY's Yahoo history starts in 2017 (D45: 119 discovery days). Z and D market-tests 51–57.

## 173. D39–D45 validated: no confirmation; the Russell fading the S&P (D45) is the one strong out-of-sample pattern (S6–S8)

**Seven trials spent: t00821–t00827. N 814 → 821.** Z and D market-tests 51–57.

| id, trial | rule | days | beyond drift, bps a day | vs always-long | placebo pct | 2018–20 / 2021–26 | tier |
|---|---|---|---|---|---|---|---|
| D39 t00821 | ZN follows the previous session of ES | 2098 | +0.93 (t +1.25) | +1.51 (t +1.40) | 75 | +1.25 / +0.76 | **WATCHLIST** |
| D40 t00822 | HG fades the previous session of NG | 2096 | -1.11 (t -0.43) | -5.20 (t -1.40) | 45 | +1.49 / -2.50 | **REJECT** |
| D41 t00823 | ZN fades the previous session of 6J | 2099 | +0.92 (t +1.24) | +1.46 (t +1.46) | 100 | +0.63 / +1.07 | **WATCHLIST** |
| D42 t00824 | NG follows the previous session of SI | 2092 | +2.19 (t +0.31) | +7.64 (t +0.73) | 50 | -1.29 / +4.04 | **WATCHLIST** |
| D43 t00825 | ZS follows the previous session of ES | 2096 | +1.29 (t +0.51) | +0.42 (t +0.12) | 85 | -1.67 / +2.86 | **WATCHLIST** |
| D44 t00826 | GC follows the previous session of ZN | 2097 | -1.98 (t -0.92) | -3.44 (t -1.11) | 20 | +2.41 / -4.31 | **REJECT** |
| D45 t00827 | RTY fades the previous session of ES | 2098 | +7.34 (t +2.26) | +0.14 (t +0.03) | 100 | +3.64 / +9.31 | **WATCHLIST** |

As the discovery count predicted (fewer passes than chance), most did not hold. **D45** — RTY's session against the previous S&P
session — is the exception: +7.34 bps a day beyond drift (t +2.26), placebo 100th percentile, stronger in 2021–26 (+9.31); it fails
only against always-long (t +0.03), because shorting the Russell after S&P up-days costs its drift. Its discovery sample was 119
days (RTY's Yahoo history from 2017), so the 2018–26 result is most of the evidence. D41 (10-year notes fading the yen) holds a
100th-percentile placebo at +0.9 bps — too small to matter. Watchlist for D39, D41, D42, D43, D45.

## 174. D-series family 11 protocol: commodity seasonality — standalone, daily round trips, net of each market's cost (S1)

**No trial spent; N 821. Written and committed BEFORE any monthly statistic is computed.** The user: keep searching on the data
we have (a year of order-book data, $369, waits until the props pay); standalone strategies count, and an account that pays a few
times before failing is a win. Commodities carry seasonal supply and demand (heating, driving, planting, harvest); this family
asks whether any market drifts reliably in a calendar month — **as a standalone strategy**, so judged against not trading.

1. **Markets and data:** CL, NG, ZC, ZS, ZW, GC, SI, HG — Yahoo daily bars (fetched, §140, §171), each session's open → settlement
   return (one bar, one contract; the account must be flat 17:00–18:00, so a strategy is a daily round trip). Bad prints: §149 rule.
2. **Cost per day (round trip at the account's tradable size, bps of notional):** CL (full) 0.7, NG (full) 1.4, ZC 1.9, ZS 0.7,
   ZW 1.4, GC via MGC 0.8, SI via SIL 0.5, HG via MHG 2.0.
3. **Tests:** market × calendar month = **96**; ~4.8 pass by chance. Statistic: the mean RAW session return on that month's days
   (standalone: drift counts), t over days. **Carried:** |t| > 1.96 AND |mean| > the day's cost. Direction = the sign.
   Discovery 2010-01 → 2017-12.
4. **Validation (one trial each), sealed 2018-01 → 2026-08:** CONFIRM if (a) the rule's net mean per day (direction × return −
   cost) > 0 with t > 1.645 — **against not trading**; (b) placebo: real ≥ 95th percentile of 1,000 draws of the same number of
   the market's days from OTHER months, same direction and cost; (c) posterior > 0, prior Normal(discovery/2, |discovery|/2);
   (d) 2021–26 alone > 0. WATCHLIST if net > 0 otherwise; REJECT. A CONFIRM is replayed as its own 50K Daily account (one-bar
   paths, trading only that month, payouts before failure counted) before it counts as usable. Z and D market-tests from 58.

## 175. Family-11 discovery: seven seasonal cells (≈4.8 by chance) with 15–35 bps a session net; D46–D52 registered (S1–S5)

**No trial spent at registration; N 821. Committed BEFORE validation data is read.** `reporting/d11_season.py`,
`reports/d11_discovery.json`; `signals/d_season.py`. 96 tests, 2010-01 → 2017-12; **7 carried** — per-session effects several
times larger than any earlier family (standalone, drift counted, net of cost):

| id | market | month | direction | discovery (bps a session) | prior |
|---|---|---|---|---|---|
| D46 | ZS | Apr | long | +23.12, t +2.85, n 165; net +22.42 | N(+11.56, 11.56) |
| D47 | ZS | Oct | long | +24.01, t +2.34, n 173; net +23.31 | N(+12.01, 12.01) |
| D48 | NG | Oct | short | -36.54, t -2.25, n 173; net +35.14 | N(+18.27, 18.27) |
| D49 | HG | Dec | long | +19.32, t +2.23, n 169; net +17.32 | N(+9.66, 9.66) |
| D50 | ZC | Oct | long | +26.47, t +2.14, n 173; net +24.57 | N(+13.23, 13.23) |
| D51 | CL | Apr | long | +28.97, t +2.10, n 165; net +28.27 | N(+14.49, 14.49) |
| D52 | HG | Mar | short | -17.44, t -1.98, n 176; net +15.44 | N(+8.72, 8.72) |

Each cell rests on ~8 Octobers / Aprils (~20 sessions each); a cell can be one or two big years — the by-year breakdown is part
of the validation report. Z and D market-tests 58–64.

## 176. D46–D52 validated: no confirmation; long grains in October is the near-miss (S6–S8)

**Seven trials spent: t00828–t00834. N 821 → 828.** Z and D market-tests 58–64. Standalone, net of cost, against not trading:

| id, trial | rule | sessions | net bps a session (t) | placebo pct | 2018–20 / 2021–26 | years positive | tier |
|---|---|---|---|---|---|---|---|
| D46 t00828 | ZS long every session in Apr | 187 | +0.46 (t +0.06) | 58 | -13.46 / +7.53 | 5 of 9 | **WATCHLIST** |
| D47 t00829 | ZS long every session in Oct | 178 | +9.35 (t +1.35) | 92 | +8.90 / +9.63 | 7 of 8 | **WATCHLIST** |
| D48 t00830 | NG short every session in Oct | 178 | -0.46 (t -0.02) | 40 | -53.68 / +32.43 | 3 of 8 | **REJECT** |
| D49 t00831 | HG long every session in Dec | 168 | +1.93 (t +0.22) | 52 | +3.10 / +1.25 | 4 of 8 | **WATCHLIST** |
| D50 t00832 | ZC long every session in Oct | 178 | +13.51 (t +1.64) | 90 | +18.19 / +10.62 | 7 of 8 | **WATCHLIST** |
| D51 t00833 | CL long every session in Apr | 185 | +0.13 (t +0.00) | 55 | +26.87 / -13.02 | 5 of 9 | **WATCHLIST** |
| D52 t00834 | HG short every session in Mar | 196 | -6.85 (t -0.65) | 43 | +8.39 / -14.23 | 5 of 9 | **REJECT** |

**D50 — corn long every October session** — is the near-miss: +13.5 bps a session net (t +1.64 against 1.645), positive in 7 of 8
Octobers, both halves positive (+18.2, +10.6); placebo 90th percentile (needs 95). D47 (soybeans, October) +9.4, 6 of 8 years.
Both are the harvest-low pattern (grains bottom near harvest and recover). The other cells were driven by a few years (natural
gas October: −118 to +98 by year; soybeans April and copper December lost their sign after 2021). Watchlist: D46, D47, D49,
D50, D51. A month-long effect gives ~20 sessions a year — Octobers of 2026–27 are the forward test.

## 177. D-series family 12 protocol: after an extreme session — follow-through or reversal over the next 1–5 sessions (S1)

**No trial spent; N 828. Written and committed BEFORE any event is computed.** The user: continue; no deploy; **no strategy that
works only part of the year** (seasonal cells §176 are not candidates for use). Large moves occur in every month; this family
asks whether the session after an unusually large move — or the next three or five — continues or reverses it, as a
standalone strategy.

1. **Universe and data:** the 14 futures of §171 (Yahoo daily, open → settlement, one contract; daily round trips — the account
   is flat 17:00–18:00); bad-print rule as §149.
2. **Event:** a session whose return exceeds 2 σ in absolute value, σ the SD of the market's previous 60 session returns.
   **Trade:** the next h sessions, h ∈ {1, 3, 5}, each open → settlement, in the event's direction (follow) or against it (fade);
   events inside an open trade are ignored (no overlap). **Cost a session (bps, the account's tradable contract):** ES (MES) 0.9,
   NQ (MNQ) 0.5, RTY (M2K) 2.0, GC (MGC) 0.8, SI (SIL) 0.5, HG (MHG) 2.0, CL 0.7, NG 1.4, ZN 0.4, 6E 0.3, 6J 0.5, ZC 1.9, ZS 0.7,
   ZW 1.4. **Tests: 14 × 3 = 42**; ~2.1 pass by chance.
3. **Discovery 2010-01 → 2017-12:** statistic = the trade's net return (sum over its h sessions, minus h costs), follow or fade by
   the sign of the gross follow mean; t over events. **Carried:** |t| > 1.96 AND net mean > 0.
4. **Validation (one trial each), sealed 2018-01 → 2026-08:** CONFIRM if (a) net mean per trade > 0, t > 1.645 (against not
   trading); (b) placebo: real ≥ 95th percentile of 1,000 draws of the same number of trades started on random non-event
   sessions, direction from that session's own sign; (c) posterior > 0, prior Normal(discovery/2, |discovery|/2); (d) 2021–26
   > 0. A CONFIRM is replayed as its own 50K Daily account before it counts. Z and D market-tests from 65.

## 178. Family-12 discovery: equity indices reverse extreme sessions over the next week — three carried (≈2.1 by chance); D53–D55 registered (S1–S5)

**No trial spent at registration; N 828. Committed BEFORE validation data is read.** `reporting/d12_extreme.py`,
`reports/d12_discovery.json`; `signals/d_extreme.py`. 42 tests, 2010-01 → 2017-12; 3 carried:

| id | market | rule | horizon | trades | discovery | prior |
|---|---|---|---|---|---|---|
| D53 | NQ | fade | next 5 | 86 | +68.04 net, t +2.78 | N(+34.02, 34.02) |
| D54 | ES | fade | next 5 | 72 | +60.78 net, t +2.63 | N(+30.39, 30.39) |
| D55 | ZN | fade | next 1 | 94 | +7.99 net, t +2.21 | N(+3.99, 3.99) |

D53 and D54 are one effect (Nasdaq and S&P correlate ~0.9). A multi-session trade is a run of daily round trips (flat each
evening, as the account requires). Z and D market-tests 65–67.

## 179. D53–D55 validated: the reversal after extreme index sessions did not survive — family 12 empty (S6–S8)

**Three trials spent: t00835–t00837. N 828 → 831.** Z and D market-tests 65–67.

| id, trial | rule | trades | net bps a trade (t) | placebo pct | 2018–20 / 2021–26 | tier |
|---|---|---|---|---|---|---|
| D53 t00835 | NQ fades a 2-sigma session over the next 5 | 92 | -23.25 (t -0.72) | 30 | -50.77 / -9.26 | **REJECT** |
| D54 t00836 | ES fades a 2-sigma session over the next 5 | 86 | -18.84 (t -0.47) | 35 | -35.83 / -9.26 | **REJECT** |
| D55 t00837 | ZN fades a 2-sigma session over the next 1 | 118 | -1.15 (t -0.28) | 37 | +10.46 / -7.34 | **REJECT** |

The 2010–17 "buy the extreme, sell the extreme" week (+68 / +61 bps net) reversed sign on 2018–26 in both halves. Nothing to adopt.

## 180. D-series family 13 protocol: volatility regimes — recent-period discovery (2018–22), sealed 2023 → 2026-08 (S1)

**No trial spent; N 831. Written and committed BEFORE any regime statistic is computed.** §179 note: nearly everything found on
2010–17 weakened or flipped on 2018–26 — the markets the user will trade behave like the recent years, not the early 2010s. The
user approved (2026-10-13) a change of design for NEW questions: **discovery 2018-01 → 2022-12; validation 2023-01 → 2026-08,
sealed**. Disclosed: the family-3/4 validations (§151, §154) read these windows' 2018–26 returns for unconditioned statistics; the
regime-conditioned statistic here was not computed.

1. **Windows and predictors** (family-3 series, §149, bad-print rule): NKD, DAX, MGC, MNQ windows — predictors their own previous
   window and their own pre-window move (NKD 15:00 → 09:00 Tokyo, DAX 17:30 → 09:00, MGC 11:30 → 03:00, MNQ 16:00 → 09:30); MCL and
   ZS sessions — predictor their own previous session. **10 predictor pairs.**
2. **Regime, from the target's own past only:** σ20 = SD of its previous 20 window returns; HIGH if σ20 is above the median of
   σ20 over its previous 250 sessions, else LOW. **10 pairs × 2 regimes = 20 tests**; ~1 pass |t| > 1.96 by chance.
3. **Discovery statistic** as §149, 4 (sign of the predictor × the target demeaned within the period), within the regime's days;
   follow or fade by the sign; carried at |t| > 1.96.
4. **Validation (one trial each), sealed:** CONFIRM if (a) **against not trading**: direction × raw return − the account's cost a
   day (bps: MNQ 0.5, MGC 0.8, MCL 5.4 — ten micros, NKD 0.2, DAX 0.3, ZS 0.7) has mean > 0 with t > 1.645 (against always-long
   reported beside it); (b) placebo, predictor shifted ±2…±11 days, ≥ 95th pct; (c) posterior > 0, prior Normal(discovery/2,
   |discovery|/2); (d) S8 has no separate half here — the sealed window IS the recent period; (d) becomes: positive in at least 3 of
   the 4 calendar years 2023–2026. WATCHLIST if net > 0 otherwise; REJECT. Z and D market-tests from 68.

## 181. Family-13 discovery: no volatility-regime pattern — 0 of 20 carried (S1)

**No trial spent; N 831.** `reporting/d13_regime.py`, `reports/d13_discovery.json`. 20 tests on 2018-01 → 2022-12; **none carried**
(best: gold's window FADING its pre-window move in high-volatility stretches, −4.9 bps, t −1.66 — the opposite of the 2010–17
continuation, §154). Conditioning the six windows' hand-offs on recent volatility finds nothing; family 13 is empty.

## 182. D-series family 14 protocol: hour-of-day drift on traded MNQ and gold, recent-period design (S1)

**No trial spent; N 831. Written and committed BEFORE any hourly statistic is computed.** The user approved this order
(2026-10-13). Families 1–2 scanned hours on free FX / CFD quotes; this scans the plan's two traded-data markets, with §180's
recent-period design (discovery 2018-01 → 2022-12; validation 2023-01 → 2026-08, sealed).

1. **Data:** the family-8 minute grids (owned Databento trades; contract-consistent, §169): MNQ day 09:30–16:00 and night
   18:00–09:30; MGC London 03:00–11:30 and Asia 18:00–03:00 (New York). **Cells:** each clock hour of each session starting on the
   hour or the session start (the last may be shorter): MNQ day 7, MNQ night 16, MGC London 9, MGC Asia 9 = **41 tests**, every
   weekday; ~2 pass by chance. Return = close at the hour's end ÷ close at its start (one contract) − 1.
2. **Standalone, net of cost a round trip** (bps, one contract): MNQ 0.56 ($2.32 + one tick on ~$50k), MGC 1.0 ($3.32 + one tick on
   ~$42k). **Carried:** |t| > 1.96 AND |mean| > cost; direction = the sign.
3. **Validation (one trial each), sealed:** CONFIRM if (a) net mean > 0 against not trading, t > 1.645; (b) placebo: real ≥ 95th
   percentile of the same session's other hours (net, same direction); (c) posterior > 0, prior Normal(discovery/2,
   |discovery|/2); (d) positive in at least 3 of the 4 years 2023–2026. WATCHLIST if net > 0; REJECT. Z and D market-tests from 68.

## 183. Family-14 discovery: one hour of 41 (≈2 by chance) — MNQ long 00:00 → 01:00; D56 registered (S1–S5)

**No trial spent at registration; N 831. Committed BEFORE validation data is read.** `reporting/d14_hours.py`,
`reports/d14_discovery.json`; `signals/d_hours.py`. 41 hours on 2018-01 → 2022-12: **1 carried** — MNQ 00:00 → 01:00 New York,
+1.13 bps gross (t +2.59, n 1272) against a 0.56 bps round trip; next MGC 19:00 +0.81 (t +2.29, below its 1.0 bps
cost). Fewer passes than chance — the hours of traded MNQ and gold carry no excess drift. Even if real, +0.57 bps net is ~$11 a night on
4 MNQ. Z and D market-test 68.

## 184. D56 validated: the midnight MNQ hour reversed — rejected; family 14 empty (S6–S8)

**One trial spent: t00838. N 831 → 832.** 932 nights, 2023-01 → 2026-08: net -1.28 bps (t -3.52), the worst of the
night session's 16 hours, negative in every year. The 2018–22 drift was the scan's chance pass. Z and D market-test 68.

## 185. D-series family 15 protocol: MNQ ↔ gold lead-lag over 15–60 minutes, recent-period design (S1)

**No trial spent; N 832. Written and committed BEFORE any lead-lag statistic is computed.** The user approved this order
(2026-10-13); recent-period design (§180): discovery 2018-01 → 2022-12; validation 2023-01 → 2026-08, sealed. Many trades a day
— the standalone route of §165.

1. **Data:** the family-8 minute grids (owned trades, contract-consistent). **Overlaps** (New York clock, same dated day):
   A 18:00 → 03:00 (MNQ night × MGC Asia); B 03:00 → 09:30 (MNQ night × MGC London); C 09:30 → 11:30 (MNQ day × MGC London).
2. **Trades:** at every k-minute mark t inside an overlap (t = start + j·k, j ≥ 1, t + k ≤ end), k ∈ {15, 30, 60}: leader's
   return over (t − k, t]; the follower is traded over (t, t + k] in the leader's direction (follow) or against it (fade);
   non-overlapping by construction. Leader → follower both ways (MNQ → MGC, MGC → MNQ). Forms: every mark; strong marks
   (|leader return| above its 2018–22 median for that overlap and k). **3 overlaps × 2 directions × 3 k × 2 forms = 36 tests**;
   ~1.8 by chance. Net of a round trip (bps): MNQ 0.56, MGC 1.0. Statistic: net bps a trade, follow or fade by the gross sign;
   t clustered by day. **Carried:** |t| > 1.96 AND net > 0.
3. **Validation (one trial each), sealed:** CONFIRM if (a) net > 0 against not trading, t > 1.645; (b) placebo: the same rule with
   the leader's return taken from a random OTHER day at the same clock time, 1,000 draws, real ≥ 95th pct; (c) posterior > 0,
   prior Normal(discovery/2, |discovery|/2); (d) positive in ≥ 3 of the 4 years 2023–2026. WATCHLIST if net > 0; REJECT.
   Z and D market-tests from 69.

## 186. Family-15 discovery: no MNQ ↔ gold lead-lag survives costs — 0 of 36 carried (S1)

**No trial spent; N 832.** `reporting/d15_leadlag.py`, `reports/d15_discovery.json`. 36 tests on 2018-01 → 2022-12 (1–34 trades
a day): **none carried.** Gross effects are within ±0.2 bps a trade almost everywhere (the largest, gold leading MNQ over 60
minutes on strong marks, +1.5 bps gross on 622 trades, t +0.43 net) against round trips of 0.56–1.0 bps. Cross-market
information between the plan's two traded-data markets is priced within minutes. Family 15 is empty; with families 13–14,
the three recent-period families (§180–§186) found nothing.

## 187. D-series family 16 protocol: intraday momentum into the window's close (S1)

**No trial spent; N 832. Written and committed BEFORE any statistic is computed.** The user: keep searching while the demo runs.
The published "market intraday momentum" (first half hour predicts the last, US index) was registered as F01 and blocked before it
ran; it was never measured here, and not on gold, Tokyo or Xetra. Recent-period design (§180): discovery 2018-01 → 2022-12;
validation 2023-01 → 2026-08, sealed.

1. **Windows and data:** MNQ 09:30–16:00 and MGC 03:00–11:30 (owned trades, family-8 grids, contract-consistent); NKD 09:00–15:00
   Tokyo and DAX 09:00–17:30 Frankfurt (corrected HistData CFD minute bars; prices at the window's start, +30 minutes, end − 30
   minutes and end — the window's end is the only session-boundary price used, as §149).
2. **Target:** the window's last 30 minutes. **Predictors:** (i) the first 30 minutes; (ii) the window from start to end − 30
   minutes. Forms: every day; strong days (|predictor| above its 2018–22 median). **4 × 2 × 2 = 16 tests**; ~0.8 by chance.
3. **Standalone, net of a round trip** (bps: MNQ 0.56, MGC 1.0, NKD 0.4, DAX 0.5). Statistic: sign(predictor) × target, follow /
   fade by the gross sign, net of cost; t over days. **Carried:** |t| > 1.96 AND net > 0.
4. **Validation as §185, 3** (sealed; (a) net > 0 against not trading t > 1.645; (b) placebo, the predictor from a random other
   day, 1,000 draws, ≥ 95th pct; (c) posterior > 0; (d) positive in ≥ 3 of 4 years 2023–26). Z and D market-tests from 69.

## 188. Family-16 discovery: DAX's last half hour follows the day — one of 16 (≈0.8 by chance); D57 registered (S1–S5)

**No trial spent at registration; N 832. Committed BEFORE validation data is read.** `reporting/d16_close.py`,
`reports/d16_discovery.json`; `signals/d_close.py`. 16 tests on 2018-01 → 2022-12: **1 carried** — DAX, strong days, last 30 minutes
in the direction of 09:00 → 17:00: net +2.35 bps (t +2.24, n 639). MNQ shows the same sign just below the bar
(every day +2.04 net, t +1.84; strong +3.37, t +1.79); gold and Nikkei nothing; the first half hour predicts nothing anywhere. Z and D 69.

## 189. D57 validated: DAX close momentum faded to zero in 2023–26 (S6–S8)

**One trial spent: t00839. N 832 → 833.** 369 strong days, 2023-01 → 2026-08: net +0.01 bps (t +0.01); placebo
75th percentile; positive in 2 of 4 years. WATCHLIST only because the mean is a hair above zero. Family 16 holds nothing.

## 190. D-series family 17 protocol: relative-value states — does a stretched pair set the next session's direction? (S1)

**No trial spent; N 833. Written and committed BEFORE any statistic is computed.** The user: keep searching alongside the demo.
Recent-period design (§180): discovery 2018-01 → 2022-12; validation 2023-01 → 2026-08, sealed. One leg traded at a time (no
spread position — opposite positions across products count as hedging in this account, §90).

1. **Pairs (Yahoo daily, §171):** GC/SI, HG/GC, ES/ZN, NQ/ES, CL/NG, ZS/ZC. Each market's ROLL-FREE log index = the cumulative sum
   of its session returns (open → settlement); the pair's state z = (index_A − index_B − its mean over the previous 60 sessions) ÷
   its SD over those sessions, known before the next session opens.
2. **Trade:** the next session of leg A or leg B. On days with |z| > 1.5, A is traded in the direction of −sign(z) (reversion)
   or +sign(z) (continuation) — and B the opposite way — the sign fixed by discovery. Forms: |z| > 1.5; |z| > 2.5.
   **6 pairs × 2 legs × 2 thresholds = 24 tests**; ~1.2 by chance. Net of the leg's cost (§177's table). Statistic: net bps a
   trade; **carried** at |t| > 1.96 AND net > 0.
3. **Validation as §187, 4** (sealed; (a) net > 0 t > 1.645 against not trading; (b) placebo: the z state from a random other day,
   1,000 draws, ≥ 95th pct; (c) posterior > 0; (d) positive in ≥ 3 of 4 years). Z and D market-tests from 70.

## 191. Family-17 discovery: no relative-value state predicts the next session — 0 of 24 carried (S1)

**No trial spent; N 833.** `reporting/d17_relative.py`, `reports/d17_discovery.json`. 24 tests on 2018-01 → 2022-12; **none
carried** (best: copper after the copper/gold ratio is 2.5 SD stretched, reversion +21.2 bps net on 64 sessions, t +1.57). Family
17 is empty.

## 192. D-series family 18 protocol: weekly structure and short-trend persistence (S1)

**No trial spent; N 833. Written and committed BEFORE any statistic is computed.** Recent-period design (§180): discovery 2018-01
→ 2022-12; validation 2023-01 → 2026-08, sealed. Year-round by construction.

1. **Universe:** the 14 futures of §171 (Yahoo daily sessions, open → settlement; roll-free; §177's costs).
2. **Tests, per market:** (i) **week so far** — the sum of Monday–Wednesday sessions predicts Thursday's and Friday's sessions
   (each traded open → settlement, in or against its direction); (ii) **5-session trend** — the sum of the previous 5 sessions
   predicts the next; (iii) **20-session trend** — the previous 20 predict the next. **14 × 3 = 42 tests**; ~2.1 by chance.
   Statistic: net bps a trade, follow or fade by the gross sign; t over trades. **Carried:** |t| > 1.96 AND net > 0.
3. **Validation as §187, 4** (sealed; (a) net > 0 t > 1.645 against not trading; (b) placebo, the predictor from a random other
   date, 1,000 draws, ≥ 95th pct; (c) posterior > 0; (d) positive in ≥ 3 of 4 years). Z and D market-tests from 70.

## 193. Family-18 discovery: no weekly or short-trend pattern — 0 of 42 carried (S1)

**No trial spent; N 833.** `reporting/d18_weekly.py`, `reports/d18_discovery.json`. 42 tests on 2018-01 → 2022-12; **none carried**;
nearest: crude following its 20-session trend, +15.9 bps net (t +1.91 — time-series momentum, published), natural gas the same
(+13.6, t +1.41). Week-so-far and 5-session trends predict nothing net of cost. Family 18 is empty; families 16–18 (§187–§193)
added one validation (D57, faded) and nothing usable.

## 194. D-series family 19 protocol: one combined model per window — many weak signals together (S1)

**No trial spent; N 833. Written and committed BEFORE any model is fitted.** Families 3–18 tested one idea at a time; several were
faintly positive but too weak alone (gold and silver London continuation, crude's 20-session trend, close momentum). This family
combines them: for each of the plan's six windows, ONE ridge regression of the window's return on every feature already built,
fitted on 2018-01 → 2022-12, scored ONCE on sealed 2023-01 → 2026-08. **6 trials** (one per window).

1. **Targets:** NKD, DAX, MGC, MNQ windows; MCL and ZS sessions (family-3 series, §149).
2. **Features, all known before the target's entry** (standardised with 2018–22 means and SDs only): the other five windows'
   most recent completed returns (the §149 hand-off timing); the target's own previous window; its pre-window move where defined
   (NKD, DAX, MGC, MNQ); its own 5- and 20-session trend; its volatility state (σ20 ÷ median σ20 of the previous 250, §180);
   weekday dummies (Mon–Thu). Missing values → 0 (the standardised mean).
3. **Model:** ridge regression (intercept free), penalty chosen from {1, 10, 100, 1,000, 10,000} by leave-one-year-out
   cross-validation inside 2018–22 (maximise the out-of-fold Sharpe of trading the prediction's sign), then refitted on all of
   2018–22. **Trade:** each day, the target window in the direction of the sign of the prediction.
4. **Validation (one trial per window), sealed:** CONFIRM if (a) net of the account's cost (§180's table) > 0 against not
   trading, t > 1.645; (b) placebo: the same frozen model scored on the features of a random other day, 1,000 draws, ≥ 95th pct;
   (c) the sign-trade beats always-long (reported; required only if the window has positive drift in 2018–22); (d) positive in
   ≥ 3 of the 4 years. WATCHLIST if net > 0; REJECT. Z and D market-tests 70–75. No discovery screen — every window's model is
   validated, so the six are the whole family.

## 195. Family-19 models fitted and frozen on 2018–22; D58–D63 registered (S1–S5)

**No trial spent at registration; N 833. Committed BEFORE the sealed window is read.** `reporting/d19_model.py`,
`reports/d19_models.json` (coefficients, standardisation, penalty). Out-of-fold skill inside 2018–22 is small:

| id | window | penalty | out-of-fold daily Sharpe (net) | in-sample net bps | long share |
|---|---|---|---|---|---|
| D58 | NKD_win | 100 | +0.067 | +10.16 | 47% |
| D59 | DAX_win | 1 | -0.077 | +2.64 | 50% |
| D60 | MGC_win | 1000 | +0.010 | +5.74 | 59% |
| D61 | MNQ_win | 10000 | +0.029 | +8.61 | 79% |
| D62 | MCL | 10000 | +0.009 | +9.76 | 99% |
| D63 | ZS | 10 | +0.036 | +8.58 | 54% |

The models lean on the relay hand-offs (yesterday's MNQ against Tokyo and Xetra), trends and volatility state; DAX's best penalty
already loses out of fold. Z and D market-tests 70–75.

## 196. D58–D63 scored: no confirmation; the gold model (D60) passes everything but always-long (S6–S8)

**Six trials spent: t00840–t00845. N 833 → 839.** Frozen 2018–22 models, sealed 2023-01 → 2026-08:

| id, trial | window | net bps a day (t) | placebo pct | vs always-long | years positive | tier |
|---|---|---|---|---|---|---|
| D58 t00840 | NKD_win | +2.25 (t +0.76) | 80 | +3.22 (t +0.74) | 2 of 4 | **WATCHLIST** |
| D59 t00841 | DAX_win | +2.52 (t +1.01) | 86 | -0.19 (t -0.05) | 2 of 4 | **WATCHLIST** |
| D60 t00842 | MGC_win | +5.35 (t +1.89) | 98 | +4.72 (t +1.30) req. | 3 of 4 | **WATCHLIST** |
| D61 t00843 | MNQ_win | -1.92 (t -0.59) | 14 | -3.64 (t -1.22) req. | 1 of 4 | **REJECT** |
| D62 t00844 | MCL | +2.44 (t +0.30) | 93 | +1.86 (t +1.17) req. | 1 of 4 | **WATCHLIST** |
| D63 t00845 | ZS | -3.75 (t -1.05) | 22 | -2.04 (t -0.41) req. | 1 of 4 | **REJECT** |

**D60, gold:** net +5.35 bps a day (t +1.89), placebo 98th percentile, positive 2024–26 (+6.7, +7.9, +7.9) — and +4.7 bps a day
over always-long (t +1.30), short of 1.645, the condition required because gold's 2018–22 drift was positive. It is the fourth
independent route to the same finding (D16, D22–D27, D32/D36, now a model): **gold and silver carry a persistent, modest
directional predictability into the London window, smaller than their own recent drift.** Combining signals did not lift the
other windows (Nikkei, DAX: watchlist on noise; MNQ, soybeans: reject; crude: long 99% of days).

## 197. A28 design, frozen on 2010–17 before any 2018–26 look: gold enters 04:00, silver 05:00 (S8)

**No trial spent; N 839. Committed BEFORE the designed trades are evaluated on 2018–26.** The user asked whether the design
questions can be answered with data: yes — on 2010–17 only, then frozen. `reporting/a28_metals_design.py`, `reports/a28_design.json`.
Criterion fixed in advance: the largest t of the direction-signed, drift-removed return over entry hours 03:00 … 10:00 (exit
11:30 New York) × day filters (every day; |overnight move| above its 2010–17 median; top fifth); follow the 11:30 → 03:00 move.

- **Where the edge sits (gold, 2010–17):** the first hour REVERSES (03:00 → 04:00: −3.1 bps, t −1.81); the continuation builds
  after 04:00 and most of all 08:00 → 11:30.
- **Gold, chosen:** enter **04:00**, every day, follow; +11.49 bps beyond drift, t +3.70, 595 days (complete
  minute days only). **Silver, chosen:** enter **05:00**, days with |overnight move| > 54.2 bps (the stronger half), follow;
  +18.16 bps, t +4.22, 1024 days.
- **Not blind:** 2018–26 already showed the gold and silver effects (§151, §154, §163, §196); only the entry hour and the day
  filter are new. The evaluation that follows is a replication with that caveat; the clean check is forward data.

## 198. A28 evaluated on 2018–26: the 2010–17 design did not transfer; silver modest; no account carried (S8)

**No trial spent; N 839.** `reports/a28_eval_trade.json`, `reports/a28_eval_account.json`.

| frozen design, 2018-01 → 2026-08 | trades | net vs not trading (t) | vs always-long (t) | 2021–26 net |
|---|---|---|---|---|
| gold, enter 04:00, every day, exit 11:30 | 2095 | +0.34 (+0.21) | +0.48 (+0.21) | +2.66 |
| silver, enter 05:00, stronger half, exit 11:30 | 1072 | +5.57 (+1.26) | +11.74 (+1.93) | +5.63 |

Gold by year: 2018 -4.3, 2019 -8.9, 2020 +0.2, 2021 +2.2, 2022 -2.4, 2023 -0.4, 2024 +5.0, 2025 +5.4, 2026 +8.1. Silver: 2018 +16.7, 2019 -23.5, 2020 +13.6, 2021 +3.3, 2022 -5.3, 2023 -6.6, 2024 +5.1, 2025 +6.6, 2026 +26.6.

**The intraday shape found on 2010–17 (a reversing first hour, the edge built after 04:00) did not hold on 2018–26:** gold's
designed trade kept almost nothing (+0.3 bps net), though 2024–26 are positive. Silver's held better (+11.7 bps a day over
always-long, t +1.93) but swings by year. **As its own account** (3–4 SIL risk-matched to the 05:00 → 11:30 swing, rule days
only): holding to 11:30 passes 0–10% (mean net −$289 to −$902 per 84 days); the plan's brackets on rule days return +$393 (2018–20)
and +$680 (2021–26) — the zero-edge staking on half the days, below the existing accounts. **The metals' London predictability
is real but cannot be engineered into a trade that carries a Tradeify account with this data.** Watchlist, forward-tested by time.

## 199. D-series family 20 protocol: where a market's real drift accrues — night or day (S1)

**No trial spent; N 839. Written and committed BEFORE any window statistic is computed.** The user: continue; report only genuine
findings. The plan's replays remove drift (zero edge), but real accounts earn it; the windows were chosen under zero edge (§105,
§106, §124). F13 (excluded) was the narrow 02:00–03:00 ET overnight-drift claim, decayed per its authors; the broad split of each
market's day into night and day sessions was never measured. Recent-period design (§180): discovery 2018-01 → 2022-12;
validation 2023-01 → 2026-08, sealed.

1. **Windows (owned minute trades, family-8 grids, contract-consistent; daily round trips, flat 17:00–18:00):** MNQ night
   18:00 → 09:30 and day 09:30 → 16:00; MGC Asia 18:00 → 03:00 and London 03:00 → 11:30. **Long only** (the question is drift).
   **4 tests.** Net of a round trip (MNQ 0.56, MGC 1.0 bps).
2. **Discovery:** each window's net mean and daily Sharpe on 2018–22; **carried** if net > 0 with t > 1.96.
3. **Validation (one trial each), sealed:** CONFIRM if (a) net > 0 against not trading, t > 1.645; (b) its daily Sharpe exceeds the
   plan's current window for that market (MNQ day / MGC London) over the same 2023–26 days — so a confirmed window is a better
   use of the account, not just a premium already earned; (c) positive in ≥ 3 of the 4 years. WATCHLIST if net > 0; REJECT.
   Z and D market-tests from 76. A CONFIRM is then replayed as the plan's account for that market (A23 engine, REAL drift) against
   the current window before anything changes.

## 200. Family-20 discovery: no window's drift is significant on 2018–22 — 0 of 4 carried (S1)

**No trial spent; N 839.** `reports/d20_discovery.json`. Net, long, 2018-01 → 2022-12: MNQ night +2.99 bps (t +1.24), MNQ day −0.84
(t −0.24), MGC Asia −1.61 (t −1.48), MGC London +0.57 (t +0.27). MNQ's drift sits in the night session, but not significantly.

## 201. D-series family 21 protocol: carry (the futures curve's slope) as the daily direction (S1)

**No trial spent; N 839. Written and committed BEFORE any carry statistic is computed.** Backwardated commodities (front above the
next contract) pay longs a hedging premium; the owned daily file measures each market's carry (`data/daily_bars.py`: C = (F1 − F2)
/ F2 / years, the front against the next liquid contract). W04 (§73–§75, retired) combined trend and carry in a daily portfolio on
2010–26; carry alone, per market, on the recent period was not measured. Recent-period design (§180).

1. **Markets** (owned GLBX daily bars, roll-correct held returns, bars ≈ the session, §74): NQ, GC, HG, CL, ZN, 6E. **Trade:** each
   day's held return in the sign of the previous day's carry (long backwardation / positive carry, short contango); a daily round
   trip at the account's contract, cost (bps) NQ 0.5, GC 0.8, HG 2.0, CL 0.7, ZN 0.4, 6E 0.3. Forms: every day; days with |carry|
   above its 2018–22 median. **6 × 2 = 12 tests.**
2. **Discovery 2018-01 → 2022-12;** net bps a day, t; **carried** if net > 0 with t > 1.96.
3. **Validation (one trial each), sealed 2023-01 → 2026-09:** (a) net > 0 against not trading t > 1.645; (b) placebo: the carry
   sign from a random other day, 1,000 draws, ≥ 95th pct; (c) positive in ≥ 3 of the 4 years; CONFIRM if all; WATCHLIST if net >
   0; REJECT. Z and D market-tests from 76.

## 202. Family-21 discovery: carry sets no direction on 2018–22 — 0 of 12 carried (S1)

**No trial spent; N 839.** `reports/d21_discovery.json`: best 6E (strong carry, short euro) +1.79 bps net (t +0.95); gold and copper
negative; crude +2.90 (t +0.31). Family 21 is empty.

## 203. D-series family 22 protocol: gap-fill brackets at the window open (S1)

**No trial spent; N 839. Written and committed BEFORE any gap statistic is computed.** A path effect in the plan's own terms. At a
window's open, the gap g = the open minus the previous window's close. A bracket toward the fill — take at the previous close
(distance |g|), stop at s·|g| beyond the open, else out at the window's end — has zero expected gross under a fair martingale; if
gaps fill more often than the geometry implies, it earns. U01 (large opening gap NON-fill, blocked before running) is the mirror
claim; the fill was never measured here. Recent-period design (§180).

1. **Windows (family-8 grids, owned trades, minute closes, contract-consistent):** MNQ day 09:30–16:00 with the previous 16:00
   close; MGC London 03:00–11:30 with the previous 11:30 close.
2. **Tests:** gap threshold |g| > {0.25, 0.5, 1.0} × σ_g (σ_g = SD of the previous 60 gaps) × stop multiple s ∈ {0.5, 1, 2}:
   **2 × 3 × 3 = 18 tests**; ~0.9 by chance. Net of a round trip (MNQ 0.56, MGC 1.0 bps). A stop touched and the take touched in the
   same minute counts as the stop (as all replays). **Carried:** net > 0 with t > 1.96.
3. **Validation (one trial each), sealed 2023-01 → 2026-08:** (a) net > 0 against not trading t > 1.645; (b) placebo: the same bracket
   in the gap's OWN direction (a breakout of equal geometry) must do worse — real minus placebo > 0 with t > 1.645; (c) positive in
   ≥ 3 of the 4 years. CONFIRM if all; WATCHLIST if net > 0; REJECT. Z and D market-tests from 76.

## 204. Family-22 discovery: gaps do not fill more than the bracket geometry implies — 0 of 18 carried (S1)

**No trial spent; N 839.** `reporting/d22_gapfill.py`, `reports/d22_discovery.json`. On 2018-01 → 2022-12, every gap-fill bracket
(MNQ day, MGC London; gaps beyond 0.25–1.0 σ; stops 0.5–2 × the gap) nets within −6 and +1 bps a trade (no t above +0.21): the
fill happens about as often as a fair martingale implies, and costs make it negative. Family 22 is empty.

## 205. D-series family 23 protocol: breakouts after range compression (NR4 / NR7) (S1)

**No trial spent; N 839. Written and committed BEFORE any statistic is computed.** A volatility-compression breakout (Crabel's
narrow-range days) in the plan's windows; F05 (volatility_compression_expansion, retired) used a different trigger and hold.
Recent-period design (§180).

1. **Windows (family-8 grids, minute closes, contract-consistent):** MNQ day 09:30–16:00; MGC London 03:00–11:30. The previous
   window's range = its highest and lowest minute close.
2. **Setup:** the previous window's range is the narrowest of the last N windows, N ∈ {4, 7}. **Trade:** in today's window, the
   first minute close beyond the previous high (long) or low (short) enters; stop at the previous range's midpoint ("mid") or its
   far side ("far"); exit at the window's end; one trade a day. **2 markets × 2 N × 2 stops = 8 tests**; net of a round trip
   (MNQ 0.56, MGC 1.0 bps). **Carried:** net > 0 with t > 1.96.
3. **Validation (one trial each), sealed 2023-01 → 2026-08:** (a) net > 0 against not trading t > 1.645; (b) placebo: the same
   breakout on the days that are NOT narrow-range must do worse — difference t > 1.645; (c) positive in ≥ 3 of the 4 years.
   CONFIRM if all; WATCHLIST if net > 0; REJECT. Z and D market-tests from 76.

## 206. Family-23 discovery: narrow-range breakouts do not follow through significantly — 0 of 8 carried (S1)

**No trial spent; N 839.** `reporting/d23_breakout.py`, `reports/d23_discovery.json`. Best: gold after an NR7 window, breakout with a
midpoint stop, +8.34 bps net (t +1.64; ordinary days −2.48); MNQ +2 to +5 bps on NR days, no better than ordinary days. Empty.

## 207. D-series family 24 protocol: the next session across markets after a shock day (S1)

**No trial spent; N 839. Written and committed BEFORE any statistic is computed.** Family 12 asked whether a market continues its
OWN extreme session; family 10 used every day's sign. This asks how OTHER markets' next sessions respond after a shock in a major
market (flight to safety, risk-on rebound). Recent-period design (§180).

1. **Data:** the §171 universe (Yahoo daily sessions, roll-free; §177's costs). **Shock day** in predictor P: |P's session| > 2 σ
   (SD of P's previous 60 sessions). Predictors: ES, CL, GC, ZN. **Target:** each other market's NEXT session, traded in the
   direction of P's shock (follow) or against it (fade), the sign fixed by discovery. **4 × 13 = 52 tests**; ~2.6 by chance.
2. **Discovery 2018-01 → 2022-12:** net bps a trade, t; **carried** if net > 0 with t > 1.96.
3. **Validation (one trial each), sealed 2023-01 → 2026-08:** (a) net > 0 against not trading t > 1.645; (b) placebo: the same
   rule after random non-shock days (direction from that day's sign), 1,000 draws, ≥ 95th pct; (c) positive in ≥ 3 of the 4 years.
   CONFIRM if all; WATCHLIST if net > 0; REJECT. Z and D market-tests from 76.

## 208. Family-24 discovery: eight cross-market shock responses (≈2.6 by chance); D64–D71 registered (S1–S5)

**No trial spent at registration; N 839. Committed BEFORE validation data is read.** `reporting/d24_shock.py`,
`reports/d24_discovery.json`; `signals/d_shock.py`. 52 tests on 2018-01 → 2022-12; **8 carried** — three times the chance count,
with per-trade effects of 11–80 bps. Bond (ZN) shocks lead four of them (euro, gold, S&P, copper all follow the next session).

| id | shock | target | rule | trades | discovery net | prior |
|---|---|---|---|---|---|---|
| D64 | ZN shock | 6E | follow | 82 | +23.84, t +3.65 | N(+11.92, 11.92) |
| D65 | GC shock | 6E | follow | 87 | +18.81, t +3.15 | N(+9.41, 9.41) |
| D66 | CL shock | ZC | fade | 75 | +44.70, t +2.64 | N(+22.35, 22.35) |
| D67 | ZN shock | GC | follow | 82 | +29.36, t +2.49 | N(+14.68, 14.68) |
| D68 | ZN shock | ES | follow | 81 | +37.60, t +2.15 | N(+18.80, 18.80) |
| D69 | GC shock | ES | follow | 86 | +46.38, t +2.11 | N(+23.19, 23.19) |
| D70 | ES shock | NG | follow | 88 | +79.63, t +2.11 | N(+39.81, 39.81) |
| D71 | ZN shock | HG | follow | 82 | +34.42, t +2.08 | N(+17.21, 17.21) |

Correlated: the four ZN-led tests share their event days. Z and D market-tests 76–83.

## 209. D66 and D68 CONFIRM: corn fades a crude shock; the S&P follows a bond shock (S6–S8)

**Eight trials spent: t00846–t00853. N 839 → 847.** Z and D market-tests 76–83. Sealed 2023-01 → 2026-08, standalone, net:

| id, trial | rule | trades | net bps a trade (t) | placebo pct | years positive | tier |
|---|---|---|---|---|---|---|
| D64 t00846 | 6E follows the previous session's ZN shock | 48 | +1.52 (t +0.20) | 60 | 2 of 4 | **WATCHLIST** |
| D65 t00847 | 6E follows the previous session's GC shock | 55 | +6.51 (t +0.97) | 91 | 2 of 4 | **WATCHLIST** |
| D66 t00848 | ZC fades the previous session's CL shock | 51 | +38.41 (t +2.47) | 99 | 4 of 4 | **CONFIRM** |
| D67 t00849 | GC follows the previous session's ZN shock | 48 | -1.01 (t -0.04) | 67 | 2 of 4 | **REJECT** |
| D68 t00850 | ES follows the previous session's ZN shock | 48 | +33.38 (t +2.01) | 100 | 3 of 4 | **CONFIRM** |
| D69 t00851 | ES follows the previous session's GC shock | 55 | +4.18 (t +0.24) | 67 | 2 of 4 | **WATCHLIST** |
| D70 t00852 | NG follows the previous session's ES shock | 52 | +16.12 (t +0.39) | 44 | 2 of 4 | **WATCHLIST** |
| D71 t00853 | HG follows the previous session's ZN shock | 48 | +13.16 (t +0.66) | 85 | 3 of 4 | **WATCHLIST** |

**D66 — after a crude session beyond 2 σ, corn's next session against the shock: +38.4 bps a trade (t +2.47), 99th percentile, all
four years positive. D68 — after a 10-year-note session beyond 2 σ, the S&P's next session with the shock: +33.4 (t +2.01), 100th
percentile, three of four years.** Per-trade effects of ~0.25–0.3 of a day's SD — about five times anything else found — on ~50
trades each (~14 a year). **Before use:** an independent-data replication (owned GLBX bars for ZN, ES, NQ, CL), robustness
(thresholds, the plan's MNQ instead of ES), and an account replay.

## 210. D66 and D68 stress-tested: D68 replicates on independent data and adds to the MNQ account after 2021; D66 does not (S8)

**No trial spent; N 847.** `reports/a29_d68_replay.json`.

**Independent data (owned GLBX daily bars — roll-correct, different session boundaries from Yahoo).**
- **D68 (S&P follows a 10-year-note shock):** positive in every variant since 2018 — ES and NQ, thresholds 1.5 / 2 / 2.5 σ, 2018–22 and
  2023–26: +12.7 to +37.0 bps a trade (t +0.75 to +1.68 individually); 2010–17 faintly positive (+0.0 to +11.5). On the plan's MNQ
  window (09:30–16:00, owned minute trades): 2018–22 +22.7 (t +1.34), **2023–26 +38.9 (t +2.15)**. Consistent sign, modest strength,
  a plain mechanism (a bond rally lifts equities the next day; a bond sell-off weighs on them).
- **D66 (corn fades a crude shock):** with the crude shock from the owned bars, 2023–26 reproduces (k = 2: +38.7, t +2.54) but
  2018–22 vanishes (+2.9, t +0.16) and 2010–17 turns negative at 2.5 σ (−33.3). A recent pattern, not a stable one: **not used.**

**D68 in the plan (A23 engine, MNQ 4 contracts, drift removed, 84-day replay):** an overlay — on the ~5–6% of sessions after a ZN
shock, the MNQ ticket takes the shock's direction instead of long (about half are shorts):

| | 2015–20 | 2021–26 |
|---|---|---|
| plan, always long | 76%, +$1,960, P(net > 0) 61% | 80%, +$1,265, 59% |
| **overlay, the shock's direction on shock days** | 72%, +$1,971, 55% | **77%, +$1,720, 64%** |
| standalone, shock days only (plan brackets / hold) | 0–7%, ≈ $0 | 0–1%, ≈ −$110 |

**Reading.** D68 is the most robust directional finding of the programme — confirmed on sealed data under the strict rule,
replicated in sign on an independent source, economically sensible — and it is modest: about +$455 per four months on one
account in 2021–26, nothing in 2015–20. Too rare (≈ 14 days a year) to carry an account alone. **Candidate for the plan, not yet
adopted:** the user decides; the clean forward test is the demo (the bot could set MNQ's direction on bond-shock days).

## 211. D68 added to the demo: the MNQ ticket follows a 10-year-note shock (S8)

**No trial spent; N 847.** The user (2026-10-13, minutes before the 17:30 alert): "go ahead". `bot/d68.py`: at each alert, today's
ZN session (Yahoo daily ZN=F, open → settlement) against 2 × the SD of its previous 60 sessions; beyond it, the MNQ ticket is
issued in the shock's direction (LONG after a bond rally, SHORT after a sell-off) and the post carries a "D68" line; otherwise, or if
the data cannot be read, LONG as before. `bot/schedule.py` passes the side to the ticket (the shadow tracker already handles
shorts). Deployed 17:22 New York with the user's go-ahead (previous schedule.py in `/opt/futures-bot/backup-2026-10-13b/`); the first
check (2026-10-13): ZN +18 bps against a 52 bps threshold — no shock, MNQ long. The `!eod` filing fix (§147) was already live.
Expected frequency ≈ 14 shock days a year; the demo's forward record is D68's first out-of-sample use.

## 212. D-series family 25 protocol: shocks into the plan's next windows (S1)

**No trial spent; N 847. Written and committed BEFORE any statistic is computed.** Family 24 found the largest per-trade effects of
the programme after shock days (D68 confirmed and deployed, §209–§211). This family carries the shocks into the plan's own next
windows. Recent-period design (§180): discovery 2018-01 → 2022-12; validation 2023-01 → 2026-08, sealed.

1. **Shock day** (Yahoo daily sessions, §171): |session| > 2 σ (SD of the previous 60) in ZN, 6E, ES, CL or GC on day D−1.
2. **Targets, the plan's windows after it** (family-3 series, §149): NKD (Tokyo date D, entry 20:00 New York D−1), DAX and MGC
   (03:00 D), MNQ (09:30 D), ZS (session D). Traded in the shock's direction (follow) or against it (fade), fixed by discovery.
   **5 × 5 = 25 pairs minus ZN → MNQ (D68) = 24 tests**; ~1.2 by chance. Net of the account's cost (§180's table).
3. **Carried:** net > 0 with t > 1.96. **Validation (one trial each), sealed:** (a) net > 0 against not trading t > 1.645;
   (b) placebo: the same rule after random non-shock days, 1,000 draws, ≥ 95th pct; (c) positive in ≥ 3 of the 4 years. CONFIRM if
   all; WATCHLIST if net > 0; REJECT. Z and D market-tests from 84.

## 213. Family-25 discovery: three shock-into-window tests (≈1.2 by chance); D72–D74 registered (S1–S5)

**No trial spent at registration; N 847. Committed BEFORE validation data is read.** `reporting/d25_shockwin.py`,
`reports/d25_discovery.json`; `signals/d_shockwin.py`. 24 tests on 2018-01 → 2022-12; 3 carried:

| id | shock | window | rule | trades | discovery net | prior |
|---|---|---|---|---|---|---|
| D72 | ZN shock | MGC_win | follow | 80 | +21.82, t +2.32 | N(+10.91, 10.91) |
| D73 | 6E shock | MGC_win | follow | 64 | +23.25, t +2.24 | N(+11.62, 11.62) |
| D74 | 6E shock | DAX_win | fade | 68 | +31.67, t +2.01 | N(+15.83, 15.83) |

Next: DAX following a ZN shock (+25.7, t +1.93), Nikkei following a ZN shock (+14.9, t +1.57) — bond shocks lead most of the list,
as in family 24. Z and D market-tests 84–86.

## 214. D72–D74 validated: no confirmation — shocks into the plan's other windows did not hold (S6–S8)

**Three trials spent: t00854–t00856. N 847 → 850.** Z and D market-tests 84–86.

| id, trial | rule | trades | net bps a trade (t) | placebo pct | years positive | tier |
|---|---|---|---|---|---|---|
| D72 t00854 | MGC_win follows the previous session's ZN shock | 47 | +15.12 (t +1.00) | 92 | 1 of 4 | **WATCHLIST** |
| D73 t00855 | MGC_win follows the previous session's 6E shock | 41 | -6.43 (t -0.34) | 42 | 2 of 4 | **REJECT** |
| D74 t00856 | DAX_win fades the previous session's 6E shock | 41 | +13.10 (t +0.74) | 81 | 2 of 4 | **WATCHLIST** |

Gold following a bond shock (D72) was positive only through one year (2026 +93); nothing generalises beyond D68's S&P response.

## 215. D-series family 26 protocol: the response to a shock over the following sessions (S1)

**No trial spent; N 850. Written and committed BEFORE any statistic is computed.** Family 24 measured the session right after a shock
(D68 confirmed). This asks whether the response continues: the next three sessions together, and sessions two and three alone
(skipping the first). Recent-period design (§180).

1. **Shock day** in P ∈ {ZN, 6E, ES, CL, GC} (Yahoo sessions, |session| > 2 σ of the previous 60). **Targets:** every other §171
   market. **Trade:** (i) sessions D+1 … D+3, or (ii) sessions D+2 … D+3, each a daily round trip in the shock's direction or against
   it (fixed by discovery); net of h costs. **5 × 13 × 2 = 130 tests**; ~6.5 by chance. Non-overlapping (a shock during an open
   trade is ignored).
2. **Carried:** net > 0 with t > 1.96. **Validation (one trial each), sealed 2023-01 → 2026-08:** as §207, 3 (net t > 1.645;
   placebo after random non-shock days ≥ 95th pct; positive in ≥ 3 of 4 years). Z and D market-tests from 87.

## 216. Family-26 discovery: 4 of 130 carried — fewer than chance (~6.5); D75–D78 registered per protocol (S1–S5)

**No trial spent at registration; N 850. Committed BEFORE validation data is read.** `reporting/d26_shocklag.py`,
`reports/d26_discovery.json`; `signals/d_shocklag.py`.

| id | shock | target | span | rule | trades | discovery net |
|---|---|---|---|---|---|---|
| D75 | GC shock | ES | next3 | follow | 63 | +90.42, t +2.52 |
| D76 | ZN shock | ZS | days2-3 | fade | 63 | +49.28, t +2.17 |
| D77 | ES shock | GC | days2-3 | follow | 60 | +33.36, t +2.09 |
| D78 | GC shock | ES | days2-3 | follow | 63 | +39.08, t +1.97 |

As a family the multi-session response shows no excess signal. Z and D market-tests 87–90.

## 217. D75–D78 validated: no confirmation — the shock response does not extend past the next session (S6–S8)

**Four trials spent: t00857–t00860. N 850 → 854.**

| id, trial | rule | trades | net bps a trade (t) | placebo pct | years positive | tier |
|---|---|---|---|---|---|---|
| D75 t00857 | ES follows a GC shock over next3 | 40 | +4.47 (t +0.19) | 53 | 3 of 4 | **WATCHLIST** |
| D76 t00858 | ZS fades a ZN shock over days2-3 | 39 | +3.83 (t +0.18) | 22 | 2 of 4 | **WATCHLIST** |
| D77 t00859 | GC follows a ES shock over days2-3 | 38 | -18.23 (t -0.63) | 37 | 0 of 4 | **REJECT** |
| D78 t00860 | ES follows a GC shock over days2-3 | 40 | +9.67 (t +0.60) | 54 | 3 of 4 | **WATCHLIST** |

## 218. D-series family 27 protocol: volume shocks — does a heavy-volume session's move continue? (S1)

**No trial spent; N 854. Written and committed BEFORE any statistic is computed.** Recent-period design (§180). Yahoo daily bars
carry volume (continuous front month; a roll day inflates it — those sessions are dropped: |volume change| with a price-series jump
is not identifiable here, so a session is a volume shock only if its volume exceeds 2 × the mean of the previous 60 AND the next
session's volume stays above 1.2 × that mean, which excludes one-day roll spikes). **Trade:** the next session (h = 1) or the next
three (h = 3) in the shock session's direction or against it, fixed by discovery; daily round trips, §177's costs. **14 markets × 2 h
= 28 tests**; ~1.4 by chance. Carried at net > 0 with t > 1.96; validation as §207, 3 (sealed 2023-01 → 2026-08). Z and D from 91.

**Amendment before any computation (a flaw in the protocol as committed):** the roll filter used the NEXT session's volume, which is
not known when the next session is entered — look-ahead. Replaced: a volume shock is volume > 2 × the mean of the previous 60
sessions, judged only on information known at the shock session's close; no roll filter (a roll-day spike in Yahoo's continuous
volume may enter as a false event — it dilutes, it cannot bias the direction rule).

## 219. Family-27 discovery: three volume-shock tests (≈1.3 by chance); D79–D81 registered (S1–S5)

**No trial spent at registration; N 854. Committed BEFORE validation data is read.** `reporting/d27_volume.py`,
`reports/d27_discovery.json`; `signals/d_volume.py`. 26 tests (two markets lacked enough shocks), 2018–22; 3 carried:

| id | market | horizon | rule | events | discovery net |
|---|---|---|---|---|---|
| D79 | NQ | next 3 | follow | 17 | +180.67, t +2.43 |
| D80 | ZS | next 1 | fade | 103 | +16.98, t +2.00 |
| D81 | ZW | next 1 | fade | 67 | +46.67, t +2.00 |

NQ rests on 17 events (2020 dominates). Z and D market-tests 91–93.

## 220. D79–D81 validated: no confirmation (S6–S8)

**Three trials spent: t00861–t00863. N 854 → 857.**

| id, trial | rule | trades | net bps (t) | placebo pct | tier |
|---|---|---|---|---|---|
| D79 t00861 | NQ follows a volume-shock session over the next 3 | 1 | -132.40 (t +nan) | 24 | **REJECT** |
| D80 t00862 | ZS fades a volume-shock session over the next 1 | 67 | +5.60 (t +0.42) | 82 | **WATCHLIST** |
| D81 t00863 | ZW fades a volume-shock session over the next 1 | 50 | +9.55 (t +0.34) | 91 | **WATCHLIST** |

## 221. D-series family 28 protocol: yield-curve shocks — steepening and flattening days (S1)

**No trial spent; N 857. Written and committed BEFORE any data is fetched.** D68 (bond shock → equities next session) is the
programme's most robust directional finding. Its natural extension: the SHAPE of the curve. Yahoo daily ZT (2-year), ZN (10-year), ZB
(30-year) sessions, open → settlement. **Curve change** = ZT − ZB session return (a steepener in price terms: the long end falls
against the short); a shock day = |change| > 2 σ of its previous 60. **Targets:** the next session of ES, NQ, GC, 6E, 6J, HG
(Yahoo, §171), each in the shock's direction or against it, fixed by discovery. **6 tests**; ~0.3 by chance. Recent-period
design (§180); carried at net > 0 with t > 1.96; validation as §207, 3. Z and D market-tests from 94.

## 222. Family-28 discovery: euro and copper fade a yield-curve shock — two of 6 (≈0.3 by chance); D82–D83 registered (S1–S5)

**No trial spent at registration; N 857. Committed BEFORE validation data is read.** `reporting/d28_curve.py`,
`reports/d28_discovery.json`; `signals/d_curve.py`. 2018-01 → 2022-12, ~70 curve-shock days:

| id | target | rule | events | discovery net |
|---|---|---|---|---|
| D82 | 6E | fade | 70 | +16.22, t +2.43 |
| D83 | HG | fade | 70 | +41.02, t +2.42 |

ES fades too (+30.1, t +1.18); every target faded. Z and D market-tests 94–95.

## 223. D82–D83 validated: the curve-shock fade reversed — rejected (S6–S8)

**Two trials spent: t00864–t00865. N 857 → 859.**

| id, trial | rule | trades | net bps (t) | placebo pct | tier |
|---|---|---|---|---|---|
| D82 t00864 | 6E fades a yield-curve shock (next session) | 48 | -6.83 (t -1.20) | 15 | **REJECT** |
| D83 t00865 | HG fades a yield-curve shock (next session) | 48 | -5.73 (t -0.31) | 45 | **REJECT** |

## 224. D-series family 29 protocol: shocks from every other market, next session (S1)

**No trial spent; N 859. Written and committed BEFORE any statistic is computed.** Family 24 (shocks in ES, CL, GC, ZN) was the
programme's most productive scan (8 carried of 52; D68 confirmed, replicated, deployed). This extends it to the other ten markets of
§171 as shock sources: NQ, RTY, SI, HG, NG, 6E, 6J, ZC, ZS, ZW — each into every other market's next session. **10 × 13 = 130
tests**; ~6.5 by chance. Method, costs, carry rule and validation exactly as §207 (recent-period design). Z and D market-tests from 96.

## 225. Family-29 discovery: eleven shock responses (≈6.5 by chance); D84–D94 registered (S1–S5)

**No trial spent at registration; N 859. Committed BEFORE validation data is read.** `reports/d29_discovery.json`;
`signals/d_shock29.py`. 130 tests, 2018–22; **11 carried** — a mild excess over chance, mostly currencies following equity shocks
and equities following yen shocks (risk-on / risk-off transmission):

| id | shock | target | rule | trades | discovery net |
|---|---|---|---|---|---|
| D84 | NQ shock | 6J | follow | 93 | +22.24, t +3.04 |
| D85 | NQ shock | 6E | follow | 93 | +14.74, t +2.74 |
| D86 | 6J shock | NQ | follow | 76 | +57.80, t +2.34 |
| D87 | ZC shock | 6J | follow | 80 | +16.19, t +2.33 |
| D88 | RTY shock | 6E | follow | 75 | +13.23, t +2.31 |
| D89 | SI shock | 6E | follow | 86 | +12.39, t +2.22 |
| D90 | 6J shock | ES | follow | 76 | +48.30, t +2.20 |
| D91 | NQ shock | ZN | follow | 93 | +10.01, t +2.19 |
| D92 | RTY shock | 6J | follow | 75 | +18.79, t +2.18 |
| D93 | HG shock | 6E | follow | 77 | +12.84, t +2.17 |
| D94 | 6J shock | RTY | follow | 76 | +51.84, t +1.97 |

Z and D market-tests 96–106.

## 226. D84–D94 validated: three CONFIRM — the yen follows Nasdaq and corn shocks, the euro follows silver shocks (S6–S8)

**Eleven trials spent: t00866–t00876. N 859 → 870.** Z and D market-tests 96–106.

| id, trial | rule | trades | net bps a trade (t) | placebo pct | years positive | tier |
|---|---|---|---|---|---|---|
| D84 t00866 | 6J follows the previous session's NQ shock | 48 | +16.33 (t +1.67) | 98 | 4 of 4 | **CONFIRM** |
| D85 t00867 | 6E follows the previous session's NQ shock | 48 | +0.31 (t +0.04) | 55 | 3 of 4 | **WATCHLIST** |
| D86 t00868 | NQ follows the previous session's 6J shock | 44 | -16.14 (t -0.66) | 12 | 2 of 4 | **REJECT** |
| D87 t00869 | 6J follows the previous session's ZC shock | 49 | +14.50 (t +1.83) | 98 | 3 of 4 | **CONFIRM** |
| D88 t00870 | 6E follows the previous session's RTY shock | 46 | +3.17 (t +0.37) | 72 | 3 of 4 | **WATCHLIST** |
| D89 t00871 | 6E follows the previous session's SI shock | 59 | +10.04 (t +2.24) | 99 | 3 of 4 | **CONFIRM** |
| D90 t00872 | ES follows the previous session's 6J shock | 44 | -15.67 (t -0.78) | 3 | 1 of 4 | **REJECT** |
| D91 t00873 | ZN follows the previous session's NQ shock | 48 | -2.97 (t -0.53) | 32 | 1 of 4 | **REJECT** |
| D92 t00874 | 6J follows the previous session's RTY shock | 46 | +1.27 (t +0.11) | 49 | 3 of 4 | **WATCHLIST** |
| D93 t00875 | 6E follows the previous session's HG shock | 60 | -2.18 (t -0.42) | 33 | 2 of 4 | **REJECT** |
| D94 t00876 | RTY follows the previous session's 6J shock | 44 | -17.33 (t -0.74) | 10 | 2 of 4 | **REJECT** |

Three of eleven confirm (≈0.4 false confirmations expected at these thresholds). **Before use:** independent-data replication
(HistData spot FX for the euro and yen sessions; owned GLBX NQ for the Nasdaq shock) and an account test.

## 227. D84/D87/D89 on independent data; a macro-shock account cannot pass an evaluation (S8)

**No trial spent; N 870.** `reports/a30_shock_account.json`.

**Independent data** (HistData spot FX sessions 18:05 → 16:55 New York; owned GLBX NQ for the shock; HistData silver):
- **D89 (euro follows a silver shock):** positive at every threshold (1.5 / 2 / 2.5 σ) in 2018–22 (t 1.5–2.5) and 2023–26 (t 0.6–2.3),
  with either silver source; ~0 in 2010–17. Holds since 2018 — the same profile as D68.
- **D84 (yen follows a Nasdaq shock):** strong in 2018–22 (t 2–3), positive but weak in 2023–26 (t 0.5–1.6), ~0 in 2010–17. Moderate.
- **D87 (yen follows a corn shock):** mixed; at 2.5 σ strongly negative in 2010–17 (t −2.5). Fragile; set aside.

**As a standalone account** (one 50K Daily account trading whichever rule fires — D68 → 8 MES, D89 → 30 M6E, D84 → 3 6J — sitting out
other days; Yahoo daily bars, one-bar paths; the plan's solver brackets; 84-day replay): 13–44 trades a year; **P(payout) 0–9%, mean
net −$25 to −$180** in both 2018–22 and 2023–26. Event rules this rare cannot reach a $3,000 target inside four months, whatever their
per-trade edge. **The macro-shock edges are real enough to keep (D68 is in the demo) but are not a standalone strategy.**

## 228. D-series family 30 protocol: speculator positioning (CFTC COT) sets next week's direction (S1)

**No trial spent; N 870. Written and committed BEFORE any positioning statistic is computed.** A daily-direction signal is what a
standalone account needs (§227: event rules are too rare). The legacy COT report (owned, `data/cot/`, 2010–2026) carries
non-commercial (speculator) long and short positions for every market of §171; Z08 (§117–§118, retired) used COMMERCIAL flow for
gold and crude only. Positions are as of Tuesday, published Friday 15:30 New York; the signal applies to the five sessions of the
following week (Monday … Friday), each a daily round trip (§177's costs). Recent-period design (§180).

1. **Signals per market:** net = (non-commercial long − short) / open interest. (i) **flow** = net this week − net last week; (ii)
   **crowding** = (net − its mean over the previous 52 weeks) / their SD, used only when |z| > 1.5. Direction: with the signal (follow)
   or against it (fade), fixed by discovery. Codes: ES 13874A, NQ 209742, RTY 239742, ZN 043602, 6E 099741, 6J 097741, GC 088691,
   SI 084691, HG 085692, CL 067651, NG 023651, ZC 002602, ZS 005602, ZW 001602.
2. **Tests: 14 × 2 = 28**; ~1.4 by chance. Statistic: net bps per session, t clustered by week. **Carried:** net > 0 with t > 1.96.
3. **Validation (one trial each), sealed 2023-01 → 2026-08:** (a) net > 0 against not trading, t > 1.645 (week-clustered); (b) placebo:
   the signal from a random other week, 1,000 draws, ≥ 95th pct; (c) positive in ≥ 3 of the 4 years. CONFIRM if all; WATCHLIST if net
   > 0; REJECT. A CONFIRM is replayed as a standalone account. Z and D market-tests from 107.

## 229. Family-30 discovery: speculator positioning sets no direction — 0 of 28 carried (S1)

**No trial spent; N 870.** `reporting/d30_cot.py`, `reports/d30_discovery.json`. Best: wheat fading crowded speculator positions
(+20.5 bps a session, t +1.55, 60 weeks), ES following speculator flow (+5.5, t +1.52). Family 30 is empty.

## 230. D-series family 31 protocol: small-trader and commercial positioning (S1)

**No trial spent; N 870. Written and committed BEFORE any statistic is computed.** The other two COT groups: non-reportable
(small traders — the retail proxy) and commercials (hedgers; Z08 used them for gold and crude only, 2010–26, retired). Exactly §228's
design (flow and crowding, next week's five sessions, week-clustered t, recent-period discovery / sealed validation), with net =
(group long − short) / open interest for each group. **14 markets × 2 groups × 2 signals = 56 tests**; ~2.8 by chance. Z and D
market-tests from 107.

## 231. Family-31 discovery: two of 56 (fewer than chance, ~2.8); D95–D96 registered per protocol (S1–S5)

**No trial spent at registration; N 870. Committed BEFORE validation data is read.** `reporting/d31_cotgroups.py`,
`reports/d31_discovery.json`; `signals/d_cot.py`.

| id | market | signal | rule | sessions | discovery net |
|---|---|---|---|---|---|
| D95 | ZW | small crowding | fade | 324 | +24.16, t +2.43 |
| D96 | SI | small flow | follow | 1255 | +7.22, t +1.98 |

Z and D market-tests 107–108.

## 232. D95–D96 validated: rejected; COT positioning holds nothing (S6–S8)

**Two trials spent: t00877–t00878. N 870 → 872.**

| id, trial | rule | sessions | net bps (t) | placebo pct | tier |
|---|---|---|---|---|---|
| D95 t00877 | ZW fades small crowding (next week) | 217 | -12.37 (t -1.25) | 12 | **REJECT** |
| D96 t00878 | SI follows small flow (next week) | 915 | -1.41 (t -0.24) | 42 | **REJECT** |

## 233. D68's timing: since 2023 the S&P's response to a bond shock is all in the day window (S8)

**No trial spent; N 872.** Owned MNQ trades after a ZN shock (Yahoo ZN, 2 σ): 2018–22 night 18:00 → 09:30 +20.1 bps (t +1.67) and day
09:30 → 16:00 +19.8 (t +1.19); **2023–26 night +2.0 (t +0.13), day +40.7 (t +2.26).** The deployed implementation (§211: the MNQ
ticket's 09:30 → 16:00 window) is the right one; no change.

## 234. D-series family 32 protocol: weekend gaps (S1)

**No trial spent; N 872. Written and committed BEFORE any statistic is computed.** Weekend news arrives while futures are shut; the
Sunday 18:00 reopen gaps from Friday's close. Does Monday's window follow or reverse it? Family-8 grids (owned trades): MNQ — gap =
the night session's first price (Sunday 18:00) against Friday's day-window close (16:00); target = Monday's day window 09:30–16:00.
MGC — gap = Sunday 18:00 against Friday's London close (11:30); target = Monday's London window 03:00–11:30. Forms: |gap| > 1 σ
and > 2 σ (σ = SD of the previous 52 weekend gaps). **2 markets × 2 thresholds = 4 tests.** Recent-period design (§180); carried at
net > 0 with t > 1.96 (follow or fade by the sign); validation as §207, 3 (placebo: random non-gap Mondays). Z and D tests from 109.

## 235. Family-32 discovery: weekend gaps predict nothing — 0 of 4 carried (S1)

**No trial spent; N 872.** `reports/d32_discovery.json`: MNQ and gold Mondays after weekend gaps beyond 1 or 2 σ: best +13.9 bps
(t +0.37). Empty.

## 236. D-series family 33 protocol: effort versus result overnight (S1)

**No trial spent; N 872. Written and committed BEFORE any statistic is computed.** The family-4 segment table (owned trades, §152)
has each night's volume ratio (to the previous 20) and return. Two states, defined in advance: **absorption** — volume ratio > 1.3
with |overnight return| below its median (heavy trading, little movement); **thin push** — volume ratio < 0.8 with |return| above its
median (a move on light trading). Direction = the sign of the overnight close location (where the night ended in its range) for
absorption, and of the overnight return for the thin push; the target window (MNQ 09:30–16:00, MGC 03:00–11:30) is traded in that
direction or against it, fixed by discovery. **2 markets × 2 states = 4 tests.** Recent-period design (§180); carried at net > 0 with
t > 1.96; validation as §207, 3 (placebo: the same rule on random other days). Z and D market-tests from 109.

## 237. Family-33 discovery: effort versus result predicts nothing usable — 0 of 4 carried (S1)

**No trial spent; N 872.** `reports/d33_discovery.json`: MNQ absorption nights (fade the close location) +24.6 bps, t +1.90, n 89 —
below the bar; thin push and both gold states ~0. Empty.

## 238. D-series family 34 protocol: failed and accepted breaks of the prior session's range (S1)

**No trial spent; N 872. Written and committed BEFORE any statistic is computed.** Family-8 minute grids (closes). For each target
session (MNQ day 09:30–16:00; MGC London 03:00–11:30), the reference range is the previous target session's high/low close, and the
excursion window is the session before the target (MNQ night 18:00–09:30; MGC Asia 18:00–03:00), same contract at both ends required.
**Failed break**: the excursion traded beyond one side of the reference range but its last close is back inside (direction = the side
broken). **Accepted break**: its last close is beyond the range (direction = that side). Days breaking both sides are excluded. The
target session is traded open→close in the direction or against it, fixed by discovery. **2 markets × 2 states = 4 tests.**
Recent-period design (§180), costs §180; carried at net > 0 with t > 1.96; validation as §207, 3. Z and D market-tests from 109.

## 239. Family-34 discovery: prior-range breaks predict nothing — 0 of 4 carried (S1)

**No trial spent; N 872.** `reports/d34_discovery.json`: failed breaks faded +7.4 bps (MNQ, t +1.07) and +6.2 bps (gold, t +1.48);
accepted breaks ~0. Empty.

## 240. D-series family 35 protocol: signed jump variation (S1)

**No trial spent; N 872. Written and committed BEFORE any statistic is computed.** From each target session's 1-minute close-to-close
returns (family-8 grids, same contract only): SJ = (Σ r² over r > 0 − Σ r² over r < 0) / Σ r². Signal for session D = sign of SJ on
session D−1 (same window: MNQ day 09:30–16:00, MGC London 03:00–11:30); session D traded open→close, follow or fade fixed by
discovery. Forms: **all** days, and **strong** (|SJ| above its discovery median). **2 markets × 2 forms = 4 tests.** Recent-period
design (§180); costs §180; carried at net > 0, t > 1.96; validation as §207, 3. Z and D market-tests from 109.

## 241. Family-35 discovery: signed jump variation predicts nothing — 0 of 4 carried (S1)

**No trial spent; N 872.** `reports/d35_discovery.json`: MNQ fade, all days +5.8 bps (t +1.66); strong +3.7 (t +0.76); gold ~0. Empty.

## 242. D-series family 36 protocol: the open against the prior session's VWAP (S1)

**No trial spent; N 872. Written and committed BEFORE any statistic is computed.** Prior target session's VWAP from the family-8 grids
(closes × volume, same contract as the target's open required). Signal = sign(target open − prior VWAP); target session open→close
(MNQ day, MGC London), follow or fade fixed by discovery. Forms: **all**, **strong** (|distance| in bps above its discovery median).
**2 × 2 = 4 tests.** Recent-period design (§180); costs §180; carried at net > 0, t > 1.96; validation as §207, 3.

## 243. Family-36 discovery: the open against prior VWAP predicts nothing — 0 of 4 carried (S1)

**No trial spent; N 872.** `reports/d36_discovery.json`: best +1.8 bps (t +0.32). Empty.

## 244. D-series family 37 protocol: the plan's foreign windows after a US-session shock (S1)

**No trial spent; N 872. Written and committed BEFORE any statistic is computed.** Family 24's design (§207) never had the two
foreign plan products as targets. Targets: the NKD Tokyo window 09:00–15:00 and the FDXM Xetra window 09:00–17:30 (A21's HistData
window paths; their within-era drift removal is kept — it only centres the target). Both windows open after the US session of the
previous weekday has closed, so the predictor (a shock on that weekday: |Yahoo daily return| > 2 × SD of the previous 60, the
family-24 definition) is known before entry. **Predictors: all 14 family-10 markets; 14 × 2 = 28 tests.** Follow or fade fixed by
discovery; costs §180 (NKD 0.2, DAX 0.3 bps). Recent-period design (§180); carried at net > 0, t > 1.96; validation as §207, 3. ~1.4
carried expected by chance — the validation is the filter.

## 245. Family-37 discovery: NKD and DAX after US shocks — 0 of 28 carried (S1)

**No trial spent; N 872.** `reports/d37_discovery.json`: best DAX after a ZN shock, follow, +25.9 bps (t +1.87), n 79; NKD after a ZN
shock, follow, +15.5 (t +1.61). Both point the same way as the confirmed D68 (MNQ follows a ZN shock) but neither clears the bar, and
no pooled test is formed after seeing them. Recorded as consistent with D68, not as evidence. Empty.

## 246. D-series family 38 protocol: the volatility index (S1)

**No trial spent; N 872. Written and committed BEFORE any statistic is computed.** First use of the VIX in the programme (Yahoo ^VIX,
^VIX3M daily closes, 16:15 ET). Signals on day D−1, known before both targets open (MNQ day 09:30–16:00 on D; MGC London 03:00–11:30
on D): **A shock** — |log VIX change| > 2 × SD of the previous 60; direction = sign of the change; follow/fade fixed by discovery.
**B inversion** — VIX close > VIX3M close; **C elevated** — VIX close ≥ 1.25 × its previous-20 mean; B and C trade the target long or
short (fixed by discovery) on those days only, judged on the DEMEANED target return (discovery-window mean removed) so that drift is
not carried. **3 signals × 2 targets = 6 tests.** Costs §180; recent-period design (§180); carried at net > 0, t > 1.96; validation as
§207, 3 (placebo: random other days).

## 247. Family-38 discovery: the VIX predicts nothing usable — 0 of 6 carried (S1)

**No trial spent; N 872.** `reports/d38_discovery.json`: MNQ follows a VIX shock +23.3 bps (t +1.36, n 75); elevated-VIX short +18.2
(t +0.95); inversion and every gold test ~0. Empty.

## 248. D-series family 39 protocol: shocks in markets new to the programme (S1)

**No trial spent; N 872. Written and committed BEFORE any statistic is computed.** D68 (a 10-year shock leads MNQ) is the strongest
confirmed rule; family 24 used only four predictors from the 14-market universe. New predictors (Yahoo daily, open→close, family-10
outlier filter): **ZT=F** (2-year), **ZB=F** (30-year), **DX-Y.NYB** (dollar index), **HYG** (high-yield credit, 16:00 close),
**BTC-USD** (dated by its UTC day, which ends 20:00 ET — before both targets open). Shock on the previous weekday: |return| > 2 × SD of
the previous 60 (family 24). Targets: MNQ day 09:30–16:00 and MGC London 03:00–11:30 (family-8 grids), follow or fade fixed by
discovery. **5 × 2 = 10 tests.** Costs §180; recent-period design; carried at net > 0, t > 1.96; validation as §207, 3.

## 249. Family-39 discovery: shocks in five new markets — 0 of 10 carried (S1)

**No trial spent; N 872.** `reports/d39_discovery.json`: best MNQ fades a bitcoin shock +31.0 bps (t +1.64, n 73); MNQ follows a
2-year shock +21.9 (t +1.44). Empty.

## 250. D-series family 40 protocol: the day after the weekly energy inventory reports (S1)

**No trial spent; N 872. Written and committed BEFORE any statistic is computed.** EIA crude stocks are released Wednesdays 10:30 ET
and natural-gas storage Thursdays 10:30 ET (holiday-shifted weeks are not adjusted — they dilute, not bias). Release-day move = the
Yahoo daily open→settlement bar of that weekday (family-10 series, which contains the release); target = the next weekday's bar,
follow or fade fixed by discovery. **CL: Wednesday → Thursday; NG: Thursday → Friday; forms all and strong (|release-day| above its
discovery median) — 4 tests.** Costs §177 (CL 0.7, NG 1.4 bps); recent-period design (§180); carried at net > 0, t > 1.96; validation
as §207, 3 (placebo: the same rule on the other weekdays).

## 251. Family-40 discovery: energy inventory days — 0 of 4 carried (S1)

**No trial spent; N 872.** `reports/d40_discovery.json`: best NG strong-Thursday fade +35.5 bps (t +1.26, n 122); CL ~0. Empty.

## 252. D-series family 41 protocol: the London 16:00 FX fix (S1)

**No trial spent; N 872. Written and committed BEFORE any statistic is computed.** The WM/Reuters benchmark fix (16:00 London) concentrates
hedging and rebalancing flow in a window around it; a move into the fix may unwind, or continue, afterwards. HistData minute bars
(corrected New York clock, §140) converted to London time. Pre-fix move = close at 16:00 vs close at 15:30 London (last bar at or before
each); target = 16:00 → 16:30, follow or fade fixed by discovery; dollar-quoted direction as the futures (USD/JPY, USD/CAD, USD/CHF
inverted to 6J, 6C, 6S). Pairs: EUR, GBP, JPY, AUD, CAD, CHF; forms **all** and **strong** (|pre-fix| above its discovery median).
**6 × 2 = 12 tests.** Costs §177 where listed (6E 0.3, 6J 0.5), 0.5 bps otherwise. Recent-period design (§180); carried at net > 0,
t > 1.96; validation as §207, 3 (placebo: the same rule at 15:00 → 15:30 / 15:30 → 16:00 on random days).

## 253. Family-41 discovery: the move into the London fix unwinds — 3 of 12 carried, registered D97–D99 (S1)

**No trial spent yet; N 872.** `reports/d41_discovery.json` (module `reporting/d41_fix.py`). All six pairs FADE the 15:30 → 16:00 move
over 16:00 → 16:30 (gross +0.2 to +1.9 bps) — one direction everywhere, the documented fix reversal. Carried:
- **D97** 6B all: fade, +0.68 bps net, t +2.37, n 1294; Z and D market-test 109.
- **D98** 6B strong: fade, +1.43 bps net, t +3.36, n 647; Z and D market-test 110.
- **D99** 6S strong: fade, +0.99 bps net, t +2.75, n 647; Z and D market-test 111.

**Before validation, the scale.** About 1 bp a day on 6B ($62,500 notional) is ~$12 a contract a day before the account's own costs;
§177's 0.5 bps is below 6B's one tick (~0.7 bps). Even confirmed, this is a D32-sized edge: it cannot carry or protect an account.
Validated once each by `signals/d_fix.py` (outcome injection first) because the protocol says so; the answer goes to the watchlist
or the record, not to the bot.

## 254. D97–D99 validated (t00879–t00881): the fix reversal did not survive — 0 CONFIRM (S1)

**N 875.** Sealed 2023-01 → 2026-08, HistData minute bars, outcome injection recovered first (power 25–37%).
- **D97** 6B fade, all days: **REJECT** — 840 days, −0.60 bps (t −2.01): the sign reversed; years 2 of 4.
- **D98** 6B fade, strong: **REJECT** — 302 days, −0.77 bps (t −1.42); years 1 of 4.
- **D99** 6S fade, strong: **WATCHLIST** — 408 days, +0.18 bps (t +0.31); placebo 0th pct; years 3 of 4. Not worth tracking:
  a positive mean this small is below any futures round trip.

The one-direction-everywhere pattern of 2018–22 was a period effect (the fix's reform after 2015 and the post-2020 shift to
algorithmic fix execution are both plausible), not a standing edge. Family 41 is closed. Z and D market-tests reach 111.

## 255. D-series family 42 protocol: D68 below the shock threshold (S1)

**No trial spent; N 875. Written and committed BEFORE any statistic is computed.** D68 trades only beyond 2σ (~14 sessions a year). If
equities absorb rate news slowly in general, moderate 10-year moves should carry the same sign, and the overlay could trade far more
often. ZN (Yahoo daily open→settlement, family-24 SD of the previous 60) on the previous weekday, in two DISJOINT bands that exclude
D68's own days: **1σ < |r| ≤ 2σ** and **0.5σ < |r| ≤ 1σ**. Targets: MNQ day 09:30–16:00 (family-8 grid), the DAX and NKD windows
(A21 paths, as family 37). Follow or fade fixed by discovery. **2 bands × 3 targets = 6 tests.** Costs §180; recent-period design;
carried at net > 0, t > 1.96; validation as §207, 3 (placebo: days with |r| ≤ 0.5σ).

## 256. Family-42 discovery: D68 does not extend below 2σ — 0 of 6 carried (S1)

**No trial spent; N 875.** `reports/d42_discovery.json`: MNQ after 1–2σ ZN moves +0.8 bps (t +0.11), after 0.5–1σ +3.0 (t +0.44);
DAX even fades moderate moves (t +1.60 for the fade). The 10-year effect is a tail phenomenon only; D68 stays as deployed. Empty.

## 257. A29 design: contracts sized to a volatility forecast (S8)

**A COMPUTATION; zero edge; no trial; N 875. Variants fixed BEFORE any result.** The plan's brackets are dollars set by the account's
state and its contract count never changes, so a quiet day ends at the window close with little decided and a wild one hits a
bracket in minutes. Direction is not predictable; volatility is. Per session d: R = the window's per-contract range (max high −
min low of its path), forecast F_d = mean R over the previous 20 sessions, reference = median F over the previous 250 (causal);
n_d = round(n × reference / F_d) clipped. Variants: **plan** (n fixed); **V1** clip [1, 2n]; **V2** clip [1, n] (only ever smaller);
**V3** the inverse, n × F_d / reference, clip [1, 2n] (direction check). A23 engine (it reproduces the live engine; `nvec` added,
default path unchanged and re-checked), 50K Daily, live sizes, both histories, every start, 84 days; books of the five live markets.
Adopt only if V1 or V2 beats the plan on the five-account book in BOTH histories on mean net and P(net > 0).

## 258. A29 result: volatility-sized contracts do not beat the plan — not adopted (S8)

**No trial; N 875.** `reports/a29_book.json`, five live markets, 50K Daily, every start, 84 days:

| book | 2016–20 mean / P(net>0) / p10 | 2021–26 mean / P(net>0) / p10 |
|---|---|---|
| plan | +8,023 / 92% / +259 | +9,468 / 93% / +1,748 |
| V1 (ref/F, [1, 2n]) | +8,268 / 88% / −140 | +10,569 / 93% / +1,237 |
| V2 (ref/F, [1, n]) | +7,246 / 89% / −272 | +8,671 / 93% / +1,286 |
| V3 (F/ref, [1, 2n]) | +7,406 / 90% / −75 | +9,517 / 91% / +285 |

V1 raises the mean in both histories but lowers P(net > 0) in 2016–20 and the 10th percentile in both, so it fails §257's rule.
Per market the sign flips between histories (MNQ +$778 in 2021–26, −$531 in 2010–20; crude worse in both), which is what a
zero-edge reshuffle of variance looks like. The fixed-contract plan stays. `a23.replay(nvec=...)` is kept for later sizing questions.

## 259. D-series family 43 protocol: gold's Asia session as a target (S1)

**No trial spent; N 875. Written and committed BEFORE any statistic is computed.** No family has traded gold's Asia session (18:00 →
03:00 ET, family-8 grid, dated by its end day D). Predictors finished before it opens, on the previous weekday: **gold's London window**
(03:00–11:30) and **MNQ's day session** (09:30–16:00), each open→close on its own grid. Target open→close, same contract; follow or
fade fixed by discovery; forms **all** and **strong** (|predictor| above its discovery median). **2 × 2 = 4 tests.** Cost MGC 0.8 bps;
recent-period design; carried at net > 0, t > 1.96; validation as §207, 3.

## 260. Family-43 discovery: gold's Asia session — 0 of 4 carried (S1)

**No trial spent; N 875.** `reports/d43_discovery.json`: best follows MNQ's day, +1.2 bps (t +1.12). Asia gold barely moves. Empty.

## 261. D-series family 44 protocol: Europe's pre-US move against MNQ's (S1)

**No trial spent; N 875. Written and committed BEFORE any statistic is computed.** If US index futures under-react to Europe's morning,
the gap closes in the US session. Divergence on day D = DAX (HistData grxeur, corrected clock) 03:00 → 09:30 ET return minus MNQ's
(night grid) over the same span, in bps. Target: MNQ day 09:30–16:00 on D, in the sign of the divergence or against it (fixed by
discovery). Forms **all** and **strong** (|divergence| above its discovery median). **2 tests.** Cost MNQ 0.5 bps; recent-period design;
carried at net > 0, t > 1.96; validation as §207, 3.

## 262. Family-44 discovery: Europe's pre-US divergence — 0 of 2 carried (S1)

**No trial spent; N 875.** `reports/d44_discovery.json`: MNQ moves with the divergence +2.6 bps (t +0.75), strong +6.6 (t +1.20). Empty.

## 263. D-series family 45 protocol: bitcoin's weekend into Monday (S1)

**No trial spent; N 875. Written and committed BEFORE any statistic is computed.** Bitcoin is the one large risk asset that trades
through the weekend. Weekend move = the sum of BTC-USD's Saturday and Sunday UTC daily open→close returns (Yahoo; ends 20:00 ET Sunday,
before both targets open). Targets on Monday: MNQ day 09:30–16:00 and MGC London 03:00–11:30 (family-8 grids), follow or fade fixed
by discovery; forms **all** and **strong** (|weekend| above its discovery median). **2 × 2 = 4 tests.** Costs §180; recent-period
design; carried at net > 0, t > 1.96; validation as §207, 3.

## 264. Family-45 discovery: bitcoin's weekend predicts nothing on Monday — 0 of 4 carried (S1)

**No trial spent; N 875.** `reports/d45_discovery.json`: all |t| < 0.5. Empty.

## 265. D-series family 46 protocol: intraday breaks of the prior session's range (S1)

**No trial spent; N 875. Written and committed BEFORE any statistic is computed.** Family 34 tested breaks made overnight; this tests
them inside the target session (MNQ day; MGC London), family-8 grids, prior session's high/low close on the same contract. The FIRST
minute (after the first 5) whose close is beyond either side defines the event; one per session. **Break**: enter at that minute's
close, with the break or against it (fixed by discovery), exit at the session close. **Sweep**: the price is back inside the range
within 15 minutes of the break — enter at that minute's close against the break's side (or with it, fixed by discovery), exit at the
close. **2 markets × 2 forms = 4 tests.** Costs §180; recent-period design; carried at net > 0, t > 1.96; validation as §207, 3.

## 266. Family-46 discovery: intraday range breaks and sweeps — 0 of 4 carried (S1)

**No trial spent; N 875.** `reports/d46_discovery.json`: MNQ with the break +2.6 bps (t +0.78); gold sweep fade +4.6 (t +1.48). Empty.

## 267. D-series family 47 protocol: the morning sets the afternoon (S1)

**No trial spent; N 875. Written and committed BEFORE any statistic is computed.** Family 16 tested only the last 30 minutes. Here the
whole afternoon: MNQ 09:30 → 12:00 predicts 13:00 → 16:00; gold (London grid) 03:00 → 07:00 predicts 08:30 → 11:30 (after the
08:30 releases). Prices at those minutes, same contract; follow or fade fixed by discovery; forms **all** and **strong** (|morning|
above its discovery median). **2 × 2 = 4 tests.** Costs §180; recent-period design; carried at net > 0, t > 1.96; validation §207, 3.

## 268. Family-47 discovery: the morning does not set the afternoon — 0 of 4 carried (S1)

**No trial spent; N 875.** `reports/d47_discovery.json`: MNQ follow +4.0 bps (t +1.81), strong +4.6 (t +1.28); gold ~0. Empty.

## 269. D-series family 48 protocol: drift after the 10:00 ET releases (S1)

**No trial spent; N 875. Written and committed BEFORE any statistic is computed.** Family 9 (§168) covered 08:30 and 14:00 only.
10:00 ET carries ISM, consumer confidence, home sales, JOLTS. Release days detected as family 9: 5-minute volume from 10:00 above 3 ×
its previous-20 median. The first k minutes (k = 5, 15) from 09:59's close predict 10:00+k → the window's close (MNQ day grid to
16:00; gold London grid to 11:30), follow or fade fixed by discovery. **2 markets × 2 k = 4 tests.** Costs §180; recent-period design;
carried at net > 0, t > 1.96; validation as §207, 3.

## 270. Family-48 discovery: 10:00 releases — 0 of 4 carried; the MNQ half is uninformative (S1)

**No trial spent; N 875.** `reports/d48_discovery.json`: gold, 68 detected release days, follow +6.9 / +6.5 bps (t +1.48 / +1.77).
MNQ: the volume detector found only **8** days in five years — 10:00 volume sits inside the opening half hour's, so 3 × the median is
rarely reached. That half tests nothing; it is NOT re-tuned after the fact (a release calendar would be needed). Empty.

## 271. D-series family 49 protocol: follow or fade the morning by the recent intraday regime (S1)

**No trial spent; N 875. Written and committed BEFORE any statistic is computed.** Family 47 asked one fixed direction of all days. Here
the direction adapts: variance ratio VR = var(30-minute returns) / (6 × var(5-minute returns)) within each session, averaged over the
previous 20 sessions (same contract within each return). Rule: trade the afternoon (family 47's windows) in sign(morning) × sign(VR − 1)
— follow after trending weeks, fade after mean-reverting ones. Also **inverse** (the opposite sign) is not a separate test: the
direction of the whole rule is fixed by discovery as usual. **2 markets = 2 tests.** Costs §180; recent-period design; carried at
net > 0, t > 1.96; validation as §207, 3.

## 272. Family-49 discovery: 1 of 2 carried — MNQ's afternoon follows the morning unless the weeks have trended; D100 registered (S1)

**No trial spent yet; N 875.** `reports/d49_discovery.json` (module `reporting/d49_vr.py`). MNQ: the rule's INVERSE carried —
afternoon in sign(morning) × −sign(VR − 1): +4.63 bps a session net, t +2.11, n 1270. Gold −0.6 (t −0.37).

**Read honestly.** VR < 1 on 90% of sessions, so the rule is mostly "follow the morning" — family 47's near-miss (+4.0, t +1.81) —
with a fade after trending weeks. It shares its data with family 47; the validation reports always-follow beside it so the regime
part's own contribution is visible. **Placebo (fixed now):** the same rule with the VR series rolled by a random 60+ sessions, 1000
draws. Registry ids widened to three digits (tests/test_registry_consistency.py) — the D-series reached D100. Z and D market-test 112.

**Scale, before validation.** +4.6 bps on MNQ (~$40,000 notional) is ~$18 a contract a session; at the plan's 4 contracts ~$75 a
session, ~$6,000 over an 84-session account — the first discovery cell large enough to matter to an account if it held.

## 273. D100 validated (t00882): WATCHLIST — the regime adds nothing; the afternoon edge shrank to noise (S1)

**N 876.** Sealed 2023-01 → 2026-08, 928 sessions, injection recovered first (power 28%): net **+1.73 bps**
(t +0.86); placebo (regime rolled) **54th** pct — the VR switch is no better than a random one; years 3 of 4
(2023 −2.0, 2024 +1.3, 2025 +5.8, 2026 +1.8). Positive mean → WATCHLIST, but nothing here to trade: what remains is a small,
insignificant "follow the morning" tilt. Not deployed. Z and D market-test 112.

## 274. D-series family 50 protocol: the LBMA gold auctions (S1)

**No trial spent; N 876. Written and committed BEFORE any statistic is computed.** The LBMA gold price is set by auction at 10:30 and
15:00 London; hedging and benchmark flow concentrates into it, as at the FX fix (family 41). Owned MGC trades (family-8 London grid,
03:00–11:30 ET); auction times converted to New York per day (London/New York DST offsets differ for a few weeks a year). Pre-move =
the 30 minutes into the auction; target = the 30 minutes after, follow or fade fixed by discovery, same contract. Forms **all** and
**strong** (|pre-move| above its discovery median). **2 auctions × 2 forms = 4 tests.** Cost MGC 0.8 bps; recent-period design;
carried at net > 0, t > 1.96; validation as §207, 3 (placebo: the same rule one hour earlier).

## 275. Family-50 discovery: the LBMA gold auctions — 0 of 4 carried (S1)

**No trial spent; N 876.** `reports/d50_discovery.json`: gross moves after either auction are +0.2 to +0.8 bps, below gold's 0.8 bps
cost; every net is ≤ 0. Empty.

## 276. D-series family 51 protocol: MNQ's night session as a target (S1)

**No trial spent; N 876. Written and committed BEFORE any statistic is computed.** The plan trades MNQ's day; the night (18:00 → 09:30,
family-8 grid, dated by its end day) has not been a target. Predictors from the preceding day session (09:30–16:00): its whole
return, and its last hour (15:00 → 16:00). Target open→close of the night, same contract as the predictor's end; follow or fade fixed
by discovery; forms **all** and **strong** (above the discovery median). **2 × 2 = 4 tests.** Cost MNQ 0.5 bps; recent-period design;
carried at net > 0, t > 1.96; validation as §207, 3.

## 277. Family-51 discovery: MNQ's night after the day — 0 of 4 carried (S1)

**No trial spent; N 876.** `reports/d51_discovery.json`: fading a strong last hour +6.6 bps (t +1.67); the day's return predicts
nothing. Empty.

## 278. D-series family 52 protocol: the opening print (S1)

**No trial spent; N 876. Written and committed BEFORE any statistic is computed.** The first minute after a pit-era open carries the
opening imbalance. MNQ: 09:30 → 09:31 (day grid); gold: 08:20 → 08:21 (COMEX open, London grid). Target: the next minute's close →
the window's close (16:00 / 11:30), follow or fade fixed by discovery, same contract. Forms **all** and **heavy** (that minute's volume
above 2 × its previous-20 median). **2 × 2 = 4 tests.** Costs §180; recent-period design; carried at net > 0, t > 1.96; validation
as §207, 3.

## 279. Family-52 discovery: 1 of 4 carried — MNQ's day follows its opening minute; D101 registered (S1)

**No trial spent yet; N 876.** `reports/d52_discovery.json` (module `reporting/d52_open.py`): MNQ, all sessions, follow the
09:30 → 09:31 move to 16:00: **+9.59 bps** net, t +2.73, n 1257. Heavy-volume form n 29 only (t +1.34);
gold's COMEX-open minute +1.1 / +4.3 (t +0.67 / +1.10). Entry at the 09:31 close, signal from the night grid's 09:30:00 close to
it — no look-ahead. **Placebo (fixed now):** first-minute signs shuffled across the sealed sessions (keeps drift, breaks the
link), 1000 draws. Scale: +9.6 bps on ~$40,000 notional ≈ $38 a contract a session; at 4 contracts ~$150 — account-sized if it held.
Z and D market-test 113.

## 280. D101 validated (t00883): WATCHLIST — the opening minute adds ~0.6 bps over the plan's long (S1)

**N 877.** Sealed 2023-01 → 2026-08, 926 sessions, injection recovered first (power 41%): net **+3.80 bps** (t
+1.13); placebo (shuffled signs) **91th** pct; years 3 of 4 (2023 +5.5, 2024 −0.6, 2025 +3.9, 2026 +7.8).
The plan's always-long MNQ ticket made **+3.24** over the same sessions, so switching to the opening-minute
direction would add ~0.6 bps — nothing. Discovery's +9.6 was 2018–22 specific. WATCHLIST by the positive mean; no action.
Z and D market-test 113.

## 281. D-series family 53 protocol: gold against the dollar before New York (S1)

**No trial spent; N 877. Written and committed BEFORE any statistic is computed.** Gold is priced in dollars; a dollar move that gold
has not matched may be closed later. Divergence = gold's 03:00 → 08:00 ET return (London grid) minus
EUR/USD's (HistData eurusd, corrected clock) over the same span, in bps (a weaker dollar should lift both). Target: gold 08:00 → 11:30,
against the divergence (catch-up) or with it, fixed by discovery; forms **all** and **strong** (above the discovery median). **2 tests.**
Cost MGC 0.8 bps; recent-period design; carried at net > 0, t > 1.96; validation as §207, 3.

## 282. Family-53 discovery: gold against the dollar before New York — 0 of 2 carried (S1)

**No trial spent; N 877.** `reports/d53_discovery.json`: catch-up +1.1 bps (t +0.63 / +0.41). Empty.

## 283. D-series family 54 protocol: the top of the hour (S1)

**No trial spent; N 877. Written and committed BEFORE any statistic is computed.** Scheduled execution (TWAP slices, hourly
rebalances) clusters at the top of the hour. Each full hour inside the window (MNQ 10:00–15:00 → 6 hours; gold 04:00–11:00 → 8):
pre = :55 → :00, target = :00 → :05, follow or fade fixed by discovery, same contract; t clustered by day (family 8's statistic).
Forms **all** and **strong** (|pre| above its discovery median). **2 markets × 2 forms = 4 tests.** Costs §180 per round trip;
recent-period design; carried at net > 0, t > 1.96; validation as §207, 3.

## 284. Family-54 discovery: the top of the hour — 0 of 4 carried (S1)

**No trial spent; N 877.** `reports/d54_discovery.json`: a fade exists in gross terms (gold +0.3 to +0.5 bps) but never covers the
round trip; every net is negative. Empty.

## 285. D-series family 55 protocol: the variance risk premium (S1)

**No trial spent; N 877. Written and committed BEFORE any statistic is computed.** VRP on day D−1 = (VIX/100)² / 252 − the mean of
squared MNQ day-session log returns over the previous 20 sessions (both per-day variances; VIX from family 38). Signal: VRP above its
trailing 250-session median → one side, below → the other, fixed by discovery; the target (MNQ day; gold London on D) judged
DEMEANED (discovery mean removed) so drift is not carried. **2 targets = 2 tests.** Costs §180; recent-period design; carried at net
> 0, t > 1.96; validation as §207, 3.

## 286. Family-55 discovery: the variance risk premium — 0 of 2 carried (S1)

**No trial spent; N 877.** `reports/d55_discovery.json`: MNQ +0.5 bps (t +0.15), gold +0.1 (t +0.04). Empty.

## 287. D-series family 56 protocol: the previous session's close location (S1)

**No trial spent; N 877. Written and committed BEFORE any statistic is computed.** CLV = (close − low) / (high − low) of the previous
target session's minute closes (MNQ day; gold London), same contract as the next session's open. Signal sign(CLV − 0.5); the next
session open→close traded with it or against it, fixed by discovery. Forms **all** and **extreme** (CLV > 0.85 or < 0.15). **2 × 2 =
4 tests.** Costs §180; recent-period design; carried at net > 0, t > 1.96; validation as §207, 3.

## 288. Family-56 discovery: the previous close location — 0 of 4 carried (S1)

**No trial spent; N 877.** `reports/d56_discovery.json`: fading an extreme close +7.7 bps on MNQ (t +1.45), +4.4 on gold (t +1.41).
Empty.

## 289. D-series family 57 protocol: the newer shock predictors into the plan's other products (S1)

**No trial spent; N 877. Written and committed BEFORE any statistic is computed.** Cross-asset tail shocks are the only class that has
confirmed (D68, D84, D89). Families 38–39 tried six newer predictors only on MNQ and gold. Here: predictors **ZT, ZB, DX, HYG, BTC**
(family 39's series) and **VIX** (family 38, log change), shock on the previous weekday as family 24 (|x| > 2 × SD of the previous
60); targets **NKD and DAX** (A21 window paths, as family 37), **CL and ZS** (family-10 Yahoo sessions). Follow or fade fixed by
discovery. **6 × 4 = 24 tests** (~1.2 carried by chance). Costs §177/§180 (NKD 0.2, DAX 0.3, CL 0.7, ZS 0.7); recent-period design;
carried at net > 0, t > 1.96; validation as §207, 3.

## 290. Family-57 discovery: 1 of 24 carried (fewer than chance, ~1.2); D102 registered per protocol (S1)

**No trial spent yet; N 877.** `reports/d57_discovery.json` (module `reporting/d57_newshock.py`): **D102** the DAX window fades a
HYG shock, +27.59 bps, t +1.98, n 89. Next: NKD follows a 2-year shock +21.7 (t +1.91); DAX follows a dollar
shock +28.6 (t +1.70). Registered as families 10, 26 and 31 did with a chance-level count; the sealed window decides. Z and D
market-test 114.

## 291. D102 validated (t00884): WATCHLIST — fails only on t, with 31 events; an untouched-period check fixed before running (S1, S8)

**N 878.** Sealed 2023-01 → 2026-08, injection recovered first (power **11%** — 31 events): net **+36.56 bps** (t
+1.58 < 1.645); placebo (after non-shock days) **100th** pct; years 3 of 4 (2023 −26.8, 2024 +0.8,
2025 +59.0, 2026 +105.4). It kept its sign and grew (discovery +27.6). WATCHLIST under §119 — not confirmed, not deployed.

**A check on untouched data, fixed now (no trial; it cannot change the tier).** 2010-01 → 2017-12 has never been used by family 57.
The same rule (HYG shock on the previous weekday, fade, 0.3 bps) on (i) A21's DAX window paths and (ii) the real index, Yahoo ^GDAXI
daily open→close. Read: the same sign with mean > 0 on both supports forward-tracking; anything else drops it to the record.

## 292. D102's untouched-period check: reversed in 2010–17 — dropped to the record, not forward-tracked (S8)

**No trial; N 878.** Fixed in §291 before running. HYG shock → fade the DAX, 2010-01 → 2017-12: A21 paths **−19.6 bps** (t −1.54,
n 111, 3 of 8 years); real index ^GDAXI **−25.0 bps (t −2.11)**, n 119, 3 of 8 years. Over 2010–26: +6.1 (t +0.69) and +0.6
(t +0.07). The sign flips by era: no standing edge. D102 stays WATCHLIST by its trial but is not tracked.

## 293. D-series family 58 protocol: MNQ's hour after the cash close (S1)

**No trial spent; N 878. Written and committed BEFORE any statistic is computed.** Index futures trade on after the 16:00 cash close
(after-hours earnings, MOC-imbalance unwinds), and the plan never trades it. New family-8 grid ("MNQ", "post"), 16:00 → 16:55 ET (ends
before the 17:00 break; `d8_intraday.EXTRA_SESSIONS`). Predictors from the same day's session (day grid): the whole day 09:30 → 16:00,
and the last 10 minutes 15:50 → 16:00. Target 16:00 → 16:55 (open of the post grid's first minute to its last close), same contract;
follow or fade fixed by discovery; forms **all** and **strong** (above the discovery median). **2 × 2 = 4 tests.** Cost MNQ 0.5 bps;
recent-period design; carried at net > 0, t > 1.96; validation as §207, 3.

## 294. Family-58 discovery: MNQ's hour after the close — 0 of 4 carried (S1)

**No trial spent; N 878.** `reports/d58_discovery.json`: following the last 10 minutes +1.3 / +1.7 bps (t +1.55 / +1.33); the day's
move predicts nothing. Empty.

## 295. D-series family 59 protocol: the post-close hour as a predictor (S1)

**No trial spent; N 878. Written and committed BEFORE any statistic is computed.** After-hours earnings land in 16:00 → 16:55 (family-58
grid). Its return (day close at 16:00 → 16:55) predicts **the night** (18:00 → 09:30, dated the next weekday) and **the next day
session** (09:30 → 16:00); follow or fade fixed by discovery; forms **all** and **strong** (above the discovery median). Same contract
at both ends of each target. **2 targets × 2 forms = 4 tests.** Cost MNQ 0.5 bps; recent-period design; carried at net > 0, t > 1.96;
validation as §207, 3.

## 296. Family-59 discovery: the post-close hour predicts neither the night nor the next day — 0 of 4 carried (S1)

**No trial spent; N 878.** `reports/d59_discovery.json`: best follows a strong post-close move into the next day +6.9 bps (t +1.21).
Empty.

## 297. D-series family 60 protocol: the 200-day average as the direction (S1)

**No trial spent; N 878. Written and committed BEFORE any statistic is computed.** Family 18 used 5- and 20-session trends. Here the
long regime: the previous weekday's Yahoo settlement (NQ=F, GC=F, family-10 universe bars) above or below its 200-session mean →
long or short the plan window on D (MNQ day; gold London; family-8 grids), JUDGED DEMEANED (discovery-window mean removed) so drift is
not carried; the sign of the rule fixed by discovery. **2 tests.** Costs §180; recent-period design; carried at net > 0, t > 1.96;
validation as §207, 3.

## 298. Family-60 discovery: the 200-day regime — 0 of 2 carried (S1)

**No trial spent; N 878.** `reports/d60_discovery.json`: MNQ −0.0 bps (t −0.01), gold +1.9 (t +0.91), demeaned. Empty.

## 299. D-series family 61 protocol: Treasury auction demand (S1)

**No trial spent; N 878. Written and committed BEFORE any data is fetched or any statistic computed.** New data: TreasuryDirect's
public auction results (`TA_WS/securities/search`), every Note and Bond auction (2, 3, 5, 7, 10, 20, 30 years; reopenings grouped by
the rounded original term; TIPS and FRNs excluded), results at ~13:00 ET. A weak auction is a timed rates shock — D68's class.
Demand measures, each as a z-score against the previous 6 auctions of the same term: **dealer share** (primaryDealerAccepted /
competitiveAccepted; high = weak) and **bid-to-cover** (low = weak). Event = |z| > 1, direction = weak (+1) or strong (−1).
Targets: **MNQ 13:01 → 16:00 the same day** (day grid) and **MNQ's next day session** 09:30 → 16:00; with or against, fixed by
discovery. **2 measures × 2 targets = 4 tests.** Cost MNQ 0.5 bps; recent-period design; carried at net > 0, t > 1.96; validation
as §207, 3 (placebo: |z| ≤ 1 auctions).

## 300. Family-61 discovery: Treasury auction demand — 0 of 4 carried (S1)

**No trial spent; N 878.** 1,357 note and bond auctions fetched (2009 → 2026; `data/cache/treasury_auctions.json`, not committed —
regenerable from the public API). `reports/d61_discovery.json`: after a weak auction by dealer share, MNQ's afternoon falls the
sensible way, +9.9 bps short (t +1.38, n 154); next day +7.2 (t +0.67); bid-to-cover weaker still. Empty.

## 301. D-series family 62 protocol: Treasury auction demand into the other plan targets (S1)

**No trial spent; N 878. Written and committed BEFORE any statistic is computed.** Family 61's events (both measures, |z| > 1) on
auction day D. Targets, all opening after the 13:00 result: **gold's London window** on the next weekday (family-8 grid), **ZN's next
session** (family-10 Yahoo bar), **NKD** and **DAX** windows on the next weekday (A21 paths). With or against the weak side, fixed by
discovery. **2 measures × 4 targets = 8 tests.** Costs §177/§180 (MGC 0.8, ZN 0.4, NKD 0.2, DAX 0.3); recent-period design; carried at
net > 0, t > 1.96; validation as §207, 3.

## 302. Family-62 discovery: auction demand into gold, ZN, NKD, DAX — 0 of 8 carried (S1)

**No trial spent; N 878.** `reports/d62_discovery.json`: best DAX short after a weak auction +14.6 bps (t +1.79); ZN itself does not
move after its own auctions (t +0.30 / +0.05) — the result is priced by the close. Empty.

## 303. D-series family 63 protocol: real-yield and breakeven shocks (S1)

**No trial spent; N 878. Written and committed BEFORE any statistic is computed.** New data: FRED daily **DFII10** (10-year TIPS real
yield) and **T10YIE** (10-year breakeven inflation), end-of-day values from that day's closing prices (fredgraph CSV; the high-yield
OAS series only reaches back to 2023 there and is excluded). Change in bps on day D; shock = |change| > 2 × SD of the previous 60.
Targets on the next weekday: **gold's London window** and **MNQ's day session** (family-8 grids), with or against the shock's sign,
fixed by discovery. **2 × 2 = 4 tests.** Costs §180; recent-period design; carried at net > 0, t > 1.96; validation as §207, 3.
(Deployment note for later: a live version needs those closing values by 03:00 ET — a market proxy, not FRED's publication.)

## 304. Family-63 discovery: 1 of 4 carried — gold moves against a real-yield shock; D103 registered (S1)

**No trial spent yet; N 878.** `reports/d63_discovery.json` (module `reporting/d63_realyield.py`): **D103** gold's next London window
against a DFII10 shock, **+31.56 bps**, t +2.22, n 71. The sign is the textbook one (gold falls when real
yields jump). MNQ +13.7 (t +0.85); breakeven shocks ~0. Z and D market-test 115.

**Fixed now, before the trial:** (i) the sealed validation as §207, 3; (ii) whatever its tier, the untouched-period check §291
introduced — 2010-01 → 2017-12 (never used by family 63) on the owned MGC London grid and on Yahoo GC=F daily sessions — the same
sign with mean > 0 on both is required before anything is forward-tracked or proposed. (iii) Scale if it held: ~14 events a year;
+30 bps on gold's ~$4,000 × 10 oz ≈ $40,000 MGC notional is ~$120 a contract per event, ~$950 at the plan's 8 contracts.

## 305. D103 validated (t00885): REJECT — gold stopped answering real yields after 2022 (S1, S8)

**N 879.** Sealed 2023-01 → 2026-08, 42 events, injection recovered first (power 31%): net **-11.08 bps** (t
-0.61); placebo **21th** pct; years 2 of 4 (2023 +2.5, 2024 +0.4, 2025 −41.0, 2026 −25.4). The
pre-committed 2010–17 check (§304): MGC London +2.7 (t +0.32, 5 of 8 years); GC=F daily sessions −6.5 (t −0.67). So the effect was a
2018–22 phenomenon: the gold/real-yield link that held then broke as central-bank buying took over the gold price from 2022. Closed.
Z and D market-test 115.

## 306. D-series family 64 protocol: platinum shocks; and a descriptive 2010–17 column from here on (S1)

**No trial spent; N 879. Written and committed BEFORE any statistic is computed.** Platinum (Yahoo PL=F daily, family-10 outlier filter) has not been a predictor. *Amended before any statistic
existed: Yahoo's PL=F has no session open (open = close), so its return is settlement → settlement.* Shock on the previous weekday as family 24 → gold's London window and MNQ's day
session (family-8 grids), follow or fade fixed by discovery. **2 tests.** Costs §180; recent-period design; carried at net > 0,
t > 1.96; validation as §207, 3.

**Descriptive only (does not change carrying):** every carried test since §252 (D97–D103) failed out of sample, and the two checked
on 2010–17 were flat or reversed. From this family on, each scan also prints the same rule on 2010-01 → 2017-12 beside the discovery
result, so a carried test's history is visible before a trial is spent. The carrying rule (§119, §133) is unchanged.

## 307. Family-64 discovery: platinum shocks — 0 of 2 carried (S1)

**No trial spent; N 879.** `reports/d64_discovery.json`: gold fades +6.9 bps (t +0.75; 2010–17 −5.9), MNQ +0.3 (t +0.02). Empty.

## 308. D-series family 65 protocol: the foreign windows' morning sets their afternoon (S1)

**No trial spent; N 879. Written and committed BEFORE any statistic is computed.** Family 47 for the two foreign plan products. Tokyo's
cash market breaks for lunch (11:30–12:30), so the Nikkei's day has two sessions. NKD: 09:00 → 11:30 Tokyo predicts 12:30 → 15:00;
DAX: 09:00 → 12:00 Berlin predicts 13:00 → 17:30 (HistData via `d3.histdata`, corrected clock, local times). Follow or fade fixed by
discovery; forms **all** and **strong** (above the discovery median). **2 × 2 = 4 tests**, with the descriptive 2010–17 column (§306).
Costs §180 (NKD 0.2, DAX 0.3); recent-period design; carried at net > 0, t > 1.96; validation as §207, 3.

## 309. Family-65 discovery: the foreign windows' morning — 0 of 4 carried (S1)

**No trial spent; N 879.** `reports/d65_discovery.json`: NKD follows a strong morning +1.5 bps (t +0.78; 2010–17 +4.6, t +2.19 —
an older effect that has faded); DAX +4.8 (t +1.47; 2010–17 0.0). Empty.

## 310. D-series family 66 protocol: the Tokyo fix on gotobi days (S1)

**No trial spent; N 879. Written and committed BEFORE any statistic is computed.** Japanese importers settle on "gotobi" days (the
5th, 10th, 15th, 20th, 25th and the month's last day; a weekend date moves to the previous weekday) and buy dollars at the 09:55 Tokyo
fix. HistData usdjpy (from 2016; corrected clock) at Tokyo times. **Pre**: 08:00 → 09:55; **post**: 09:55 → 12:00. Each traded on
gotobi days only, in 6J's direction (long 6J = short USD/JPY), side fixed by discovery. **2 tests.** Non-gotobi days shown beside
(descriptive) and are the validation placebo. Cost 6J 0.5 bps; recent-period design; carried at net > 0, t > 1.96; §306's
descriptive early column covers 2016–17 only.

## 311. Family-66 discovery: 1 of 2 carried — the yen recovers after the gotobi fix; D104 registered (S1)

**No trial spent yet; N 879.** `reports/d66_discovery.json` (module `reporting/d66_gotobi.py`): **D104** long 6J 09:55 → 12:00 Tokyo
on gotobi days, **+1.70 bps**, t +2.69, n 359; the same window on other days +0.34; 2016–17
+5.01 (t +1.65) — the mechanism's sign in both periods. The run-up (08:00 → 09:55) +0.8 (t +1.04). Scale,
before validation: ~1.7 bps on 6J's ~$85,000 is ~$14 a contract, ~70 times a year — a D32-sized edge; it would not carry an account.
Z and D market-test 116.

## 312. D104 validated (t00886): WATCHLIST — the gotobi reversal replicated in size, failing only on years (S1)

**N 880.** Sealed 2023-01 → 2026-08, 249 gotobi days, injection recovered first (power 22%): net **+1.78 bps**
(t +1.74 > 1.645 ✓); placebo (non-gotobi days, same window, -1.64) **100th** pct ✓;
years **2 of 4** ✗ (2023 −1.08, 2024 +3.80, 2025 +3.41, 2026 −0.32, eight months). The size matched discovery (+1.70) and the
gotobi-specific difference is ~3.4 bps — the most robust replication in the D-series since D68 — but under §119 it is WATCHLIST.

**Usability, regardless of tier:** ~$15 a 6J contract per trade, ~70 trades a year (~$1,000 a contract a year); 6J is not one of the
plan's products, and a standalone 50K evaluation ($3,000 target) would take years. Forward-tracked on the watchlist (§133): the next
gotobi days' 09:55 → 12:00 6J moves can be logged at no cost. Not deployed. Z and D market-test 116.

## 313. D-series family 67 protocol: the Shanghai Gold Exchange benchmark auctions (S1)

**No trial spent; N 880. Written and committed BEFORE any statistic is computed.** The one robust recent replication (D104) is a
scheduled-flow effect at a fix. The Shanghai gold benchmark is set by auction at 10:15 and 14:15 Beijing (no DST; 22:15 / 02:15 ET in
summer, 21:15 / 01:15 in winter) — inside gold's Asia session (owned MGC trades, family-8 grid). Pre = the 30 minutes into the auction,
target = the 30 minutes after, follow or fade fixed by discovery, same contract; forms **all** and **strong** (|pre| above its discovery
median). **2 × 2 = 4 tests**, with the descriptive 2010–17 column (§306; the SGE benchmark began April 2016, so 2016–17 only). Cost
MGC 0.8 bps; recent-period design; carried at net > 0, t > 1.96; validation as §207, 3 (placebo: the same rule one hour earlier).

## 314. Family-67 discovery: the Shanghai gold auctions — 0 of 4 carried (S1)

**No trial spent; N 880.** `reports/d67_discovery.json`: gross moves around either auction are +0.1 to +0.3 bps against 0.8 bps of
cost; every net is negative (2016–17 the same). Empty.

## 315. D-series family 68 protocol: gold's New York afternoon (S1)

**No trial spent; N 880. Written and committed BEFORE any statistic is computed.** New family-8 grid ("MGC", "ny"), 11:30 → 16:55 ET.
(i) **Settlement**: COMEX gold settles on 13:28–13:30 ET trades; pre = 13:00 → 13:30, target 13:30 → 14:00, follow or fade fixed by
discovery; forms **all** and **strong**. (ii) **Relay**: the same day's London window (03:00 → 11:30) predicts the afternoon 11:30 →
16:55, follow or fade; forms **all** and **strong**. Same contract throughout. **4 tests**, with the descriptive 2010–17 column (§306).
Cost MGC 0.8 bps; recent-period design; carried at net > 0, t > 1.96; validation as §207, 3.

## 316. Family-68 discovery: gold's New York afternoon — 0 of 4 carried (S1)

**No trial spent; N 880.** `reports/d68_discovery.json`: a small settlement fade (strong +0.7 bps net, t +1.29; 2010–17 +0.8, t +1.73)
and a London→afternoon follow (+1.4, t +0.87) — consistent in sign across periods but below the bar and below cost-worthiness. Empty.

## 317. D-series family 69 protocol: the Friday afternoon before the weekend (S1)

**No trial spent; N 880. Written and committed BEFORE any statistic is computed.** Weekend risk is hedged on Friday afternoons. Gold:
Friday 11:30 → 16:55 (family-68 grid); MNQ: Friday 13:00 → 16:00 (day grid). Each Friday's return minus the mean of the same window on
Monday–Thursday in discovery (so drift and time-of-day are not credited); long or short fixed by discovery. **2 tests**, with the
descriptive 2010–17 column (§306). Costs §180; recent-period design; carried at net > 0, t > 1.96; validation as §207, 3 (placebo: the
same window on other weekdays).

## 318. Family-69 discovery: the Friday afternoon — 0 of 2 carried (S1)

**No trial spent; N 880.** `reports/d69_discovery.json`: gold's Friday afternoon was strong in 2010–17 (+8.5 bps over other days,
t +2.48) and is gone in 2018–22 (−0.5, t −0.20); MNQ +5.0 (t +1.11; 2010–17 −2.3). Empty.

## 319. D-series family 70 protocol: the commodity index roll (S1)

**No trial spent; N 880. Written and committed BEFORE any statistic is computed.** Index funds tracking the S&P GSCI roll from the
front contract to the next on the 5th–9th business days of each month (the "Goldman roll"): selling pressure on the front month in
those days is a documented, monthly flow. Family-10 Yahoo front-continuous sessions (open → settlement) of the GSCI's commodity
futures in the universe: **CL, NG, HG, GC, SI, ZC, ZS, ZW**. Each roll-day session's return minus the market's mean on other days in
discovery (not crediting drift); long or short fixed by discovery. **8 tests** (~0.4 by chance), with the descriptive 2010–17 column
(§306). Costs §177; recent-period design; carried at net > 0, t > 1.96; validation as §207, 3 (placebo: other business days).
Business days = weekdays with a session in the market's own series.

## 320. Family-70 discovery: the commodity index roll — 0 of 8 carried (S1)

**No trial spent; N 880.** `reports/d70_discovery.json`: crude is weaker on roll days in both periods (short +15.4 bps, t +0.94;
2010–17 +14.0, t +1.66) — the documented sign, but not significant; every other market ~0 or inconsistent. Empty.

## 321. D-series family 71 protocol: the Nikkei on gotobi days (S1)

**No trial spent; N 880. Written and committed BEFORE any statistic is computed.** D104's gotobi dollar demand weakens the yen into the
09:55 Tokyo fix; a weaker yen lifts Japanese exporters. NKD (HistData jpxjpy, Tokyo times): **pre** 09:00 → 09:55 and **post** 09:55 →
12:00 on gotobi days (family-66 calendar), each minus the same window's mean on non-gotobi days in discovery; long or short fixed by
discovery. **2 tests**, with the descriptive 2010–17 column (§306). Cost NKD 0.2 bps; recent-period design; carried at net > 0,
t > 1.96; validation as §207, 3 (placebo: non-gotobi days).

## 322. Family-71 discovery: the Nikkei on gotobi days — 0 of 2 carried (S1)

**No trial spent; N 880.** `reports/d71_discovery.json`: pre −0.1 bps (t −0.02), post +1.4 (t +0.64). The gotobi flow does not reach
the Nikkei. Empty.

## 323. D-series family 72 protocol: pinning to round strikes into the close (S1)

**No trial spent; N 880. Written and committed BEFORE any statistic is computed.** Option open interest clusters at round strikes, and
dealers' hedging can pull the underlying toward them into expiry and the close. **MNQ**: at 15:00 the NQ price's nearest multiple of
100; trade 15:00 → 16:00 toward it (direction = sign(level − price)), or away (fixed by discovery). **Gold**: at 13:00 the nearest
multiple of $10; trade 13:00 → 13:30 (into settlement, family-68 grid) toward or away. Only when the distance is under half the grid
step (always true) — so all days. **2 tests**, with the descriptive 2010–17 column (§306). Costs §180; recent-period design; carried
at net > 0, t > 1.96; validation as §207, 3 (placebo: a level grid shifted by half a step).

## 324. Family-72 discovery: pinning to round strikes — 0 of 2 carried (S1)

**No trial spent; N 880.** `reports/d72_discovery.json`: MNQ toward the 100-point level +1.1 bps (t +0.72); gold moves slightly
AWAY from $10 levels into settlement but below cost (−0.7 net). Empty.

## 325. D-series family 73 protocol: gold and silver catching up with each other in London (S1)

**No trial spent; N 880. Written and committed BEFORE any statistic is computed.** Divergence over 03:00 → 07:00 ET = silver's return
(HistData xagusd, corrected clock) minus gold's (owned MGC London grid). Targets 07:00 → 11:30: **gold** in the sign of the divergence
(catch-up) or against it, and **silver** (xagusd, the D32 instrument) against the divergence or with it; fixed by discovery. **2 tests**,
with the descriptive 2010–17 column (§306). Costs §177/§180 (MGC 0.8, SI 0.5); recent-period design; carried at net > 0, t > 1.96;
validation as §207, 3.

## 326. Family-73 discovery: gold and silver catching up — 0 of 2 carried (S1)

**No trial spent; N 880.** `reports/d73_discovery.json`: gold +0.5 bps (t +0.27), silver +2.4 (t +0.77). Empty.

## 327. D-series family 74 protocol: the ECB reference-rate fix (S1)

**No trial spent; N 880. Written and committed BEFORE any statistic is computed.** The ECB publishes euro reference rates from a 14:15
Frankfurt concertation; some corporate and fund flows execute against it. HistData (corrected clock) at Frankfurt times for EUR, GBP,
JPY, CHF against the dollar, in the futures' direction (6E, 6B, 6J, 6S). **Pre** 13:45 → 14:15 and **post** 14:15 → 14:45, each traded
long or short (fixed by discovery) every day — the question is a directional drift around the fix, judged against the same pair's
mean 30-minute return in 10:00–13:00 Frankfurt (not crediting drift). **4 pairs × 2 windows = 8 tests**, with the descriptive 2010–17
column (§306; JPY from 2016). Costs §177 (6E 0.3, 6J 0.5; 6B, 6S 0.5); recent-period design; carried at net > 0, t > 1.96; validation
as §207, 3.

## 328. Family-74 discovery: the ECB reference-rate fix — 0 of 8 carried (S1)

**No trial spent; N 880.** `reports/d74_discovery.json`: every |net| < 0.5 bps; best 6E long after the fix +0.5 (t +1.36). Empty.

## 329. D-series family 75 protocol: crude against its refining margin (S1)

**No trial spent; N 880. Written and committed BEFORE any statistic is computed.** The 3-2-1 crack (Yahoo settlements; $/bbl =
(2 × RB × 42 + HO × 42 − 3 × CL) / 3) measures refiners' margin; a jump in it raises refiners' demand for crude. Days where any of the
three front-continuous series moves more than 6 × its MAD (contract-roll jumps) are dropped. Signals on day D: **A shock** — the
crack's daily change beyond 2 × SD of the previous 60; **B stretch** — the crack's level more than 2 SD from its previous-60 mean.
Target CL's next session (family-10 open → settlement), with the signal's sign or against it, fixed by discovery. **2 tests**, with
the descriptive 2010–17 column (§306). Cost CL 0.7 bps; recent-period design; carried at net > 0, t > 1.96; validation as §207, 3.

## 330. Family-75 discovery: crude against its refining margin — 0 of 2 carried (S1)

**No trial spent; N 880.** `reports/d75_discovery.json`: fading a crack shock +20.3 bps (t +0.51; 2010–17 +34.0, t +1.90); following a
stretch +26.8 (t +1.09; 2010–17 −17.2). Empty.

## 331. D-series family 76 protocol: sector and regional ETF shocks (S1)

**No trial spent; N 880. Written and committed BEFORE any statistic is computed.** Predictors new to the programme (Yahoo daily, open →
close, 16:00 ET; family-10 outlier filter): **SMH** (semiconductors), **XLF** (banks), **XLE** (energy), **EEM** (emerging markets),
**FXI** (China large caps), **TLT** (long Treasuries). Shock on the previous weekday as family 24. Targets: MNQ's day session and gold's
London window (family-8 grids), follow or fade fixed by discovery. **6 × 2 = 12 tests** (~0.6 by chance), with the descriptive 2010–17
column (§306). Costs §180; recent-period design; carried at net > 0, t > 1.96; validation as §207, 3.

## 332. Family-76 discovery: 1 of 12 carried — MNQ fades a bank-stock shock; D105 registered (S1)

**No trial spent yet; N 880.** `reports/d76_discovery.json` (module `reporting/d76_etf.py`): **D105** MNQ fades an XLF shock,
**+55.20 bps**, t +2.33, n 69; 2010–17 +9.01 (t +0.69) — same sign, weak. Next: MNQ fades a
semiconductor shock +35.3 (t +1.74; 2010–17 +23.2, t +2.18); MNQ follows a TLT shock +31.1 (t +1.64 — D68's direction). Z and D
market-test 117.

## 333. D105 validated (t00887): WATCHLIST — the bank-shock fade replicated in size; fails only on years (S1)

**N 881.** Sealed 2023-01 → 2026-08, 57 events, injection recovered first (power 23%): net **+47.84 bps** (t
+1.85 ✓); placebo (non-shock days) **100th** pct ✓; years **2 of 4** ✗ (2023 +23.7, 2024 −7.9, 2025
+163.5, 2026 −22.6). The size matched discovery (+55.2) but the out-of-sample gain is concentrated in 2025 (the April sell-off and
rebound), and 2010–17 was only weakly the same sign (+9.0, t +0.69). WATCHLIST under §207, 3 — forward-tracked, not deployed. The
second result in a row (after D104) that fails only (c). Z and D market-test 117.

## 334. D-series family 77 protocol: a second set of ETF shocks (S1)

**No trial spent; N 881. Written and committed BEFORE any statistic is computed.** Family 76's design (§331) with six more predictors:
**GDX** (gold miners), **KRE** (regional banks), **XLU** (utilities), **LQD** (investment-grade credit), **XLK** (technology), **XLY**
(consumer discretionary). Targets MNQ day and gold London; **12 tests**, descriptive 2010–17 column. Costs §180; recent-period design;
carried at net > 0, t > 1.96; validation as §207, 3.

## 335. Family-77 discovery: 1 of 12 carried — MNQ fades a technology shock; D106 registered (S1)

**No trial spent yet; N 881.** `reports/d77_discovery.json` (scan via `d76_etf.py --family77`): **D106** MNQ fades an XLK shock,
**+43.70 bps**, t +2.21, n 80; **2010–17 +23.06 (t +1.97)** — the first carried test of
recent families whose earlier history is nearly significant the same way. Across families 76–77 MNQ FADES every equity-sector shock
(XLF, XLK, SMH, KRE, XLY: +21 to +55 bps), while it FOLLOWS bond-side shocks (TLT, LQD, and D68's ZN). Z and D market-test 118.

## 336. D106 validated (t00888): WATCHLIST — and what the equity-shock fades are: crisis rebounds (S1, S8)

**N 882.** Sealed 2023-01 → 2026-08, 52 events (power 10%): net **+38.51 bps** (t +1.39); placebo
**100th** pct; years **1 of 4** (2023 −12.7, 2024 −8.3, **2025 +151.8**, 2026 −19.7). WATCHLIST by the mean only.

**Reading D105 and D106 together.** Both fade an equity-sector shock, both replicate their discovery size, and both owe it to one
year: 2025 (the April crash and V-shaped rebound), as discovery owes much to 2020. These rules are "buy the crash" — paid in
V-shaped crises, slightly negative in ordinary years. That is a crisis bet, not a standing edge, and for a prop account it is worse
than it looks: the losing years are the normal ones, and the winning trades come in the weeks the daily loss limits bind hardest.
Neither is forward-tracked for deployment; future sector-shock fades on MNQ are read in this light. Z and D market-test 118.

## 337. D-series family 78 protocol: Nasdaq against the S&P inside the day (S1)

**No trial spent; N 882. Written and committed BEFORE any statistic is computed.** Family 17 tested relative value on daily bars only.
Divergence = MNQ's 09:30 → 12:00 return (day grid) minus the S&P's (HistData spxusd, corrected clock) over the same span, in bps.
Target MNQ 12:00 → 16:00, against the divergence (catch-down) or with it, fixed by discovery. Forms **all** and **strong** (|divergence|
above its discovery median). **2 tests**, with the descriptive 2010–17 column (§306; NQ day sessions are sparse before 2013). Cost MNQ
0.5 bps; recent-period design; carried at net > 0, t > 1.96; validation as §207, 3.

## 338. Family-78 discovery: Nasdaq against the S&P inside the day — 0 of 2 carried (S1)

**No trial spent; N 882.** `reports/d78_discovery.json`: MNQ with the morning divergence +3.7 bps (t +1.51) — and the opposite sign
in 2010–17 (−2.3, t −1.60). Empty.

## 339. D-series family 79 protocol: MNQ's Asian night sets its European morning (S1)

**No trial spent; N 882. Written and committed BEFORE any statistic is computed.** MNQ's night grid split at 03:00 ET: the Asian part
18:00 → 03:00 predicts the European part 03:00 → 09:30, follow or fade fixed by discovery, same contract; forms **all** and **strong**
(above the discovery median). **2 tests**, with the descriptive 2010–17 column. Cost MNQ 0.5 bps; recent-period design; carried at
net > 0, t > 1.96; validation as §207, 3.

## 340. Family-79 discovery: MNQ's Asian night and European morning — 0 of 2 carried (S1)

**No trial spent; N 882.** `reports/d79_discovery.json`: fading a strong Asian night +5.1 bps (t +1.87; 2010–17 +1.7, t +0.67). Empty.

## 341. D-series family 80 protocol: soybeans against the crush margin (S1)

**No trial spent; N 882. Written and committed BEFORE any statistic is computed.** Family 75's design for the demo's soybean account:
board crush ($/bu) = ZM × 0.022 + ZL × 0.11 − ZS (Yahoo settlements; ZM $/short ton, ZL ¢/lb, ZS ¢/bu converted to $), roll-jump days
dropped as §329. **A shock** — the crush's daily change beyond 2 SD of the previous 60; **B stretch** — its level more than 2 SD from
the previous-60 mean. Target ZS's next session (family-10 open → settlement), with or against, fixed by discovery. **2 tests**, with
the descriptive 2010–17 column. Cost ZS 0.7 bps; recent-period design; carried at net > 0, t > 1.96; validation as §207, 3.

## 342. Family-80 discovery: soybeans against the crush margin — 0 of 2 carried (S1)

**No trial spent; N 882.** `reports/d80_discovery.json`: +5.9 / +9.0 bps (t +0.46 / +0.96), opposite in 2010–17. Empty.

## 343. D-series family 81 protocol: the mid-month Treasury settlement (S1)

**No trial spent; N 882. Written and committed BEFORE any statistic is computed.** Coupon Treasuries settle and pay on the 15th and
the month's end; the mid-month date (the 15th, or the next business day) moves cash between the Treasury's account and banks' reserves
— a liquidity flow twice a month that the turn-of-month calendar (family 5) did not isolate at mid-month. Target on that day: MNQ's
day session and gold's London window, each minus its mean on other days in discovery; long or short fixed by discovery. **2 tests**,
with the descriptive 2010–17 column. Costs §180; recent-period design; carried at net > 0, t > 1.96; validation as §207, 3.

## 344. Family-81 discovery: the mid-month Treasury settlement — 0 of 2 carried (S1)

**No trial spent; N 882.** `reports/d81_discovery.json`: MNQ long +10.5 bps (t +0.68; 2010–17 +10.4, t +1.22); gold short +13.3
(t +1.62; 2010–17 +11.3, t +1.19). The same signs in both periods, ~12 events a year, neither significant. Empty.

## 345. D-series family 82 protocol: VVIX and SKEW shocks (S1)

**No trial spent; N 882. Written and committed BEFORE any statistic is computed.** Two option-market gauges new to the programme (Yahoo
daily closes): **VVIX** (volatility of the VIX) and **SKEW** (CBOE tail-risk pricing). Daily log change on day D; shock = beyond 2 SD
of the previous 60. Targets on the next weekday: MNQ's day session and gold's London window, with the shock's sign or against it,
fixed by discovery. **2 × 2 = 4 tests**, with the descriptive 2010–17 column. Costs §180; recent-period design; carried at net > 0,
t > 1.96; validation as §207, 3.

## 346. Family-82 discovery: VVIX and SKEW shocks — 0 of 4 carried (S1)

**No trial spent; N 882.** `reports/d82_discovery.json`: every |t| < 0.5. Empty.

## 347. D-series family 83 protocol: shocks into the currencies not yet targeted (S1)

**No trial spent; N 882. Written and committed BEFORE any statistic is computed.** Families 24/29 targeted only 6E and 6J among
currencies. Targets: **6A, 6B, 6C, 6S** (Yahoo daily open → settlement, family-10 cleaning). Predictors from the family-10 universe:
**ES, NQ, CL, GC, HG, ZN** (commodity-currency links: copper/gold → AUD, crude → CAD), shock on the previous weekday as family 24;
follow or fade fixed by discovery. **6 × 4 = 24 tests** (~1.2 by chance), with the descriptive 2010–17 column. Cost 0.5 bps (§180's
FX level); recent-period design; carried at net > 0, t > 1.96; validation as §207, 3.

## 348. Family-83 discovery: 8 of 24 carried (vs ~1.2 by chance) — all "follow", none in 2010–17; D107–D114 registered (S1)

**No trial spent yet; N 882.** `reports/d83_discovery.json` (module `reporting/d83_fx.py`):
- **D107** 6B follows a ZN shock: +33.5 bps, t +3.63, n 82; 2010–17 -5.1 (t -0.80); market-test 119.
- **D108** 6A follows a ZN shock: +30.8 bps, t +3.44, n 82; 2010–17 -0.4 (t -0.05); market-test 120.
- **D109** 6S follows a NQ shock: +19.6 bps, t +3.28, n 93; 2010–17 -2.5 (t -0.34); market-test 121.
- **D110** 6S follows a GC shock: +15.9 bps, t +2.65, n 87; 2010–17 +0.9 (t +0.12); market-test 122.
- **D111** 6B follows a GC shock: +22.6 bps, t +2.60, n 87; 2010–17 -4.1 (t -0.92); market-test 123.
- **D112** 6S follows a ZN shock: +18.0 bps, t +2.56, n 82; 2010–17 +10.9 (t +1.28); market-test 124.
- **D113** 6S follows a ES shock: +15.8 bps, t +2.37, n 88; 2010–17 -5.9 (t -0.75); market-test 125.
- **D114** 6C follows a ZN shock: +12.1 bps, t +2.32, n 82; 2010–17 +3.5 (t +0.61); market-test 126.

**Before the trials, the reading.** Eight passes against ~1.2 expected is a real 2018–22 pattern, but the descriptive 2010–17 column
shows none of it, and every carried test FOLLOWS a rates, equity or gold shock into the dollar crosses — the signature of 2022's
one-way dollar trend under repeated rate shocks. Checked first for an artifact: Yahoo's currency-future opens are not the previous
settlement (2–9% of days equal, median gap 5–10 bps), and the target session opens at 18:00 ET after every predictor has settled, so
there is no look-ahead. Registered and validated once each, per protocol; expectation: most fail.

## 349. D107–D114 validated (t00889–t00896): none confirm — the 2022 dollar trend, as read in §348 (S1)

**N 890.** Sealed 2023-01 → 2026-08, injection recovered first for each:
- **D107** 6B follows the previous session's ZN shock: **WATCHLIST** — 48 events, +2.37 bps (t +0.37), placebo 70th.
- **D108** 6A follows the previous session's ZN shock: **REJECT** — 48 events, -2.56 bps (t -0.29), placebo 39th.
- **D109** 6S follows the previous session's NQ shock: **WATCHLIST** — 48 events, +9.05 bps (t +0.85), placebo 93th.
- **D110** 6S follows the previous session's GC shock: **WATCHLIST** — 55 events, +3.20 bps (t +0.32), placebo 76th.
- **D111** 6B follows the previous session's GC shock: **WATCHLIST** — 55 events, +5.79 bps (t +0.90), placebo 86th.
- **D112** 6S follows the previous session's ZN shock: **REJECT** — 48 events, -13.89 bps (t -1.24), placebo 2th.
- **D113** 6S follows the previous session's ES shock: **WATCHLIST** — 52 events, +10.80 bps (t +1.05), placebo 97th.
- **D114** 6C follows the previous session's ZN shock: **WATCHLIST** — 48 events, +3.51 bps (t +0.70), placebo 84th.

Discovery t +2.3 to +3.6 became −1.2 to +1.05; two flipped sign. Family 83 was a 2018–22 (mostly 2022) regime, which the descriptive
2010–17 column had already shown. Lesson recorded for the remaining search: a carried test whose 2010–17 column is flat (|t| < 1) has
now failed out of sample every time (D97–D99, D102, D103, D107–D114). Z and D market-tests reach 126.

## 350. D-series family 84 protocol: signed volume (a tick-rule order-flow proxy) overnight (S1)

**No trial spent; N 890. Written and committed BEFORE any statistic is computed.** Earlier families used volume levels (27, 33), never
its sign. Per minute, signed volume = sign(close − previous close) × volume (same contract; zero change → 0), from the family-8 grids.
Imbalance = Σ signed / Σ volume over the session before the target: **MNQ** night (18:00 → 09:30) → day session; **gold** Asia
(18:00 → 03:00) → London window. Signal sign(imbalance); follow or fade fixed by discovery; forms **all** and **strong** (|imbalance|
above its discovery median). **2 × 2 = 4 tests**, with the descriptive 2010–17 column. Costs §180; recent-period design; carried at
net > 0, t > 1.96; validation as §207, 3.

## 351. Family-84 discovery: overnight signed volume — 0 of 4 carried (S1)

**No trial spent; N 890.** `reports/d84_discovery.json`: MNQ follow +3.2 bps (t +0.91; 2010–17 the opposite, −4.4, t −2.19); gold ~0.
Empty.

## 352. D-series family 85 protocol: a session's signed volume into the next session (S1)

**No trial spent; N 890. Written and committed BEFORE any statistic is computed.** Family 84's imbalance measured over the target
window itself (MNQ day 09:30 → 16:00; gold London 03:00 → 11:30), predicting the same window on the next weekday; follow or fade fixed
by discovery; forms **all** and **strong**. **4 tests**, descriptive 2010–17 column. Costs §180; recent-period design; carried at
net > 0, t > 1.96; validation as §207, 3.

## 353. Family-85 discovery: a session's signed volume — 0 of 4 carried (S1)

**No trial spent; N 890.** `reports/d85_discovery.json`: fades of +2 to +3 bps, |t| ≤ 1.0. Empty.

## 354. D-series family 86 protocol: near-misses that held in both periods (a pooled re-read) (S1)

**No trial spent; N 890. Written and committed BEFORE any pooled statistic is computed.** In this search every carried test whose
2010–17 column was flat failed out of sample (§349), and the few results that held in both periods were the most robust (D104).
**Rule, fixed now:** over every test in families 64–85 that printed a 2010–17 column, recompute the same rule (direction fixed by
2018–22) on 2010-01 → 2022-12 pooled; **carried** if net > 0 in 2018–22 AND in 2010–17 AND pooled t > 1.96. Honest caveat: the
2010–17 columns were already printed, so this selection is informed by them; it spends no sealed data — 2023-01 → 2026-08 stays the
only test, validation as §207, 3 (each family's own placebo). Tests already validated (D104, D105, D106) and the equity-sector-shock
fades on MNQ (crisis-rebound class, §336) are excluded before computing.

## 355. Family-86: 6 of 9 two-period near-misses clear pooled t > 1.96; D115–D120 registered (S1)

**No trial spent yet; N 890.** `reports/d86_discovery.json`, module `reporting/d86_pooled.py` (each rule's direction and strong
threshold fixed by its 2018–22 discovery; placebos fixed per rule in the registry). Not carried: CL roll-day short (t +1.78), MNQ
strong-Asia fade (t +1.96, not above), gold mid-month short (t +1.86).
- **D115** (nkd_morning) NKD strong morning follow: pooled +3.30 bps, t +2.24, n 1484 (2010–17 +4.64, 2018–22 +1.52); market-test 127.
- **D116** (gotobi_pre) gotobi pre short 6J: pooled +1.42 bps, t +2.01, n 502 (2010–17 +2.95, 2018–22 +0.81); market-test 128.
- **D117** (gold_settlement) gold settlement strong fade: pooled +0.78 bps, t +2.16, n 1645 (2010–17 +0.80, 2018–22 +0.74); market-test 129.
- **D118** (ecb_fix_6e) 6E long after ECB fix: pooled +0.68 bps, t +2.65, n 3365 (2010–17 +0.81, 2018–22 +0.47); market-test 130.
- **D119** (gold_tlt) 77 MGC follows TLT shock: pooled +18.79 bps, t +2.47, n 171 (2010–17 +20.79, 2018–22 +16.40); market-test 131.
- **D120** (gold_lqd) 77 MGC follows LQD shock: pooled +14.18 bps, t +1.97, n 169 (2010–17 +24.99, 2018–22 +0.63); market-test 132.

**Scale, before validation.** D117 (+0.8 bps) and D118 (+0.7) are below anything an account would notice; D116 (+1.4 on 6J) is
D104-sized. **D119** (+18.8 bps a gold London window, ~14 events a year; ~$600 an event at the plan's 8 MGC) would be a D68-like overlay
for the gold account; **D115** (+3.3 bps on NKD's ~$200,000 notional, ~$66 a contract on half the sessions) is NKD-account-sized.

## 356. D115–D120 validated (t00897–t00902): none confirm; gold's rates link reversed after 2022 (S1)

**N 896.** Sealed 2023-01 → 2026-08, injection recovered first for each:
- **D115** nkd_morning: **REJECT** — 515 trades, -0.56 bps (t -0.28), placebo 28th.
- **D116** gotobi_pre: **WATCHLIST** — 249 trades, +0.68 bps (t +0.66), placebo 69th.
- **D117** gold_settlement: **REJECT** — 508 trades, -0.16 bps (t -0.19), placebo 28th.
- **D118** ecb_fix_6e: **WATCHLIST** — 873 trades, +0.15 bps (t +0.32), placebo 100th.
- **D119** gold_tlt: **REJECT** — 48 trades, -36.03 bps (t -2.05), placebo 0th.
- **D120** gold_lqd: **REJECT** — 50 trades, -18.37 bps (t -1.15), placebo 5th.

Two-period consistency (2010–17 and 2018–22) did not protect any of them. **D119** reversed hard — gold FADED long-bond shocks in
every sealed year (−36 bps, t −2.05) — the same post-2022 break as D103 (§305): since central-bank buying took over, gold no longer
moves with US rates the next day. The pooled re-read (§354) is closed. Z and D market-tests reach 132.

## 357. D-series family 87 protocol: "net liquidity" week to week (S1)

**No trial spent; N 896. Written and committed BEFORE any statistic is computed.** New data: FRED weekly **WALCL** (Fed balance sheet),
**WTREGEN** (Treasury General Account), daily **RRPONTSYD** (reverse repo, taken on the same Wednesday); net liquidity = WALCL − TGA −
RRP ($bn, Wednesday levels), published Thursday 16:30 ET (H.4.1). Signal = sign of the week's change. Target: the five sessions from
the next Friday through Thursday — MNQ day sessions and gold London windows — each traded in the signal's direction or against it
(fixed by discovery), judged DEMEANED (discovery mean removed) with week-clustered t. Forms **all** and **strong** (|change| above its
discovery median). **2 markets × 2 forms = 4 tests**, descriptive 2010–17 column. Costs §180 per session; recent-period design;
carried at net > 0, t > 1.96; validation as §207, 3 (placebo: signs shuffled across weeks).

## 358. Family-87 discovery: "net liquidity" week to week — 0 of 4 carried (S1)

**No trial spent; N 896.** `reports/d87_discovery.json`: MNQ with liquidity +2.0 / +3.9 bps a session (t +0.67 / +0.96; 2010–17 ~0);
gold against it +2.0 / +3.9 (t +1.04 / +1.26; 2010–17 the opposite). The popular weekly liquidity signal predicts nothing. Empty.

## 359. D-series family 88 protocol: MNQ around the European close (S1)

**No trial spent; N 896. Written and committed BEFORE any statistic is computed.** European cash markets close at 11:30 ET (17:30 CET);
their closing flows land in US index futures. MNQ day grid: pre 11:00 → 11:30, target 11:30 → 12:00, follow or fade fixed by
discovery; forms **all** and **strong** (above the discovery median). **2 tests**, descriptive 2010–17 column. (The weeks when US and
European clocks differ shift the close to 10:30 or 12:30 ET; those days are kept at 11:30 — a dilution, not a bias.) Cost MNQ 0.5 bps;
recent-period design; carried at net > 0, t > 1.96; validation as §207, 3 (placebo: one hour earlier).

## 360. Family-88 discovery: MNQ around the European close — 0 of 2 carried (S1)

**No trial spent; N 896.** `reports/d88_discovery.json`: 2018–22 ~0 (+0.5 / +0.0 bps); in 2010–17 the move into the European close
reversed significantly (fade +1.7 / +2.8 gross, t −3.33 / −2.68 for "follow") — an effect that has disappeared. Empty.

## 361. D-series family 89 protocol: crude after the EIA release, intraday (S1)

**No trial spent; N 896. Written and committed BEFORE any statistic is computed.** New data: HistData Brent (bcousd) minute bars, 2010 →
2026-09, corrected clock, grid `reporting/hd_grid.py` (WTI has a 2024–26 gap there, so Brent stands in for crude intraday). The EIA
weekly petroleum report (Wednesdays 10:30 ET; holiday-shifted weeks not adjusted) is crude's largest scheduled flow. The first k
minutes after 10:30 (k = 5, 15; from the 10:29 close) predict 10:30 + k → 14:30 (NYMEX settlement), follow or fade fixed by
discovery. **2 tests**, descriptive 2010–17 column. Cost: the MCL account's **5.4 bps** (§180) — what the plan would pay. Recent-period
design; carried at net > 0, t > 1.96; validation as §207, 3 (placebo: the same rule on Tuesdays and Thursdays).

## 362. Family-89 discovery: crude after the EIA release — 0 of 2 carried (S1)

**No trial spent; N 896.** `reports/d89_discovery.json`: k = 15 follow +14.3 bps gross, +8.9 net of MCL's 5.4 (t +1.02); 2010–17 ~0.
Empty.

## 363. D-series family 90 protocol: crude's settlement and its London morning (S1)

**No trial spent; N 896. Written and committed BEFORE any statistic is computed.** Brent grid (§361). **(i) Settlement**: 14:00 → 14:30
ET into NYMEX settlement predicts 14:30 → 15:30, follow or fade; forms all / strong. **(ii) Relay**: London morning 03:00 → 08:00 ET
predicts New York 09:00 → 14:30, follow or fade; forms all / strong. **4 tests**, descriptive 2010–17 column. Cost MCL 5.4 bps;
recent-period design; carried at net > 0, t > 1.96; validation as §207, 3.

## 364. Family-90 discovery: crude's settlement and London morning — 0 of 4 carried; MCL's cost rules out intraday crude (S1)

**No trial spent; N 896.** `reports/d90_discovery.json`: gross moves of +0.7 to +2.3 bps against MCL's 5.4 bps of cost; every net is
negative in 2018–22 (2010–17's relay +14.6 on strong mornings has gone). At MCL's cost, crude sub-windows of a few hours need a gross
edge several times what any minute-level effect here has shown. Empty.

## 365. D-series family 91 protocol: crude's post-settlement drift into the next MCL day (S1)

**No trial spent; N 896. Written and committed BEFORE any statistic is computed.** At the MCL ticket's own scale: crude's move from
settlement to the close, 14:30 → 16:55 ET (Brent grid), predicts the next full window 18:00 → 16:55 (the ticket), follow or fade fixed
by discovery; forms **all** and **strong**. **2 tests**, descriptive 2010–17 column. Cost MCL 5.4 bps; recent-period design; carried
at net > 0, t > 1.96; validation as §207, 3.

## 366. Family-91 discovery: uninformative — Brent has no 18:00 ET price (S1)

**No trial spent; N 896.** `reports/d91_discovery.json`: only 201 of ~1,250 days matched in 2018–22 (ICE Brent pauses 18:00 → 20:00
ET, so the ticket's 18:00 entry is usually missing); net −2.7 / −4.8 (t −0.23 / −0.29). Not re-defined after the fact. Closed as
uninformative; crude at the ticket's scale was covered on daily bars by families 24–29.

## 367. D-series family 92 protocol: the Hang Seng's day into gold and MNQ (S1)

**No trial spent; N 896. Written and committed BEFORE any statistic is computed.** New data: HistData Hang Seng (hkxhkd) minute bars,
corrected clock. Predictor: the Hang Seng's session 09:30 → 16:00 Hong Kong (ends 03:00–04:00 ET). Targets the same ET day: gold
04:00 → 11:30 ET (family-8 London grid, after Hong Kong has closed) and MNQ's day session; follow or fade fixed by discovery; forms
**all** and **strong**. **2 × 2 = 4 tests**, descriptive 2010–17 column. Costs §180; recent-period design; carried at net > 0,
t > 1.96; validation as §207, 3.

## 368. Family-92 discovery: the Hang Seng into gold and MNQ — 0 of 4 carried (S1)

**No trial spent; N 896.** `reports/d92_discovery.json`: every |t| ≤ 1.0 in 2018–22. Empty.

## 369. A30 design: skip the quietest forecast days (S8)

**A COMPUTATION; zero edge; no trial; N 896. Variants fixed BEFORE any result.** Under zero edge a trade's expectation is minus its
cost. On days whose range is small against the brackets, the window usually ends between them with a small P&L — little progress
toward the target, a full round trip paid. Forecast F_d = mean per-contract window range over the previous 20 sessions (A29's);
reference = its previous-250 median. Variants: **plan** (trade every day); **S20** skip days with F_d below the 20th percentile of
the previous 250 forecasts; **S40** below the 40th. A23 engine with `skip` (the account sits; no cost), 50K Daily, live sizes, both
histories, every start, 84 days; five-account books. Adopt only if S20 or S40 beats the plan in BOTH histories on mean net AND
P(net > 0).

## 370. A30 result: skipping quiet days loses — not adopted (S8)

**No trial; N 896.** `reports/a30_book.json`, five live markets: plan +8,023 / 92% (2016–20) and +9,468 / 93% (2021–26); S20
+5,132 / 89% and +7,139 / 84%; S40 +4,935 / 84% and +5,523 / 81%. Skipping 16–40% of days saves fees but costs far more: within an
84-day account, trading days are the scarce resource — the quiet days' small P&L still moves accounts toward targets and the payout
clock. Trade every day, as the plan does.

## 371. D-series family 93 protocol: nearness to the 52-week high (S1)

**No trial spent; N 896. Written and committed BEFORE any statistic is computed.** Anchoring: traders treat the 52-week high as a
reference, under-reacting near it. Nearness on day D−1 = Yahoo settlement / max settlement of the previous 252 sessions (NQ=F,
GC=F). Signal: nearness in the top third of its trailing 250-session distribution → one side; bottom third → the other; middle not
traded; side fixed by discovery; the target (MNQ day; gold London on D, family-8 grids) judged DEMEANED. **2 tests**, descriptive
2010–17 column. Costs §180; recent-period design; carried at net > 0, t > 1.96; validation as §207, 3.

## 372. Family-93 discovery: nearness to the 52-week high — 0 of 2 carried (S1)

**No trial spent; N 896.** `reports/d93_discovery.json`: MNQ +1.2 bps (t +0.26), gold +1.1 (t +0.50), both reversed in 2012–17. Empty.

## 373. D-series family 94 protocol: the month-end London fix and equity-hedge rebalancing (S1)

**No trial spent; N 896. Written and committed BEFORE any statistic is computed.** Foreign holders of US equities re-hedge at the
month-end WM/R 16:00 London fix: after a month in which US equities rose, they sell dollars into it. Last London business day of
each month; signal = sign of the S&P's month (ES=F Yahoo settlements, last day of the prior month → the day before the fix).
Windows (HistData via family 41's `d41_fix.rows`, futures' direction): **pre** 15:30 → 16:00 and **post** 16:00 → 16:30, each traded
in the direction "dollar weaker when equities rose" or the reverse, fixed by discovery. Pairs pooled per window across 6E, 6B, 6J
(day-clustered). **2 tests**, descriptive 2010–17 column. Cost 0.5 bps; recent-period design; carried at net > 0, t > 1.96;
validation as §207, 3 (placebo: the same rule on the second-last business day).

## 374. Family-94 discovery: 1 of 2 carried — the dollar recovers after the month-end fix; D121 registered (S1)

**No trial spent yet; N 896.** `reports/d94_discovery.json` (module `reporting/d94_monthend.py`): **post** (16:00 → 16:30), dollar
stronger after a rising S&P month, **+2.20 bps**, t +1.98, n 60 months; 2010–17 +1.67 (t +1.57).
**pre** (into the fix) ~0 in 2018–22 — but in 2010–17 the documented run-up was strong (dollar weaker into the fix after equity gains,
+5.7 bps, t +4.5): the published effect has gone; only its unwind remains. Scale: ~2 bps on a currency future 12 times a year —
unusable whatever the trial says. Z and D market-test 133.

## 375. D121 validated (t00903): WATCHLIST — the unwind persists in sign but is not month-end specific (S1)

**N 897.** Sealed 2023-01 → 2026-08, 40 month-ends (power 29%): net **+1.53 bps** (t +1.40); placebo
(second-last business day) **48th** pct — the same move happens a day earlier, so it is not the month-end flow;
years 3 of 4. WATCHLIST by the mean; unusable at ~2 bps twelve times a year. Z and D market-test 133.

## 376. D-series family 95 protocol: the 10-year's move into MNQ, by stock–bond correlation regime (S1)

**No trial spent; N 897. Written and committed BEFORE any statistic is computed.** Family 10 found no all-days link from ZN to NQ, and
D68 uses only ZN's tails. The sign of the stock–bond correlation changes what a bond move means for equities (inflation scare vs
growth scare). Regime on day D−1: correlation of ES and ZN daily open→settlement returns (family-10 series) over the previous 60
sessions, positive or negative. Signal: sign of ZN's session on D−1 (every day, not only shocks). Target: MNQ's day session on D
(family-8 grid), with or against, fixed by discovery within each regime. **2 regimes = 2 tests**, descriptive 2010–17 column. Cost
MNQ 0.5 bps; recent-period design; carried at net > 0, t > 1.96; validation as §207, 3.

## 377. Family-95 discovery: ZN into MNQ by correlation regime — 0 of 2 carried (S1)

**No trial spent; N 897.** `reports/d95_discovery.json`: positive-correlation regime follow +5.4 bps (t +0.67; 2010–17 −6.4), negative
+0.2 (t +0.04). D68's link lives only in ZN's tails. Empty.

## 378. D-series family 96 protocol: D68's 10-year tail into the DAX and NKD accounts, pooled (S1)

**No trial spent; N 897. Written and committed BEFORE any pooled statistic is computed.** D68 (MNQ follows a ZN shock) is confirmed and
deployed; family 37 found the same sign for the DAX (+25.9 bps, t +1.87) and NKD (+15.5, t +1.61) windows on 2018–22. Rule as §354:
the same rule (follow a ZN shock, family 24's definition; A21 window paths; costs DAX 0.3, NKD 0.2) on 2010-01 → 2022-12 pooled;
**carried** if net > 0 in both 2010–17 and 2018–22 AND pooled t > 1.96. **2 tests.** Validation as §207, 3 on sealed 2023-01 → 2026-08
(placebo: after non-shock days).

## 379. Family-96: D68's 10-year tail does not carry to the DAX or NKD — 0 of 2 (S1)

**No trial spent; N 897.** `reports/d96_discovery.json`: DAX pooled +6.6 bps (t +0.74; 2010–17 −10.9); NKD pooled +18.4 (t +1.74;
both periods positive, +23.5 and +15.5, but below the bar). NKD's sign matches D68 throughout and is the nearest thing to a second
D68 — noted for the NKD account's demo review, not adopted. Empty.

## 380. D-series family 97 protocol: the Brazilian real into soybeans and corn (S1)

**No trial spent; N 897. Written and committed BEFORE any statistic is computed.** Brazil is the largest soy exporter; a sharply
weaker real raises farmers' local-currency price and their selling. Yahoo BRL=X daily, close → close (its opens are stale on a third
of days; CNY=X, stale on 71%, is not used), dated by its UTC day (closes 20:00 ET). Shock = |change| beyond 2 SD of the previous 60.
Targets: ZS and ZC sessions (family-10 open → settlement) dated the next weekday (grains reopen 20:00 ET), with the shock (USD/BRL up)
or against it, fixed by discovery. **2 tests**, descriptive 2010–17 column. Costs §177 (ZS 0.7, ZC 1.9); recent-period design;
carried at net > 0, t > 1.96; validation as §207, 3.

## 381. Family-97 discovery: 2 of 2 carried — grains fall after the real weakens; D122–D123 registered (S1)

**No trial spent yet; N 897.** `reports/d97_discovery.json` (module `reporting/d97_brl.py`):
- **D122** ZS short after the real weakens (long after it strengthens): +39.37 bps, t +2.92, n 64; 2010–17 +2.36 (t +0.19); market-test 134.
- **D123** ZC short after the real weakens (long after it strengthens): +40.10 bps, t +2.22, n 64; 2010–17 +3.78 (t +0.21); market-test 135.

The sign is the mechanism's (a weaker real → more Brazilian selling → lower US grain prices). Caution recorded before the trials: the
2010–17 column is flat (t ≈ 0.2), the pattern that has preceded every out-of-sample failure in this search (§349). ZS is the demo's
sixth account; a confirmed D122 would be a D68-like overlay for it.

## 382. D122 CONFIRMED (t00904): soybeans fall after the Brazilian real weakens; D123 (corn) WATCHLIST (t00905) (S1)

**N 899.** Sealed 2023-01 → 2026-08, injection recovered first (power 30% / 35%):
- **D122 ZS: CONFIRM** — 51 events, net **+32.86 bps** (t +1.88 > 1.645), placebo (non-shock days)
  **97th** pct, years 3 of 4 (2023 +39.9, 2024 −3.3, 2025 +53.2, 2026 +86.5). The first confirmation since D89, on a
  product the plan trades (the demo's soybean account), with the mechanism's sign (a weaker real → Brazilian farmer and exporter
  selling → lower US soybeans next session; a stronger real → the reverse).
- **D123 ZC: WATCHLIST** — 51 events, +15.81 bps (t +1.00), placebo 78th, years 3 of 4.

**Before any use — stress tests fixed now (no trial), as D68's §210:** (1) **independent data on both sides** — USD/BRL from FRED
DEXBZUS (the noon New York buying rate, close → close; a shock as before) and soybeans from the owned GLBX daily bars (roll-correct
settle → settle, the next session) *[amended before computing: the owned bar file has no ZS (0 dates), and Stooq answers with a
browser challenge, which is not circumvented; the independent soybean price is the SOYB ETF (NYSE Arca, holds soybean futures),
Yahoo daily open → close; combinations FRED-BRL × Yahoo-ZS, Yahoo-BRL × SOYB, FRED-BRL × SOYB]*; periods 2010–17, 2018–22, 2023–26; thresholds 1.5 / 2 / 2.5 σ. (2) **The ZS account overlay** —
A23 engine, 3 ZS, both histories, drift removed: the plan (always long) against the overlay (short the session after the real weakens
beyond 2σ; long otherwise), as D68's table. Read: adopt for the demo only if (1) keeps the sign in 2023–26 on independent data and (2)
does not lower the account's P(payout) in 2021–26.

## 383. D122 stress-tested: the sign survives on independent data, weakly; the overlay meets the pre-set reading but lowers mean net (S8)

**No trial; N 899.** `reports/a31_d122.json`, module `reporting/a31_d122.py`.

**(1) Independent data, 2σ, 2023–26** (short soybeans the session after the real weakens): Yahoo BRL × Yahoo ZS (the trial's own data)
+32.9 (t +1.88); **FRED BRL × Yahoo ZS +7.4 (t +0.48); Yahoo BRL × SOYB +6.6 (t +0.57); FRED BRL × SOYB +11.5 (t +1.12)**. 2018–22
+11 to +39 throughout; 2010–17 ≈ 0 (−10.9 to +4.9). The sign holds out of sample on every independent combination at 2σ, at a
fraction of the trial's size — partly the FRED rate's noon timing (half a day earlier than the close the rule uses). At 2.5σ the
2023–26 events are 13–15 and the FRED × Yahoo cell turns negative (−34, n 13). A real but modest effect, as D68 was.

**(2) The ZS account (3 ZS, 50K Daily, drift removed, 84 days; short days 3.3% of sessions):**

| | 2010–20 | 2021–26 |
|---|---|---|
| plan, always long | P(payout) 70%, +$3,061, P(net > 0) 59% | 86%, +$3,310, 81% |
| overlay, D122 short days | 75%, +$2,990, 62% | 87%, +$2,792, 85% |

The pre-set reading (§382) is met — the sign holds on independent data in 2023–26, and P(payout) in 2021–26 does not fall (86 → 87%)
— but the mean net is LOWER in both histories (−$71, −$518): with brackets, a handful of flipped days moves outcomes more by
path than by the edge. **Status: a demo candidate for the soybean account, NOT deployed** — changes to the droplet need the user's
confirmation (and the soybean ticket is itself still being evaluated by the demo). Recorded for the 2026-10-25 review.

## 384. D-series family 98 protocol: producer currencies into their commodities (S1)

**No trial spent; N 899. Written and committed BEFORE any statistic is computed.** D122's mechanism generalised: when an exporter's
currency weakens, its producers' local-currency price rises and they sell more. Pairs (Yahoo daily, close → close, UTC day, shock
beyond 2 SD of the previous 60, as family 97): **CLP → HG** (Chile, copper), **ZAR → GC** (South Africa, gold), **RUB → ZW** (Russia,
wheat), **CAD → CL** (Canada, crude), **AUD → GC** (Australia, gold; AUDUSD inverted so "up" = the local currency weaker). Target the
commodity's next-weekday session (family-10), with or against the local-currency weakening, fixed by discovery. A currency whose
closes are unchanged on more than 30% of days in discovery is reported but not carried (stale quotes). **5 tests**, descriptive
2010–17 column. Costs §177; recent-period design; carried at net > 0, t > 1.96; validation as §207, 3.

## 385. Family-98 discovery: 1 of 5 carried — copper falls after the peso weakens; D124 registered (S1)

**No trial spent yet; N 899.** `reports/d98_discovery.json` (module `reporting/d98_producer.py`): **D124** HG against a CLP weakening,
**+34.81 bps**, t +2.16, n 75; 2010–17 +13.32 (t +1.23) — the same sign. All five pairs chose
"against local weakness" (the mechanism's sign): ZAR → GC +24.9 (t +1.49), CAD → CL +49.9 (t +0.72), AUD → GC +6.1, RUB → ZW +1.1.
D122's mechanism looks general in direction, strong only where the producer dominates (Brazil soy, Chile copper). HG is not a
plan product (MHG was listed as a candidate market, §140s). Z and D market-test 136.

## 386. D124 validated (t00906): WATCHLIST — copper after the peso keeps its sign, not its strength (S1)

**N 900.** Sealed 2023-01 → 2026-08, 52 events (power 20%): net **+14.62 bps** (t +0.73); placebo
77th; years 2 of 4 (2023 +19.5, 2024 −8.6, 2025 +47.1, 2026 −21.9). Positive across all three periods (2010–17
+13.3, 2018–22 +34.8, 2023–26 +14.6), never significant out of sample. WATCHLIST; HG is not a plan product. Z and D market-test 136.

## 387. D-series family 99 protocol: the real into Brazil's other CME exports (S1)

**No trial spent; N 900. Written and committed BEFORE any statistic is computed.** D122's mechanism for the other CME products Brazil
exports in volume: **ZM** (soybean meal), **ZL** (soybean oil), **LE** (live cattle — Brazil is the largest beef exporter). Family 97's
USD/BRL shock (2σ, close → close, UTC day) → the next-weekday session (Yahoo open → settlement, family-10 cleaning), with or against,
fixed by discovery. **3 tests**, descriptive 2010–17 column. Costs: 1.5 bps each (between §177's ZS 0.7 and ZC 1.9; these are thinner);
recent-period design; carried at net > 0, t > 1.96; validation as §207, 3.

## 388. Family-99 discovery and a D122 mechanism check: the real moves commodities, not equities (S1, S8)

**No trial spent; N 900.** `reports/d99_discovery.json`: ZM +29.7 bps (t +1.83), ZL +15.5 (t +1.00), LE +18.7 (t +1.00) — none carried,
all with the mechanism's sign (short after the real weakens). **Descriptive check of what a real shock moves next session** (short after
weakening, gross, 2018–22 | 2023–26): ZS +40.1 (t +2.97) | **+33.6 (t +1.92)**; ZC +42.0 | +17.7; ZW +33.3 | +15.4; CL +135.8 | +29.6;
HG +25.6 | −12.3; GC −0.1 | +4.8; ES −3.5 | −10.2; NQ −34.4 | −13.5. Equities do not fall after a real shock and gold is flat: D122 is a
commodity-exporter effect, strongest and most persistent in soybeans — not a general emerging-market risk-off signal. It supports
reading D122 as the producer-selling mechanism it was registered under.

## 389. D-series family 100 protocol: oil exporters' currencies into crude (S1)

**No trial spent; N 900. Written and committed BEFORE any statistic is computed.** Family 98's design (§384) for crude: **NOK, MXN,
RUB, COP** (Yahoo, close → close, UTC day; up = the producer's currency weaker; 2σ) → CL's next-weekday session (family 10), with or
against, fixed by discovery; currencies stale (> 30% unchanged closes) reported, not carried. **4 tests**, descriptive 2010–17 column.
Cost CL 0.7 bps (§177; the MCL account would pay 5.4, noted at validation); recent-period design; carried at net > 0, t > 1.96;
validation as §207, 3.

## 390. Family-100 discovery: 1 of 4 carried — crude falls after the Colombian peso weakens; D125 registered (S1)

**No trial spent yet; N 900.** `reports/d100_discovery.json`: **D125** COP → CL against, **+88.32 bps**, t +2.05, n 73;
2010–17 +13.62 (t +0.73). MXN +80.8 (t +1.37; 2010–17 +50.9, t +1.89), RUB +44.6, NOK +28.2 — all four with the
mechanism's sign, as every pair in families 97–99. Crude's 2020 swings inflate 2018–22 sizes. Z and D market-test 137.

## 391. D125 validated (t00907): REJECT — crude after the peso was 2020 (S1)

**N 901.** Sealed 2023-01 → 2026-08, 50 events (power 44%): **-21.93 bps** (t -0.73); placebo
21th; years 1 of 4. The 2018–22 size came from crude's 2020 swings. The producer-currency mechanism holds out of sample
only for soybeans (D122) so far; copper (D124) kept its sign weakly, crude did not. Z and D market-test 137.

## 392. D-series family 101 protocol: does D122 last beyond the next session? (S1)

**No trial spent; N 901. Written and committed BEFORE any statistic is computed.** D122 trades only the session after a real shock.
Lags: the **2nd** and **3rd** ZS sessions after the shock day (Yahoo, family 10), short after the real weakens / long after it
strengthens (D122's direction, not re-chosen). **2 tests**, descriptive 2010–17 column. Cost ZS 0.7; recent-period design; carried at
net > 0, t > 1.96; validation as §207, 3. A carried lag would extend D122's overlay; none changes D122 itself.

## 393. Family-101 discovery: D122 is a one-session effect — 0 of 2 carried (S1)

**No trial spent; N 901.** `reports/d101_discovery.json`: lag 2 +19.4 bps (t +1.32; 2010–17 −19.0), lag 3 −13.8 (t −1.14). The
response is the next session only; D122's overlay stays one day. Empty.

## 394. D-series family 102 protocol: importers' currencies into what they import (S1)

**No trial spent; N 901. Written and committed BEFORE any statistic is computed.** The mirror of D122: when a large importer's currency
weakens, its local price rises and demand falls. **INR → GC** (India, gold), **INR → CL** (India, crude), **KRW → CL** (Korea, crude).
Yahoo close → close, UTC day, 2σ, up = the importer's currency weaker; target the next-weekday session (family 10), with or against,
fixed by discovery; stale (> 30% unchanged) reported, not carried. **3 tests**, descriptive 2010–17 column. Costs §177; recent-period
design; carried at net > 0, t > 1.96; validation as §207, 3.

## 395. Family-102 discovery: importers' currencies — 0 of 3 carried; the sign is universal (S1)

**No trial spent; N 901.** `reports/d102_discovery.json`: INR → GC +18.2 (t +1.37), INR → CL +70.3 (t +1.22), KRW → CL +97.6 (t +1.57) —
all "against local weakness", as every one of the 12 pairs in families 97–102, producer and importer alike. So the broad pattern is
"an emerging currency's sharp fall precedes weaker commodities next session" (a dollar-funding / risk channel), of which the soybean
case (D122) is the strongest and the only one confirmed out of sample. Empty.

## 396. D-series family 103 protocol: an emerging-currency stress composite into the plan's commodities (S1)

**No trial spent; N 901. Written and committed BEFORE any composite statistic is computed.** Families 97–102 found one sign in all
12 currency → commodity pairs. Composite on day D (UTC): the mean of z = change / SD(previous 60 changes) over **BRL, MXN, ZAR, CLP, COP,
INR, KRW** (Yahoo close → close; RUB excluded — its 2022 sanctions break), each oriented so + = that currency weaker; requires ≥ 5 of 7.
Shock: |composite| > 2 SD of its own previous 60. Targets the next-weekday session (family 10): **ZS, CL, GC** — the plan's commodity
products — with or against, fixed by discovery. **3 tests**, descriptive 2010–17 column. Honest caveat: the composite is motivated
by results already seen in 2018–22 and 2010–17; the sealed 2023–26 window is untouched by it and is the test. Costs §177; carried at
net > 0, t > 1.96; validation as §207, 3.

## 397. Family-103 discovery: 1 of 3 carried — crude falls after emerging-currency stress; D126 registered (S1)

**No trial spent yet; N 901.** `reports/d103_discovery.json` (module `reporting/d103_emfx.py`): **D126** CL against the composite,
**+120.22 bps**, t +2.08, n 67; **2010–17 +37.13 (t +1.89)** — the same sign and nearly
significant in the untouched earlier period. ZS +31.6 (t +1.82; 2010–17 +14.3), GC +30.4 (t +1.84; 2010–17 +1.4): same sign, below the
bar. MCL's 5.4 bps of cost is small against this size. Z and D market-test 138.

## 398. D126 validated (t00908): REJECT — the composite did not carry crude out of sample (S1)

**N 902.** Sealed 2023-01 → 2026-08, 50 events (power 51%): **-3.28 bps** (t -0.09); placebo
28th; years 2 of 4. Even a rule positive in both 2010–17 and 2018–22 fell to zero after 2022 — crude's response to
emerging-currency stress was a pre-2023 regime. D122 (soybeans × the real) remains the one currency → commodity rule that held.
Z and D market-test 138.

## 399. D-series family 104 protocol: dominant-producer currencies in oilseeds and wheat (S1)

**No trial spent; N 902. Written and committed BEFORE any statistic is computed.** D122 held where one producer dominates. Pairs:
**MYR → ZL** and **IDR → ZL** (Malaysia/Indonesia, palm oil — soybean oil's substitute), **ARS → ZM** (Argentina, the largest meal
exporter; its crawling peg makes shocks devaluation days), **AUD → ZW**, **CAD → ZW** (wheat exporters). Family 98's construction
(Yahoo close → close, UTC day, 2σ, up = local currency weaker); targets next-weekday sessions (ZL, ZM: Yahoo open → settlement as
family 99; ZW: family 10), with or against, fixed by discovery. **5 tests**, descriptive 2010–17 column. Costs ZL/ZM 1.5, ZW 1.4;
recent-period design; carried at net > 0, t > 1.96; validation as §207, 3.

## 400. Family-104 discovery: dominant-producer currencies in oilseeds and wheat — 0 of 5 carried (S1)

**No trial spent; N 902.** `reports/d104_discovery.json`: IDR → ZL against +38.9 (t +1.92), AUD → ZW against +41.9 (t +1.79); MYR → ZL
and ARS → ZM chose "with" (+6.2, +10.6; 2010–17 the mechanism's way, −28.2 t −2.40 and −21.5) — the first pairs off the universal
sign, both weak. Empty.

## 401. D-series family 105 protocol: gold's and crude's own implied-volatility shocks (S1)

**No trial spent; N 902. Written and committed BEFORE any statistic is computed.** CBOE's GVZ (gold) and OVX (crude) implied-volatility
indices (Yahoo daily closes), new to the programme. Daily log change; shock beyond 2 SD of the previous 60 on day D. Targets the
next-weekday: **GVZ → gold's London window** (family-8 grid), **OVX → CL's session** (family 10), with the volatility move or against
it, fixed by discovery. **2 tests**, descriptive 2010–17 column. Costs §177/§180; recent-period design; carried at net > 0, t > 1.96;
validation as §207, 3.

## 402. Family-105 discovery: gold's and crude's implied-volatility shocks — 0 of 2 carried (S1)

**No trial spent; N 902.** `reports/d105_discovery.json`: GVZ → gold +10.2 bps (t +1.14), OVX → crude +41.4 (t +0.96). Empty.

## 403. D-series family 106 protocol: grain traders' stocks into grains (S1)

**No trial spent; N 902. Written and committed BEFORE any statistic is computed.** ADM and Bunge (BG) crush and ship most of the US
soybean flow; their share prices react first to margin and demand news. Yahoo daily open → close (16:00 ET), shock beyond 2 SD of the
previous 60 on day D → the next-weekday ZS and ZC sessions (family 10; grains reopen 20:00 ET), with or against, fixed by discovery.
**2 × 2 = 4 tests**, descriptive 2010–17 column. Costs §177; recent-period design; carried at net > 0, t > 1.96; validation as §207, 3.

## 404. Family-106 discovery: grain traders' stocks — 0 of 4 carried (S1)

**No trial spent; N 902.** `reports/d106_discovery.json`: grains fade an ADM/BG shock +17 to +26 bps (t +1.08 to +1.81), mixed in
2010–17. Empty.

## 405. D-series family 107 protocol: energy stocks into crude (S1)

**No trial spent; N 902. Written and committed BEFORE any statistic is computed.** Family 106's design for crude: **XLE** (integrated
energy) and **XOP** (exploration and production) shocks (Yahoo open → close, 2σ) → CL's next-weekday session (family 10), with or
against, fixed by discovery. **2 tests**, descriptive 2010–17 column. Cost CL 0.7 (MCL 5.4 noted); recent-period design; carried at
net > 0, t > 1.96; validation as §207, 3.

## 406. Family-107 discovery: energy stocks into crude — 0 of 2 carried (S1)

**No trial spent; N 902.** `reports/d107_discovery.json`: XLE +10.1 (t +0.26), XOP +47.5 (t +1.20). Empty.

## 407. D-series family 108 protocol: 2-year Treasury shocks into currencies (S1)

**No trial spent; N 902. Written and committed BEFORE any statistic is computed.** The 2-year yield carries Fed expectations, the core of
rate differentials; families 24/29 used only ZN for currencies. ZT=F shocks (family 39's series, 2σ) on the previous weekday → the
next sessions of **6E, 6J** (family 10) and **6B, 6A** (family 83's series), with or against, fixed by discovery. **4 tests**,
descriptive 2010–17 column. Costs: 6E 0.3, 6J 0.5, 6B/6A 0.5; recent-period design; carried at net > 0, t > 1.96; validation as
§207, 3.

## 408. Family-108 discovery: 2 of 4 carried, both negative in 2010–17; D127–D128 registered (S1)

**No trial spent yet; N 902.** `reports/d108_discovery.json` (module `reporting/d108_zt.py`):
- **D127** 6E follows a ZT shock: +12.38 bps, t +2.33, n 90; 2010–17 -3.45; market-test 139.
- **D128** 6A follows a ZT shock: +15.23 bps, t +2.12, n 90; 2010–17 -5.04; market-test 140.

The 2022 dollar-regime signature again (family 83, §348–349): expected to fail; validated once each per protocol.

## 409. D127–D128 validated (t00909–t00910): none confirm, as expected (S1)

**N 904.** D127 6E: WATCHLIST, +7.05 bps (t +0.83), placebo 94th; D128 6A: REJECT, -6.83 (t -0.52).
Negative 2010–17 columns again preceded failure. Z and D market-tests reach 140.

## 410. D-series family 109 protocol: D68 when equities have not yet moved (S1)

**No trial spent; N 904. Written and committed BEFORE any statistic is computed.** If D68 is slow diffusion from bonds to equities, the
next-day catch-up should be largest when the S&P barely moved on the ZN-shock day. D68's events (ZN beyond 2σ, family 24), split by the
same day's ES session (family 10): **quiet** — |ES| below its own 60-session median absolute move — vs the rest. Target MNQ's next day
session (family-8 grid), following the ZN shock (D68's direction, not re-chosen). **1 test (quiet)**; the other half reported beside.
Descriptive 2010–17 column. Cost MNQ 0.5; recent-period design; carried at net > 0, t > 1.96; validation as §207, 3. A carried test
would sharpen D68's overlay, not replace it.

## 411. Family-109 discovery: D68 is not sharper when equities were quiet — 0 of 1 carried (S1)

**No trial spent; N 904.** `reports/d109_discovery.json`: quiet-equity ZN shocks +15.8 bps (t +0.60, n 23) vs the rest +21.5 (t +1.02,
n 56). No support for a slow-diffusion refinement; D68 stays as deployed. Empty.

## 412. D-series family 110 protocol: dominant-producer currencies in copper and silver (S1)

**No trial spent; N 904. Written and committed BEFORE any statistic is computed.** Family 98's construction for metals where one or two
countries dominate supply: **PEN → HG** (Peru, copper), **MXN → SI** (Mexico, the largest silver producer), **PEN → SI**. Yahoo close →
close, UTC day, 2σ, up = local currency weaker; targets next-weekday sessions (family 10), with or against, fixed by discovery; stale
(> 30% unchanged) reported, not carried. **3 tests**, descriptive 2010–17 column. Costs §177 (HG 2.0, SI 0.5); recent-period design;
carried at net > 0, t > 1.96; validation as §207, 3.

## 413. Family-110 discovery: copper and silver producer currencies — 0 of 3 carried (S1)

**No trial spent; N 904.** `reports/d110_discovery.json`: PEN → HG +6.9 (t +0.67, "with"); MXN → SI +19.8 (t +0.69), PEN → SI +15.8 (t +1.04),
both "against" and the same in 2010–17 (+17.1, +18.7), all weak. Empty.

## 414. A timing caveat found, and D-series family 111 protocol: a two-period screen of the whole shock class (S1)

**Caveat (recorded, no result changes).** Yahoo's currency bars are dated by UTC day and close at 19:00 (winter) / 20:00 (summer) New
York time — after crude's Globex session opens (18:00 ET). Currency → CL tests (families 98's CAD → CL, 100, 102's INR/KRW → CL, 103's
D126) could therefore see up to two hours of the target session. All were null or rejected, so no conclusion changes; D125 and D126's
REJECTs stand (a look-ahead could only have helped them). Soybeans reopen at 20:00 ET, at or after the currency close, so **D122 is not
affected**; nor are targets opening later (MGC 03:00, DAX 03:00, MNQ 09:30 ET).

**Family 111 protocol (no trial spent; N 904; written and committed BEFORE any statistic is computed).** Predictors: every daily series
fetched so far — futures and ETFs open → close; VIX-type indices, PL=F and currencies close → close (log); FRED DFII10/T10YIE changes;
stale CNY/CNH excluded. Shock 2σ on the previous weekday (family 24). Targets: **MNQ day, MGC London** (family-8 grids), **NKD, DAX**
(A21 paths), **CL, ZS** (family 10). Excluded before computing: a predictor on its own market; currency/BTC-USD predictors for CL and NKD
(their sessions open before the currency close); pairs already validated (D68, D102, D103, D105, D106, D119, D120, D122, D123); and
family-29 pairs (14-universe → CL/ZS). Follow or fade fixed by 2018–22. **Carried only if** 2018–22 net > 0 with t > 1.96 AND the same
rule in 2010–17 net > 0 with t > 1.0 (≈ 0.4% of null tests pass both; the count is reported against it). Costs §177/§180; validation
as §207, 3.

## 415. Family-111 screen: 4 of 359 carried (≈ 1.4 by chance); D129–D132 registered (S1)

**No trial spent yet; N 904.** `reports/d111_discovery.json` (module `reporting/d111_screen.py`); 12 pass 2018–22 alone (≈ 9 by chance).
- **D129** NKD follows a ^VIX3M shock: +29.25 bps, t +2.49, n 73; 2010–17 +33.64 (t +1.48); market-test 141.
- **D130** MGC fades a CLP=X shock: +19.25 bps, t +2.25, n 70; 2010–17 +14.26 (t +2.09); market-test 142.
- **D131** MGC follows a 6S=F shock: +19.87 bps, t +2.22, n 71; 2010–17 +11.67 (t +1.39); market-test 143.
- **D132** NKD follows a LQD shock: +35.58 bps, t +2.08, n 72; 2010–17 +27.73 (t +1.25); market-test 144.

A modest excess over chance. NKD after an LQD shock follows bonds the way D68 does; NKD after a VIX3M shock follows a fear spike
(a crisis-rebound reading, §336, is likely); gold fading a CLP shock carries the emerging-currency sign (§395).

## 416. D129–D132 validated (t00911–t00914): none confirm — the screen's excess was chance (S1)

**N 908.**
- **D129** NKD follows the previous session's ^VIX3M shock: **REJECT** — 57 events, -10.91 bps (t -0.51), placebo 9th.
- **D130** MGC fades the previous session's CLP=X shock: **WATCHLIST** — 43 events, +8.10 bps (t +0.74), placebo 80th.
- **D131** MGC follows the previous session's 6S=F shock: **WATCHLIST** — 47 events, +6.66 bps (t +0.35), placebo 82th.
- **D132** NKD follows the previous session's LQD shock: **REJECT** — 51 events, -1.98 bps (t -0.19), placebo 43th.

The two-period filter (2010–17 t > 1.0) did not rescue any of them. With families 24, 29, 37, 39, 57, 76–77, 83, 108 and this screen,
the next-session shock class has now been searched across ~45 predictors and every plan product; its survivors out of sample are D68
(ZN → MNQ), D84, D89, and D122 (BRL → ZS). The shock class is exhausted on the data in hand.

## 417. D122's implementation caveat: the bot cannot see the close the rule was confirmed on (S8)

**No trial; N 908.** The bot issues every ticket at its 17:30 ET alert; the ZS ticket enters 20:00 ET (19:00 CT). D122 was confirmed on
Yahoo's USD/BRL bar dated by UTC day, which closes at 19:00 (winter) / 20:00 (summer) ET — after the alert. A live rule would read the
real at ~17:30 ET (Brazil's onshore market has closed at ~16:00 ET; offshore trading is thin). The only other timing tested, FRED's
noon rate, gave a far weaker 2023–26 result (+7.4 bps, t +0.48, vs +32.9 at the UTC close, §383): the effect is sensitive to when the
real's move is measured, and the implementable reading lies between the two. No intraday USD/BRL source is in hand to test 17:30
directly. **For the user's decision:** D122 as confirmed is not exactly implementable by the current bot; a live version would either
move the ZS ticket's direction decision to just before 20:00 ET (a second, later bot step) or accept an untested 17:30 reading.

## 418. D122 on an implementable reading: CME's real future (6L) — positive in every period (S8)

**No trial; N 908. Descriptive (the rule is unchanged; this is its implementable form).** CME's Brazilian real future (Yahoo 6L=F)
settles before the bot's 17:30 ET alert. Shock = the 6L session beyond 2σ (oriented so + = real weaker), short ZS's next session:

| 6L measure | 2010–17 | 2018–22 | 2023–26 |
|---|---|---|---|
| open → settle | +11.9 (t +1.19, n 128) | +7.6 (t +0.59, n 70) | +11.7 (t +0.75, n 44) |
| **settle → settle** | **+10.3 (t +0.86, n 111)** | **+13.7 (t +1.18, n 75)** | **+22.4 (t +1.55, n 45)** |

Weaker than the confirmed Yahoo-close version (+32.9 in 2023–26) but the same sign in all three periods — including 2010–17, where
the confirmed version was flat — and computable at the alert. **If the user adopts D122 for the demo, this is the version the bot can
run** (yesterday's 6L settle → settle move, 60-session SD, 2σ; ZS ticket short after a real weakening).

## 419. D122's implementable overlay does not help the soybean account — recommendation: do not adopt (S8)

**No trial; N 908.** `reports/a31_d122_6l_overlay.json` — the 6L (settle → settle) version as the ZS account's overlay (short days
2.8–3.5%): 2010–20 P(payout) 70 → 69%, mean net +$3,061 → +$2,796, P(net > 0) 59 → 61%; 2021–26 86 → 87%, +$3,310 → +$2,815,
81 → 82%. Mean net falls in both histories, as with the Yahoo-close version (§383). With brackets, a few flipped days per year change
paths more than the rule's ~10–20 bps edge adds. **D122 stays CONFIRMED as a finding, but is not recommended for the bot** — unlike D68,
whose overlay added ~$455 per four months in 2021–26 (§210). Recorded for the user and the 2026-10-25 review.

## 420. D-series family 112 protocol: the opening half-hour's volatility sets the rest of the session (S1)

**No trial spent; N 908. Written and committed BEFORE any statistic is computed.** The leverage effect intraday: a turbulent open
signals selling pressure. Ratio = realized volatility of 1-minute returns in the window's first 30 minutes (MNQ 09:30–10:00; gold
03:00–03:30) over its mean in the previous 20 sessions. Top third of its trailing-250 distribution → one side, bottom third → the other,
middle not traded; target the rest of the window (10:00 → 16:00; 03:30 → 11:30), JUDGED DEMEANED; side fixed by discovery. **2 tests**,
descriptive 2010–17 column. Costs §180; recent-period design; carried at net > 0, t > 1.96; validation as §207, 3.

## 421. Family-112 discovery: the opening half-hour's volatility — 0 of 2 carried (S1)

**No trial spent; N 908.** `reports/d112_discovery.json`: MNQ +0.7 bps (t +0.17), gold −0.4 (t −0.16). Empty.

## 422. A32 design: D68 as a flip (deployed) or as a skip (S8)

**A COMPUTATION; no trial; N 908. Variants fixed BEFORE any result.** The overlay replays (§383, §419) suggest flipped days can cost
more in bracket paths than their edge adds. MNQ account (4 MNQ, 50K Daily, drift removed, A23 engine, both histories, 84 days):
**plan** (always long); **flip** (deployed: the ZN shock's direction on shock days); **skip** (sit out the day after a ZN sell-off,
long otherwise); **flip-short-only** is identical to flip (a bond rally already means long). Read: if skip beats flip on mean net in
both histories without lowering P(payout), propose it to the user as a change to the bot (not made without confirmation).

## 423. A32 result: D68's flip beats a skip — the deployed form stays (S8)

**No trial; N 908.** `reports/a32_d68_skip.json` (sell-off days 2.4% / 3.3% of sessions): 2015–20 plan +$1,960 (76%, 61%), flip +$1,971
(72%, 55%), skip +$1,767 (72%, 63%); 2021–26 plan +$1,265 (80%, 59%), **flip +$1,720 (77%, 64%)**, skip +$1,337 (79%, 63%). The flip
reproduces §210 exactly and earns more than skipping in both histories; the bot's D68 is unchanged.

## 424. D-series family 113 protocol: the DAX's reaction to US 08:30 data (S1)

**No trial spent; N 908. Written and committed BEFORE any statistic is computed.** US releases at 08:30 ET land at 14:30 Frankfurt, inside
the DAX window. HistData grxeur at New York times: the move 08:29 → 08:44 ET predicts 08:44 → 11:30 ET (17:30 Frankfurt, the window's
close; the weeks when the clocks differ shift the close by an hour — kept, a dilution), follow or fade fixed by discovery; forms **all**
and **strong** (|first 15 min| above its discovery median — mostly release days). **2 tests**, descriptive 2010–17 column. Cost DAX 0.3;
recent-period design; carried at net > 0, t > 1.96; validation as §207, 3.

## 425. Family-113 discovery: the DAX after US 08:30 data — 0 of 2 carried (S1)

**No trial spent; N 908.** `reports/d113_discovery.json`: fade +0.3 / +3.0 bps (t +0.16 / +1.03). Empty.

## 426. The user's decisions (2026-10-14): D122 not adopted; a new search design — the current regime (S1, S8)

**D122:** the user agrees with §419 — not adopted, not deployed; it stays a CONFIRMED finding on record.

**New design, from family 114 on (user-approved), replacing §180's for new families:** discovery **2021-01-01 → 2024-12-31**; sealed
validation **2025-01-01 → 2026-08-31** (20 months). Why: §349, §356 and §416 showed that rules found in 2018–22 rarely survived
2023–26 — the market after 2022 behaves differently, and the plan trades now. Rules, fixed now:
1. Discovery as before: carried at net > 0 with t > 1.96 (no multiple-testing cut, §133); the 2010–20 column is printed for context
   only and does not gate carrying.
2. Validation, once per carried test, on 2025-01 → 2026-08: CONFIRM if (a) net > 0 with t > 1.645, (b) ≥ 95th pct of the family's
   placebo, (c) positive in BOTH 2025 and 2026 (Jan–Aug) — two periods replace §207's "3 of 4 years"; WATCHLIST if net > 0; REJECT.
3. Not re-tested: any rule already validated (D01–D132). Rules scanned under older designs but never validated may be re-scanned.
4. Honest caveats: 2023–24 sits inside the new discovery window and was the older design's validation data, so what failed or worked
   there is known in general terms; 2025–26 has been read only through earlier trials' validations, never to choose a rule. Power is
   low (20 months), so true effects will often land on WATCHLIST.
5. A CONFIRM is stress-tested (independent data, account replay) before any proposal, and nothing reaches the bot without the user.

## 427. D-series family 114 protocol: the shock screen on the current regime (S1)

**No trial spent; N 908. Written and committed BEFORE any statistic is computed.** Family 111's screen (§414: ~45 predictors' 2σ shocks
on the previous weekday → MNQ day, MGC London, NKD, DAX, CL, ZS; the same exclusions, including currency predictors for CL and NKD and
pairs already validated) under §426's design: discovery 2021-01 → 2024-12, carried at net > 0 with t > 1.96 (~2.5% of nulls pass;
the count is reported against it); 2010–20 printed for context only. Validation on 2025-01 → 2026-08 per §426, 2 (placebo: after
non-shock days). Module `reporting/d114_screen.py` (family 111's functions with the new windows).

## 428. Family-114 screen: 19 of 359 carried (≈ 9 by chance); D133–D151 registered (S1)

**No trial spent yet; N 908.** `reports/d114_discovery.json` (2021–24 discovery, §426):
- **D133** NKD follows a ^GDAXI shock: +41.32 bps, t +4.58, n 60; market-test 145.
- **D134** ZS follows a 6A=F shock: +50.67 bps, t +2.92, n 54; market-test 146.
- **D135** NKD follows a XLF shock: +30.52 bps, t +2.71, n 54; market-test 147.
- **D136** CL follows a 6A=F shock: +75.98 bps, t +2.38, n 54; market-test 148.
- **D137** DAX follows a PL=F shock: +33.92 bps, t +2.30, n 41; market-test 149.
- **D138** ZS fades a KRW=X shock: +49.85 bps, t +2.21, n 50; market-test 150.
- **D139** NKD fades a BTC=F shock: +22.23 bps, t +2.18, n 59; market-test 151.
- **D140** DAX follows a GC=F shock: +35.78 bps, t +2.15, n 44; market-test 152.
- **D141** ZS fades a COP=X shock: +30.94 bps, t +2.13, n 59; market-test 153.
- **D142** ZS follows a AUDUSD=X shock: +32.17 bps, t +2.13, n 54; market-test 154.
- **D143** MNQ fades a HG=F shock: +34.73 bps, t +2.09, n 63; market-test 155.
- **D144** ZS fades a CLP=X shock: +40.34 bps, t +2.08, n 54; market-test 156.
- **D145** ZS follows a FXI shock: +38.34 bps, t +2.07, n 49; market-test 157.
- **D146** DAX follows a ZN=F shock: +32.26 bps, t +2.03, n 49; market-test 158.
- **D147** DAX fades a 6B=F shock: +27.03 bps, t +2.02, n 52; market-test 159.
- **D148** DAX follows a 6C=F shock: +27.72 bps, t +2.01, n 48; market-test 160.
- **D149** NKD fades a ZS=F shock: +25.95 bps, t +2.01, n 52; market-test 161.
- **D150** DAX follows a RUB=X shock: +30.89 bps, t +2.01, n 54; market-test 162.
- **D151** ZS fades a ZM=F shock: +38.47 bps, t +1.96, n 56; market-test 163.

About twice the chance count: some of these should be real, most are not; the sealed 2025–26 window decides. The strongest by far is
NKD following a DAX shock (t +4.58, n 60).

## 429. D133–D151 validated (t00915–t00933): two CONFIRM — soybeans fade a meal shock (D151), NKD fades a bitcoin-futures shock (D139) (S1)

**N 927.** Sealed 2025-01 → 2026-08 under §426, 2:
- **D133** NKD follows the previous session's ^GDAXI shock: **REJECT** — n 28, -13.7 bps (t -0.74), placebo 31th, 2025 -26.7, 2026 +6.3
- **D134** ZS follows the previous session's 6A=F shock: **REJECT** — n 21, -2.2 bps (t -0.08), placebo 44th, 2025 -25.1, 2026 +18.7
- **D135** NKD follows the previous session's XLF shock: **WATCHLIST** — n 27, +4.6 bps (t +0.24), placebo 79th, 2025 +14.8, 2026 -12.7
- **D136** CL follows the previous session's 6A=F shock: **REJECT** — n 21, -15.4 bps (t -0.17), placebo 31th, 2025 -62.2, 2026 +27.2
- **D137** DAX follows the previous session's PL=F shock: **REJECT** — n 30, -19.3 bps (t -0.84), placebo 10th, 2025 -6.8, 2026 -81.8
- **D138** ZS fades the previous session's KRW=X shock: **WATCHLIST** — n 19, +9.7 bps (t +0.47), placebo 58th, 2025 +18.7, 2026 -2.6
- **D139** NKD fades the previous session's BTC=F shock: **CONFIRM** — n 20, +53.9 bps (t +2.80), placebo 100th, 2025 +1.7, 2026 +96.7
- **D140** DAX follows the previous session's GC=F shock: **REJECT** — n 32, -31.1 bps (t -1.16), placebo 2th, 2025 -39.8, 2026 -18.2
- **D141** ZS fades the previous session's COP=X shock: **WATCHLIST** — n 19, +18.2 bps (t +0.79), placebo 74th, 2025 +21.2, 2026 +13.0
- **D142** ZS follows the previous session's AUDUSD=X shock: **WATCHLIST** — n 15, +16.5 bps (t +0.63), placebo 75th, 2025 -12.8, 2026 +36.0
- **D143** MNQ fades the previous session's HG=F shock: **REJECT** — n 29, -5.7 bps (t -0.21), placebo 19th, 2025 -5.4, 2026 -6.3
- **D144** ZS fades the previous session's CLP=X shock: **WATCHLIST** — n 19, +15.4 bps (t +0.43), placebo 68th, 2025 -3.3, 2026 +47.6
- **D145** ZS follows the previous session's FXI shock: **REJECT** — n 24, -7.8 bps (t -0.31), placebo 42th, 2025 +6.6, 2026 -51.0
- **D146** DAX follows the previous session's ZN=F shock: **WATCHLIST** — n 24, +28.4 bps (t +1.30), placebo 99th, 2025 +28.9, 2026 +28.0
- **D147** DAX fades the previous session's 6B=F shock: **WATCHLIST** — n 30, +20.0 bps (t +1.02), placebo 83th, 2025 +8.7, 2026 +36.9
- **D148** DAX follows the previous session's 6C=F shock: **REJECT** — n 24, -9.2 bps (t -0.38), placebo 28th, 2025 -30.8, 2026 +12.5
- **D149** NKD fades the previous session's ZS=F shock: **WATCHLIST** — n 26, +18.7 bps (t +0.76), placebo 88th, 2025 +41.1, 2026 -23.7
- **D150** DAX follows the previous session's RUB=X shock: **WATCHLIST** — n 20, +36.1 bps (t +1.47), placebo 94th, 2025 +20.8, 2026 +54.8
- **D151** ZS fades the previous session's ZM=F shock: **CONFIRM** — n 27, +30.3 bps (t +2.32), placebo 99th, 2025 +40.4, 2026 +10.1

**Reading.** Under a null, each trial confirms with probability ~2% (t, placebo and both years together), so ~0.4 confirmations
were expected by chance from 19; two arrived. **D151** (ZS, a plan product): +30.3 bps, t +2.32, placebo 99th, both years positive.
**D139** (NKD, a plan product): +53.9, t +2.80, placebo 100th — but 20 events and 2025 barely positive (+1.7). D146 (the DAX follows a
ZN shock — D68's mechanism on the DAX) held in both years with placebo 99th but t +1.30: WATCHLIST. Per §426, 5 both confirmations
are stress-tested before anything is proposed (§430).

## 430. Stress tests for D151 and D139, fixed before running (S8)

**No trial; N 927.** As §210 / §382. **D151 (ZS fades a ZM shock):** (1) thresholds 1.5 / 2 / 2.5σ; periods 2010–20, 2021–24, 2025–26;
target also the SOYB ETF (open → close, next weekday) as an independent soybean price; (2) the ZS account (3 ZS, A23, drift removed,
both histories): plan vs the overlay (short ZS the session after a ZM up-shock; a down-shock already means long). **D139 (NKD fades a
BTC=F shock):** (1) thresholds 1.5 / 2 / 2.5σ; predictor also BTC-USD spot (UTC day; closes at Tokyo's open, no overlap); target also
Yahoo NKD=F's CME session (open → settlement) as an independent Nikkei price; periods 2018–20, 2021–24, 2025–26 (BTC=F starts Dec
2017); (2) the NKD account (1 NKD): plan vs short the window after a bitcoin up-shock. Read, per §426, 5: propose to the user only if
(1) keeps the sign in 2025–26 on the independent variants and (2) does not lower mean net or P(payout) in 2021–26.

## 431. D139 replicates strongly on independent data; D151 holds in sign; neither moves its account much (S8)

**No trial; N 927.** `reports/a33_stress.json`, module `reporting/a33_stress.py`.

**D139 (NKD fades a bitcoin shock) — 2025–26, every independent variant positive:** spot BTC-USD → NKD window +38.7 bps (t +2.51, n 28),
spot → NKD=F CME session +65.0 (t +2.28); BTC=F → NKD=F +128.8 (t +3.40); thresholds 1.5σ (+25 to +48, t +1.5 to +2.5) and 2.5σ the
same sign. 2021–24 positive throughout (+3 to +47); 2018–20 mixed (≈ 0). The most consistent independent replication in the programme
— a post-2021 phenomenon (bitcoin's spot ETFs and Japanese retail's crypto/equity overlap are the plausible channel: a crypto rally
pulls Japanese risk money the next morning, then reverses). **D151 (ZS fades a meal shock):** SOYB 2025–26 +17.4 (t +1.51) at 2σ,
+8 to +11 at 1.5 / 2.5σ — the sign holds; but 2010–20 is negative on ZS (−19.1, t −1.79): a current-regime effect.

**The accounts (A23, drift removed, 2021–26 | 2010–20):**

| | 2021–26 P(payout), mean net, P(net > 0) | 2010–20 |
|---|---|---|
| ZS plan | 86%, +$3,310, 81% | 70%, +$3,061, 59% |
| ZS + D151 (short 3.7% of days) | 88%, +$3,318, 81% | 71%, +$2,503, 58% |
| NKD plan (1 contract) | 74%, +$2,763, 63% | 67%, +$1,189, 58% |
| NKD + D139 (short 3.0% of days) | 75%, +$2,715, 65% | 67%, +$1,099, 55% |

§430's reading: D151 meets it narrowly in 2021–26 (+$8, P(payout) +2 pts); D139 misses it by mean net (−$48) while raising P(payout)
and P(net > 0). Both are real-looking and both are too rare (~3% of days) to change an account under brackets — the same lesson as
D68 and D122. **Status: CONFIRMED and replicated findings; candidates for the user, not deployed.**

## 432. The user's decisions (2026-10-14): D139 to the demo's NKD ticket; D151 not adopted; the search continues (S8)

**D139 deployed** to the demo bot at 14:41 ET on 2026-10-14 (backup `/opt/futures-bot/backup-2026-10-14`): `bot/d139.py` reads Yahoo
BTC=F's daily sessions at the 17:30 ET alert (CME's session has closed at 17:00); if today's open → close is beyond 2 × the SD of the
previous 60 sessions, the next NKD ticket FADES it (short after a rally, long after a sell-off) and the post carries a "D139:" note;
otherwise, or on any data error, long. Wired in `bot/schedule.py` beside D68; `tests/test_bot_ticket.py` covers it. A forward test at
no cost: the account replay (§431) expects it roughly neutral to the account, the statistics expect the shock days to favour it.
**D151 not adopted** (the user, per §431). The search continues under §426's design.

## 433. D-series family 115 protocol: the intraday structures on the current regime (S1)

**No trial spent; N 927. Written and committed BEFORE any statistic is computed.** Earlier intraday families re-run under §426's design
(owned minute grids, family 8; each predictor → target same contract; follow or fade fixed by 2021–24; forms **all** and **strong**
(|predictor| above its discovery median)). MNQ (day/night/post grids) and gold (London/Asia/NY grids):
1. the session before → the window (MNQ night → day; gold Asia → London);
2. morning → afternoon (MNQ 09:30–12:00 → 13:00–16:00; gold 03:00–07:00 → 08:30–11:30);
3. first 30 minutes → the rest (MNQ 10:00 → 16:00; gold 03:30 → 11:30);
4. the opening minute → the rest (MNQ 09:30 → 09:31 vs night close; gold 08:20 → 08:21);
5. the previous window → the window (day → next day; London → next London);
6. the previous window's close location → the window (sign of CLV − 0.5);
7. the window's last hour → the next session (MNQ 15:00–16:00 → night; gold 10:30–11:30 → NY afternoon 11:30–16:55);
8. overnight signed volume → the window (family 84's imbalance);
9. into a fix → after it (MNQ 11:00–11:30 → 11:30–12:00, the European close; gold 13:00–13:30 → 13:30–14:00, COMEX settlement).
**9 rules × 2 markets × 2 forms = 36 tests** (~0.9 by chance at 2.5%). Costs §180; validation per §426, 2 (placebo: predictor signs
shuffled across the sealed sessions).

## 434. Family-115 discovery: 2 of 36 carried (≈ 0.9 by chance); D152–D153 registered (S1)

**No trial spent yet; N 927.** `reports/d115_discovery.json` (module `reporting/d115_intraday.py`):
- **D152** MNQ opening_minute (strong) follow: +11.57 bps, t +2.06, n 505; 2010–20 +11.55 (t +2.69); market-test 164.
- **D153** MNQ last_hour_next (all) fade: +4.90 bps, t +2.03, n 954; 2010–20 +0.61 (t +0.43); market-test 165.

D152 is the strong form of D101 (the all-days opening-minute rule, WATCHLIST in §280); the strong form was never validated, and its
2010–20 context is the same sign and size. Validation per §426, 2 with shuffled predictor signs as the placebo.

## 435. D152–D153 validated (t00934–t00935): WATCHLIST both — positive in both years, below significance (S1)

**N 929.** D152 MNQ strong opening minute, follow: +8.26 bps (t +0.94), placebo 86th, 2025 +9.4 / 2026 +6.7 —
but always-long over the same sessions earned +7.08, so it adds ~1 bp over the plan (as D101). D153 MNQ night fades the last hour:
+3.51 (t +0.92), placebo 87th, both years positive. Neither usable. Z and D market-tests reach 165.

## 436. D-series family 116 protocol: the calendar on the current regime (S1)

**No trial spent; N 929. Written and committed BEFORE any statistic is computed.** Family 5's question (§155) under §426's design. Cells
from the dates alone: Monday … Friday; the first three trading days of the month; the last trading day; the first trading day on or
after the 15th; the third Friday (expiry); its Monday–Thursday (expiry week). **10 cells × 6 plan windows** (MNQ day, MGC London —
family-8 grids; NKD, DAX — A21 paths; CL, ZS — family 10) **= 60 tests** (~1.5 by chance). Statistic: the window on the cell's days
minus its mean on all other days in the period; long or short fixed by 2021–24. Costs §177/§180; validation per §426, 2 (placebo: the
same number of random other days, 1,000 draws).

## 437. Family-116 discovery and D154 (t00936): the calendar on the current regime — 1 of 60 carried, rejected (S1)

**N 930.** `reports/d116_discovery.json` (module `reporting/d116_calendar.py`): one carried, at chance level — **D154** ZS short in
equity-option expiry week (+21.7 bps, t +2.16, n 187; no mechanism). Sealed 2025–26: -1.55 bps (t -0.12), placebo
47th, 2025 −7.6 / 2026 +7.4: **REJECT**. The calendar sets no direction in the current regime either. Z and D
market-test 166.

## 438. D-series family 117 protocol: each plan market's own past on the current regime (S1)

**No trial spent; N 930. Written and committed BEFORE any statistic is computed.** For each plan window (MNQ day, MGC London, NKD, DAX,
CL, ZS; family 114's targets), from the window's own series: **(i) own shock** — the previous window beyond 2 × the SD of the previous
60; **(ii) trend5** — the sign of the sum of the previous 5 windows; **(iii) trend20** — of the previous 20. Follow or fade fixed by
2021–24. **3 × 6 = 18 tests** (~0.5 by chance). Costs §177/§180; validation per §426, 2 (placebo: signals shuffled across the sealed
windows).

## 439. Family-117 discovery: 2 of 18 carried; D155–D156 registered (S1)

**No trial spent yet; N 930.** `reports/d117_discovery.json` (module `reporting/d117_own.py`):
- **D155** MNQ fades its trend5: +7.87 bps, t +2.19, n 1016; 2010–20 +0.69 (t +0.34); market-test 167.
- **D156** DAX fades its own_shock: +27.56 bps, t +1.98, n 53; 2010–20 -11.67 (t -1.33); market-test 168.

D155 is an every-session rule (short-horizon mean reversion on MNQ's day window): if it held, it would change the plan's direction on
about half the days — the scale an account notices (~$125 a session at 4 MNQ for +7.9 bps). Its 2010–20 context is flat.

## 440. D155–D156 validated (t00937–t00938): MNQ's weekly reversal fails; the DAX's own-shock fade is WATCHLIST (S1)

**N 932.** D155 MNQ fades its 5-day trend: **REJECT**, -0.72 bps (t -0.13), placebo 50th, 2025 +5.4 / 2026 −10.0. D156 the
DAX fades its own shock: **WATCHLIST**, +31.16 (t +1.37, n 30), placebo 88th, both years positive. Z and D market-tests
reach 168.

## 441. D-series family 118 protocol: currency fix flows on the current regime (S1)

**No trial spent; N 932. Written and committed BEFORE any statistic is computed.** Families 41, 66 and 74 under §426's design (HistData,
corrected clock). **London 16:00 fix** (family 41's `d41_fix.rows`): 15:30 → 16:00 predicts 16:00 → 16:30, follow or fade, forms all /
strong, for 6E, 6B, 6J, 6A, 6C, 6S (12 tests). **Gotobi** (family 66's `d66_gotobi.rows`): pre and post windows, long or short 6J
(2 tests; D104 and D116 were validated on 2023–26 with the same rules and are therefore NOT re-tested — the gotobi tests are skipped).
**ECB fix** (family 74): pre / post 6E (2 tests; D118, the post-fix 6E rule, is excluded — pre only, 1 test). **13 tests**. Costs as the
originals; validation per §426, 2 (placebos as the originals).

## 442. Family-118 discovery: fix flows on the current regime — the only carry is an already-validated rule; empty (S1)

**No trial spent; N 932.** `reports/d118_discovery.json`: 6B fades a strong move into the London fix, +0.98 bps (t +1.98) — the same
rule as D98, REJECTED on 2023–26 (§254), so not re-tested (§426, 3; §441 should have listed D97–D99 among the exclusions — it omitted
them, and the global rule governs). Everything else |t| < 1.7, all below 1 bp. The fixes are not where the current regime pays.

## 443. D-series family 119 protocol: yesterday's direction across markets, every day, on the current regime (S1)

**No trial spent; N 932. Written and committed BEFORE any statistic is computed.** Family 10's question under §426's design with family
111's predictor list: the sign of each predictor's previous-weekday move (every day, not only shocks) → each plan window (MNQ, MGC,
NKD, DAX, CL, ZS), with or against, fixed by 2021–24; family 111's exclusions (own market, currency → CL/NKD timing, family-29 pairs,
validated pairs). Forms **all** and **strong** (|move| above its 2021–24 median). Carried at net > 0, t > 1.96 (~2.5% of nulls; the count
is reported against it). Costs §177/§180; validation per §426, 2 (placebo: signs shuffled across the sealed sessions). These are
every-day rules, so a survivor would be account-sized.

## 444. Family-119 discovery: 44 of 718 carried (≈ 18 by chance); D157–D200 registered (S1)

**No trial spent yet; N 932.** `reports/d119_discovery.json` (module `reporting/d119_alldays.py`):
- **D157** CL follows KRE (all): +25.25, t +3.57; 2010–20 -6.17 (t -1.36).
- **D158** DAX fades 6S=F (strong): +14.51, t +3.35; 2010–20 +6.19 (t +1.98).
- **D159** CL follows KRE (strong): +33.46, t +3.28; 2010–20 -13.38 (t -1.51).
- **D160** CL follows XOP (strong): +33.27, t +3.27; 2010–20 +3.89 (t +0.51).
- **D161** CL follows XOP (all): +22.76, t +3.21; 2010–20 +0.56 (t +0.12).
- **D162** DAX fades 6E=F (all): +9.43, t +3.18; 2010–20 +2.72 (t +1.31).
- **D163** NKD follows XOP (all): +7.83, t +3.00; 2010–20 -3.28 (t -1.18).
- **D164** MNQ follows ^SKEW (strong): +15.36, t +2.99; 2010–20 +4.14 (t +1.40).
- **D165** CL follows XLF (all): +20.59, t +2.89; 2010–20 -11.46 (t -2.49).
- **D166** NKD follows NG=F (all): +7.34, t +2.80; 2010–20 +3.71 (t +1.34).
- **D167** DAX fades 6C=F (strong): +12.32, t +2.71; 2010–20 +1.47 (t +0.51).
- **D168** MNQ fades ZL=F (strong): +13.83, t +2.69; 2010–20 -0.85 (t -0.20).
- **D169** DAX fades 6E=F (strong): +12.41, t +2.61; 2010–20 +5.57 (t +1.84).
- **D170** CL follows HYG (all): +18.62, t +2.59; 2010–20 +0.42 (t +0.09).
- **D171** DAX fades 6B=F (all): +7.56, t +2.55; 2010–20 -1.59 (t -0.76).
- **D172** CL follows NKD=F (all): +17.71, t +2.50; 2010–20 -2.18 (t -0.48).
- **D173** CL follows XLF (strong): +26.08, t +2.44; 2010–20 -16.31 (t -2.21).
- **D174** DAX follows DX-Y.NYB (strong): +10.94, t +2.42; 2010–20 +5.23 (t +1.63).
- **D175** DAX fades 6A=F (strong): +11.27, t +2.41; 2010–20 -2.26 (t -0.68).
- **D176** NKD fades ^GVZ (all): +6.22, t +2.36; 2010–20 -3.23 (t -1.16).
- **D177** DAX fades 6S=F (all): +6.90, t +2.31; 2010–20 +3.89 (t +1.87).
- **D178** NKD follows XOP (strong): +9.48, t +2.31; 2010–20 -3.12 (t -0.79).
- **D179** CL follows EEM (all): +15.97, t +2.24; 2010–20 +1.00 (t +0.22).
- **D180** ZS follows BG (strong): +14.06, t +2.23; 2010–20 +5.24 (t +1.44).
- **D181** ZS fades ^VIX (strong): +13.48, t +2.20; 2010–20 +4.30 (t +1.32).
- **D182** MNQ follows ^SKEW (all): +8.29, t +2.18; 2010–20 +1.10 (t +0.54).
- **D183** DAX fades MXN=X (all): +6.96, t +2.17; 2010–20 +9.69 (t +4.49).
- **D184** NKD follows ADM (strong): +8.42, t +2.16; 2010–20 -2.94 (t -0.68).
- **D185** CL follows XLE (strong): +22.20, t +2.14; 2010–20 +6.58 (t +0.77).
- **D186** CL follows HYG (strong): +23.75, t +2.12; 2010–20 -4.31 (t -0.53).
- **D187** MNQ fades CLP=X (strong): +12.14, t +2.09; 2010–20 +2.18 (t +0.49).
- **D188** DAX fades 6J=F (all): +6.18, t +2.06; 2010–20 -0.23 (t -0.11).
- **D189** MNQ fades ZL=F (all): +7.84, t +2.06; 2010–20 -3.28 (t -1.59).
- **D190** MNQ fades INR=X (all): +8.09, t +2.05; 2010–20 -2.43 (t -1.11).
- **D191** NKD follows FXI (all): +5.35, t +2.03; 2010–20 -3.10 (t -1.12).
- **D192** NKD follows HYG (strong): +6.83, t +2.02; 2010–20 -9.53 (t -1.97).
- **D193** MNQ fades ZS=F (all): +7.51, t +2.02; 2010–20 +2.87 (t +1.42).
- **D194** CL follows EEM (strong): +21.35, t +2.00; 2010–20 -0.71 (t -0.11).
- **D195** ZS follows EEM (strong): +12.58, t +2.00; 2010–20 +1.89 (t +0.58).
- **D196** NKD follows XLE (all): +5.19, t +1.98; 2010–20 -3.64 (t -1.32).
- **D197** DAX fades 6J=F (strong): +9.14, t +1.97; 2010–20 +0.91 (t +0.28).
- **D198** DAX follows KRW=X (all): +6.32, t +1.97; 2010–20 +0.78 (t +0.36).
- **D199** NKD fades ^GVZ (strong): +7.98, t +1.97; 2010–20 -5.85 (t -1.50).
- **D200** DAX follows DX-Y.NYB (all): +5.86, t +1.96; 2010–20 +2.18 (t +1.04).

The clearest excess over chance in the search, in themes: **the DAX moves against the dollar crosses** (6S, 6E, 6C, 6A, 6B, 6J — fade;
the dollar index — follow): a weaker euro lifts German exporters the next morning, partly visible in 2010–20 too; **crude follows the
previous day's risk assets** (KRE, XLF, XOP, HYG, EEM) — opposite in 2010–20; **MNQ follows SKEW**. Many tests share days (correlated);
each is validated once per §426, 2.

## 445. D157–D200 validated (t00939–t00982): three CONFIRM, all one theme — the DAX moves with the dollar the next day (S1)

**N 976.** Sealed 2025-01 → 2026-08 under §426, 2. Non-rejected (the other 23 REJECT — every crude-follows-risk rule among them):
- **D158** DAX fades 6S=F (strong): **WATCHLIST** — n 215, +7.86 (t +1.27), placebo 89th, 2025 +3.2, 2026 +15.2
- **D159** CL follows KRE (strong): **WATCHLIST** — n 149, +3.24 (t +0.16), placebo 66th, 2025 -16.4, 2026 +31.6
- **D160** CL follows XOP (strong): **WATCHLIST** — n 167, +0.16 (t +0.01), placebo 51th, 2025 -15.9, 2026 +24.2
- **D162** DAX fades 6E=F (all): **WATCHLIST** — n 409, +6.84 (t +1.65), placebo 96th, 2025 -1.1, 2026 +18.9
- **D163** NKD follows XOP (all): **WATCHLIST** — n 405, +0.27 (t +0.06), placebo 57th, 2025 -3.4, 2026 +5.8
- **D164** MNQ follows ^SKEW (strong): **WATCHLIST** — n 215, +8.47 (t +0.92), placebo 85th, 2025 +15.8, 2026 -3.6
- **D167** DAX fades 6C=F (strong): **WATCHLIST** — n 153, +4.10 (t +0.56), placebo 74th, 2025 +5.1, 2026 +2.3
- **D169** DAX fades 6E=F (strong): **WATCHLIST** — n 187, +10.36 (t +1.51), placebo 94th, 2025 +3.7, 2026 +24.1
- **D171** DAX fades 6B=F (all): **CONFIRM** — n 409, +7.05 (t +1.70), placebo 97th, 2025 +2.6, 2026 +13.7
- **D174** DAX follows DX-Y.NYB (strong): **CONFIRM** — n 198, +10.93 (t +1.66), placebo 96th, 2025 +7.0, 2026 +18.4
- **D175** DAX fades 6A=F (strong): **CONFIRM** — n 173, +19.01 (t +2.54), placebo 100th, 2025 +7.1, 2026 +36.9
- **D177** DAX fades 6S=F (all): **WATCHLIST** — n 411, +5.03 (t +1.22), placebo 92th, 2025 +2.5, 2026 +8.8
- **D182** MNQ follows ^SKEW (all): **WATCHLIST** — n 402, +6.75 (t +1.17), placebo 89th, 2025 +10.6, 2026 +0.9
- **D184** NKD follows ADM (strong): **WATCHLIST** — n 242, +9.24 (t +1.55), placebo 93th, 2025 +7.7, 2026 +11.1
- **D185** CL follows XLE (strong): **WATCHLIST** — n 175, +2.40 (t +0.12), placebo 56th, 2025 -16.0, 2026 +28.1
- **D188** DAX fades 6J=F (all): **WATCHLIST** — n 405, +5.10 (t +1.21), placebo 90th, 2025 +2.5, 2026 +9.2
- **D195** ZS follows EEM (strong): **WATCHLIST** — n 208, +0.58 (t +0.08), placebo 53th, 2025 +6.4, 2026 -4.8
- **D197** DAX fades 6J=F (strong): **WATCHLIST** — n 200, +7.27 (t +1.07), placebo 86th, 2025 +3.6, 2026 +16.4
- **D198** DAX follows KRW=X (all): **WATCHLIST** — n 373, +3.27 (t +0.75), placebo 76th, 2025 -1.9, 2026 +11.1
- **D200** DAX follows DX-Y.NYB (all): **WATCHLIST** — n 408, +6.94 (t +1.68), placebo 95th, 2025 -2.4, 2026 +21.2

**The theme.** Every DAX × dollar rule (6B, 6A, 6E, 6S, 6C, 6J faded; the dollar index followed) is positive out of sample; three
pass every condition (**D171** 6B all, **D174** DXY strong, **D175** 6A strong) and the rest sit just below. The DAX rises the session
after the dollar strengthens and falls after it weakens — a weaker euro lifting exporters, read a session late. Unlike every earlier
confirmation this is an EVERY-DAY rule on a plan product (FDXM): at 2 FDXM (~$260,000 notional) +7 bps a session is ~$180. Crude
following risk assets — the largest discovery cluster — failed completely (2025–26 negative). Stress tests fixed in §446.

## 446. Stress tests for the DAX–dollar theme, fixed before running (S8)

**No trial; N 976.** The theme's rule in one form: **the DAX window takes the sign of the previous weekday's dollar move** (dollar up →
long DAX; dollar down → short). (1) **Independent data** — dollar: Yahoo DX-Y.NYB (the trial's), FRED **DTWEXBGS** (broad trade-weighted,
daily change), and **EUR/USD** from HistData (16:55 → 16:55 ET, inverted); DAX: A21's window (the trial's) and the real index **^GDAXI**
(Yahoo open → close); forms all and strong (2021–24 medians); periods 2010–20, 2021–24, 2025–26. (2) **The FDXM account** (2 FDXM, A23,
drift removed, both histories): plan (always long) vs **every-day** (the rule's sign every session) vs **strong-only** (short only after a
strong dollar fall; long otherwise). Read: propose to the user if (1) holds in 2025–26 on the independent variants and (2) raises mean net
and P(net > 0) in 2021–26 without lowering P(payout).

## 447. The DAX–dollar rule passes every stress test and nearly doubles the FDXM account's net — the first account-sized edge (S8)

**No trial; N 976.** `reports/a34_daxdollar.json`, module `reporting/a34_daxdollar.py`. Rule: the DAX window takes the sign of the
previous weekday's dollar move.

**(1) Independent data, 2025–26 (sealed for this theme):** all 12 variants positive — DX-Y.NYB → ^GDAXI +7.0 (t +1.64); FRED broad dollar
→ A21 +9.2 (t +2.22), → ^GDAXI +8.5 (t +2.00); EUR/USD (16:55 ET) → A21 +4.8 / strong +10.3, → ^GDAXI +4.6 / +10.5. 2021–24: all 12
positive (t +0.94 to +2.91). 2010–20: weakly positive on DX-Y.NYB and EUR/USD (+1.1 to +5.2), negative on FRED's noon-fixed broad index —
the effect is strongest in the current regime and on end-of-day dollar measures.

**(2) The FDXM account (2 FDXM, 50K Daily, A23, drift removed, every start, 84 days):**

| | 2021–26 P(payout), mean net, P(net > 0) | 2010–20 |
|---|---|---|
| plan, always long | 83%, +$1,879, 67% | 73%, +$2,071, 62% |
| **every-day rule** (short after a dollar fall; 45% of sessions) | **85%, +$3,720, 81%** | **85%, +$3,144, 73%** |
| strong-only (short after a strong fall; 23%) | 86%, +$3,241, 76% | 70%, +$2,174, 60% |

The every-day rule raises mean net by **+$1,841** per four months in 2021–26 and +$1,073 in 2010–20, and P(net > 0) by 14 and 11 points,
without lowering P(payout) — §446's reading is met in full. Unlike D68/D122/D139/D151 (event rules on ~3% of days, account-neutral),
this acts every session. **Status: CONFIRMED (D171, D174, D175 and the theme), stress-tested, proposed to the user; NOT deployed.**
Implementation note: the bot's 17:30 ET alert can read the day's dollar move (EUR/USD to 16:55 ET, or DX-Y.NYB's session) before
the FDXM ticket's 03:00 ET entry.

## 448. The DAX–dollar rule deployed to the demo's FDXM ticket (2026-10-14, the user) (S8)

**No trial; N 976.** Deployed at ~15:00 ET (backup `/opt/futures-bot/backup-2026-10-14b`): `bot/daxdollar.py` reads Yahoo DX-Y.NYB's
daily bar at the 17:30 ET alert (open → latest; the bar updates through the day) and sets the FDXM ticket LONG after a dollar rise,
SHORT after a fall — every session; unchanged or unreadable → long. Wired in `bot/schedule.py` beside D68 and D139, posts carry a
"DAX-dollar:" note; `tests/test_bot_ticket.py` covers it. First reading: 2026-10-14 dollar +36 bps → FDXM long.

**What the replay's numbers mean (answered to the user):** §447's means are per FDXM account (2 contracts, 50K Daily) per 84 trading days
(~4 months) from each start date — payouts after Tradeify's 10% minus evaluation/reset fees, commissions included, drift removed. Only
the FDXM account changes: the five-account book gains ~+$1,841 per four months, not five times it. Not modelled: extra slippage, and
whether the 2021–26 strength persists — which is what the demo now tests.

## 449. D-series family 120 protocol: the last five days' direction across markets, every day, current regime (S1)

**No trial spent; N 976. Written and committed BEFORE any statistic is computed.** Family 119 (§443) found the DAX–dollar rule with
one-day predictors. Here the predictor is the sign of each series' summed moves over the previous 5 weekdays (ending the previous
weekday), every session; same predictor list, targets and exclusions; forms **all** and **strong** (|5-day sum| above its 2021–24
median); pairs carried in family 119 are kept (a 5-day sum is a different rule). Carried at net > 0, t > 1.96; the count reported
against ~2.5% by chance. Validation per §426, 2 (placebo: signs shuffled across the sealed sessions).

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

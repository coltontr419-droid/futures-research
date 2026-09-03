# Four gate defects, and why measurement precedes scheduling

The detectability gate decides which hypotheses can produce evidence. Between 2026-09-01 and
2026-09-02 it was wrong four times, in four different ways. Each was caught by accident
rather than by design, each had already cost something, and the pattern connecting them is
worth more than any of them individually.

This document is the argument for measuring a firing rate before scheduling a hypothesis. It
should be readable without the rest of the repo.

---

## What the gate is for

A hypothesis can only produce evidence if its sample is large enough for the effect it
claims to be detectable at all. Below that threshold, "nothing found" carries no
information — nothing would have been found either way, and a null reads identically whether
the market is empty or the test is blind.

The gate compares each hypothesis's usable event count against the smallest sample at which
a detection floor was ever measured. Below it, the combination is marked **uninformative**
rather than allowed to report a null.

The event count is the input. All four defects were in that input.

---

## Defect 1 — scan multiplicity: counting firings the cell never sees

**What it was.** The gate stored how often a hypothesis's condition fires *across its whole
scan*. But Benjamini-Hochberg tests **cells**, and a cell fixes the scanned dimension. A scan
over 13 half-hour slots fires 13 times a session; each individual cell fires **once**.

| | gate said | per cell |
|---|---|---|
| F03 | 53,625 | 234–2,384 |
| F07 | 48,072 | ~4,000 |
| F04 | 8,250 | 3,554–3,880 |

**What it cost.** F03 was retired on reasoning that quoted its per-cell BH result — a result
now known to have been uninformative. The verdict survived, on its aggregate, but the stated
reason had to be rewritten. F04's headline "best cell at 0.30× the floor" was **withdrawn**:
it came from a 60-minute cell that the corrected gate places below the swept range.

**What caught it.** Scheduling F07 and noticing its row claimed 48,072 events for a condition
firing twelve times a session over ~4,000 sessions. The arithmetic only works if every cell
gets all twelve firings, which no cell does.

**The second-order version, caught minutes later.** Pooling a scan's cells restores sample
*only when the positions are disjoint in time*. F03's 13 slots are separate trades, so its
aggregate genuinely holds 13× the observations. F07's 12 slots are twelve **predictors of one
target** — every cell enters at the same 15:30 minute — so pooling stacks correlated readings
of one sample. Treating that overlap as sample would have repeated the same error one level
up. F01 turned out to be the same trap in miniature: two entry times, 15:00 and 15:30, that
look disjoint until you notice they **share a 15:55 exit**.

---

## Defect 2 — an uncounted rate falling through to the data ceiling

**What it was.** Four hypotheses had no firing rate recorded. The gate treated a missing rate
as "no event constraint" and fell through to the **data ceiling** — every observation in the
sample. The most generous possible assumption, applied precisely where least was known.

**What it cost.** 24 combinations across F05, F08, F10 and F11 were cleared on it. Among them
F10, the **negative control**, which measurement then showed reaching 1,585–5,594 events
against a swept range starting at 19,722. An unpowered control coming back empty is
indistinguishable from a powered one working correctly, so the catalog could not verify its
own control and did not know it.

**What caught it.** Reading the code path while fixing defect 1.

**The fix that mattered.** The default became *blocking*. A missing rate is now
`FIRING RATE UNMEASURED`, which is a status, not a silent pass.

---

## Defect 3 — a declared rate counting opportunities, not triggers

**What it was.** F02 declared one firing per session. It fires at **0.061**. The declaration
counted the *opportunity* — one closing-imbalance reading per session per window — while the
condition only **triggers** when `|imb| > k·σ`, on 6–23% of rows. A mandatory pre/post-2021
regime split then halved the remainder again, and that requirement lived in a *different
hypothesis's exclusion note*, so the gate never saw it.

| | gate said | actual |
|---|---|---|
| per cell | 4,006–4,125 | **106–707** |
| aggregate | 6,142–8,250 | ~210–1,414 |

**What it cost. 144 trials.** Every cell came back uninformative. N went from 348 to 492 and
SR\* — the Sharpe any future candidate must clear before its result means anything — rose
from **0.0902 to 0.1402**. Every hypothesis still untested now faces a higher bar because of
trials spent learning a fact a measurement would have shown first.

**What caught it.** Running F02 and comparing the event counts to the prediction.

**Why defect 2's fix could not have caught it.** That repair added a test asserting every
hypothesis has a declared **or** measured rate. F02 had a declaration, so it passed. **No test
can check whether a declaration is correct, because a declaration has no independent source
to check against.** That is the whole argument, in one sentence.

**The fix.** Declared rates no longer gate anything. They are retained as
`DECLARED_ESTIMATE` purely so the gap stays visible, and `assess()` is forbidden by test from
reading them.

The correction was not small, and the status labels understated it:

| | previously gated on | measured | factor |
|---|---|---|---|
| **F01** | 4,125 | **66** | **62.5×** |
| F03 | 4,125 | 234 | 17.6× |
| F11 | 78,888 | 12,285 | 6.4× |
| F06 | 4,125 | 1,621 | 2.5× |
| F02 | 251 | 106 | 2.4× |

Only two combinations changed *status*. Most of the catalog was already blocked, and a
hypothesis 4.8× short of the bar is not made more blocked by learning it is 62× short.

---

## Defect 4 — a remediation command that did nothing

**What it was.** With measurement now mandatory, three places told anyone hitting a blocked
row to run `python -m futuresres.reporting.measured_rates`. **That module had no `main()`.**
The command printed nothing, did nothing, exited 0.

**What it cost.** Nothing yet, which is the only reason it appears last. But the file the
entire gate depends on could be produced *only* by an ad-hoc script that lived outside the
repository. The gate's single input had no reproducible provenance — the same property the
trial log exists to guarantee for N.

**What caught it.** Re-reading the error message and running the command it recommends.

**The fix.** A real entry point, plus `--check`, which measures fresh and confirms the
committed cache reproduces exactly. And a test that scans the source for every
`python -m futuresres…` string and fails if the named module has no `main()`.

---

## The shape they share

All four are **a control that exists in form but not in effect**.

- A gate that reads a number nobody measured.
- A default that clears what it cannot assess.
- A declaration that no test can verify.
- An instruction that runs nothing.

Each looked correct from the outside. Each had passing tests around it. Three of the four
were caught only because something downstream happened to contradict them — and the fourth
was caught by reading rather than by any check.

Two nearby defects have the same shape and are recorded elsewhere: the **trial log** that was
ported with passing tests and that no runner ever called, so N was reconstructed by counting
rows in output files; and F14's **scope statement**, first written as a YAML comment, which
`yaml.safe_load` discards — every tool reading the registry would have seen a control with no
stated scope.

**The generalisation the repo now runs on: anything a decision depends on must be measured,
and anything a tool must check must survive parsing.** A number that was asserted rather than
observed is not evidence about the world; it is evidence about what someone expected.

---

## What this costs, both ways

| | |
|---|---|
| measuring all twelve hypotheses' firing rates | **16 seconds**, 0 trials |
| discovering the same fact by running F02 | **144 trials**, SR\* 0.0902 → 0.1402 |

Measurement is not a reporting nicety appended after scheduling. **It is a scheduling
precondition** (CLAUDE_FUTURES.md §5.11), and a hypothesis absent from
`reports/measured_rates.json` cannot be scheduled at all.

## What is still owed

The gate now takes only measured input, but measurement cannot repair a condition that is
underspecified. Three hypotheses are blocked on decisions rather than on data:

- **F05** — its `k·σ` trigger measures σ on the very window compression selects for being
  quiet, so it fires on 79–91% of armings even after a mechanism-derived deadline was
  applied. The specification is self-defeating.
- **F06** — `vol_filter` names no quantity and no lookback, and that choice changes the
  event count and therefore whether its routes are open.
- **F08** — "the lower volume-weighted move" decides which leg is traded, and so decides the
  strategy's direction, without being defined anywhere.

**These are worse than a wrong rate, because a vacuous condition with plenty of events
produces a confident-looking result about nothing.** The gate cannot catch them: they pass
every event-count check it makes.

# Checkpoint — 2026-09-02, updated 2026-09-09

Written at a hard stop on 2026-09-02 and **updated 2026-09-09, when it was found to be
issuing an instruction that had already been carried out.** The batch it says must be re-run
completed on 2026-09-05 and was committed as `fb07e80`. Anyone who followed this file between
those dates would have re-run twenty minutes of work for nothing.

Everything below is committed; nothing is in flight on disk.

---

## Where things stand

**The F-series is closed.** 14 registered, 576 trials, SR\* = 0.1334, 0 promoted. See
`reports/futures_conclusion.md` — it stands alone and is the document to read first.

**The L-series is registered and now MEASURED.** Ten price-level hypotheses (L01–L10) are in
`hypotheses.yaml` under the Stage 0 schema. All remain `schedulable: false`. **No Stage 1 has
been run on any of them and no L-series trial has been spent** — N is still 576 and SR\* still
0.1334.

The measurement says the L-series does not have a route to a verdict as it stands:

- **Event count.** Only **L07** clears the 180-minute floor on both instruments. L02 and L03
  clear on MGC at 120m+; L04 is mixed; everything else is below the swept range.
- **Disjointness.** Nine of ten aggregate routes are **closed**, at 97–100% pairwise overlap.
  The only open one is **L10**, which is the placebo control and spends no trials.
- **Placebo matching: FAIL.** 53 of 55 level types under the original daily-ATR scale, **52 of
  55 after the 2026-09-09 scale correction.** The three that pass are `prior_week`/MGC and
  `prior_month`/MGC (both **L09**, 8–62× below floor) and `sess_US`/MGC (**L04**, US-session
  cells only, 7–17× below floor).

**Those three results cross, and the crossing is the finding.** L07 clears the floor on both
instruments and all six of its FVG level types fail matching, at the worst distance ratios in
the study. **L04 shows the crossing inside a single hypothesis on a single instrument**: its
best cell fires 5,130 times but is an *Asia*-session cell whose placebo fails, while the
*US*-session cells whose placebo passes fire 168 to 399 against a floor of 2,862.
**No L-series hypothesis has a resolvable sample and a valid placebo in the same cells.**

---

## ~~The one thing that must be re-run~~ — DONE 2026-09-05, re-run again 2026-09-09

```
python -m futuresres.reporting.level_rates          # ~65 min, both instruments
```

**The runtime figure in this file used to say ~20 min and that was wrong by a factor of three.**
Measured 2026-09-09: 64 minutes wall clock, CPU-bound throughout, on both instruments. The
opening-range stage alone is roughly half of it, and the disjointness pass at the end holds
every cell's firing minutes in memory and peaks near 1 GB.

It writes `reports/level_rates.md`, `reports/placebo_match.md` and
`reports/disjointness.md`, **all at the end**, so an interrupted run leaves nothing behind.

**It completed on 2026-09-05** (commit `fb07e80`) and was re-run on 2026-09-09 after the
placebo scale correction described below. **This section stood for four days telling readers
to run work that was already finished** — recorded rather than quietly deleted, because a
checkpoint that outlives its own instructions is its own failure mode and this project keeps
a list of those.

---

## What the run is expected to produce

Three things, none of them yet known:

1. **Firing rate per Stage 1 cell**, thresholds applied, against the swept range.
2. **Placebo matching** — count, distance distribution and touch frequency, verified rather
   than asserted. `verify()` raises `PlaceboMismatch` on divergence.
3. **Disjointness per hypothesis** — maximum pairwise overlap of firing minutes across a
   hypothesis's cells. Per F07 the aggregate route is assumed closed until this says
   otherwise.

Then still owed, and **not yet done**: projected N and SR\* if the schedulable subset runs its
full grids, and a flag on any hypothesis whose trial cost looks disproportionate to what it
can establish.

---

## The finding that is already firm, before the batch finishes

**`d ATR` does not say which ATR, and that decides whether L01, L06 and L08 are testable at
all.**

Under the natural reading — daily ATR(20), which is what the code uses and states — price is
rarely a full daily ATR away from VWAP intraday:

| L01 VWAP, MNQ, RTH anchor | sessions firing |
|---|---|
| d = 0.5 | 2.2% |
| d = 1.0 | 0.0% |
| d = 1.5 | 0.0% |

At d ≥ 1.0 the condition fires on essentially nothing. A shorter ATR period, or an intraday
ATR, would make these hypotheses fire freely.

**This is an F05-class specification gap**: an unspecified reference scale that determines the
event count and therefore the verdict. It is recorded rather than resolved, because choosing
the period that makes L01 look schedulable would be choosing a parameter to get a result.
**A decision is required before L01, L06 or L08 can be scheduled.**

L02, L03, L04, L05, L07 and L09 do not depend on it — their thresholds are in ticks.

---

## Bugs found and fixed while building this

Recorded because three of them would have silently misrouted the scheduling decision rather
than failing visibly.

1. **`fill_fraction` measured after forward-filling** — every product read 100%. Now 83.16%
   MNQ / 64.16% MGC, which match F05's independently-computed figures exactly.
2. **The "≥ d ATR away for ≥ 15 min" precondition reset on any intermediate bar.** Price must
   pass through the middle zone to reach the level, so the condition fired 6 times in sixteen
   years. Qualification is now earned once and survives.
3. **VWAP and EMA were treated as static levels.** They are curves; the condition means the
   value *at that minute*. Sampling once understated firing by orders of magnitude.
4. **`numpy.datetime64` has no `isocalendar`** — crashed the first batch after ~15 minutes.
   Same coercion class as F04's `datetime.combine()`.
5. **`np.array([...tuples...], dtype=object)` builds a 2-D array**, so a tuple comparison
   raised on an ambiguous truth value.
6. **A stale `python -m` reference in a docstring** pointed at a module that never existed.
   Caught by `test_every_documented_entry_point_actually_runs`, which exists because the
   detectability gate once told people to run a command that did nothing.

Level counts cross-check against the catalog: **1,658 weekly and 380 monthly levels**, against
L09's stated ~830 weekly and ~190 monthly (×2 for high and low).

---

## Registry defects the existing tests caught

Fixed in the entries, not by loosening the tests:

- **L04, L06, L07, L08, L09 named no counterparty.** L07's and L08's are now named *and
  doubted in the same breath* — L07 states outright that it does not believe the claimed
  counterparty exists.
- **L05 cannot reach Stage 4** — it is MNQ-only by mechanism. Rather than padding the symbol
  list with an instrument the mechanism does not hold in (the F02 error), it declares
  `stage4_reachable: false` with a reason.

---

## State

- **370 tests with the data layer present; 300 from a clean clone** (plus 3 collection
  errors). Both figures are stated because for most of this project's life only the first was
  ever measured, and it was measured on the one machine where the untracked package existed.
  **The 70-test gap is the finding, not either number** — see `decisions.md` §36. Now closed:
  `.gitignore` had `data/` unanchored, which excluded `src/futuresres/data/` from every commit
  ever made. A clean clone will read 370 from the next commit onward.
- **N = 684, SR\* = 0.1357.** L07 Stage 1 spent 108 trials on 2026-09-09 (was 576 / 0.1335). The repo now has a private remote at
  `github.com/coltontr419-droid/futures-research` and all commits are pushed; it had none
  until 2026-09-09, while every other programme depended on its detection floors.
- `trials.jsonl` N = 576, chain verified. `measurements.jsonl` 120 records including F14's
  three control runs and the firing-rate measurements.
- No L-series trial spent. No Stage 1 run since F06.

## To resume

1. ~~`python -m futuresres.reporting.level_rates`~~ — done; read the three reports it wrote.
2. **Decide the `d ATR` reference period for L01/L06/L08.** Still outstanding and still not
   mine to make. See the section above: choosing the period that makes L01 look schedulable
   would be choosing a parameter to get a result.
3. ~~**Decide whether the placebo control should be redesigned.**~~ **SETTLED 2026-09-09.**
   The null is now **an arbitrary region matched on distance-from-price and checked on touch
   frequency**, not a real level displaced. Displacement was only ever a *method* for
   generating comparable regions, and its geometry forced a 1.4× distance mismatch at any
   scale. `decisions.md` §37 and `LEVEL_HYPOTHESES.md` carry the reasoning and the **cost**:
   the new control is **weaker**, because it no longer holds constant how price arrived.
   **L06 has no valid control under it and cannot get one** — `open_RTH` and `open_CME` sit
   exactly at the reference price, so there is no distance to match.
4. Then: projected N and SR\*, and the disproportionate-cost flags. Both are moot while the
   placebo is invalid, since no L-series result can be reported as real-minus-placebo.

**Item 3 is settled, so that bar is lifted for the level types that now match** — but read
§37 before running anything. A Stage 1 result on a level type that still fails matching would
measure exposure rather than reaction and would look like a finding. **L06 can never clear
that bar.**

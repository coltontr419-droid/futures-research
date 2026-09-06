# Checkpoint — 2026-09-02, mid L-series measurement

Written at a hard stop. Everything below is committed; nothing is in flight on disk.

---

## Where things stand

**The F-series is closed.** 14 registered, 576 trials, SR\* = 0.1334, 0 promoted. See
`reports/futures_conclusion.md` — it stands alone and is the document to read first.

**The L-series is registered but not measured.** Ten price-level hypotheses (L01–L10) are in
`hypotheses.yaml` under the Stage 0 schema. All are `schedulable: false` pending measured
firing rates. No Stage 1 has been run on any of them and no L-series trial has been spent.

---

## The one thing that must be re-run

```
python -m futuresres.reporting.level_rates          # ~20 min, both instruments
```

It writes `reports/level_rates.md`, `reports/placebo_match.md` and
`reports/disjointness.md`, **all at the end**, so an interrupted run leaves nothing behind.
It was interrupted twice: once by a crash (now fixed) and once by this stop. It had completed
MNQ entirely and MGC through L03.

Nothing depends on that run except the reporting — the code is committed and tested.

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

- 346 tests pass, working tree clean.
- `trials.jsonl` N = 576, chain verified. `measurements.jsonl` 120 records including F14's
  three control runs and the firing-rate measurements.
- No L-series trial spent. No Stage 1 run since F06.

## To resume

1. `python -m futuresres.reporting.level_rates`
2. Read the three reports it writes.
3. Decide the `d ATR` reference period for L01/L06/L08 — that decision is outstanding and is
   not mine to make.
4. Then: projected N and SR\*, and the disproportionate-cost flags.

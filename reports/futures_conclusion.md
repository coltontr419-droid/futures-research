# MNQ / MGC futures catalog — terminal report

**This closes the catalog as registered. It does not close the research.**

Fourteen hypotheses were registered against 16 years of 1-minute CME data (MNQ, spliced from
NQ before 2019; MGC). None was promoted. This document states what was tested, what could
not be, and what would have to change for the question to be worth reopening. It assumes no
familiarity with the code.

---

## 1. The headline

**Of 14 registered hypotheses, exactly one was tested at adequate power.**

That is F05, volatility compression/expansion: 45 informative cells across 11,000–18,600
events each, best cell at 0.05× its detection floor. It came back empty, and for F05 alone
"empty" means *the effect is absent* rather than *the effect is undetectable*.

Every other closure turned on something other than the market:

| | count | what closed them |
|---|---|---|
| tested at adequate power | **1** | F05 |
| tested, but no sample could carry a verdict | 2 | F02, F07 |
| tested only on a narrow or attenuated route | 3 | F03, F04, F06 |
| never run — arithmetic or premise closed them first | 4 | F01, F08, F10, F11 |
| excluded before registration | 2 | F12, F13 |
| never scheduled | 2 | F09 (closed on both routes), F14 (the control) |

**What that says about what is establishable on 1-minute CME data at retail scale.** The
binding constraint was not the absence of signal. It was **event scarcity** — most of these
mechanisms fire once per session, and sixteen years of once-per-session conditions yields
about 4,000 observations against a detection floor that needs 19,722 on MNQ. A hypothesis
that fires once a day cannot be tested to this standard on this much data, no matter how
good the idea is or how carefully the pipeline is built. That is a property of the sample,
not of the strategies.

---

## 2. Every hypothesis

| id | name | verdict | resolved by | trials |
|---|---|---|---|---|
| F01 | market_intraday_momentum | `blocked_insufficient_events` | arithmetic, before running: 4,125 events vs 19,722, and its two entry times share a 15:55 exit so pooling adds nothing | 0 |
| F02 | order_imbalance_conditional_overnight_reversal | `stage1_uninformative` | sample — all 144 cells below the swept range; a *declared* firing rate was wrong by 40× | 144 |
| F03 | half_hour_periodicity | `retired` | evidence, on its **aggregate** route only (53,625 independent events); per-cell was uninformative | 234 |
| F04 | lbma_auction_flow | `retired` | evidence, narrowed to MGC 120m alone; best cell 0.09× floor | 36 |
| **F05** | **volatility_compression_expansion** | **`retired`** | **evidence, at adequate power — the only one** | **54** |
| F06 | cash_open_drive_continuation | `retired` | evidence, but only on MGC where the mechanism is attenuated; MNQ never tested | 36 |
| F07 | gold_session_specific_momentum | `stage1_uninformative` | sample — per-cell *and* aggregate below range; its 12 slots predict one target so pooling is impossible | 72 |
| F08 | cross_asset_risk_regime | `retired` | **premise** — the mechanism identifies a divergence but names no mispriced leg | 0 |
| F09 | settlement_anchored_flow | `untested` | closed on both routes at 2,365–3,406 events; also overlaps F01's window | 0 |
| F10 | rsi_mean_reversion_control | `retired` | **power** — a control that could never resolve (1,585–5,594 vs 19,722) | 0 |
| F11 | ma_crossover_control | `retired` | **premise** — a momentum rule cannot control a catalog containing a momentum hypothesis | 0 |
| F12 | pre_fomc_announcement_drift | `excluded` | ~128 events in 16 years; and a 24h hold crosses the 17:00 hard exit | 0 |
| F13 | unconditional_overnight_drift | `excluded` | measured as decayed by its own authors; the conditional form is F02 | 0 |
| F14 | timestamp_hash_control | control, **passed ×3** | mechanism-free by construction; does not spend trials | 0 |

**N = 576. SR\* = 0.1334.** SR\* is the Sharpe the best of 576 random trials would reach by
chance; any candidate must clear it before its Sharpe means anything.

Note where the trials went: **F02 and F07 together consumed 216 of 576 — 38% — and neither
could produce evidence.** That is the cost of a gate that was wrong, quantified.

---

## 3. The measured constraints

Everything below was measured on this data, not assumed.

### Detection floor — the smallest effect recoverable at all

| instrument | horizon | independent observations | smallest sample that resolved a floor | best floor |
|---|---|---|---|---|
| MNQ | 1m | 2,534,668 | 5,000 | 0.045σ |
| MNQ | 60m | 39,444 | **19,722** | 0.084σ |
| MNQ | 180m | 11,768 | 5,884 | 0.30σ |
| MGC | 1m | 3,102,696 | 5,000 | 0.045σ |
| MGC | 60m | 31,591 | 5,620 | 0.159σ |
| MGC | 180m | 8,190 | **2,862** | 0.30σ |

In basis points that is roughly **2.6 bps (MNQ 60m)**, **4.2 (MGC 60m)**, **14–16 (both at
120–180m)**.

### Cost floor — the smallest effect worth having

**MNQ 0.48 bps, MGC 0.65 bps** round trip, commission plus estimated spread.

### Firing-rate ceiling — the constraint that actually bound

A once-per-session condition over 16 years reaches **~4,000 events**. Threshold-gated
conditions reach far less: F02 fires on 6–23% of sessions and then splits by regime, landing
at **106–707 events per cell**.

### Where detection binds rather than economics

This is the crossover worth stating plainly, because it inverts with horizon:

- **At 1 minute**, the detection floor (~0.045σ ≈ 0.18 bps) sits *below* the cost floor
  (0.48–0.65 bps). Economics binds: you can detect effects too small to trade.
- **At 60 minutes and beyond**, the detection floor (2.6–16 bps) sits *far above* the cost
  floor. **Detection binds.** Anything you could trade profitably at these horizons is
  smaller than what this much data can distinguish from zero.

Every hypothesis in this catalog operates at 30 minutes or longer. **All of them live on the
side of the crossover where the limit is statistical, not economic** — which is why "no edge
found" is so often the wrong reading of these results, and "could not have found one" is the
right one.

---

## 4. Pipeline validation

The null results are only worth as much as the evidence that the pipeline could have found
something. That evidence:

**Synthetic nulls.** GARCH(1,1) Student-t generators fitted to each instrument's *measured*
kurtosis (MNQ 115.1, MGC 226.5), plus a random walk. **0 of 24 promoted on every null arm**,
under the futures-calibrated bootstrap α\* = 0.0409.

**Positive control.** A deliberately modest injected drift (0.3× volatility). **24 of 24
promoted.** The harness finds an edge that is there.

**F14, the real-data control.** A direction that is the low bit of SHA-256 of the bar's
timestamp — a deterministic function of the clock that never touches price, aperiodic, and
unable to align with time-of-day. Run three times, most recently under current settings:
**0 nominal separations, 0 BH survivors, long share 0.497** on ~48,000–52,000 events per
cell. The harness declines to promote a mechanism-free signal on *real* futures data, with
real gaps, real volatility clustering and real session boundaries.

> **F14's scope limit, which is part of the claim.** It fires ~13 times a session and speaks
> to ~50,000-event samples. **It says nothing about ~4,000-event samples**, and no control
> can be built at that regime on this data: measured candidates at the once-per-session
> regime resolved in only 2 of 12 combinations, both on the thinnest instrument at the
> longest hold.

**Lookahead re-derivation.** The corrected Stage 1 estimator is exactly drift-invariant, to
1e-15, verified by a test that also pins the old biased behaviour so the bug cannot silently
return. A prior version oriented off-event bars long, producing a false-positive rate of
0.180 against a nominal 0.05.

**Reproducibility.** F03 was re-run months after its original execution, in a different
process, to recover cells that had never been persisted. All 117 MNQ cells reproduced
**exactly**: identical event counts, identical mean basis points to 1e-9, identical p-values
to **1e-12**. The SHA-256 cell seeding holds across processes and across time.

**Trial accounting.** Every trial is in a hash-chained append-only log whose chain verifies.
342 records predating the logging wiring are marked `reconstructed` and are distinguishable
from the 234 written natively.

---

## 5. What the catalog could not test, and why

**The once-per-session regime has no real-data control and cannot get one.** F01, F02, F04,
F06 and F09 all fire about once a day. F14 validates the harness at ~50,000 events; these
hypotheses hold ~4,000. **Their verdicts carry the synthetic-GARCH assurance and nothing
more.** That is a genuine gap, not a formality: synthetic nulls test the harness against
idealised noise, while a real-data control tests it against actual microstructure.

**Three mechanisms were never tested on the instrument they describe.**

- **F02's** counterparty is the NYSE closing auction. Gold has none — 72 of its 144 trials
  went to an instrument where the hypothesis is undefined.
- **F06's** mechanism is the *equity* cash open. Its only open routes were MGC, so the
  registered claim has never been tested on MNQ at all.
- **F01** was never run anywhere.

**Two conditions could not be tested as written and were corrected first.** F05's trigger
measured against the compressed window's own volatility — compression shrank the trigger
exactly when the filter fired, so it broke on 79–91% of armings and tested nothing. F06's
`vol_filter` named neither a quantity nor a lookback. Both corrections were derived from the
mechanism and recorded *before* the runs. **The F05 correction is what made its null the
catalog's only meaningful one.**

**Two conditions remain untestable as written.** F08's direction rule ("fade the lower
volume-weighted move") is undefined and appears nowhere in its mechanism. F01's `vol_filter`
has the same gap F06's had and was never settled.

**The gate itself was wrong four times**, in four different ways, costing 144 trials on F02
before the pattern was visible. That history is in **`reports/gate_history.md`** and is not
repeated here; it is the strongest single argument in this repository for measuring before
scheduling, and it should be read alongside this document.

---

## 6. What would have to change

This catalog is closed as registered. Reopening it usefully would require at least one of:

**More events per hypothesis — by far the most important.** Not more history: the
once-per-session ceiling is ~4,000 events over 16 years, and reaching MNQ's 19,722 would take
roughly eighty years. The fix is conditions that fire *more often* — several times a session,
as F03's slot scan and F14 do — or accepting that once-daily mechanisms are not testable to
this standard on this data.

**A cheaper detection floor.** The floor scales roughly as n^−0.6 to n^−0.7 here, measured,
against the √n a naive estimate would predict. Getting the 60-minute floor from 2.6 bps to
1 bps on MNQ would need roughly an order of magnitude more independent observations.

**Instruments where the mechanisms actually live.** Several hypotheses are equity-index
claims that could only be tested on gold. ES or NQ full-size contracts carry the same
mechanisms with more liquidity, and MNQ's own coverage (83–99% depending on window) is far
better than MGC's (46–71%). The catalog's habit of registering both instruments by default
was itself a defect, now blocked at Stage 0.

**Conditions specified tightly enough to test.** Three of fourteen had terms that changed the
event count and therefore the verdict, and one had a direction rule invented at the condition
stage to fill a gap the mechanism left. A condition that needs a decision after registration
is not yet a hypothesis.

**A control that reaches the regime being tested.** Until one exists for once-per-session
conditions, every verdict in that regime rests on synthetic noise alone.

---

## 7. What this closes

**The catalog as registered is closed: 14 hypotheses, 576 trials, 0 promoted.**

The result is not "there is no edge in MNQ and MGC." It is narrower and more useful:

> **Of fourteen pre-registered mechanisms, one was tested at adequate power on this data and
> found absent. The other thirteen were closed by event scarcity, registration defects,
> control design, or exclusion — none of which is a statement about the market.**

The pipeline works: it finds an injected edge every time, declines noise on both synthetic
and real data, reproduces exactly across processes and months, and accounts for every trial
it spends. What it did not have was hypotheses that fire often enough to be tested with it.

**That is a finding about the research design, not about the markets, and it is the honest
one.**

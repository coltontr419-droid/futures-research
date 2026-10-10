# Checkpoint — 2026-09-02, updated 2026-09-09

Written at a hard stop on 2026-09-02 and **updated 2026-09-09, when it was found to be
issuing an instruction that had already been carried out.** The batch it says must be re-run
completed on 2026-09-05 and was committed as `fb07e80`. Anyone who followed this file between
those dates would have re-run twenty minutes of work for nothing.

Everything below is committed; nothing is in flight on disk.

---

## THE STOPPING RULE — added 2026-09-29, before any seventh series is designed

**This section is a gate on designing, not a summary.** Two conditions. A candidate series must
state where it sits against both, in its own registration, before a trial is spent. Every number
below was computed on 2026-09-29 from this repository and `r-series-research`; the derivations and
the open decisions are in `decisions.md` §61.

---

### 1. Success condition — REVISED 2026-09-29 under two rulings (§62)

**Two rulings supersede the first version of this section.** (a) The marking convention is
**intraday**: the firm evaluates its trailing floor continuously, and the condition is stated as
losing $2,000 from any point, so daily marks measure something nobody enforces. (b) The bar is **two
objects, not one**, and the stated condition describes only the second.

**The account size is derived, not assumed:** $2,000 is 4% of $50,000 and 4% is the account's own
floor, so the condition is a 4% peak-to-trough excursion on $50,000. The rule is
**floor = min(peak − $2,000, $50,000)** — trailing pre-lock, fixed at breakeven once the peak reaches
$52,000.

---

#### PHASE 1, pre-lock: a RUIN PROBABILITY. A rate is not computable here.

Before the lock the floor *is* peak − $2,000, so **the first 4% excursion is terminal** — it can
happen at most once, and a frequency has no meaning against a single absorbing barrier.

| Sharpe | P(reach lock) | **P(ruin)** |
|---|---|---|
| 0 (no edge) | 0.384 | **0.616** |
| 0.59 | 0.425 | 0.575 |
| 0.95 | 0.482 | 0.518 |
| 1.31 | 0.564 | **0.436** |
| 2.00 | 0.766 | 0.234 |
| 3.00 | 0.965 | 0.035 |

**Even at Sharpe 1.31 the account fails to survive phase 1 more than two times in five.** The
zero-edge row validates the simulator against theory: it converges to exp(−1) = 0.3679 as marking
tightens (0.4068 daily → 0.3843 at 30-min → 0.3720 at 52,416 marks), which is the figure already in
`programme_conclusion.md` §4.

#### PHASE 2, post-lock: an EVENT RATE — and it must be conditioned on survival

**"A few times per year" was stated against a regime the account does not start in.** It applies
only here, and only once cushion exists: at the lock point the floor sits **exactly one $2,000
drawdown below equity**, so early in phase 2 "experiencing a $2k drawdown" *is* hitting the floor.

**OPERATIVE BAR** — post-lock, intraday marks (3,276/yr), start $52,000, floor $50,000, events counted
among **survivors**. Sharpe is a floor, volatility a ceiling:

| annual return | ≤3 events/yr | max vol | P(floor), yr 1 | ≤5 events/yr | max vol | P(floor), yr 1 |
|---|---|---|---|---|---|---|
| **10%** | **SR ≥ 0.80** | 12.4% | 52.9% | SR ≥ 0.55 | 18.1% | 69.9% |
| **15%** | **SR ≥ 1.21** | 12.4% | 42.0% | SR ≥ 0.85 | 17.7% | 62.5% |
| **20%** | **SR ≥ 1.61** | 12.4% | 33.4% | SR ≥ 1.15 | 17.4% | 55.3% |

**The event rate alone is not a sufficient bar**, because every cell that satisfies it still ruins
often. Sharpe required to hold first-year P(floor) down, post-lock:

| annual return | P ≤ 20% | P ≤ 10% | P ≤ 5% |
|---|---|---|---|
| 10% | 1.36 | 1.66 | 1.90 |
| 15% | **1.71** | **2.06** | 2.34 |
| 20% | 1.99 | 2.39 | 2.72 |

**A registration is checked against the binding one, which is whichever is higher** — for 15% at
≤3 events with P(floor) ≤ 10%, that is **SR ≥ 2.06**, not 1.21.

#### SUPERSEDED — the daily-mark table, kept for the record

Not deleted, because it is what the first version of this rule asserted. It is **too lenient**: daily
marks miss excursions the firm would enforce.

| annual return | ≤3 events/yr | ≤5 events/yr | ≤10 events/yr |
|---|---|---|---|
| 10% | SR ≥ 0.59 (vol ≤ 17.00%) | SR ≥ 0.26 (vol ≤ 38.23%) | infeasible |
| 15% | SR ≥ 0.95 (vol ≤ 15.82%) | SR ≥ 0.44 (vol ≤ 34.24%) | infeasible |
| 20% | SR ≥ 1.31 (vol ≤ 15.21%) | SR ≥ 0.66 (vol ≤ 30.51%) | infeasible |

The bar **converges** as marking tightens, so the intraday figure is a real limit, not grid-dependent
(R = 15%, ≤3 events, single-phase): 0.95 daily → 1.13 hourly → 1.17 at 30-min → 1.19 at 15-min →
1.20 at 7.5-min. The ten-events column stays infeasible at daily marks for the reason recorded in
§61: distinct episodes are bounded by new equity highs, ~0.5·√marks, giving a ceiling of 8.76/yr.

---

### 1b. The first version of this section, for reference

**SUPERSEDED 2026-09-29 — do not register against this.** Kept because it is what the rule asserted
on 2026-09-13, and because deleting it would hide that the bar moved. Its two "OPEN DECISION" items
are both now **ruled on** (§62): the marking convention is intraday, and the bar is two objects. Its
single-table framing measures a rate in a phase where the event is terminal, so it is too lenient in
phase 1 and unconditioned in phase 2.


The stated goal — *large profits while experiencing a trailing $2,000 drawdown no more than a few
times per year* — is converted here so a result can be **checked** against it rather than judged.

**The account follows from the number.** $2,000 is 4% of $50,000, and 4% is the account's own
trailing-drawdown floor (§1 of `programme_conclusion.md`), so the success condition is a **4%
peak-to-trough excursion** on a $50,000 account. Annual profit at 10 / 15 / 20% is
$5,000 / $7,500 / $10,000.

**Required Sharpe is a floor, and permitted volatility is a ceiling.** Tolerating more drawdown
events lowers the bar; the event count falls monotonically in Sharpe (verified on a grid from
Sharpe 0.05 to 6.0, all three return targets).

| annual return | ≤3 events/yr | ≤5 events/yr | ≤10 events/yr |
|---|---|---|---|
| **10%** | **SR ≥ 0.59** (vol ≤ 17.00%, $8,500) | SR ≥ 0.26 (vol ≤ 38.23%, $19,114) | **infeasible** |
| **15%** | **SR ≥ 0.95** (vol ≤ 15.82%, $7,908) | SR ≥ 0.44 (vol ≤ 34.24%, $17,119) | **infeasible** |
| **20%** | **SR ≥ 1.31** (vol ≤ 15.21%, $7,605) | SR ≥ 0.66 (vol ≤ 30.51%, $15,255) | **infeasible** |

Model: iid normal daily P&L, arithmetic dollars on a fixed $50,000 base, 252 marks/year, 20,000
paths. An event is counted once when an excursion first reaches $2,000 deep; a **new equity high is
required before another can be counted**, so these are distinct episodes, not days underwater.
Using the programme's own ~245 usable sessions instead of 252 moves the required Sharpe by 0.006 —
immaterial.

**Ten events per year is infeasible at daily marks, and that is a finding about the metric, not a
missing row.** Distinct episodes are bounded by the number of new equity highs, which for a
low-Sharpe path grows like √(marks). Measured ceilings as Sharpe → 0, at R = 15%:

| marking | marks/yr | max attainable events/yr |
|---|---|---|
| daily | 252 | **8.76** |
| hourly | 1,638 | 20.81 |
| half-hourly | 3,276 | 28.52 |

≈ 0.5·√marks. So **the marking convention is load-bearing and is an open decision** (§61): finer
marking detects more excursions, so it *raises* the required Sharpe for the same event budget.
Measured at R = 15%: ≤3 events needs SR ≥ 0.95 at daily marks but **SR ≥ 1.14 hourly**; ≤5 needs
0.44 daily and **0.66 hourly**; ≤10 is infeasible daily and **SR ≥ 0.23 hourly**.

### Where the programme's measured effects sit against this bar

**Not close, and not by a margin that precision could close.** The bar is a Sharpe floor; every
measured effect has a non-positive net edge, and a non-positive edge is Sharpe ≤ 0 at any
volatility.

| | gross bps/event | net of 0.48 cost |
|---|---|---|
| R01 (largest effect measured anywhere) | +0.452 | **−0.028** |
| L12 | +0.306 | −0.174 |
| P03 real leg | +0.200 | −0.280 |
| L07 | negative in 108/108 cells, 1.8–10.3× cost | wrong sign |

Turned the other way — what one MNQ contract ($48,000 notional) would have to earn **gross** per
trade to produce the target, against R01's +0.452:

| trades/yr | gross @10% | gross @15% | gross @20% | ×R01 @15% |
|---|---|---|---|---|
| 245 | 4.732 | 6.858 | 8.983 | **15.2×** |
| 1,000 | 1.522 | 2.042 | 2.563 | 4.5× |
| 5,000 | 0.688 | 0.792 | 0.897 | 1.8× |
| 25,000 | 0.522 | 0.542 | 0.563 | 1.2× |

**The ratio never reaches 1 at any frequency.** Its floor as trades → ∞ is **1.062×**, because the
0.48 bps cost floor alone exceeds the 0.452 bps best measured effect. Raising trade count cannot
close the gap; it is closed only by a larger effect or a lower cost.

For scale: **SR\* = 0.1368** at N = 760 is the bar a Sharpe must clear merely to *mean* anything.
The lowest success bar in the table (SR ≥ 0.26) is **1.9× SR\***; the 15%/≤3 bar is **6.9×**.

---

### 2. Termination condition: the next series stops when its expected value falls below its cost

**Base rate, measured, both logs:**

| | count |
|---|---|
| registered hypotheses | **35** |
| spent ≥1 trial (13 in `futures-research` + R01, R02) | **15** |
| promoted | **0** |

Per-registration promotion probability, 0 successes in 35: exact 95% one-sided upper **0.0820**,
rule of three 0.0857, Laplace 0.0270, Jeffreys 0.0139. Per series, 0 in 6: exact 95% upper
**0.3930**, Laplace 0.1250, Jeffreys 0.0714.

**Implied prior that a seventh series promotes anything**, at the measured mean of 5.83
registrations per series:

| per-hypothesis prior | P(7th series promotes ≥1) | promotion must be worth |
|---|---|---|
| Jeffreys 0.0139 | **7.8%** | **12.8× one series' cost** |
| Laplace 0.0270 | 14.8% | 6.8× |
| rule of three 0.0857 | 40.7% | 2.5× |

Read the upper end with the caveat it deserves: the rule-of-three figure is a **95% upper bound on
what the data cannot exclude**, not an estimate. And this base rate is if anything **optimistic**
for a seventh series, because the six spent the best ideas first — the strongest unexplored one on
record, R04, is closed by account permission rather than by evidence (§10 of
`programme_conclusion.md`).

**Cost of one series, in the three currencies that matter:**

| currency | measured |
|---|---|
| **trials** | mean **128.3**, median **6.5** (F 576, L 180, R 10, N 3, P 1, Q 0) — wildly skewed |
| **SR\* imposed on all future work** | +0.0002 at 10 trials, **+0.0019 at the mean 128**, +0.0026 at 180, +0.0069 at 576 |
| **calendar** | 6 series in **16 days** of repository history (2026-08-28 → 2026-09-13), ≈2.7 days/series |

The SR\* cost is small per series and **permanent and shared**: it is paid by every future
hypothesis, including the one that would have promoted. That is the asymmetry the trial log exists
to make visible.

---

### 3. "We cannot think of new hypotheses" is NOT a valid termination condition

Stated plainly because it is the rule a closed programme drifts toward.

Hypothesis generation is **unbounded and cheap** — this programme drafted 66 candidates in 16 days,
and could draft 66 more in another 16 without learning anything. A termination condition that
depends on running out of ideas therefore **can never bind**, and a rule that cannot bind is not a
rule.

The consequence is specific, not rhetorical. If the programme stops only when ideas run out, then
whatever eventually survives is selected by **persistence** — by how long the search continued —
rather than by evidence. That is precisely what N, SR\* and the trial log exist to prevent, and it
is the failure the terminal report names in its own last line (§10: *"a seventh series would be
widening the search until something appears, which is exactly what the trial log exists to
prevent"*).

**Valid termination conditions are about cost and evidence:** the expected value of the next series
below its cost (§2 above), or one of the four binding constraints moving — information, permission,
cost, time (§10 of `programme_conclusion.md`). **Not** the exhaustion of imagination.

---

## READ FIRST — `reports/STAGES.md`

**The programme uses one stage numbering, S1-S8, adopted 2026-09-12.** Every document, run
report and `decisions.md` entry names the stage it concerns.

    S1  Mechanism          who is losing money to you, and why they keep doing it
    S2  Pre-registration   every parameter fixed before testing
    S3  Firing rate        measured on real data, never declared
    S4  Detection floor    smallest detectable edge vs effective n
    S5  Condition validity negative control, fault injection, firing-minute variance
    S6  Placebo            real vs distance-matched arbitrary level
    S7  Multiplicity       trial log, N, SR*, BH correction
    S8  Out-of-sample      era split, other instruments, cost floor

Old language maps as: **Stage 0 ~ S1-S2, Stage 1 ~ S6-S8.** Historical `decisions.md` entries
are NOT rewritten - the mapping lives in `STAGES.md` instead, because rewriting them would
destroy the record of what was known when.

**S5 IS A GATE AND IT IS NEW.** It had no name before 2026-09-12, and that is exactly how
L11's placebo came to be measured against a condition that fired unconditionally: the S6
numbers looked clean and meant nothing. No condition proceeds to S6 until it passes S5.


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

## Machine limitations — DOCUMENTED, not folklore

Read this before planning a run. This laptop has **2.7 GB RAM, ~1.1 GB typically available**,
and the programme has been OOM-killed on it **seven times**. Six were fixed (decisions.md 41,
45); one is open.

### `f01_rates` is OOM-killed and is NOT fixed

    python -m futuresres.reporting.measured_rates        # DIES at ~1,064 MB, during F01

**A full `measured_rates` run cannot complete on this laptop.** It is killed inside
`f01_rates`, the first hypothesis measured. The frames are not the cause - both products
together are ~200 MB of data and ~460 MB peak - the F01 computation itself is.

**Use the targeted refresh instead:**

    python -m futuresres.reporting.measured_rates --only L      # works, ~1 min
    python -m futuresres.reporting.measured_rates --only L12,L04

A partial refresh **merges** into the cached file and prints what it carried forward
(`873 refreshed, 248 carried forward`). Records it does not touch keep whatever measurement
they last had. `--check` still compares a FULL fresh measurement, so it cannot run here
either - which means **cache drift cannot be verified on this machine.**

**A full run requires the Windows PC or a machine with more memory.** That is the fix, not a
code change: F01's measurement is legitimate work that needs headroom.

### The test suite no longer fits in one process either

383 tests pass across 16 files **run individually**. Run together they accumulate past ~900 MB
and the run is killed. No single test is heavy; the total is.

    for f in tests/test_*.py; do .venv/bin/python -m pytest -q "$f"; done

### Everything else runs here, after the fixes

`level_rates` (~2 h, peaks ~440 MB), `roll`, `splice`, the grid loader (626 MB), and every
Stage 1 runner. Six memory fixes got them there; see decisions.md 41 and 45 for what each one
was, because the same patterns will recur: eager frames, global sorts that are avoidable
rather than expensive, Python containers where a packed array belongs, and reading columns
nothing uses.

### Tools

    ./progress.sh        what is running: pid, RSS, elapsed, memory, logs, parquets, OOM count
    ./progress.sh -w     the same, refreshing every 30s
    ./done.sh            BLOCKS until the running job exits, then prints a pasteable report

## State

### CURRENT, 2026-09-13 — read this, not the historical bullets beneath it

**THE PROGRAMME IS CLOSED, 2026-09-13.** Read `reports/programme_conclusion.md` first; it stands
alone. Six series registered plus a seventh and an eighth drafted, and two single hypotheses (U01, V01), a ninth series designed (W) with one registration (W04, run and retired), and a tenth (X) closed at X02, 96 candidates, 38 registered, 771 trials across
two logs (futures-research 761, SR\* 0.1368; r-series 10), nothing promoted. The Q-series closed
without registration (§60). Two standards adopted as gates for any future entry: the post-2021 split
decides (S8), and a null is reportable only from a pipeline shown to recover the effect size sought at
the run's n (§60). **Nothing is scheduled. Nothing is pending.**

**S-SERIES, 2026-10-02 — DESIGNED, NOT REGISTERED (§63).** A seventh series: nine retail indicators
(fair value gaps, RSI, VWAP, EMAs, volume profile, Bollinger, MACD, stochastic, floor pivots) against
a matched arbitrary reference, at 5m/15m/30m/1h/4h, each indicator its own hypothesis.
`reports/S_SERIES_DESIGN.md`; arithmetic in `reports/s_series_s2.json`. **`hypotheses.yaml` is
untouched, no trial is spent, S5/S6/S7 were not run, N stays 760 and SR\* stays 0.1368.** It is
counted in the ledger as the seventh series at 9 drafted / 0 registered / 0 trials, the same way Q is
counted at 12/0/0.

Stated against this file's own stopping rule, which is what it asks a candidate series to do:

- **Five of nine entries are already registered under another letter** — L07 (108 trials spent), F10,
  L01, L08/F11, L11. Three have measured firing rates on disk.
- **Within-entry cost:** 30 cells each, BH rank-1 at FDR 0.05 (z = 3.1440), post-2021 decisive, which
  multiplies every bar by 1.72×. Best-cell bars run 2.91 to 33.68 bps; **four of nine — S03, S04,
  S05, S09 — exceed 5.79 bps, the largest effect this programme has ever measured.**
- **Across-programme cost:** 270 trials, N 760 → **1,030**, SR\* 0.1368 → **0.1406** — a 36% increase
  in N and about twice the SR\* one series costs at the measured mean of 128 trials.
- **The two bars meet badly.** SR\* at N = 1,030, expressed as the per-event effect that reaches it,
  is **9.10 bps at H=180m and 3.71 bps at H=30m**. Four entries (S02 RSI, S06 Bollinger, S07 MACD,
  S08 stochastic) clear their own BH bar in their 5m cells at 1.19–1.88 bps and **every one sits below
  the prevailing SR\* by about 2×**. The only entry whose magnitude reaches SR\* is the fair-value-gap
  repeat, whose magnitude is **measured and negative**.
- **Nothing in the series has a route to the operative bar** of §62 (SR ≥ 2.06 at 15% / ≤3 events /
  P(floor) ≤ 10%, 15.1× SR\*).

**If it is taken further, the first two steps spend no trials:** the five collinearity measurements
(S02↔S08, S04↔S06, S04↔S07, S03↔S05, S09↔L03 — the Q01/Q02 precedent suggests four entries may be
two), and firing rates for S05–S09, none of which has a firing rate of its own at any timeframe.

**T-SERIES, 2026-10-02 — CLOSED (§65, §66). T01 AND T05 MEASURED, T02–T07 CLOSED AT S2, NOT REGISTERED.** An
eighth series on the statistical character of the price path. `T_SERIES_CANDIDATES.md` (draft with
[§65] corrections). **No trial spent; N 760, SR\* 0.1368; `hypotheses.yaml` untouched.** Counted in
the ledger at 7 drafted / 0 registered.

- **T01 (volume clock) reopens nothing.** There are no dead bars to remove; effective n *falls*
  (0.48× MNQ, 0.41× MGC); kurtosis falls on MNQ at matched n but MGC's two strongest cells fail the
  construction's own pre-stated check and are withdrawn; the floor blocking L01/L08/F01 is a power
  floor kurtosis does not move. F01's "4,125" is the pre-§22 ceiling; measured best cell 3,523.
- **T05 (sign split) changes no closed conclusion.** L07 (108 cells), P03 and R01 reproduced exactly
  from the record, then split: every one carries its effect on both sides. §60 injection passed for
  all three (P03 narrowly, power 0.82).
- **T02–T07 fail the S2 filter.** T02's condition holds in 57–94% of windows and J is not
  scale-free (price discreteness); T04 barely fires; T03 clears its own BH bar and sits below SR\*;
  T06 is F05 restated; T07 has no primary.
- **Decided (§66):** the discreteness finding is promoted as **finding 11** of the terminal report — a
  new finding, not an amendment to finding 6, because finding 6 would have called J safe.
- **The statistical-character axis is closed** alongside level, state and time: the fourth and last
  structural dimension reachable from data on disk. What remains needs a data purchase or a
  different account structure.
- **Working rule (§65 addendum):** design and measurement tasks in this programme do not route to
  Sonnet, even when they look routine — the T-series' fabricated figures came from a Sonnet session.
- `tests/test_roll.py` OOM-killed after 12 of 18 tests on 2026-10-02 — unverified, untouched code.

**U01, 2026-10-02 — REGISTERED, BLOCKED ON EVENT COUNT (§67).** A single hypothesis, not a series:
"large opening gaps (≥ 0.4%) fill same-session only ~8% of the time", from an unsourced clip, no
prior weight. Read as the CME reopen (daily 18:00 ET, weekly Sunday). **104 index and 46 MGC gaps in
sixteen years (42 / 28 since 2021) against floors of 5,884 / 2,862 — blocked like F01. No trial
spent.** The fill curve declines smoothly with no break at 0.4% and tracks a driftless random walk;
gaps that size fill 46–100% here (46–81% where n exceeds three), not 8%. Control decided for the record (state_control strict,
volatility-matched); S5–S7 not run. Registrations now 36.
Rulings (§68): the CME reopen definition is settled in the entry (a cash-open version would be a
separate registration); the daily-reopen fill excess is recorded as a measured property, at its
corrected scale of 5–30 bps, tradeability not established; the early-NQ session-length defect
(a source-data truncation, verified in the vendor CSV) is in the terminal report's error table; the
8-hour hold check stays as it is.

**V01, 2026-10-03 — REGISTERED POST-HOC, BLOCKED AT ITS CEILING (§69).** Reopen displacement
reversion: the first print after the maintenance break, set against thin depth, corrects when depth
arrives (closest relative L02's absorption arm, not L03). Written after U01's curve showed the effect,
and marked so. **Every valid daily reopen firing would give 2,469 index / 1,926 MGC events (1,015 / 901
since 2021), below every floor — so no threshold was chosen and no forward return computed** (a
real-minus-control return is the S6/S7 comparison, i.e. a trial). No valid strict-mode control without
a threshold. Registrations now 37. **Open, for the user:** whether the forward-return economics is
still wanted as a logged trial; it cannot change the verdict.

**COST-FLOOR AUDIT, 2026-10-03 (§70) — SCOPED, NOT YET QUOTED.** The floor is ~80% commission; quotes
can only confirm or raise the spread part, so the convergence result inverts only via commission (below
~$1.69 per MNQ round trip vs the assumed $1.82) or passive fills — neither measured by mbp-1. The
30-session sample is pre-registered (`reports/spread_sample_sessions.json`) and the quote script is
committed (`reporting/cost_floor_quote.py`). **Blocked on a Databento API key** — the `.env` holds FTP
credentials only. **V01 corrected:** L02 tested only the 09:30 cash open on MGC; no entry ever tested the
CME reopen, so V01's mechanism had no prior test.

**Premise corrected (§71):** quotes cannot lower the floor — the spread term already assumes the
one-tick minimum. **The audit that matters is a fee-schedule check of all-in commission against the
assumed $1.82 MNQ round trip** (the flip point is ~$1.69); `cost_floor_quote.py` stays ready but audits
the smaller term. Passive fills are the one route needing a measurement quotes cannot make (resting
orders, measured fill probability). **Finding 12** promoted: cite prior evidence by what it tested,
not by counterparty.

**W-SERIES, 2026-10-03 — DESIGNED, NOT REGISTERED (§72).** Daily horizons via chained 18:00-to-16:55
session holds: the record filed them as forbidden; measured, the chain keeps 98–99% of the day's
variance and cost stops binding. Binding instead: the multiple-testing bar for daily strategies (0.96
full / 1.39 post-2021, or 2.17 under the single SR\*) and, under §62's objective, the drawdown risk
budget (not contract count — a prop account allows 20–30 micros). Best candidate W04 (trend + carry,
prior 0.77–1.27) straddles the full-sample bar. **Open, for the user:** confirm the overnight-inside-the-
session hold with the firm; choose §62's bar or prop-evaluation EV (and supply the eval terms); rule on
the SR\* convention; buy ohlcv-1d; then W04 as one trial.

**W04 REGISTERED, 2026-10-03 (§73). No trial spent; N 760.** The firm confirmed the hold; objective =
prop-evaluation EV ($80 fee, +$3k target, $2k buffer, 90/10, no resets, $1k daily limit, 30 micros); SR\*
unit-consistent, decided post-2021 at ≈1.39. Daily data on disk (ohlcv-1d, to 2026-09-11), **not yet
read**; entry amended before reading it (one-session delay, same-bar carry). EV computed
(`reports/w_prop_ev.md`): optimum ~$150–250/day of σ, ≈+$2,300 per evaluation at Sharpe 1.39; positive
at zero edge at some sizes, so not evidence; one MNQ ($847/day) puts the integer book above the optimum,
where a HARD daily limit makes EV negative. **Alignment measured (§74):** UTC-day bars track the
held sessions at 0.97 daily, 0.98–0.99 over 21 days; ohlcv-1d is adequate. **Next:** the W04 runner
with outcome injection at 1.39 (drop Sunday bars; resolve the vendor's one-digit contract years). **Daily loss limit ruled SOFT (§75)** — flat for the day, not a breach.

**W04 RUN AND RETIRED, 2026-10-03 (§76), trial t00767; N 761.** Post-2021 net Sharpe −0.42 vs bar 1.31
(SR\* at the file's own T = 1,481); gross 0.31, so not even at zero cost. Rotation null: 13.4% at or
above. Injection recovered (1.29 → 1.32, power 51% at the bar). **Premise corrected:** a daily round
trip is ~5% of a day's SD on M6E and the micro 10Y (0.5% on MNQ); equal-risk sizing loads them; drag
0.73 Sharpe. Integer-book economics row defective (over the 30-micro cap 61% of days) and moot.
**Nothing is scheduled.**

**X-SERIES, 2026-10-03 — CLOSED AT X02, NOTHING REGISTERED (§77).** Overlap: X03/X04/X07 repeat W
work (W04's sleeves); X05, X06 new. X01: only MNQ cost-eligible at full time in market; MES, MGC, MCL
marginal; M6E, micro 10Y, MHG excluded (fees partly unverified; broker charge assumed). X02: post-2021
pooled effective n 255 (185 on cost survivors) vs SR\* floor 404 at 0.2 monthly Sharpe. X07 not
blocked on data. **Nothing is scheduled.**

**BLOCKED-ENTRY RECONCILIATION, 2026-10-09 (§78) — no gap narrowed.** Two superseded numbers corrected,
both widening the gap: F01 (4,125 → best cell 3,523 / 3,449, worst 66 / 115) and L05 (count withdrawn by
§45; **status `excluded`, was `blocked_insufficient_events`**, L11's precedent; pinned set in the
registry test updated). V01's 1.15× (180m proxy, Sunday reopens included) is the narrowest live figure and
a ceiling, not a candidate. Source reconciliation ran on Sonnet at the user's instruction (§65 caveat).
**Nothing is scheduled.**

**Y-SERIES, 2026-10-09 — DESIGNED, NOT REGISTERED (§79).** The account's payoff structure, not a market
edge. Y01 on real MNQ paths, drift removed: zero-edge EV +$5 to +$127 per $80 evaluation (RTH 2 MNQ
+$119 / +$127 pre/post-2021; +$77 under an imposed Sharpe −0.3). Structural value ≈ +$82 (martingale
bound). Very skewed: 10 evaluations net positive 26%, 40 evaluations 59%. **Blocking: Y02, the firm's
full rulebook** (consistency rules, payout caps, time limits, floor timing). Then Y05, a forward demo
test. **Nothing is scheduled.**

**Y02, 2026-10-09 (§80): Tradeify daily accounts modelled.** Zero-edge EV still positive. The 40% eval
consistency rule binds hardest on large positions, so the policy is **RTH 09:30–16:00, 1 MNQ, long:
+$93–$145 per $80** (both eras, every payout frequency), +$53 under an imposed Sharpe −0.3. Open with the
user: payout frequency, when the account goes live, whether an intraday dip below the EOD floor fails
(the gentler reading gives +$208). **Next: Y05, a forward demo test.**

**Tradeify rules confirmed, 2026-10-09 (§81).** Intraday breach fails; daily payouts, $1,250 cap until
live (3 payouts on one account / 10 total); fee $80. **RTH, 1 MNQ, long: +$85 / +$125 per $80
(2015–20 / post-2021)**, +$69 at an imposed Sharpe −0.3; 10 evaluations net positive 46%, 40 76%.
**Next: Y05, forward demo test. Nothing else is scheduled.**

**CORRECTION, 2026-10-09 (§82): Tradeify's evaluation floor never locks** (funded does, at $50,000).
§81's figures superseded: **RTH, 1 MNQ, long: +$62 / +$78 per $80 (2015–20 / post-2021)**, +$45 at an
imposed Sharpe −0.3; pass 18–19%; 10 evaluations net positive 40%, 40 67%. **Next: Y05.**

**Y03, 2026-10-09 (§83): sessions, direction, MGC.** Window choice is mostly noise (MNQ Asia long
+$97 → +$17). **Two stable policies: MNQ 09:30–16:00 long (+$67 / +$82) and MGC London 03:00–11:30 long
(+$68 / +$70).** Shorts no better; shorter windows no better. **Next: Y05 forward demo test.**

**Y04, 2026-10-09 (§84):** both policies on ONE account: +$65 / +$46 per $80, worse than each alone (MNQ
+$71 / +$82, MGC +$45 / +$74 on the same paired dates). **Separate accounts per instrument.**

**Y05 historical replay, 2026-10-09 (§85).** Every start date, real order: drift removed MNQ **+$1**, MGC
**+$44** per $80 (actual history +$119 / +$115, bull markets included, descriptive only). Block bootstrap:
−$61 to +$162 depending on era and run length. **The resampled ±$5 understated real uncertainty by ~10×.**
Zero-edge value now stated as roughly $0–80 per evaluation, uncertain by as much; spread evaluations over
time. Forward demo test still needed.

**Y-series set aside by the user, 2026-10-09:** the structure value is too small for income.

**Z-SERIES, 2026-10-09 — DESIGNED, NOT REGISTERED (§86).** Evidence from outside, tested after the
authors' sample. Z01: front-running rebalancers (Harvey, Mazzoleni & Melone 2025; Sharpe ~1.1 in
1997–2023, skew +5.2), long/short ES–ZN; Z02 the MES leg alone. Test window 2023-03-18 to 2026-09-11.
**Open, for the user:** the decision rule (proposed: post-2023 Sharpe > 0 with the published sign, and
positive prop EV at the posterior), Tradeify's rule on long-equity/short-bond, optional ES/ZN 1-hour data.

**Z02 CONFIRMED, 2026-10-09 (§87–§88), trial t00768; N 762.** Rulings: rule accepted; long/short is
hedging, so Z01 not run; daily bars. Construction calibrated to the paper's published signal AR(1) before
any return. **Test 2023-03-18 → 2026-09-11: net Sharpe +0.51, beats 98.4% of rotations; posterior
0.50 ± 0.28.** Tradeify EV (cost double-count corrected): +$93 per $80 with the paper's sizing; **one MES
by the signal's sign: +$410** (unverified Sharpe for that sizing). **Next: forward demo of Z02, sign-only,
1 MES.**

**Z02 CLOSED FOR THE ACCOUNT (§89).** +$410 corrected to +$110 (today's MES ~$38k, ~$380/day); every-start
replay in real order ≈ break-even (−$5; 2023 starts −$78). Effect real, too small against the account's
barriers. Lesson: need high Sharpe per day in the market. **Searching for the next Z candidate.**

**Z03 DESIGNED (§90): Treasury end-of-month (Hartley & Schwarz 2019).** Long ZN the last 2 business days
of each month; test 2019-01 → 2026-09, after the paper's sample. Account check before testing: 1 ZN at the
prior P(pass) 49%, EV +$202 (~490 days to pass); 2 ZN ~170 days. **Open: Tradeify product permission; go-ahead.**

**Z03 NOT RUN — the user needs a payout within 1–2 months (§91).** Computed: a 50% chance of a payout
within 42 trading days needs an annual Sharpe of ~5 (1 MNQ); at Sharpe 1, 12%; at no edge, 7%. Nothing
available approaches it. The account's geometry, not only the edge, sets the frontier.

**Firms compared (§92), 4-month payout window.** 11 account types × 4 strategies. Best P(payout ≤ 84 days):
Lucid Flex 13% (no edge) / 21% (Sharpe 1) — but only if its drawdown is checked at the close; intraday
8% / 13%, level with Topstep (9% / 17%) and Tradeify Select Daily (7% / 12%). No firm makes it likely.

**A-SERIES, 2026-10-09 (§93): the account played optimally.** Staking solved by DP on Tradeify's rules,
executed on real MNQ paths with drift removed. Single attempt (2 MNQ): pass 23%, EV +$123, resolves in
1–2 weeks. **Back-to-back for 4 months, real history replayed: P(≥1 payout) 61%, mean net +$675 after
~$824 fees, P(net > 0) 45%** (passive: 32%, +$84). **Next: confirm Tradeify permits it; forward demo.**

**Route 1 closed (§94):** parallel accounts with payouts reinvested go bust in 68–84% of runs within 12
months (mean net positive, carried by ~3 in 10). Kelly needs ~$4–8k reserve per concurrent account.
Zero edge cannot scale. **Open: route 2 — find an edge large on the days it is held; stake it with A01.**

**Route 2's bar (§95):** a coin-flip payout within 4 months needs annual Sharpe ~3; nothing published and
surviving is near it. EV per attempt rises steeply from Sharpe ~1 (+$155–326). Target: a portfolio of modest
confirmed edges (~1–1.5 combined), staked with A01. Rejected: end-of-day reversal, OpEx week, dash for cash.

**Z03 dropped (ZN not tradable). Z04 run and RETIRED (§96–§97), t00769, N 763:** no announcement premium in
ES 2010–2026 (+3.4 vs +5.7 bps, t −0.43). Portfolio so far: Z02 only (~0.4–0.5). Search continues.

**Screened out (§98):** buyback blackouts, oil→stocks lag, gold autumn effect. **Open: the Goldman roll
(Mou 2011, Sharpe ≤4.39 to 2010) — a CL calendar spread; needs the user's ruling on whether spreads count
as hedging.**

**Goldman roll out (a spread is long and short at once). Z05 run (§99–§100), t00770, N 764: gold long
overnight / short NY day CONFIRMED marginally** (net Sharpe +0.22, t 1.82; only 2021–26 positive; short leg
earns nothing). Portfolio: Z02 + Z05 ≈ 0.5 combined. Search continues.

**Edge portfolio in the account (§101): worse than zero-edge solved staking.** Z02 + Z05 replayed 2013–2026:
4-month P(payout) 15%, net −$230 (A03: 61%, +$675). Z02's one-MES version is +0.06 over the full period.
Weak edges can't move the solver's bracket odds. **Search continues; the bar is now A03.**

**A05 (§102): real-odds re-solve fails** — learned on 2015–20 (57% of brackets end at the close), tested
2021–26: 43%, −$8 vs A01's 61%, +$675. Fair-odds policy is the robust one; A03 remains the bar.

**Option 2 (§103): two candidates screened out, no trial.** Intraday momentum (Baltussen et al. 2021) is ~1 bp/day
gross on MNQ and MGC inside the paper's own sample (m00152); pre-holiday has no large-cap effect after 1990
(Ko & Yang 2024). No surviving effect of several bps/held day found; demo forward test of A03 is the alternative.

**A06 (§104): demo forward test of A03 starts; search continues alongside.** Daily ticket:
`python -m futuresres.reporting.a06_playbook eval --balance B --peak P --best D`; tables in reports/a06_playbook_*.csv.
Judge the demo on execution vs replay, not P&L (P(net>0) is 45% even if it works).

**A07 (§105): run the demo at 4 MNQ, not 2.** 4 beats 2 on both histories (2021–26, 2015–20), replay and block
bootstrap: ~65–78% P(payout in 4 months), +$1,000–1,500 mean net vs 35–61%, +$95–675. Vol scaling adds nothing.
m00153 superseded by m00154. Playbook default now 4.

**A08 (§106): a second demo account on gold — 8 MGC, London 03:00–11:30 ET long.** 48–64% P(payout in 4 months),
+$700–1,350 across both histories; correlation with the MNQ account +0.06. `a06_playbook --product MGC`.

**A09 (§107): fills within ~$10 (user) change little;** at $20 MNQ drops to 56–63%. Gold holds 03:00–11:30 ET (AM),
never through the 17:00–18:00 break.

**A10 (§108): unseen data 08-28→10-09 + stop-price fills.** With fills at the stop (the user's execution) the 4-month
results rise: 4 MNQ 65–79% / +$1,140–1,830; 8 MGC 74–77% / +$2,030–2,420. Forward 6 weeks: MNQ −$160 (in funded),
MGC −$560 — both at the historical median for that length. New data in data/{raw,parquet,continuous}_update.

**A11 (§109): new edge bar.** A directional tilt of annual Sharpe ≥ ~0.25 on the traded window adds +$100–600 per
4 months (most on gold); 0.5 adds +$260–1,450. Screen against THAT, not §95's Sharpe-3 bar.

**Z06 (§110), t00771, N 765: trend sign as bracket direction REJECTED on both** (MNQ −0.17, MGC −0.25 vs always-long
+0.35 / +0.13). Plans stay always-long.

**Z07 (§111), t00772, N 766: index reversal (MAC(5)) as MNQ direction REJECTED** (+0.09 vs always-long +0.35;
faded to −0.15 in 2021–26). Screen queue for in-window edges near dry; plans run always-long.

**A12 (§112): both accounts together:** P(≥1 payout in 4 months) 93–97%, median first payout ~22–25 trading days,
mean net +$3,400–4,400, P(net>0) 72–79%, 10th pct −$1,000 to −$1,400, worst −$2,600.

**A13 (§113): size-aware solver rejected** (24–46% vs fixed 70–79%, worse even in sample). Fixed 4 MNQ / 8 MGC stay.
Stuck-at-floor replay defect fixed; no recorded result changed.

**§114 scaling:** k parallel MNQ+MGC pairs scale mean net linearly (+$34–43k for 10 pairs / 4 months) but NOT the
odds (P(net>0) stays 72–83%; worst −$24k at 10). Breadth across uncorrelated markets is the lever. Open: funded-account cap.

**§115:** 5 funded accounts max; copying allowed. Crude ≈ uncorrelated with MNQ/gold → third market. Hourly candles +
OHLC rule within ~10–15% of 1-minute → order ohlcv-1h CL.v.0, NG.v.0 (minute data quoted $549–668, too expensive).


**Latest, 2026-09-13 (after P03):** N = **760**, SR\* **0.1368**. P03 retired at S7 (§58); the
P-series closed with zero promotions. **Q-series S1 reviewed in §59, nothing registered:**
three candidates are already in the registry (Q01 = F02, Q03 = F12, Q04 under F12's note); Q01 and
Q02 share a conditioner (Spearman +0.972); the magnitude filter leaves one straddle (Q01, not
testable cleanly on disk data, which ends 2026-08-27) and four below their post-2021 bars. The
drawdown rule was confirmed with the firm and Q09 recomputed (`q09_drawdown.py`). **Open decision:**
write up the finding, or wait for post-2026-08-27 data and test Q01 once.


The bullets under this block were accurate on 2026-09-10 and went **stale for three sessions**
while N moved from 684 to 759 and four series closed. They are kept, not deleted, because a
checkpoint that silently rewrites itself hides that it was ever wrong (`decisions.md` §36).

- **Four series closed. N = 759, SR\* = 0.1369, chain verified. Nothing promoted.**
  F (14), R (5, separate repo), L (12, `reports/level_conclusion.md`), N (1 of 10 candidates
  tested, `decisions.md` §51).
- **P-series: S1 draft only**, `P_SERIES_CANDIDATES.md`, reviewed in `decisions.md` §54.
  Nothing registered. One candidate (P03) is recommended first, and only after a
  **confound-matched control for state conditions** is built — that control is the open item.
- Stage numbering S1–S8 (`reports/STAGES.md`); S2 now carries a magnitude check and a
  scale-invariance check (tested and fault-injected, §53).
- 42/42 registry tests pass; the full suite must be run one file at a time on this laptop.

### Historical (2026-09-10)


- **372 tests with the data layer present; 300 from a clean clone at the pre-fix commit** (plus 3 collection
  errors). Both figures are stated because for most of this project's life only the first was
  ever measured, and it was measured on the one machine where the untracked package existed.
  **The 70-test gap is the finding, not either number** — see `decisions.md` §36. Now closed:
  `.gitignore` had `data/` unanchored, which excluded `src/futuresres/data/` from every commit
  ever made.
- **Measured on a clean checkout of `9fd2ae5` (2026-09-10): 372 collected, 360 passed, 12
  skipped by design — but ONLY after `pip install zstandard`.** From the declared dependencies
  alone it was 2 collection errors, because `data/parse.py` imports `zstandard` and
  `pyproject.toml` never listed it. **An untracked module has untracked requirements**, and
  restoring one does not restore the other. Declared now; `decisions.md` §39. The earlier
  claim here that "a clean clone reads the full suite from 160ed05 onward" was true of the
  code and false of the environment. **After L11's registration the suite is 378 collected /
  366 passed / 12 skipped** — the 6 added tests are `bollinger_levels` band arithmetic on
  synthetic input, which needs no market data.
- **N = 684, SR\* = 0.1357.** L07 Stage 1 spent 108 trials on 2026-09-09 (was 576 / 0.1335). The repo now has a private remote at
  `github.com/coltontr419-droid/futures-research` and all commits are pushed; it had none
  until 2026-09-09, while every other programme depended on its detection floors.
- `trials.jsonl` **N = 684, chain verified** (`ChainResult(ok=True, n_records=684)`,
  re-verified 2026-09-10). `measurements.jsonl` holds F14's three control runs, the
  firing-rate measurements, and L07's market-state comparison as m00115.
  **The "N = 576" this line used to carry contradicted the line directly above it.**
- **L07 spent 108 trials and ran Stage 1 on 2026-09-09** — retired, registered mechanism
  refuted; `decisions.md` §38. The previous "no L-series trial spent, no Stage 1 since F06"
  was stale on both counts.
- **L11 registered 2026-09-10** — Bollinger band breakout, Stage 0 only, `schedulable: false`,
  firing rate and placebo match **not measured** because `data/continuous/` is absent on the
  laptop. No trial spent. `decisions.md` §39.

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

**L07 HAS RUN AND IS RETIRED** (2026-09-10, `decisions.md` §38). 108 trials spent. Every one
of 108 cells separates on both instruments against 2.7 expected by chance per product, which
was predicted and is not a finding at these event counts. **The difference is negative in
every cell at 1.8×–10.3× the round-trip cost floor**, and the decomposition is sharper than
the difference: the real zone loses while the matched placebo wins, so conditioning on the
region being a real fair-value gap *reverses the sign* of the trade. The registered mechanism
is refuted in the direction it was stated.

**The confound that was expected did not appear, and a different one did.** Real entries
follow 4–11% *less* prior volatility than their placebos, not more. But they fire a median of
16 minutes earlier on MGC and 47 on MNQ, up to 81 — so real and placebo are not sampling the
same part of the session, and this design cannot separate reaction from timing.
`reports/l07_market_state.md`.

**The mirror hypothesis is NOT registered and must not be** on this evidence. The sign came
from looking at this data, it has no mechanism — the registered story predicts reaction at the
zone, not continuation through it — and the timing confound applies to it equally. If it is
worth testing it has to be frozen and evaluated on history that did not generate it.

**Item 3 is settled, so that bar is lifted for the level types that now match** — but read
§37 before running anything. A Stage 1 result on a level type that still fails matching would
measure exposure rather than reaction and would look like a finding. **L06 can never clear
that bar.**

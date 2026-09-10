# Price-Level Reaction Hypotheses (L-series)

Extension to `FUTURES_STRATEGY_HYPOTHESES.md`. Registers in the same
`hypotheses.yaml`, counts toward the same `N`. MNQ and MGC, flat by 17:00 ET.

---

## Read this first

### What this catalog is

Level-reaction is the most widely traded idea in retail futures and among the least
rigorously evidenced. Prior day highs, VWAP, opening ranges, fair value gaps — every chart
platform draws them, every course teaches them, and almost nobody has established that reaction
at them differs from reaction anywhere else.

That gap is exactly what this pipeline exists to close. The F-series closed with one hypothesis
tested at adequate power. This series is registered specifically to satisfy the conditions the
conclusion document named as necessary for reopening: **conditions that fire several times a
session, on the instrument where the mechanism lives, specified tightly enough that no decision
remains after registration.**

### The cost, stated upfront

`N` is already 576 with `SR* = 0.1334`. This catalog is ten hypotheses. Registered at the
parameter caps below, a full sweep adds roughly 200–300 trials and pushes `SR*` toward 0.15.
Every hypothesis here is paid for by every other one.

**Measure firing rates before scheduling anything.** Two hypotheses in the F-series consumed
216 of 576 trials — 38% — and neither could produce evidence. That was the price of a gate
reading a declared rate instead of a measured one.

---

## The methodological core: the random-level benchmark

**This is the single most important requirement in this document, and it is what almost every
retail backtest omits.**

Price mean-reverts and continues around *arbitrary* levels. Volatility clusters near any
reference point price is currently trading through. So the null hypothesis for a level test is
**not** "no reaction." Any level, real or invented, will show reaction.

The correct null is: **does reaction at this level differ from reaction at a matched placebo
level?**

### Placebo construction — required for every L-series hypothesis

For each real level, generate a matched placebo:

```
placebo_offset = deterministic hash(session_date, level_type, index)
                 mapped to ±[0.3, 1.5] × SCALE
placebo_level  = real_level + placebo_offset
```

Requirements:
- Same count per session as the real levels
- Same distance-from-current-price distribution (verify, don't assume)
- Same touch-frequency distribution (verify — if placebos are touched far less often, the
  offset range is wrong and the comparison is invalid)
- Deterministic hash seeding, never `hash()`, per the reproducibility requirement

**SCALE WAS `ATR(20)` — DAILY — UNTIL 2026-09-09, AND THAT FAILED 53 OF 55 LEVEL TYPES.**
A single daily scale was applied to a one-minute fair-value gap and a prior-month extreme
alike. Placebos landed 3× to 63× further from price than the levels they stood in for, and
were touched 6–17% of the time against the real levels' 30–96%. Every real-minus-placebo
comparison on those types would have measured **exposure, not reaction** — the exact failure
the two "verify, don't assume" requirements above exist to catch. **They did catch it.**
`reports/placebo_match.md` has said `FAIL — 53 of 55` since the first complete run; nothing
was blocked by it because no Stage 1 ever ran.

The scale is now `definitions.window_scale`: the intraday range over **each level's own
validity window**, since `touches` gives every level the remainder of its own row and no
longer. The offset bounds `[0.3, 1.5]` are unchanged — only the unit they multiply.

**Matching still fails after the correction, and the residual is geometric rather than a
matter of scale.** A placebo built as `level + offset × scale` sits at roughly `2d` or `0`
when the level is already displaced by `d`, giving a median near `1.4d` for any scale
whatsoever. Making the distance distribution match requires changing what the control *is*,
which is a specification decision and is recorded as open in `decisions.md` §36 and
`reports/CHECKPOINT.md` item 3.

**No L-series Stage 1 may run until that is settled.** A result computed against an unmatched
placebo would measure exposure and would look like a finding.

**The reported effect is (real level) − (placebo level), not (real level) − 0.** A hypothesis
whose real-minus-placebo difference is indistinguishable from zero is refuted even if its raw
reaction is strongly significant.

Report both figures. The gap between them is the most informative number this catalog will
produce, and it applies to every entry below.

---

## The two-mechanism problem

Every level hypothesis has one mechanism — **resting orders and stops cluster at reference
levels** — which licenses two opposite predictions:

- **Absorption:** resting limit orders soak up aggressive flow, price reverses
- **Sweep:** stops trigger, cascade, price continues

The mechanism does not say which. Testing both on the same condition doubles the trial count
and means neither outcome supports the mechanism — the F08 failure, where an invented direction
rule was retired on premise.

**Resolution adopted here:** each hypothesis pre-specifies its direction from a *distinguishing
condition*, not from the level alone. Where a hypothesis cannot state a distinguishing
condition, it is registered as **magnitude-only** — testing whether volatility or volume differ
at the level, with no directional claim — or it is not registered.

The distinguishing conditions used below:

| condition | prediction |
|---|---|
| price penetrates level by >= *m* ticks, then closes back inside within *k* bars | absorption -> fade |
| price closes beyond level for >= *k* consecutive bars | sweep -> continue |
| approach velocity above/below threshold | (used as a filter, never as direction) |

These must be fixed before any run and are stated per hypothesis.

---

## Universal specification requirements

Every entry below must satisfy these before it can be scheduled. They exist because each was
violated at least once in the F-series.

1. **Level definition is mechanical and complete.** No discretion, no "significant" swing
   points, no judgement at run time. If a definition requires a decision, it is not ready.
2. **Firing rate measured, never declared** — with all thresholds and any mandatory regime split
   applied, counted per Stage 1 cell.
3. **Verdict route declared.** Are cells disjoint in time (aggregate route available) or do they
   share entry timestamps (aggregate closed)? Most level hypotheses have *overlapping* cells —
   the same touch enters under multiple parameter settings — so **assume the aggregate route is
   closed until disjointness is verified**, as with F07.
4. **`mechanism_instruments` stated.** VWAP and opening range exist on both. Equity-cash-open
   anchors are MNQ-native and attenuated on MGC.
5. **Time-based exits.** Fixed hold, no intrabar stop, per §9 — resolvable on 1m bars.
6. **Parameter cap 4.**
7. **sigma and ATR references measured against normal volatility**, never against the window the
   condition selects on. This is the F05 correction: a trigger that shrinks whenever the filter
   fires tests nothing.
8. **MGC coverage caveat applies** — 70% RTH fill rate, forward-fill biases toward apparent
   significance, so an unaccompanied MGC positive is discounted.

---

# TIER A — mechanism names a participant

---

## L01 — VWAP Reaction

**Params: 3** | **MNQ + MGC** | **Hold: 30–120 min** | **Fires: many per session**

### Mechanism
The only level in this catalog where a named participant has a stated reason to transact at it.
Institutional execution algorithms are benchmarked to VWAP — a desk filling a large order is
measured on whether it beat VWAP, which creates genuine, non-discretionary flow referencing
that specific price. Buy programs become more aggressive below VWAP and passive above it.

That is a real mechanism with a real counterparty, and it is why VWAP is graded above every
other level here despite being equally popular.

### Level definition
Session VWAP anchored to the RTH open (09:30 ET), computed from 1m typical price times volume.
**The anchor is a hidden parameter** — anchoring to the CME open (18:00 ET) or a rolling 24h
window gives a different level. Test all three anchors and log each as a trial; do not pick one
silently.

### Condition
```
touch = price trades within t ticks of VWAP after being >= d ATR away for >= 15 min
direction: absorption — fade the approach
entry: on the 1m close following the touch
exit: fixed H minutes, or 15:55 ET, whichever first
```

### Parameters
`anchor` in {RTH open, CME open, rolling 24h} · `d` in {0.5, 1.0, 1.5} ATR · `H` in {30, 60, 120} min

### Placebo
VWAP +/- hash-derived offset, matched on touch frequency.

### Why it might fail
- The mechanism predicts flow *toward* VWAP, not reversal *at* it. Absorption is an additional
  assumption the mechanism does not license — flag this, it is the weakest link.
- In trending sessions VWAP is a continuation reference, not a reversion target. The `d`
  filter is doing the regime work; test whether removing it destroys the result.
- Crypto S15 tested a version of this and did not clear.

---

## L02 — Opening Range Boundary

**Params: 4** | **MNQ native, MGC attenuated** | **Hold: 60–180 min** | **Fires: 1–4 per session**

### Mechanism
Two mechanisms compound here, which is unusual and is why this ranks high.

The opening range is a genuine liquidity event — 09:30 ET is the largest participant-composition
change of the day, and the first minutes establish where overnight positioning meets cash
liquidity. It is also the most-watched level in retail futures, so stop clustering at its
boundaries is plausible on self-fulfilling grounds *in addition to* the structural story.

### Level definition
High and low of [09:30, 09:30 + W] ET. Fixed, unambiguous, no discretion.

### Condition — sweep variant (directional, pre-specified)
```
if price closes beyond the boundary for k consecutive 1m bars:
    enter in the break direction
    exit at H minutes or 15:55 ET
```

### Condition — absorption variant (registered separately, own trials)
```
if price penetrates the boundary by >= m ticks then closes back inside within k bars:
    enter counter to the penetration
    exit at H minutes or 15:55 ET
```

Both are registered because each has a distinguishing condition. They are **not** two directions
on the same signal — they fire on different, mutually exclusive price paths.

### Parameters
`W` in {15, 30, 60} min · `k` in {1, 2, 3} bars · `m` in {2, 4, 8} ticks (absorption only) ·
`H` in {60, 120, 180} min

### Why it might fail
Opening range breakout is possibly the most heavily traded pattern in retail futures. Decades of
attention. A positive result deserves more suspicion than a negative one — treat it the way F06's
entry treats its own result.

---

## L03 — Prior Day High/Low Sweep and Reclaim

**Params: 4** | **Both** | **Hold: 60–180 min** | **Fires: 0.5–2 per session**

### Mechanism
The mechanized version of the ICT "liquidity sweep," and the reason to register it is that the
underlying claim is genuinely mechanical: stop orders cluster immediately beyond obvious
reference points, because that is where a large number of traders place them. A sweep triggers
those stops, the resulting flow is forced and price-insensitive, and once exhausted price
returns inside — the same absorption story as a liquidation cascade, at a smaller scale.

**This is registered only because it can be fully mechanized.** As usually taught it is not
falsifiable — swing points, "displacement," and validity are defined loosely enough that any
chart can be read to fit. Every term below is fixed in advance.

### Level definition
Prior RTH session high and low (09:30–16:00 ET), and prior full trading-day high and low
(18:00–17:00 ET), tested as separate level types.

### Condition
```
sweep    = price exceeds the level by >= m ticks
reclaim  = a 1m close back inside the level within k bars of the sweep
entry    = close of the reclaim bar, direction counter to the sweep
exit     = H minutes or 15:55 ET
```

### Parameters
`level_type` in {prior RTH, prior full day} · `m` in {2, 4, 8} ticks · `k` in {2, 3, 5} bars ·
`H` in {60, 120, 180} min

### Why it might fail
- Firing rate is the risk. Two levels times ~1 touch each = borderline against the
  once-per-session ceiling that closed five F-series hypotheses. **Measure before scheduling.**
- The reclaim condition is doing all the work, and it is also what makes the setup visible only
  in hindsight on a chart. If `k` matters a great deal, that is a tell.
- Sweep-then-reclaim is a subset of ordinary noise around a level. The placebo benchmark is
  essential here — placebos will also produce sweeps and reclaims.

---

# TIER B

---

## L04 — Prior Session Extremes

**Params: 4** | **Both** | **Hold: 60–180 min** | **Fires: 2–6 per session**

### Mechanism
Same stop-clustering story as L03, but with more levels and therefore a higher firing rate,
which is the point of registering it separately. Asia (19:00–03:00 ET), London (03:00–11:30 ET)
and US RTH each leave a high and a low, and each session's extremes are watched by the
participants of the *following* session.

### Level definition
High and low of each completed session, defined via the DST-aware session mapper. Six levels
carried forward at any time.

### Condition
Same sweep-and-reclaim as L03, applied per session-extreme type. Session type is a scan
dimension — **each session type is its own cell, and the cells share entry timestamps only when
extremes coincide.** Verify disjointness before claiming an aggregate route.

### Parameters
`session` in {Asia, London, US} · `m` in {2, 4, 8} ticks · `k` in {2, 3, 5} bars ·
`H` in {60, 120, 180} min

### Why it might fail
Asia and London session extremes on MGC are more plausible than on MNQ, since gold trades
meaningfully in those hours while index futures are thin. Expect the instruments to diverge, and
resist reading a split as confirmation.

---

## L05 — Overnight Range Boundaries

**Params: 3** | **MNQ native** | **Hold: 60–180 min** | **Fires: 1–3 per session**

### Mechanism
The overnight range (18:00 previous day to 09:30 ET) is where positioning accumulates without
cash liquidity. When RTH opens, that positioning is tested against real depth. Breaks of the
overnight high or low during RTH are a genuine liquidity event rather than a pattern.

### Level definition
High and low of [18:00 ET prev day, 09:30 ET].

### Condition
```
during RTH only:
  first close beyond the overnight boundary
  enter in break direction
  exit at H or 15:55 ET
```
Only the **first** break per boundary per session counts. Subsequent re-tests are a different
claim and are not registered.

### Parameters
`k` in {1, 2, 3} confirming bars · `H` in {60, 120, 180} min ·
`vol_filter` in {none, ON range > median, ON range < median}

### Why it might fail
Heavily overlaps L02 — an overnight high broken at 09:35 is often also an opening-range break.
**Test the overlap explicitly and report it.** If the two hypotheses fire on the same events,
they are one hypothesis and should not both consume trials.

---

## L06 — Session Open as Reference

**Params: 3** | **Both** | **Hold: 60–180 min** | **Fires: 2–8 per session**

### Mechanism
The session open price is the reference against which the session's P&L is marked. Positions
opened at the start of a session are at breakeven when price returns to it, which is a real
behavioural anchor with a real decision attached — hold or flatten.

Higher firing rate than most of this catalog because price crosses the open repeatedly.

### Level definition
RTH open (09:30 ET) and CME open (18:00 ET) prices, converted through the session mapper.

### Condition
```
cross = price crosses the open price after being >= d ATR away for >= 30 min
direction: magnitude-only test first (see below)
```

**Registered as magnitude-only initially.** The mechanism licenses "a decision happens here,"
not a direction. Stage 1 tests whether forward *volatility* and *volume* differ after a cross,
not whether returns are directional. Only if magnitude separates does a directional variant get
registered, and it would need its own trial budget.

### Parameters
`open_type` in {RTH, CME} · `d` in {0.5, 1.0, 1.5} ATR · `H` in {60, 120, 180} min

---

## L07 — Fair Value Gap Fill

**Params: 4** | **Both** | **Hold: 60–180 min** | **Fires: many per session**

### Mechanism, stated honestly
A three-bar imbalance — where bar 1's high is below bar 3's low, or vice versa — marks a price
zone that traded through quickly with little two-sided activity. The claim is that price returns
to fill it because the zone contains unfilled interest.

**I am sceptical and the entry says so.** The competing explanation is that price is
approximately a random walk with fat tails and revisits nearby levels regardless of what
happened there. Gaps get filled because *most nearby prices get revisited*, not because the gap
means anything.

**This hypothesis is the strongest possible argument for the placebo benchmark.** A raw
fill-rate statistic will look impressive — likely 70–90% — and will be equally impressive for
placebo zones. Only the difference is evidence.

### Level definition
```
bullish FVG: high[i-1] < low[i+1]  -> zone = [high[i-1], low[i+1]]
bearish FVG: low[i-1]  > high[i+1] -> zone = [high[i+1], low[i-1]]
minimum zone width: w ticks (excludes noise gaps)
```

### Condition
```
entry: first 1m close inside an unfilled zone created >= g bars earlier
direction: counter to the move that created the gap (fade the imbalance)
exit: H minutes or 15:55 ET
```

### Parameters
`w` in {2, 4, 8} ticks · `g` in {10, 30, 60} bars · `H` in {60, 120, 180} min ·
`timeframe` in {1m, 5m}

### Why it might fail
The honest prior is that it does not survive the placebo. Register it anyway — it is the most
widely traded idea in this catalog and a clean, powered null on it would be one of the more
useful results the pipeline could produce.

---

# TIER C — weak mechanism, registered for completeness

---

## L08 — Moving Average Reaction

**Params: 3** | **Both** | **Hold: 60–180 min** | **Fires: many per session**

### Mechanism — and the problem with it
No institution executes against a 50 EMA. The only available story is **self-fulfilling**: enough
traders watch the same standard settings that orders cluster near them.

That is a real mechanism in principle, but note it is the same premise that disqualified F11 as a
control — "widely watched, therefore orders cluster" is a claim about the market that has to be
tested, not assumed. Here it is being tested, which is legitimate; it just makes the prior weak.

### Level definition
EMA(20), EMA(50), EMA(200) on 5m and 15m bars. **Fixed a-priori values — no optimization of
period.** If 47 works and 50 does not, that is the tell.

### Condition
```
touch after >= d ATR separation for >= 30 min, fade the approach
exit at H or 15:55 ET
```

### Parameters
`period` in {20, 50, 200} · `timeframe` in {5m, 15m} · `H` in {60, 120, 180} min

**Note:** period times timeframe is a 6-cell scan and every cell is a trial. BH within the
hypothesis.

---

## L09 — Higher-Timeframe Levels — **LIKELY BELOW FIRING-RATE GATE**

Prior week and prior month high/low. Two to four levels, touched perhaps weekly.

Over sixteen years: ~830 weekly levels, ~190 monthly. Against the ~19,700 at which a floor
resolves at MNQ 60m, and against the 2,400-observation ceiling that closed five F-series
hypotheses.

**Measure the rate before registering.** If it lands where I expect, record it as
`blocked_insufficient_events` with the arithmetic and do not spend trials on it. This entry
exists so the exclusion is documented rather than rediscovered.

---

# CONTROL

## L10 — Placebo Level Control

**Params: 0** | **Both** | **Fires: matched to L01 by construction**

Hash-derived levels with no relationship to price history, run through the identical L01
pipeline. Premise: **cannot relate to future returns by construction** — not "should have been
arbitraged away," per §7.6.

Two jobs:
1. Standing harness check at the level-reaction event regime, which the F14 control does not
   cover (different condition shape, different firing pattern).
2. Direct validation that the placebo machinery is correctly matched. If placebo levels are
   touched at a materially different rate than real levels, the offset distribution is wrong and
   every placebo comparison in this catalog is invalid.

Logs to `measurements.jsonl`, not `trials.jsonl`.

---

# Testing order

Measure all firing rates first — one batch, before anything is scheduled.

| # | id | rationale |
|---|---|---|
| 0 | L10 | control and placebo validation — nothing is interpretable until this passes |
| 1 | L01 | only entry with a named participant; high firing rate |
| 2 | L07 | highest firing rate; the placebo benchmark's decisive test case |
| 3 | L02 | two compounding mechanisms, MNQ-native, cleanly defined |
| 4 | L06 | high firing rate, magnitude-only so no direction invented |
| 5 | L04 | more levels than L03, better rate |
| 6 | L03 | mechanically the most interesting, rate is the risk |
| 7 | L05 | test L02 overlap first — may be the same hypothesis |
| 8 | L08 | weak mechanism, registered for completeness |
| — | L09 | measure rate, expect to block |

---

# Honest assessment

**What I'd expect to survive to Stage 8: none.** These are the most heavily traded ideas in
retail futures, and the F-series produced one powered null and thirteen closures on structural
grounds.

**What I'd expect this catalog to actually produce**, which is worth more than it sounds: the
first properly powered, placebo-controlled measurement of whether level reaction exists. High
firing rates mean most of these clear the detection floor that closed the F-series — so unlike
F01 and F02, these can produce *interpretable* nulls rather than uninformative ones.

Ranked by what I'd least expect to fail:

1. **L01 (VWAP)** — the only mechanism naming a participant with a reason to transact at the
   level. Weakness is that the mechanism predicts flow toward VWAP, not reversal at it.
2. **L02 (opening range)** — two compounding mechanisms, though decades of attention.
3. **L06 (session open, magnitude-only)** — the most modest claim in the catalog, which is why it
   might be the one that holds.

I'd expect **L07 and L08 to fail outright**, and L07's failure to be the most informative result
here, because fair value gaps are traded on a raw fill-rate statistic that the placebo benchmark
should demolish.

**The thing most likely to go wrong:** placebo mismatch. If placebo levels are touched at a
different rate or a different distance distribution than real ones, every comparison in this
catalog is invalid and the results will look decisive while meaning nothing. L10 runs first for
that reason, and its verification is not optional.

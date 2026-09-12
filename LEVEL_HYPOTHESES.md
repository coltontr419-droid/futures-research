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

**THE NULL WAS REDEFINED 2026-09-09.** It is stated first, then the reasoning, then what it
costs.

```
scale_i    = intraday range over level i's own validity window
u          = { |real_level - reference| / scale }   over all levels of this type
placebo_i  = reference_i  ±  hash(date, level_type, index) drawn from u  ×  scale_i
```

**A placebo is an ARBITRARY REGION matched to the real levels on distance-from-price and
checked on touch frequency. It is no longer the real level displaced.**

Requirements, unchanged:
- Same count per session as the real levels
- Same distance-from-current-price distribution — now matched **by construction**
- Same touch-frequency distribution — **left free and measured**, so it stays an independent
  check rather than a second thing fitted
- Deterministic hash seeding, never `hash()`, per the reproducibility requirement

### Why the null changed

**The hypotheses never asked about displacement.** L07 asks whether fair-value-gap zones react
differently from *ordinary regions price reaches equally often*. Displacement was a **method
for generating such regions** — a reasonable one — and it was never the null itself. Reading it
as the null is what made a defect in the method look like a property of the comparison.

**The method had a defect that no parameter could remove.** A real level already sits at
distance `d` from the reference price, so adding a signed offset of magnitude `~d` lands the
placebo at `~2d` or `~0`, with a median near `1.4d`. Measured, that ratio held at **1.32–1.54
across every level type, both products and three different scale rules**. The failure was
geometric, so no scale fixed it and no scale ever could.

The first scale correction, from daily ATR to the intraday validity window, was still worth
making and is retained — it is the right unit. It moved matching from 2 of 55 to 3 of 55 and
went no further, which is what identified the remaining error as structural.

### What this costs — stated plainly, because it is a real loss

**A matched-distance arbitrary region is a WEAKER control than a displaced real level.**

A displaced level inherits the *history* of the level it came from: the same session, the same
approach, the same sequence of prices that brought the market to that neighbourhood. Comparing
against it holds constant **how price arrived**. An arbitrary region at a matched distance does
not hold that constant. It equalises where the region sits and how often price reaches it, and
nothing else.

**So a surviving real-minus-placebo difference now has one more competing explanation than it
used to**: that price *arrives* at real levels differently, rather than *reacting* at them
differently. The new control cannot separate those. A result under it should be read as "reacts
differently from an equally-reachable arbitrary region", which is a weaker claim than "reacts
differently given the same approach".

**This was accepted deliberately.** The stronger control was unattainable — its geometry
guarantees a 1.4× distance mismatch, so it was never actually delivering the comparison it
appeared to. **A weaker control that is matched beats a stronger one that is not**, because an
unmatched control measures exposure and reports it as reaction. `decisions.md` §37.

### The degenerate case

`open_RTH` and `open_CME` sit **exactly at** the reference price: their distance distribution is
identically zero. There is no distance to match and no arbitrary region is comparable to them.
`verify` reports this as its own failure kind rather than as a tuning problem, because no
construction fixes it. **L06 has no valid control and cannot get one under this definition.**

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

## L11 — Bollinger Band Breakout

**Params: 2** | **Both** | **Fires: NOT MEASURED**

Confirmed break of a Bollinger boundary on 1h bars, mean ± k·σ, trading in the direction of
the break. **Period 20 and k 2.0 are fixed a priori and are not swept.**

**Premise: weak, and it is the same weak premise as L08.** No institution executes against a
20-period 2-sigma band. The only story available is self-fulfilling — enough traders watch the
same platform defaults that resting orders and stops cluster near the boundary, so a break
through it meets thinner liquidity and continues. That is *the premise that disqualified F11
as a control*: "widely watched, therefore orders cluster" is a claim about the market, not a
structural fact about how it operates. Testing it is legitimate. Assuming it is not.

**The counterparty, such as it is:** the retail trader whose stop sits just beyond a band
because a charting platform drew the line there on its default settings. A real person
transacting for a non-informational reason, which is what §7 asks for — but nothing obliges
them to be there, and this entry does not pretend otherwise.

**Why the settings are frozen.** The mechanism *is* that these particular numbers are the
watched ones. A period chosen because it scored better carries no self-fulfilling story at
all — it is an ordinary volatility-breakout rule with a fitted lookback, which is a different
hypothesis with no mechanism section. L08 names the same tell: *if 47 works and 50 does not,
that is the tell.* The level type records the settings in its own name (`bb20k2_60m_upper`),
so a swept variant appearing in a later report is visible as one.

**Upper and lower are separate level types.** Price is not symmetrically placed between the
bands, so their distance distributions differ. One shared type would let a placebo drawn for
the upper stand in for the lower and quietly break the matching.

**Provenance, and it carries no weight.** The idea came from a third-party claim with no
accessible trial count, no cost assumption and no control — so there is no way to know how
many settings were tried before that one was published, whether the reported edge survives a
spread, or what it was compared against. An unaudited claim is a reason to ask the question
and is not evidence for the answer.

**Open before this can be scheduled:** the firing rate and the placebo match, neither
measured. The placebo question is genuine rather than a formality — bands widen with
volatility, so a boundary's distance from price is not stationary the way a prior-week
extreme's is, which is exactly what the ±25% distance and touch criteria exist to catch.

---

## L12 — Asia Session Extreme Reclaim, Out of Sample

**Params: 2** | **MNQ only** | **Fires: 4,903–5,442 per cell (measured)**

Sweep and reclaim at Asia-session extremes on MNQ — the identical condition L04 ran on MGC.
Nine cells, m ∈ {2,4,8}, k ∈ {2,3,5}, H=180.

**This hypothesis was suggested by looking at data, and the registration says so first.**
L04 tested three session types on MGC; `sess_Asia` gave 5 of 18 nominal separations and
`sess_London` gave none. Asia was **selected by its result**.

Selection by result is not repaired by registering the survivor and re-testing it on the same
data — §38 refused that for L07's mirror and §43 refused it here. It **is** repaired by
testing the selected claim on data that did not generate it. MNQ is that data.

**The prediction is registered before the run**: a positive difference of +1.3 to +3.5 bps,
matching the MGC range. It confirms only on a positive mean **and** at least one BH survivor
at FDR 0.05 — both, not either. A positive point estimate that fails correction is *not* a
confirmation; that is what L04 already produced, and reproducing it without clearing the bar
leaves the claim where it was.

**MNQ only, and that is the point.** The two-instrument Stage 4 requirement cannot be met:
MGC generated the claim, so it cannot also validate it. An out-of-sample test that includes
the data it is validating against is not one.

**Power is short of the tabulated floor and the entry says so.** 4,903–5,442 firings against
a tabulated 5,884 at 180m — but that floor sizes the pipeline's *minimum* resolvable effect
(15.66 bps), not the +3.5 bps under test. MGC separated on 2,715 paired events. So this is
powered for the effect in question and a null is correspondingly weaker evidence than a null
at full power.

**The mechanism is unchanged and not strengthened by the MGC result.** Nothing about those
numbers makes session extremes more plausible as reference prices; the grade stays at C.

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
| — | L11 | measure rate AND placebo match first; weak mechanism, no prior weight |
| — | L12 | out-of-sample test of L04's Asia result on MNQ; prediction pre-registered |

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

---

# N-series — selectivity-first level hypotheses

Registered 2026-09-12 after the L-series closeout. **The design lever is selectivity, not
firing rate** (`decisions.md` §45): measured on L07, loosening 5.05× gives effect ×0.513
against bar ×0.364, so loosening wins statistically and loses economically, because the cost
floor is fixed and does not shrink with n.

Both entries below are sited at ~3–6.5 firings/session on 5-minute fractal pivots with
lookback **L = 20**. `L` is the dominant knob, not the penetration depth: at L=5 there are
286,257 pivots (69/session) and no value of `m` reaches the target band.

## N04 — Failed-Breakout Trap

**Params: 2** | **MNQ** | **Fires: 6.4–6.7/session (measured)**

Breakout entrants place stops back inside the level they broke; a failed break traps them and
their forced exit is price-insensitive supply. **The counterparty is the breakout buyer**,
who keeps doing it because breakout entry is the most widely taught retail pattern and the
losses get attributed to "fakeouts" rather than to the entry rule.

Entry on a **confirmed break** — first run of k=3 consecutive 5m closes beyond the pivot —
traded counter to it. **S5 passed** (entry-minute sd 327, up and down firing different
counts). **The §41 guard was verified to discriminate**, not merely to pass: on the opening
range it *raises* at 44.2% already-beyond against a 25% limit; on swing pivots it passes.

**S2: provable across the whole predicted range.** 2.0–5.0 bps against a BH bar of 1.42.

## N05 — Swing-Level Sweep and Reclaim

**Params: 2** | **MNQ** | **Fires: 3.2–4.0/session (measured)**

L03/L04's mechanism, whose failure was event count rather than logic. **The counterparty is
whoever was stopped or filled beyond the extreme.** `sweep_reclaim` at 5m pivots, m ∈ {16,24}
ticks, k=3.

**S2: STRADDLES, and this is the marginal registration.** 1.5–4.0 bps against a bar of
1.83–2.05 — the bottom of the range is unreachable. Registered under the surface-don't-reject
rule because the upper two thirds are reachable at eff/cost 5.7×. **A null from N05 is weaker
evidence than a null from N04.**

**N04 and N05 are not duplicates**: measured overlap 2.1% of shared (row, minute), because
N04 enters at the break bar and N05 at the reclaim bar.

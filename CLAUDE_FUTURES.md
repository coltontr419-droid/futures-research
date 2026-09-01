# MNQ / MGC Futures Research Pipeline — Project Spec

Persistent context for Claude Code. Read this before writing any code.

> **Hypothesis catalog:** the candidate strategies, their mechanisms, evidence grades,
> parameter caps and testing order live in
> [`FUTURES_STRATEGY_HYPOTHESES.md`](./FUTURES_STRATEGY_HYPOTHESES.md). The
> machine-readable registry is [`hypotheses.yaml`](./hypotheses.yaml).

> **Lineage.** This spec is adapted from the crypto research project. **Sections 5, 6 and 7
> are carried over unchanged** — the pipeline, the statistical-integrity rules and the
> integrity tests are instrument-agnostic and they worked. Sections 1–4 and 8–11 are
> rewritten: the data source, the venue, the cost structure and the constraints are all
> different. What the crypto project concluded is in its `reports/crypto_conclusion.md`,
> and the one-line version is that **ten hypotheses were resolved, zero promoted, and the
> binding constraint was economic rather than statistical** — every measured effect was
> smaller than an 8 bps commission floor. That floor is ~15× lower here, which is the
> entire reason this project exists.

---

## 1. Objective

Find and validate systematic intraday strategies for **MNQ (Micro E-mini Nasdaq-100)** and
**MGC (Micro Gold)** on CME, executed on a prop account.

The output of this project is **not** a strategy. The output is a *process* that can
honestly distinguish a real edge from noise, and that reports "nothing found" when nothing
is there.

### Non-goals

- Do not maximize backtest PnL.
- Do not search large parameter grids and select the winner.
- Do not add parameters to rescue a failing hypothesis.
- Do not build a live trading system in this repo.

### Definition of success

A run that tests 13 hypotheses and promotes zero of them is a **successful run**. A run that
promotes a strategy with Sharpe 4.0 is almost certainly a bug.

### What is different from the crypto project, and what is not

**Different — the arithmetic no longer forecloses the answer.** The crypto catalog measured
effects of 3–12 bps against an 8 bps floor, and the outcome was determined before testing
began. Here the floor is 0.48 bps on MNQ and several catalogued effects are documented at
1–50 bps.

**The same — most of these will still fail**, and the pipeline's job is to establish that
cleanly rather than to find a winner.

**Two things carried over from crypto must be RE-MEASURED, not inherited.** See §7.

---

## 2. Execution context (constrains everything downstream)

| Item | Value |
|---|---|
| Venue | CME Globex |
| Instruments | **MNQ** (Micro E-mini Nasdaq-100), **MGC** (Micro Gold) |
| Robustness only | ES / YM / RTY — ρ ≈ 0.9 with NQ, **never Stage 4 evidence** |
| Account | prop, with a trailing drawdown constraint |
| Hours | Globex 18:00 ET open, 17:00 ET close, 17:00–18:00 maintenance |
| **Hard exit** | **17:00 ET. Flat, no exceptions. See below.** |
| Contract handling | per-contract unadjusted, roll on volume crossover |

### The 17:00 ET hard exit is a HARD CONSTRAINT, not a preference

**Every position must be flat by 17:00 ET on every trading day.** A backtest that holds
through 17:00 ET is not an optimistic backtest — it is an invalid one, describing trades the
account cannot take.

Three consequences that bind on design, not just on execution:

1. **Every hypothesis declares a maximum hold that provably terminates before 17:00 ET.**
   A hold that *usually* finishes in time is a hold that fails on its worst day, which is
   the day that matters for a trailing drawdown.
2. **The time-stop is part of the signal, not part of the exit logic.** §5 Stage 1 forbids
   rescuing a hypothesis with exit rules. A hard 17:00 flat is a venue constraint that
   applies identically to every cell, so it is applied in Stage 1 and never tuned.
3. **It is less binding than it looks, and that is measurable.** The CME trading day runs
   18:00 ET to 17:00 ET, so an overnight hypothesis entering at 19:00 ET sits *inside* one
   trading day and never approaches the exit. Only US-session hypotheses reach it, and the
   cash close is 16:00 ET, so even a last-half-hour trade finishes an hour clear.
   `session.calendar.cme_trading_day` implements this and
   `tests/test_session_calendar.py` asserts it.

### Sessions are anchored in exchange local time, never in ET

| session | anchor | ET |
|---|---|---|
| CME open | 17:00 America/Chicago | 18:00 ET always |
| Tokyo cash open | 09:00 Asia/Tokyo | 19:00 ET winter / 20:00 ET summer |
| London cash open | 08:00 Europe/London | **03:00 ET, or 04:00 ET when offsets diverge** |
| US cash | 09:30–16:00 America/New_York | fixed |
| hard exit | 17:00 America/New_York | fixed |

**DST is the single most likely source of a silent bug in this catalog.** The US and Europe
shift on different dates, so for roughly four weeks a year the gap between London and New
York is four hours rather than five. A one-hour misalignment in those weeks produces real
returns from the wrong hour, and nothing downstream would flag it.

> **A correction to the catalog, measured 2026-08-28.** `FUTURES_STRATEGY_HYPOTHESES.md`
> states that the London open "sits at 03:00 ET most of the year and 02:00 ET for a few
> weeks each spring and autumn." **The direction is inverted — it is 04:00 ET, and 02:00
> never occurs.** During divergence the US has sprung forward and Europe has not, so
> London's fixed local open lands one hour *later* in ET, not earlier. 02:00 ET would
> require Europe on summer time while the US is on standard time, and EU summer time is
> entirely nested inside US daylight time, so that combination cannot happen.
> `test_session_calendar.py` asserts the 04:00 result and asserts 02:00 is unreachable
> across three years, so the catalog's number cannot be reintroduced by trusting the prose.

Sessions live in `futuresres.session.calendar`, defined in local time with the ET
expression derived. **Never store a session as a fixed ET offset.**

---

## 3. Data layer

### Source

**Databento, dataset `GLBX.MDP3`** — CME Globex MDP 3.0. Credentials are in `.env`
(gitignored; `.env.example` records the required keys).

This is a different arrangement from the crypto project, and the difference matters: Binance
publishes flat files anyone can fetch, so the downloader was idempotent against a stable
public URL. Databento delivers a **batch job** to per-request FTP paths. The extract is a
fixed deliverable, not a queryable endpoint, so the repo treats it as an immutable input to
be validated rather than a source to be re-fetched at will.

### Schemas to pull

| schema | purpose |
|---|---|
| `ohlcv-1m` | primary bars |
| `definition` | contract metadata: expiry, symbol mapping, `instrument_id` resolution |
| `ohlcv-1d` | daily volume, for the roll rule |
| `mbp-1` *(not yet)* | top-of-book, for a spread measurement — do not pull until needed |

Symbols: `MNQ`, `MGC` as parents; the raw data is **per contract** (`MNQZ5`, `MGCG6`, …).

### Per-contract roll handling — this is the part that goes wrong quietly

Futures are not one series. They are a sequence of contracts, and how they are joined
decides what a "return" means.

**The rule, and it is not negotiable:**

1. **Store per-contract, unadjusted.** Never write a back-adjusted continuous series to
   disk as though it were price data. Back-adjustment shifts historical prices by the
   accumulated roll gaps, which corrupts any level-based condition (a round number, a
   prior day's high) and silently changes what a percentage return means.
2. **Roll on volume crossover.** The front contract is the one with the highest daily
   volume. When the next contract's daily volume exceeds the front's, the roll date is that
   day.
3. **DROP THE CROSSOVER SESSION ENTIRELY.** Do not stitch across it. The session where
   volume crosses has liquidity in both contracts and a price gap between them; any return
   computed across the join is an artifact of the join, not a market move. Dropping one
   session per quarter costs ~64 sessions over 16 years and removes an entire class of
   phantom result.
4. **Returns are computed WITHIN a contract, never across a roll.** Any windowed
   calculation — a trailing σ, an ATR, a multi-day range — must not span a roll boundary.
   A validator asserts this.
5. **Record the roll dates as an artifact.** `reports/roll_calendar.md` lists every roll,
   its contracts and its volume figures. A roll rule that cannot be inspected is a roll rule
   that cannot be debugged.

### Storage

- Parquet, partitioned by `symbol` / `contract` / `year` / `month`.
- Query with DuckDB or Polars. Do not load full history into pandas.
- All timestamps **UTC, tz-aware**. Never naive datetimes. Never local time. Session
  membership is derived through `session.calendar`, never by string-slicing an ET clock.
- Canonical bar schema:
  `ts_event, symbol, contract, open, high, low, close, volume, trades`


### STANDING CAVEAT: MGC trades only ~71% of RTH minutes

Measured 2026-09-01 while running F03, on the front-month continuous series reindexed to
the 390-minute RTH session:

| instrument | RTH minutes actually traded |
|---|---|
| MNQ (spliced NQ+MNQ) | **98.31%** |
| **MGC** | **70.85%** |

**This applies to every MGC result, not to one hypothesis.** Nearly three minutes in ten
inside US cash hours have no trade, so any analysis on a fixed minute grid is carrying the
last price forward across them.

Two consequences, and the second is the one that matters:

1. **A carried price is a stale price.** Any condition keyed to a specific minute — a slot
   open, a session anchor, a settlement window — may be reading a quote from several minutes
   earlier, so the return attributed to that minute partly belongs to an earlier one.
2. **Forward-filling inserts zero returns, which thins measured volatility.** A thinner
   denominator inflates every t-like quantity built on it. The direction of the bias is
   toward APPARENT SIGNIFICANCE, which means an MGC **null is weaker evidence than the same
   null on MNQ**, while an MGC **positive is weaker evidence still**.

**How to treat it.** An MGC result that agrees with MNQ is fine. An MGC result that stands
alone — positive or null — carries a discount, and the report must say so rather than
present the two instruments as equals. Where a hypothesis is retired on the strength of
both, state which instrument actually carried the verdict; for F03 it was MNQ at 98%
coverage, and MGC alone would not have been enough.

This is not a data fault. `ohlcv-1m` emits no bar for a minute with no trade (§3, checks 5
and 6), and MGC is simply a thinner book than MNQ. It is a property of the instrument that
every MGC analysis inherits.

### Validation (run before any research; fail loudly)

1. **Gap check** — enumerate expected 1m timestamps *within each session*, report every
   missing bar. Futures have real closed periods; a validator that does not know the session
   calendar will report the maintenance window as a data gap on every single day.
2. **Duplicate check** — assert unique on `(contract, ts_event)`.
3. **OHLC sanity** — assert `low <= min(open, close)` and `high >= max(open, close)`.
4. **Outlier scan** — flag any 1m return exceeding 10σ of trailing 30d realized vol.
5. **Zero-volume runs** — flag consecutive bars with `volume == 0`.
6. **Zero volume with a live range** — flag any bar where `volume == 0` but `high > low`,
   reported separately from item 5. A genuinely quiet minute prints no trades *and* no
   range; zero volume against a real spread is a synthesized or carried-forward bar.
7. **Roll integrity** — assert no window spans a roll, assert the crossover session is
   absent, and assert every contract's data ends at or before its expiry.
8. **Session coverage** — assert every expected RTH session is present, and that the
   session mapper's boundaries contain the bars they should on both sides of every DST
   transition.

Write validation output to `reports/data_quality.md`. Do not proceed with unresolved
failures.

---

## 4. Cost model

Costs are a **parameter object**, not hardcoded constants. Every backtest runs at 1× and 2×.

```python
@dataclass
class CostModel:
    commission_bps: float          # per instrument, see table
    spread_bps: float              # per instrument, see table
    slippage_bps: float | None = None    # NOT measured
    latency_seconds: float = 1.0
```

| instrument | notional | commission | + spread | **round trip** |
|---|---|---|---|---|
| **MNQ** | ~$48k | 0.38 bps | 0.10 | **0.48 bps** |
| **MGC** | ~$40k | 0.53 bps | 0.12 | **0.65 bps** |
| NQ (mini) | ~$480k | 0.12 bps | 0.10 | 0.22 bps |
| ES (mini) | ~$335k | 0.17 bps | 0.10 | 0.27 bps |

> **This is the single reason the project is worth restarting.** The crypto catalog died
> against an 8 bps floor. **MNQ's floor is 0.48 bps — roughly 17× lower.** Effects of 3–12
> bps, the range that closed the entire crypto catalog, are comfortably tradeable here.
>
> **The micro/mini trade-off is real, not free.** Minis are ~3× cheaper in bps: same tick,
> 10× notional, only 3.2× commission. Prop trailing-drawdown rules push toward micros. The
> cost model therefore carries both, and any result must state which contract it assumes.
>
> **Spread is included above but is an estimate, not a measurement.** It is a far smaller
> share of total cost than it was in crypto, where it was the decisive unknown — but it is
> still unmeasured. A `mbp-1` pull would measure it; do not pull until a candidate's
> economics actually turn on it.
>
> **A pairs trade pays both legs.** F08 crosses MNQ and MGC, so its floor is 1.13 bps, not
> 0.48. Any cross-instrument hypothesis must charge both sides.

- **Latency:** entries fill at the price `latency_seconds` after bar close, not at the
  close. Model this explicitly using the next bar's path.
- Any strategy that dies at 2× costs is not a strategy.
- **Every strategy must beat scaled buy-and-hold.** Index futures have real drift and a
  long-biased intraday strategy inherits it. This is the drift-attribution bug from the
  crypto project arriving as a design requirement — see §5 Stage 1, "A long/short signal
  must be scored against its own exposure."
- **Every strategy must beat a random-entry benchmark** with matched holding-time
  distribution and matched trade count.

---

### Two carried-over calibrations that are WRONG here until re-measured

**Sections 5, 6 and 7 below are carried over from the crypto project byte-for-byte.** They
are the pipeline, the integrity rules and the integrity tests, and they are
instrument-agnostic. But two *numbers* inside them were measured against crypto's return
distribution, and crypto's return distribution is not this one.

**BTC measured kurtosis 199.9 at 1m and 66.9 at 60m. Index futures run an order of
magnitude lower.** Two things follow, and both must be re-measured before any Stage 1
result here is believed:

| carried-over | where | why it is wrong here | expected direction |
|---|---|---|---|
| **Stage 1 bootstrap α calibration** — `COVERAGE_CALIBRATION` in `signals/stage1.py`, nominal α of 0.031–0.050 by block count | §5 Stage 1 | fitted so a percentile interval actually covers 95% **on crypto tails**. A thinner tail needs a different nominal α, and using crypto's will mis-state coverage in an unknown direction | unknown — measure, do not assume |
| **Detection floor — 0.1592× one-minute volatility** | §7 | measured on GARCH calibrated to BTC moments. Lower kurtosis should lower the floor | should **improve** |

A third consequence is favourable and also unverified: the **46-event DSR wall** — below
which no effect size clears DSR at any magnitude — is a kurtosis artifact of
`N_min = 2·√((N−1)/(γ₄−1))`. At γ₄ ≈ 8 rather than 67 it falls to roughly **5 events** and
should effectively disappear.

> **All three are predictions, not findings.** They are written here so they are not quietly
> inherited as facts. The entire lesson of the crypto project was that assumed statistical
> properties get falsified by measurement — the drift-attribution bug survived four
> hypotheses precisely because nobody re-derived a statistic that "obviously" worked.
>
> **Build-order step 8 is where these get re-measured**, and no Stage 1 verdict is quotable
> until it has run. Until then, treat every §7 number below as *the crypto value*, clearly
> labelled as such, and treat the floor as unknown rather than as 0.1592×.

---

## 5. Research pipeline

Strictly staged. Each stage kills candidates. Nothing skips ahead.

### Stage 0 — Hypothesis registration

Every hypothesis is registered in `hypotheses.yaml` **before** it is tested:

```yaml
- id: H007
  name: funding_extreme_reversion
  mechanism: >
    Extreme positive funding indicates crowded long positioning financed at high cost.
    Leveraged longs are forced out when price stalls; the unwind produces short-horizon
    downside. Counterparty is the over-leveraged retail long.
  condition: funding_rate_8h > 95th percentile trailing 90d
  horizon_minutes: [60, 240, 1440]
  registered: 2026-08-22
  status: untested
```

If the `mechanism` field cannot be written in plain language, the hypothesis is rejected.

### Hold duration cannot solve a detection problem

Assess a hypothesis on its **firing rate before its mechanism**. A condition that fires too rarely is undetectable at any hold, with any mechanism, however good the story is.

The arithmetic. Required events for 80% power are

    n = ( (z_{1−α/2} + z_power) · σ_h / effect_h )²

With σ_h ∝ h^0.5 and effect_h ∝ h^a, this gives **n ∝ h^(1−2a)** — so the requirement falls with hold when a > 0.5 and rises when a < 0.5. On S01 the measured exponent was **a = 0.736**, and the requirement duly *fell*, from 41,016 events at a 1-hour hold to 2,764 at 24 hours. **Longer holds did help.**

They still could not fix it, and the reason is the one that generalises: **a longer hold cannot create observations.**

| | |
|---|---|
| once-daily condition, full 6.6-year sample | **≈ 2,426 events maximum** |
| requirement at the most favourable hold (S01) | **≈ 2,100 events** |
| S01's actual firing count after its threshold | **464** |

The ceiling on a daily condition and the requirement are the **same order of magnitude**. There is no headroom at any hold, and a selectivity filter — S01's `k` cut it to 19% of the cap — spends what little exists. At the volatilities measured here (σ of 120–514 bps across 1h–24h), a daily-firing condition is at or below the floor before any filter is applied.

**Consequences for Stage 0.** Before writing a mechanism, state the expected firing rate and check it against this table. A hypothesis whose condition fires once a day or less is a candidate for the trial budget only if its expected effect is large enough that a few hundred events suffice — which, at these volatilities, means tens of basis points. If it is not, the honest options are a condition that fires more often, a lower-volatility instrument, or not registering it.

> An earlier version of this section, and of S01's retirement note, said the requirement *rises* with hold. That was wrong — it inverts the exponent. The conclusion survives the correction because it never depended on that step, but the reasoning did and is fixed here.

### Stage 1 — Signal-level separation (no strategy, no stops, no targets)

For condition X, compute the distribution of forward returns at each horizon vs the unconditional distribution.

Report: mean shift, median shift, hit rate, information coefficient, sample count, and a **bootstrap confidence interval on each**. A Newey-West t-stat (adjusted for overlapping windows) may be reported alongside as a descriptive statistic, but it is not the basis for any accept/reject decision — see immediately below.

#### Return distributions are heavy-tailed — measured, not assumed

At 10σ of trailing 30-day realized vol, **~0.05% of 1m bars exceed the threshold** (1,695 of 3,494,880 on BTCUSDT; 1,616 of 3,494,880 on ETHUSDT) where a Gaussian predicts essentially none — 10σ carries a normal probability near 1e-23. Those exceedances were checked and are real, not bad prints: none is a move under 0.1%, none sits on a zero-volume bar, every one is volume-backed, and they cluster on known event dates (2020-03-12, 2021-05-19, 2024-08-05, 2025-02-03). Evidence: [`reports/data_quality.md`](./reports/data_quality.md), check 4.

Three consequences, binding on every stage that computes a statistic:

1. **Use non-parametric tests and bootstrap confidence intervals, not normal-theory t-stats.** A t-stat on this data assumes a tail that demonstrably is not there, and it fails in the dangerous direction — the tail carries the losses. Prefer a stationary or block bootstrap, which also preserves the serial dependence that Newey-West exists to correct for, and take the interval from the empirical resampling distribution.
2. **Any σ-based threshold must be justified against the empirical distribution, not assumed.** "A 3σ move" is not a definition on this series. State the empirical quantile it corresponds to, on this symbol and this era. Any hypothesis whose condition is written in σ must be restated in quantiles before it is tested.
3. **Report empirical quantiles, not sigma multiples,** wherever a distribution is summarized.

Corollary for §6: Sharpe is itself a normal-theory statistic and understates tail risk on a series like this. That is a further reason the **Deflated** Sharpe is the reported metric, and why §7.4 sizes against the 95th-percentile bootstrap drawdown rather than the realized one.

#### A long/short signal must be scored against its own exposure

**Compare a signal to what it would have earned taking the same long/short decisions at other times — never to a long-only baseline.** Mixing exposures puts the asset's drift into the statistic, and the drift is not something the signal predicts.

This was a live defect, found 2026-08-27 during S09 and present in every signed Stage 1 run before it. `evaluate_cell` built its return series with off-event bars oriented **long**, so the unconditional mean was the asset's long-only drift while the observed statistic was the signal's roughly 50/50 mix. The gap between the two exposures *is* the drift:

| cell | per-event return | statistic as computed |
|---|---|---|
| S09 SOL pct20 k1.5 h60 | +4.76 bps | +2.34 bps |
| S09 BTC pct20 k1.5 h60 | +0.05 bps | **−1.24 bps** |

The bias runs **negative** for a market-neutral signal in a rising sample, so it does not fail safe — it manufactures apparent short edges. Measured on 400 GARCH nulls with no edge by construction (a constant drift is not an edge; nothing observable predicts it):

| null | biased statistic | corrected |
|---|---|---|
| no drift, 200 reps | 0.070 ± 0.018 | 0.080 ± 0.019 |
| **drifting, 200 reps** | **0.180 ± 0.027** | **0.055 ± 0.016** |

At a nominal α = 0.05 the biased statistic rejected at **3.6×** the intended rate, 4.8 SE above nominal. The arms agreeing when there is no drift is what identifies the cause as drift attribution rather than a general miscalibration.

**The corrected estimator is `stage1.evaluate_signed_signal`.** It rotates the *signed* indicator against the raw forward return:

```
stat[k] = (1/n_sig) · Σ_t d[t] · F[(t+k) mod n],   d ∈ {−1, 0, +1}
```

k = 0 is the observed per-event mean by construction, so the point estimate and the null are the same quantity at different alignments. The null's centre is `(Σd/n_sig)·mean(F)` — exactly what the signal's net exposure earns from drift — so the charge is removed rather than assumed away. Cost is one FFT pair, the same as before.

**The property to test is exact drift invariance,** not approximate agreement: adding a constant drift to the price series must not move the statistic at all. `tests/test_signed_stage1.py` asserts it to 1e-15, and holds a companion test that pins the old behaviour so the defect cannot return unnoticed.

**Per-event means were never affected** — they are computed directly from the signed return and carry no baseline. Any finding resting on effect *sizes* rather than on pass/fail survives this correction unchanged; S04's cross-instrument sign disagreement is one such finding, and S01's scaling exponents are another.

**Gate:** if there is no separation at the signal level, STOP. Do not attempt to rescue it with exit logic. If a clever exit is required to make it profitable, the exit has become the strategy and the hypothesis is unsupported.

### Stage 2 — Event study

Mean cumulative return over ±240 minutes around the condition, with bootstrap confidence bands.

**Gate:** real effects build gradually and have shape. A single spiky bar is an artifact.

### Stage 3 — Regime stability

Split by regime and report each separately — never only the aggregate:

| regime | bars (BTCUSDT 1m) | share | detection floor here |
|---|---|---|---|
| 2020–21 (extreme bull) — **expect this to dominate; discount accordingly** | 1,052,640 | 30.1% | 0.0461× |
| **2022 (bear)** | **525,600** | **15.0%** | **0.0575×** |
| 2023–24 | 1,052,640 | 30.1% | 0.0461× |
| 2025–26 | 864,000 | 24.7% | 0.0491× |

**Gate:** must hold in at least one bear regime. An effect present only in 2020–21 is a description of that regime, not an edge.

> **The bear regime is the shortest split, so this gate has the least power behind it.** At 525,600 bars its detection floor is 0.0575× — the only regime that fails the 0.05× mark, and roughly 1.8× weaker than full history (§7, [`reports/pipeline_power.md`](./reports/pipeline_power.md)). An effect can therefore be real, clear full history, and still be undetectable in the one regime this gate insists on.
>
> Consequence for how a Stage 3 result is read: **a bear-regime failure is much weaker evidence of absence than a full-history failure**, and must not be reported as if the two were equivalent. Where a candidate passes elsewhere and fails only in 2022, say so explicitly and give the bear-regime effect size against the 0.0575× floor rather than treating the failure as settled. This does not relax the gate — an effect that cannot be seen in a bear market still cannot be traded through one — it constrains the claim the failure supports.

### Stage 4 — Cross-instrument confirmation

Test the identical, unchanged condition on ETH, SOL, XRP.

**Gate:** must appear in at least two instruments, **and the confirming set must include at least one of SOL or XRP. BTC + ETH alone does not satisfy this stage.**

#### Why the gate is written that way — measured, not assumed

The original reasoning was that "correlated instruments provide nearly free out-of-sample evidence." The word doing the work is *correlated*, and it cuts both ways: a confirmation is only evidence to the extent the second instrument could plausibly have disagreed. Measured over 3,124,380 aligned bars, 2020-09-14 → 2026-08-23 ([`reports/cross_instrument.md`](./reports/cross_instrument.md)):

| pair | ρ (1m) | ρ (1h) | ρ (1d) | P(spurious hit replicates) | inflation vs independence |
|---|---|---|---|---|---|
| **BTC / ETH** | 0.806 | **0.835** | 0.821 | 0.0539 | **22×** |
| ETH / SOL | 0.625 | 0.686 | 0.661 | 0.0379 | 15× |
| BTC / SOL | 0.611 | 0.647 | 0.604 | 0.0346 | 14× |
| ETH / XRP | 0.613 | 0.628 | 0.612 | 0.0331 | 13× |
| BTC / XRP | 0.598 | 0.601 | 0.566 | 0.0311 | 12× |
| SOL / XRP | 0.501 | 0.540 | 0.492 | 0.0269 | 11× |

Under the null, a spurious hit replicates on a second instrument **11–22× more often than independence would predict** (α² = 0.0025 at a one-sided α = 0.05 on each). The four instruments together carry **N_eff = 1.73 effective independent series, not 4**. Correlation also rises slightly with horizon, so the gate is thinnest where most of the catalog operates.

**BTC + ETH is the worst possible confirming pair at 22×** — close to one instrument observed twice. SOL and XRP sit at ρ ≈ 0.54–0.65 and carry materially more independent evidence, which is why at least one of them is now required. Name which instruments confirmed, not merely that two did.

#### How to read the result

- **Passing Stage 4 is weak evidence.** It is not free out-of-sample evidence at these correlations. The §6 corrections, the walk-forward and the holdout carry the weight instead.
- **Failing Stage 4 is strong evidence.** This is the useful asymmetry: when instruments this correlated *disagree*, something instrument-specific is driving the result, and that is usually a data or microstructure artifact rather than an edge.
- **Stage 4 is NOT counted as an independent trial** in the §6 deflation math. It is not a fresh look at fresh data, and counting it as one would inflate N in the direction that flatters the result.

### Stage 5 — Minimal strategy

Only now wrap it in entries/exits.

- **Hard cap: 4 parameters.** No exceptions.
- Coarse grid only: 3–5 values per parameter.
- Round, a-priori values (20/50/200, not 47).
- **Bar-close decisions only.** No intrabar stops in the research engine — path dependency reintroduces the fill ambiguity this design exists to avoid.
- Record MAE/MFE from bar highs/lows separately so intrabar excursion is still *measured* even though it is not *acted on*.

### Stage 6 — Robustness

- Perturb every parameter ±20%; result must survive.
- Plot the parameter surface. **Require a plateau, reject a spike.**

### Stage 7 — Walk-forward

Anchored or rolling, with genuine re-fit at each step. Report walk-forward efficiency (OOS return ÷ IS return). Below 0.5 → reject.

### Stage 8 — Holdout

Final 25% of history. **Touched exactly once.** If it is examined a second time, it is training data and the strategy is dead.

### Stage 9 — Port verification

Implement in Pine Script v6. Export Python signal timestamps and Pine `strategy` fills over the same window and **diff bar by bar**. Any discrepancy must be resolved before going live.

Pine config requirements:

- `calc_on_every_tick = false`
- Alerts set to **once per bar close**
- No `request.security` lookahead

### Stage 10 — Sim

Route through AlgoWay to a demo/eval account. Measure real spread, slippage, and latency. Feed the measured values back into Stage 5 and re-verify the strategy still survives.

---

## 6. Statistical integrity — non-negotiable

### Trial log

Every backtest run — including abandoned and hand-tweaked ones — appends **one JSON object per line** to `trials.jsonl`:

```json
{"trial_id": "t0417", "hypothesis_id": "S03", "timestamp": "2026-08-24T18:02:11Z", "params": {"lookback": 50, "threshold": 2.0}, "symbol": "BTCUSDT", "date_range": ["2020-01-01", "2026-08-23"], "sharpe": 0.41, "sortino": 0.58, "total_return": 0.12, "max_dd": -0.19, "trade_count": 431, "profit_factor": 1.07, "status": "abandoned"}
```

The trial count `N` is the input to every correction below. Silent trials invalidate the math.

**Append-only, and committed to git.** Both halves are load-bearing:

- *Append-only* — never rewrite a line, never delete one, never edit one in place. A trial later found to be a bug is superseded by a new record that references it, not erased. Deleting a bad trial lowers `N`, and **every correction below moves in the optimistic direction when `N` falls** — so quietly tidying the log is indistinguishable from inflating the results.
- *Committed* — the log is evidence, not a generated artifact. A gitignored log is one `git clean` away from a reset `N`, and nothing about the resulting Deflated Sharpe would look wrong. Its history is also the audit trail: `git log -p trials.jsonl` shows when each trial was run and demonstrates that nothing was removed after the fact.

JSONL rather than parquet for exactly this reason. Parquet is a columnar binary format: it cannot be appended to without rewriting the whole file, every rewrite is an opportunity to silently drop rows, and the result cannot be diffed or reviewed. A line-delimited text log appends without touching what is already on disk, a merge conflict resolves by keeping both sides, and every added trial is visible in a diff.

#### Do Stage 1 tests enter the trial count? **Yes.**

They produce no Sharpe, so the instinct is that they cannot enter a correction built on the *maximum Sharpe*. That instinct is wrong, and the reason matters more than the ruling.

The DSR deflates by SR\* = E[max Sharpe over N trials] — the bar a winner must clear once you account for having *chosen* it. What makes a chosen Sharpe biased is not that its rivals' Sharpes were computed; it is that the choice was made **using the same returns**. Stage 1 is exactly such a choice. It reads the same data, and a configuration that clears it is more likely to show a high Sharpe by luck. So the survivors handed to Stage 5 are a pre-filtered, upward-biased sample, and counting only the survivors understates N by the whole width of the search.

The counterfactual makes it clean: if Stage 1 were a coin flip, it would not bias anything and would not count. It is not a coin flip — it is correlated with Stage 5 performance by construction.

**Operational consequence: compute and log a Sharpe for every configuration tested, including those that fail Stage 1.** The DSR needs both N *and* V, the dispersion of trial Sharpes, and V estimated over survivors alone is the same error a second time. The Sharpe of a failed configuration costs nothing to compute and is what keeps `trials.jsonl` honest.

**What counts as one family.** N is the trial count of the family the reported result was selected from:

- a claim about **one hypothesis** ("S04 shows an edge") → N is that hypothesis's own grid, across every stage
- a claim about **the catalog** ("we searched and found S04") → N is every trial run across every hypothesis

Both are legitimate; reporting the first while having done the second is not. State which claim is being made alongside the number.

**A Stage-1-only hypothesis still consumes trials.** One that cannot reach Stage 5 — S14, below its event floor — still adds its grid to the catalog-level N whenever a cross-catalog claim is made, raising SR\* for every hypothesis that *can* be promoted. Testing it is not free; it is paid for by the others. That is a reason to sequence it deliberately, not a reason to leave it out of the count.

### Required corrections

| Metric | Requirement |
|---|---|
| **Deflated Sharpe Ratio** | Bailey & López de Prado. Adjust for N trials, dispersion of trial Sharpes, skew, kurtosis. **Primary reported metric.** |
| **PBO via CSCV** | Combinatorially symmetric cross-validation. **Reject if > 0.5.** |
| **Reality Check / SPA** | White / Hansen bootstrap over the full trial set. |
| **Multiple comparisons** | Benjamini-Hochberg FDR on any scan over many cells. |

### Calibration — what a real edge looks like

| Metric | Plausible | Suspicious |
|---|---|---|
| Sharpe (net) | 0.8 – 1.5 | > 2.5 |
| Profit factor | 1.1 – 1.35 | > 1.8 |
| Win rate | 45–55% | > 65% |
| Trade count | > 200 | < 100 = no information |
| Top-5-trade share of PnL | < 30% | > 50% = fitted |

If a result lands in the "suspicious" column, the prior that it is a **bug** — lookahead, a timezone error, an impossible fill — is far higher than the prior it is an edge. Hunt the bug first.

---

## 7. Integrity tests — build these BEFORE the first backtest

These are the load-bearing components. Without them the pipeline generates confidence, not knowledge.

> **Detection floor: 0.16× one-minute volatility — and it does not move.** Measured in [`reports/pipeline_power.md`](./reports/pipeline_power.md) on 20,000-bar series across four configurations, 25 reps per cell:
>
> | configuration | trials/run | floor | rung below |
> |---|---|---|---|
> | baseline — 10m / 1h / 4h | 45 | **0.1592×** | 0.0845× @ 60% |
> | 1h horizon only | 15 | **0.1592×** | 0.0845× @ 68% |
> | 3h horizon only | 15 | **0.1592×** | 0.0845× @ 52% |
> | BTC+ETH pooled | 45 | **0.1592×** | 0.0845× @ 60% |
>
> **No configuration reaches 0.05×; the best is 3.2× above it.** Cutting trials from 45 to 15 — two-thirds off the multiple-testing burden the DSR deflates away — did not shift the floor by one rung, which says the binding constraint is sample information rather than trial count. Pooling BTC with ETH cannot help either: at the measured ρ = 0.801 a two-leg basket buys a 1.054× SNR gain against the 1.414× independent instruments would give, and pooling the sample rather than the prices gives the same 1.054× because two series correlated at ρ carry effective sample size 2n/(1+ρ). There is no version of "use both instruments" that escapes ρ.
>
> **Sample length is the only lever that moves it — and it moves slower than √n.** Measured at three sizes, baseline configuration, every other parameter held fixed:
>
> | bars | floor | vs 20k | √n would predict |
> |---|---|---|---|
> | 20,000 | 0.1592× | 1.000× | 1.000× |
> | 200,000 | 0.08446× | 0.531× | 0.316× |
> | 1,000,000 | 0.04481× | 0.282× | 0.141× |
>
> **Fitted exponent −0.321, not −0.5.** Assuming √n would have overstated the benefit of more data by ~2.6× at full history. Extrapolating the fitted exponent:
>
> | sample | bars | fitted floor | clears 0.05×? |
> |---|---|---|---|
> | full history | 3,494,880 | 0.0313× | yes |
> | 2020–21 / 2023–24 | 1,052,640 | 0.0461× | yes |
> | 2025–26 | 864,000 | 0.0491× | yes |
> | **2022 (bear) — shortest** | **525,600** | **0.0575×** | **no** |
>
> These are extrapolations beyond the largest size swept, and they assume a stationary edge; treat them as optimistic bounds. Re-measure whenever the candidate family or series length changes.
>
> **Below the floor a "nothing found" result carries no information**, because nothing would have been found either way. Every §7.2 null must be read against it.

### 7.1 Causal re-derivation test

Re-derive every signal from a strictly causal reconstruction and require **exact equality**.

For each checked bar *t*, feed the signal function only `returns[:t+1]` and compare its value at *t* against the value the vectorized path produced on the full series:

```
signal_fn(returns[:t+1])[t]  ==  signal_fn(returns)[t]
```

A causal function cannot change its answer at *t* when data after *t* is removed. Any disagreement is lookahead, and the first mismatching index points at the bar where it happens. There is no effect size, no horizon, and no statistical power to run out of.

**Independence is structural, not duplicated.** The obvious construction — write a second loop-based implementation and compare — fails the way two implementations by one author usually agree: a shared misunderstanding cancels out and both are wrong together. Feeding a *prefix* to the same function tests the property directly and needs no second copy kept in sync.

> **Calibrated: +100% discrimination at every cell.** Leaks of 1, 5 and 20 bars injected into a clean signal, 25 reps per cell, across signal windows 5–240 ([`reports/pipeline_power.md`](./reports/pipeline_power.md)):
>
> | signal window | clean (false +) | leak 1 | leak 5 | leak 20 | discrimination |
> |---|---|---|---|---|---|
> | 5 / 10 / 30 / 60 / 240 | **0%** | 100% | 100% | 100% | **+100%** |
>
> Detection is invariant to signal timescale and to leak span, including the **one-bar** leak. It also catches leak classes no shift-based test can see at all — a full-series mean used for standardisation, an off-by-one forward shift — because those change the answer under truncation like anything else.
>
> A clean result is only as strong as `n_checked`, which is reported: cost is O(n · checks), so bars are sampled rather than exhausted. A leak touching most bars is caught by the first check; one confined to a handful of bars needs more.

> **This replaced the shift test, which was removed rather than kept alongside.** The original §7.1 — shift the signal forward one bar, expect the edge to degrade — calibrated at **negative discrimination at every horizon**: clean persistent signals flagged 96–100%, a pure one-bar leak flagged 0%. Delaying by one bar removes exactly the bar such a leak read, so the leak collapsed and looked clean while a legitimately persistent signal barely moved and looked guilty. It measured persistence, not lookahead. A known-broken detector left in the codebase is an invitation to read its output as evidence, so it is gone; the measurement survives in the report.

### 7.2 Synthetic noise test

Run the complete pipeline on data with **no edge by construction**:

- Bootstrap-shuffled returns (destroys serial structure, preserves distribution)
- GARCH(1,1) simulated series with realistic vol clustering
- Random-walk with matched drift and volatility

**The pipeline must report "nothing found."** If it promotes a strategy on synthetic noise, the pipeline is broken and every result it has ever produced is void. Run this on every material change to the harness.

> **A drifting null belongs in this set, and it caught a real defect.** GARCH with a constant `mean` is still a pure null — a constant drift is not an edge, because nothing observable predicts it — but it is the arm that exposes an estimator which mis-attributes drift to the signal. On 2026-08-27 the Stage 1 statistic measured **0.180 ± 0.027 false positives against a nominal 0.05** on that arm while sitting at 0.070 ± 0.018 on the zero-drift arm (§5 Stage 1). A zero-drift-only test would have passed it.
>
> **Run both arms.** An estimator that is calibrated on driftless noise can still be badly wrong on a real series, and every series in this project drifts.

> **A replacement estimator must be calibrated before it is believed, not after it produces a nicer number.** The temptation on finding a bug is to fix it, observe that the p-values improved, and move on — which is indistinguishable from choosing the estimator that flatters the result. The order is: state the property the correct estimator must have, assert it exactly where possible (drift invariance is exact, so it is tested to 1e-15), then measure the false-positive rate on data where the answer is known to be nothing. Only then look at what it says about real data.

### 7.3 Shuffled-label test

Randomly permute the condition flags against the return series. Effect size must collapse to zero.

### 7.4 Monte Carlo drawdown distribution

Realized max drawdown is **one draw from a distribution**, not a property of the strategy.

- Trade-order shuffle, 10,000 iterations
- Block bootstrap on daily returns
- Report the 95th percentile drawdown, and size against **that**, not the backtest figure

---


---

## 8. Output artifacts

### `reports/strategy_scan.xlsx`

One row per surviving candidate:

**Identity:** hypothesis_id, params, instrument, contract, date range
**Returns:** gross PnL, net PnL, CAGR, expectancy per trade (bps)
**Risk:** max DD, MC 95th pct DD, DD duration, max consecutive losses, MAE/MFE distribution
**Ratios:** Sharpe, **Deflated Sharpe**, Sortino, Calmar, profit factor
**Integrity:** trial count N, PBO, walk-forward efficiency, top-5-trade PnL share
**Sensitivity:** net PnL at 1× / 1.5× / 2× costs, micro *and* mini
**Stability:** per-year return, per-regime return, long vs short split, by-session split
**Prop fit:** worst intraday drawdown against the account's trailing limit; latest exit time

Sort by **Deflated Sharpe**, not by PnL. Highlight any row failing a gate in red.

### `reports/roll_calendar.md`

Every roll: date, outgoing and incoming contract, both volumes, and the dropped session.
Generated, never hand-maintained.

### `reports/session_map.md`

Every session anchor for a sample of dates spanning both DST transitions in both zones,
including the divergence weeks. This is the artifact that makes a timezone bug visible to
inspection rather than only to a test.

### `reports/eda/` — visual exploration (generated, not hand-scrolled)

- Half-hour-slot × day-of-week return heatmap, with bootstrap intervals, faceted by year
- Conditional vs unconditional forward-return distributions
- Event-study panels (200 aligned instances + median path)
- Volatility and volume by minute-of-session, **separately for RTH and overnight**
- Return autocorrelation by horizon
- Realized kurtosis by horizon, per instrument — the input to the §7 re-measurement
- **Event counts for every pre-specified event hypothesis**, per cell and per regime

---

## 9. Build order

1. Repo scaffold, this file at root
2. Environment: `polars duckdb numpy scipy statsmodels pyarrow matplotlib pytest tzdata`
3. **Session mapper (§2)** ← before the downloader, and before anything session-anchored
4. Databento extract handling: per-contract, roll on volume crossover, drop the crossover
   session
5. Data validators (§3) → `reports/data_quality.md`
6. **Trial log + DSR + PBO implementations** ← before any backtest
7. **Integrity tests (§7)** ← before any backtest
8. **Re-measure the two carried-over calibrations (§7)** ← before believing any Stage 1 result
9. EDA notebook (§8) — look at output before writing a strategy
10. Stage 1–2 signal testing harness
11. Backtest engine (bar-close only, cost model injected, 17:00 ET flat enforced)
12. Reporting layer

Steps 6 and 7 come before step 11. **The session mapper comes before the downloader**, which
is a change from the crypto build order: there, time was a 24/7 continuum and the mapper was
a utility. Here half the catalog is session-anchored and the mapper is what decides which
bars a hypothesis even sees.

### Exit design: prefer time-based exits over price-based stops

**Default to a time exit. Reach for a price stop only when the hypothesis is specifically
about a price level, and say so.**

The reason is data resolution, and it decides what this repo has to buy and maintain.

A **time exit** — "hold 60 minutes", "flat at 15:55 ET" — resolves entirely on 1-minute
bars. The exit bar is known, the exit price is that bar's close, and the backtest and the
live implementation agree by construction.

A **price stop** — "exit if price trades 15 ticks against me" — does not. Whether the stop
was hit, and at what price, depends on the *path within* the bar. A 1-minute bar that
touches both a stop and a target tells you neither which came first nor what a resting order
would have filled at. Resolving that honestly requires **1-second or tick data**, and §5
Stage 9 requires a bar-by-bar diff between the Python signal and the live implementation —
which cannot be done at all if the backtest's fills were never determinate.

Three consequences:

1. **A time-exit hypothesis can be validated on the data this project already has.** A
   price-stop hypothesis cannot, without a second, larger, more expensive extract.
2. **Intrabar excursion is still MEASURED, just not ACTED ON.** §5 Stage 5 already requires
   recording MAE/MFE from bar highs and lows. That is how a stop's plausibility is assessed
   without a stop being in the strategy.
3. **The 17:00 ET hard exit is itself a time exit**, so the venue's binding constraint and
   the preferred exit mechanism are the same kind of object. That is convenient rather than
   coincidental: both resolve on a clock, and neither depends on path.

Where a price stop is genuinely required, it must be declared at Stage 0, its data
requirement stated, and the 1-second extract budgeted before Stage 5 — not discovered at
Stage 9.

---

## 10. Coding conventions

- Python 3.11+, type hints throughout
- Polars over pandas for anything over 1M rows
- Pure functions for all signal logic — must be unit-testable without I/O
- Every stage writes a versioned artifact; nothing lives only in memory
- Seed all RNG; log seeds
- `pytest` for the integrity tests; they run in CI, not ad hoc
- No notebook contains logic — notebooks call library functions only
- **All time arithmetic goes through `futuresres.session.calendar`.** No module may
  construct a session boundary from a hardcoded ET offset, and no module may call
  `datetime.combine` with a fixed `tzinfo` for a non-US session. This is the same class of
  rule as §5 Stage 1's ban on signal modules building their own return series, and it exists
  for the same reason: the bug is easy to write, invisible once written, and fatal.

---

## 11. Standing reminders

- The most likely outcome of this project is discovering there is no tradeable edge. That is
  a real and valuable result. Report it plainly.
- Any request to "just relax the filter a bit" or "try a few more parameter values" must be
  logged as additional trials and passed through the deflation math. Overfitting happens one
  reasonable-sounding tweak at a time.
- **The cost floor changed; the standard of evidence did not.** A lower floor means more
  effects are economically viable, not that weaker evidence is acceptable. The crypto
  project's one BH-surviving result was reported as uneconomic rather than promoted; the
  same machinery applied here must be as willing to reject a *profitable-looking* result.
- **DST is the most likely silent bug.** When a session-anchored result looks strong, check
  the divergence weeks before celebrating.
- **A scheduled-macro hypothesis is untestable here regardless of its published effect.**
  FOMC gives ~128 observations over the sample and CPI/NFP ~200. The pre-FOMC drift is 49
  bps — 100× the cost floor — and it cannot be established on 128 observations. F12 records
  this; excluding it on measured grounds before testing is the gate doing its job.
- When results look great, look for the bug before celebrating.

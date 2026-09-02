# MNQ / MGC Intraday Strategy Hypotheses

Companion to [`CLAUDE_FUTURES.md`](./CLAUDE_FUTURES.md). Candidate strategies for CME index
and metals futures on a prop account. Session-scoped, **flat by 17:00 ET without exception**.

> **Source.** Transcribed from the catalog document supplied 2026-08-28. One factual
> correction has been applied and is marked inline: the London-open DST claim. Everything
> else is as supplied.

## Read this first

Same standard as the crypto catalog: none of these is a validated edge. They are hypotheses
with mechanisms, graded by independent evidence.

Three things are different this time, and all three matter more than the hypothesis list.

### 1. The cost floor is ~15x lower

| | notional | commission | + spread | round trip |
|---|---|---|---|---|
| MNQ | ~$48k | 0.38 bps | 0.10 | **0.48 bps** |
| MGC | ~$40k | 0.53 bps | 0.12 | **0.65 bps** |
| NQ | ~$480k | 0.12 bps | 0.10 | **0.22 bps** |
| ES | ~$335k | 0.17 bps | 0.10 | **0.27 bps** |

Against Tradeify247's 8 bps. Effects of 3-12 bps — the range that closed the entire crypto
catalog — are comfortably tradeable here. **This is the single reason the project is worth
restarting.**

Minis are ~3x cheaper in bps than micros: same tick, 10x notional, only 3.2x commission.
Prop drawdown rules push toward micros, so that's a real trade-off, not a free choice.

### 2. Kurtosis is far lower, so the detection floor should improve

BTC measured 199.9 at 1m and 66.9 at 60m. Index futures run an order of magnitude lower.

- The **46-event DSR wall** was a kurtosis artifact (`N_min = 2*sqrt((N-1)/(g4-1))`). At
  g4 ~ 8 instead of 67 that wall drops to roughly 5 events and should effectively disappear.
- The Stage 1 bootstrap alpha calibration was fitted to crypto kurtosis and **will be wrong
  here**. It must be re-measured, not carried over.

**Both are predictions. Re-measure before relying on either.**

### 3. The firing-rate gate rules out a whole class before testing

| condition | per year | over 16 years | verdict |
|---|---|---|---|
| every RTH session | 252 | ~4,000 | viable |
| every half-hour bar | ~3,300 | ~52,000 | comfortable |
| LBMA auctions | 504 | ~8,000 | comfortable |
| CPI or NFP release | 12 | ~200 | **below gate** |
| FOMC announcement | 8 | ~128 | **below gate** |

**Every scheduled-macro hypothesis is structurally untestable on this sample**, no matter
how large its published effect.

## Session map (all times ET)

| session | window | notes |
|---|---|---|
| CME open | 18:00 | new trading day begins |
| Asia | 19:00 - 03:00 | Tokyo cash 19:00/20:00 ET depending on US DST |
| Europe | 02:00 - 11:30 | London cash 03:00 ET |
| US cash | 09:30 - 16:00 | RTH |
| **hard exit** | **17:00** | **prop constraint, no exceptions** |
| CME close | 17:00 | maintenance 17:00-18:00 |

**The constraint is less binding than it looks.** An Asia-session hypothesis opens at 19:00
ET and runs overnight inside a single CME trading day — it never crosses a close.

> **CORRECTION, measured 2026-08-28.** The source document states the London open "sits at
> 03:00 ET most of the year and **02:00 ET** for a few weeks each spring and autumn." The
> direction is inverted. It is **04:00 ET** during the divergence weeks, and 02:00 ET never
> occurs: that would require Europe on summer time while the US is on standard time, and EU
> summer time is entirely nested inside US daylight time. Verified across 2024-2026 in
> `tests/test_session_calendar.py`. The underlying warning stands and is correct — anchor to
> exchange local time and convert, never to a fixed ET offset.

## Universal rules

- Every hypothesis tests on **MNQ and MGC**. They are genuinely uncorrelated, which makes
  Stage 4 a real gate here — unlike BTC/ETH at rho=0.835.
- ES/YM/RTY are rho~0.9 with NQ. Use as a robustness check, **never as Stage 4 evidence**.
- Roll on volume crossover, unadjusted per-contract, **drop the crossover session entirely**.
- Every strategy beats a **random-entry benchmark** with matched holding-time distribution.
- Every strategy beats **scaled buy-and-hold**. Index futures have real drift; a long-biased
  intraday strategy inherits it and must be charged for it.

---

## TIER A

### F01 — Market Intraday Momentum
**Grade: A | Params: 3 | Session: US | Hold: 30-60 min | Exit 16:00 ET**

Gao, Han, Li & Zhou (JFE 2018): the first half-hour return on the market, from the previous
day's close, predicts the last half-hour return. Baltussen, Da, Lammers & Martens (JFE 2021)
supplied the mechanism: **hedging demand**. Leveraged ETFs must rebalance daily to maintain
their multiple — structurally short gamma, buying into strength and selling into weakness,
pegged to the closing price. Options dealers short gamma trade the same direction. These are
risk systems executing a formula, and the direction is known in advance from the day's
return. Nomura estimated that at peak size every 1% move required the leveraged ETF complex
to trade $10 billion.

```
r1 = return from previous close (16:00 ET) to 10:00 ET
at 15:00 or 15:30 ET:
  if |r1| > k * ATR(20d):
      enter in direction of r1
      exit at 15:55 ET     # before the close, not into it
```

`entry_time` in {15:00, 15:30} · `k` in {0, 0.5, 1.0} · `vol_filter` in {none, >median, >p66}

`k=0` is the unconditional version and should be tested — the papers find the effect
unconditionally, with volatility strengthening rather than enabling it.

**Why it might fail.** Effect is ~1 bps per session (2.47% annualized at Sharpe 0.49) —
positive against MNQ's 0.48 bps but thin, and it would have been dead in crypto. Published
2018, so decay is likely and must be tested by regime. The leveraged-ETF literature is
contested: Lenkey (2024) argues the economic magnitudes are insignificant. **Take the
mechanism as plausible, not established.** Exiting at 15:55 avoids the close, where the flow
concentrates but the spread is widest.

### F02 — Order-Imbalance-Conditional Overnight Reversal
**Grade: A- (unconditional version DECAYED) | Params: 3 | Session: Asia/Europe | Hold: 1-4h**

Boyarchenko, Larsen & Whelan (RFS 2023): almost the entire US equity premium accrued between
02:00 and 03:00 ET when European markets open — 3.6% annualized, 1998-2019. Mechanism is
Grossman-Miller inventory risk: intermediaries absorb closing order imbalances and are
compensated through overnight returns. The conditional finding is asymmetric — **selloffs
generate robust positive reversals, rallies much weaker** — which follows from the mechanism:
dealers absorbing a sell imbalance hold unwanted long inventory and must be paid to carry it.

**The unconditional version is dead.** The same authors' *The Disappearing Overnight Drift*
(July 2026) reports the window has averaged near zero since 2021, having previously been
responsible for more than 60% of the contract's 5.9% annualized close-to-close return. Test
only the conditional relationship, and test whether it decayed too.

```
imb = return from 15:00 to 16:00 ET      # proxy for closing order imbalance
if imb < -k * sigma:                     # selloff — the strong side of the asymmetry
    enter long at 01:30 ET
    exit at 04:00 ET
test the symmetric long-side condition separately, expecting it to be weaker
```

Direction is *opposite* the closing imbalance. Test the migration too: the authors note
dealers increasingly offload inventory shocks at the **Asian** open, so run the same
condition with a 19:00-22:00 ET window.

`k` in {0.5, 1.0, 1.5} · `window` in {Europe 01:30-04:00, Asia 19:00-22:00} · `hold` in {1,2,4}h

**Why it might fail.** Decay is documented by the authors. Closing return is a proxy for
order imbalance, not the imbalance. **Regime split is mandatory, not optional** — pre-2021
and post-2021 are different objects.

### F03 — Half-Hour Periodicity (Micro-Momentum)
**Grade: A- | Params: 3 | Session: US | Hold: 30 min**

Heston, Korajczyk & Sadka: returns persist at the same half-hour intervals across trading
days, up to 40 days. Cause is institutional execution — large orders worked at similar times,
attributed specifically to *repetitive* institutional traders. This is the futures analogue
of the crypto quarter-hour effect, with a better-documented cause.

```
For each half-hour slot s in the RTH session:
  hist = mean return of slot s over trailing N days
  if |hist| > threshold and t-stat over trailing window is significant:
      enter at slot open in sign(hist) direction
      exit at slot close
```

`N` in {10, 20, 40} days · `threshold` in {0.5, 1.0, 1.5} x slot sigma · all 13 RTH slots

**Why it might fail.** The original finding is on individual stocks, where one institution's
order is large relative to volume; **an index future is the aggregate**, so idiosyncratic
execution schedules should largely cancel. This is the biggest weakness and the first thing
to test. 52,000 observations means you will detect small effects including small artifacts.
**BH within the hypothesis across 13 slots.**

### F04 — LBMA Auction Flow (MGC)
**Grade: B+ | Params: 3 | Session: Europe/US | Hold: 30-120 min**

The LBMA runs electronic gold auctions twice per business day, 10:30 and 15:00 London. These
are the benchmark prices institutions transact on. The 15:00 auction is the more important:
it covers both London and New York, giving commercial participants higher liquidity, and many
producers are North American. It lands at 10:00 ET. Scheduled, benchmark-anchored,
non-discretionary institutional flow — the same class of mechanism as F01.

```
For each auction (10:30 and 15:00 London, converted to ET with DST handling):
  pre = return over [T-30min, T]
  test: does pre predict [T, T+60min]?
  test both continuation and reversion; the mechanism predicts
  temporary impact reverting after the auction clears
```

`auction` in {AM, PM} tested separately · `pre_window` in {15,30,60} min · `hold` in {30,60,120} min

**Why it might fail.** COMEX futures and the LBMA auction are different markets linked by
arbitrage — the auction is a physical OTC process, MGC is a paper future. **The 15:00 London
auction is 10:00 ET, when US data has landed at 08:30 and US liquidity is peaking, so any
effect could be a US-session effect wearing an auction costume.** The confound control is
mandatory: there are no non-auction weekdays, so use a same-time random-day benchmark, as
with S04 in the crypto work.

**A caution on sourcing.** There is a body of writing claiming systematic suppression via the
gold fix, typically citing an AM-higher-than-PM pattern. **Do not use it as evidence.** The
academic treatment is contested and the LBMA's response notes that afternoon liquidity and US
data releases account for the pattern without manipulation. Test the mechanism as scheduled
institutional flow; if a directional bias exists the data will show it without the framing.

### F05 — Volatility Compression Expansion
**Grade: B+ | Params: 3 | Both instruments | Hold: 1-3h**

Carried over from the crypto catalog, where it was recorded **stage1_inconclusive rather
than retired** — 7 nominal hits on SOL against 2.7 expected, none surviving BH, mechanism
uncontradicted, drift explanation tested and refuted. It failed on power and multiplicity,
not on story. Two reasons for a fresh test: the cost floor is 15x lower, and index futures
have session structure that crypto lacks — compression into the cash open or into a scheduled
release is a mechanically different setup from compression at a random hour.

```
if realized_vol(1h) < p20 of trailing 20 sessions at the same clock time:
    arm
    on first close beyond k*sigma from the compression midpoint:
        enter that direction, exit at H or 16:55 ET whichever first
```

`vol_pct` in {15,20,25} · `k` in {1.5,2,2.5} · `H` in {1,2,3}h

**Why it might fail.** The variance forecast is sound; the direction is close to a coin flip.
**Verify the win rate is near 50% and that the edge is payoff asymmetry. A hit rate
meaningfully above 50% contradicts the mechanism and indicates a bug.**

---

## TIER B

### F06 — Cash Open Drive Continuation
**Grade: B | Params: 4 | Session: US | Hold: 1-3h**

09:30 ET is a genuine liquidity event — the largest participant-composition change in the
day. Overnight positioning meets cash liquidity and the imbalance resolves. Differs from F01
by trading the *near* continuation rather than the close.

```
range = [09:30, 09:30+W] high/low
on close beyond range boundary:
    enter that direction
    exit at H hours or 15:55 ET
```

`W` in {5,15,30} min · `confirm` in {close beyond, 2 closes beyond} · `H` in {1,2,3}h ·
`vol_filter` in {none, >median}

**Why it might fail.** Opening range breakout is possibly the most widely traded retail
futures pattern in existence. Any edge has had decades of attention. **Treat a positive
result with more suspicion than a negative one.**

### F07 — Gold Session-Specific Momentum
**Grade: B | Params: 3 | MGC | Hold: 30-90 min**

In the intraday momentum literature, for gold **the fifth half-hour return has the highest
and significantly positive predictive power** — not the first, as in equities. If it holds,
gold's information arrival is anchored to a different session point, plausibly the
London/New York overlap rather than the cash open. Testing whether the predictive slot
differs between MNQ and MGC is a cleaner question than testing either alone.

```
For MGC, regress last-half-hour return on each of the first 12 half-hour returns separately.
Identify which slot predicts, if any. Compare to MNQ's slot structure.
```

`slot` in {1..12} — **this is a scan, so every slot is a trial and BH applies within the
hypothesis** · `hold` in {30,60,90} min

**Why it might fail.** This is closer to exploratory analysis than a hypothesis and is
registered as such. The mechanism — "gold's session anchor differs from equities" — is a real
claim, but which slot carries it is being discovered rather than predicted. **Log all 12 as
trials.**

### F08 — Cross-Asset Risk Regime (MNQ / MGC)
**Grade: B- | Params: 3 | Both | Hold: 1-3h**

Gold and equities have an unstable but real relationship: risk-off flows bid gold and sell
equities, while a rising-real-yield regime pressures both. The relationship inverts by
regime, which is precisely why a conditional formulation is more defensible than an
unconditional one. The tradeable version is divergence: when both move the same direction
sharply during a risk-off signal, one of them is wrong.

```
if sign(MNQ return over W) == sign(MGC return over W) and both |r| > k*sigma:
    fade the weaker-conviction leg (lower volume-weighted move)
    exit at H
```

`W` in {30,60} min · `k` in {1,1.5,2} · `H` in {1,2,3}h

**Why it might fail.** The correlation regime is the whole strategy and it is unstable across
the sample. Regime split mandatory. **This is a pairs trade in disguise, so it pays two sets
of costs — 1.13 bps combined, not 0.48.**

### F09 — Settlement-Anchored Flow
**Grade: B- | Params: 3 | Both | Hold: 30-90 min**

Daily settlement is the price institutions use for margining, P&L and risk models — 15:00 ET
for equity index futures, 13:30 ET for COMEX gold. Positions marked against it create flow
into the window from anyone whose risk system references it. Practitioner accounts describe a
flurry of activity before the window followed by calm after.

```
pre = return over [S-60min, S-15min]
enter at S-15min, exit at S+30min
test both continuation and reversion
```

`instrument` in {MNQ 15:00, MGC 13:30} · `pre_window` in {30,60} min · `hold` in {30,60,90} min

**Why it might fail.** **MNQ's 15:00 ET settlement overlaps F01's entry window, so the two
are not independent and a hit on one may be the other. Test them jointly before treating
either as confirmed.**

---

## TIER C — Controls

### F14 — Timestamp Hash (control) — **the live control**
**Grade: D | 0 params.** Direction is the low bit of SHA-256 of the bar's ISO timestamp,
fired at each 30-minute RTH slot open, held 30/60/120 minutes, on MNQ and MGC. **Clearing
Stage 1 indicates a harness bug — halt and run the synthetic-noise test.**

Its premise is that the signal **cannot** relate to future returns by construction — a
deterministic function of the clock that never touches price, aperiodic, and unable to align
with time-of-day because each date hashes differently. That is the only kind of premise a
control may rest on. Parameters were fixed in writing before any run and there are none to
sweep.

**Scope, which is part of the claim.** It fires ~9.2 times a session on MNQ and 7.9 on MGC,
reaching ~40,000 independent events, so it validates the harness at **F03-like event counts
only**. It says nothing about ~4,000-event samples. **No control exists for the
once-a-session regime on this data and none can be built** — a once-a-session condition over
sixteen years yields ~3,500 events against MNQ's 19,722, which is a property of the sample
rather than of any signal. F01, F02, F04, F06 and F09 all live in that regime and none of
them has a control.

### F10 — RSI Mean Reversion (control) — **RETIRED, unpowered**
**Grade: D | 1 param (hold).** RSI(14) 30/70, fixed a-priori. Sound premise, but 1,585–5,594
independent events against a swept range starting at 19,722, and no tuning fixes a firing
rate. An unpowered control coming back empty is indistinguishable from a powered one working
correctly. Never run.

### F11 — MA Crossover (control) — **RETIRED, not a control**
**Grade: D | 2 params.** Its premise was that a canonical published trend rule should have
been arbitraged away — a contestable market prediction, not a construction. A fast/slow MA
crossover is time-series momentum, the same family as **F01**, so a promotion would be
unreadable as either harness failure or true detection. It was *powered*; it failed on
premise and would have at any sample size. Never run.

---

## EXCLUDED — do not register as testable

### F12 — Pre-FOMC Announcement Drift — BELOW FIRING-RATE GATE

Lucca & Moench (2015): the S&P 500 rises an average **49 bps in the 24 hours before
scheduled FOMC announcements**, accounting for roughly 80% of annual returns, with a Sharpe
of 1.14 for buying at 14:00 the prior day and selling 15 minutes before the announcement.
Similar magnitude in the German DAX. The effect is *not* explained by the announcement
surprise — returns at and after the announcement are approximately zero.

**Excluded for two independent reasons, either sufficient:**

1. **Event count.** Eight per year, ~128 over the sample. Far below the gate. You cannot
   establish a 49 bps effect on 128 observations against index volatility, and a null would
   be uninterpretable.
2. **The window crosses the 17:00 ET exit.** A 24-hour hold from 14:00 the prior day is
   structurally incompatible with the prop constraint. A truncated version is a different
   hypothesis needing its own validation.

The literature is also split on whether it still exists — one line of work finds it
essentially disappeared after 2015, other commentary argues it persists. Unresolved, and
unresolvable on this sample. Same exclusion applies to CPI, NFP and every other scheduled
release: ~200 observations maximum.

**Keep this entry.** It is this catalog's version of the CME gap: a large, famous,
well-documented effect the pipeline cannot evaluate. Excluding it on measured grounds before
testing is the gate doing its job.

### F13 — Unconditional Overnight Drift — DECAYED

The 02:00-03:00 ET window is flat since 2021 per the original authors. Only the conditional
version (F02) is worth testing. **Recorded so it isn't rediscovered.**

---

## Testing order

| # | id | rationale |
|---|---|---|
| 1 | F01 | strongest evidence, mechanical cause, ~4,000 events, perfect prop fit |
| 2 | F03 | 52,000 events — best power in the catalog |
| 3 | F04 | MGC's best structural hypothesis, ~8,000 events |
| 4 | F02 | strong mechanism but decay is documented; regime split mandatory |
| 5 | F05 | carried over as inconclusive, deserves a fair test at lower cost |
| 6 | F06 | high frequency, but heavily traded by others |
| 7 | F09 | test jointly with F01 |
| 8 | F07 | exploratory, register as a scan |
| 9 | F08 | double costs, unstable regime |
| — | F10, F11 | controls — validate the harness |
| — | F12, F13 | never |

## Honest assessment

Ranked by what would be expected to survive to Stage 8:

1. **F01** — best evidence, mechanical cause, and the cost floor finally allows a ~1 bps
   per-session effect to be tradeable. The risk is that it has already decayed.
2. **F03** — the power is exceptional, and if institutional execution schedules leave any
   footprint in the index it will show up here. The risk is that aggregation cancels it.
3. **F04** — the cleanest scheduled event in gold, but the 10:00 ET confound is severe.

**F06, F08, F10, F11 would be expected to fail outright.**

**What's genuinely different from the crypto project:** there, effects of 3-12 bps died
against an 8 bps floor and the outcome was determined before testing began. Here the floor
is 0.48 bps and several of these are documented at 1-50 bps. The arithmetic no longer
forecloses the answer.

**What's the same:** most of these will still fail, and the pipeline's job is to establish
that cleanly rather than to find a winner. The crypto catalog produced one hypothesis that
cleared BH — S08's OI divergence at 4.70 bps — and correctly reported it as uneconomic. That
same machinery applied here should find fewer false positives than the raw numbers suggest,
because lower kurtosis means the extreme-mean-with-high-p-value pattern that made SOL and XRP
look strongest should largely disappear.

**The thing most likely to go wrong:** DST handling across Europe and the US. Half this
catalog is session-anchored, the shifts happen on different dates, and a one-hour
misalignment for a few weeks a year will produce results that look real and aren't. Build the
session mapper first, test it against known dates, and treat it as load-bearing
infrastructure rather than a utility function.

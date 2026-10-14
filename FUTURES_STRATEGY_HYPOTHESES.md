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

---

# P-series — non-price observables

Registered from `P_SERIES_CANDIDATES.md` after the S1 review in `decisions.md` §54. Thirteen
candidates were evaluated; **one was registered.** The rest are below their BH bar, lack a
trade rule, or are conditioners with no live primary to condition.

## P03 — Thin-Move Reversion  *(RETIRED at S7)*

**Params: 2** | **NQ state / MNQ traded** | **Fires: 27,437 (measured), 7.71 per session**

Amihud/Kyle. A price move is bought with volume, so a move achieved on **little** volume moved
a thin book rather than absorbing informed flow. The displacement it creates is more likely
transitory and should give part of itself back. **The counterparty is whoever crossed a thin
book without information**, and they keep doing it because order size is chosen from account
size rather than from book depth.

**The threshold is a rank, not a level.** λ = |return in bps| / bar volume, thresholded at the
90th percentile of λ over the same 30-minute bucket across the previous 60 sessions. That is
dimensionless, so the NQ→MNQ notional change and the secular volume growth divide out. Measured
evidence: the firing rate holds at **7.95–12.10% across 2012–2026** while median bar volume runs
1,752 → 5,325.

**H = 15 was measured, not assumed.** The state's own decay half-life is **3.5 minutes** — log
illiquidity elevation falls to 0.29 of its spike within one 5-minute bar — and 15 is the nearest
grid point (R01's precedent). It is resolution-limited, and H=15 is already ~4 half-lives past
decay: **P03's clock is faster than the tradeable grid.**

**S2: NOT BELOW, crossing at 6.8%.** Measured excess displacement at a firing is **9.18 bps**
(median move 13.59, what its volume buys 4.21) against a binding constraint of 0.625 bps. The
excess is a **ceiling, not a prediction** — part of it is permanent information — so the honest
prior on the reversion fraction is **unknown, not high**.

**This is an economics-binding regime.** Cost floor 0.48 bps against a BH bar of 0.463–0.625.
Every earlier P-series entry was significance-dominated (P01 needed 4.2–5.4 bps, P09 72–102), so
a null here means the effect is small in bps, **not** that the test could not see it.

**S6 is the matched state control in `bar` mode**, not a level placebo. Strict mode is
structurally unavailable: the state touches 92.6% of sessions. Bar mode's contamination costs
power, not validity, so a null under it is weaker evidence than a null under strict mode.

**P03 RETIRED AT S7, 2026-09-13.** Real − control **+0.0794 bps** against a pre-registered
**+0.625** — 7.9× short, and the real leg is **−0.28 bps net of cost**, so it loses money before
significance matters. Not separated (p 0.691); era split agrees with no sign flip. **The
measured reversion is 0.86% of the excess, against the 6.8% required.** The null was
fault-injected before it was believed: an injected +4.0 bps reversion is recovered as +3.45.
**Caveat recorded before the run:** the state's half-life is 3.5 minutes and H=15 is the
grid's shortest horizon, so this sits ~4 half-lives past the mechanism's clock. See
`reports/p03_stage1.md` and `decisions.md` §58.

**The P-series closes: thirteen candidates, one registered, one tested, zero promoted, 1 trial
spent.**

---

## U01 — Large Opening Gap Non-Fill  *(BLOCKED at S4)*

**A single hypothesis, not a series.** Registered 2026-10-02 from a third-party claim: "large
opening gaps fill same-session only about 8% of the time." The source is a social media clip
describing its author's own backtest, with no visible trial count, cost assumption or control, so
it carries **no prior weight** and is registered on its own terms — recorded as L11's was.

**Condition.** A CME reopen — daily (18:00 ET after the 17:00–18:00 break) or weekly (Sunday
18:00 ET) — whose first price is 0.4% or more from the prior session's last price. **Credit where
due:** 0.4% is a percentage, so the threshold satisfies the S2 scale check (§52) natively.

**Blocked before any test.** Measured on the NQ→MNQ splice and MGC, 2010–2026: 104 and 46 such
gaps in sixteen years (42 and 28 since 2021), against floors of 5,884 and 2,862. No trial spent.

**And the claim does not describe these instruments.** Gaps of 0.4% or more fill same-session
46–100% of the time here, and the fill-rate curve tracks a driftless random walk scaled by session
volatility — a smooth decline with no break at 0.4%, which is what arithmetic alone predicts.

**Why the 8% would not have supported a trade anyway.** Non-fill includes drifting sideways,
continuing away from the gap and partial retracement; only continuation pays. The registered S2
claim is a forward-return distribution against a volatility-matched control, not a fill rate.

`hypotheses.yaml` (U01) · `reports/u01_gap_fill.md` · `decisions.md` §67

---

## V01 — Reopen Displacement Reversion  *(BLOCKED at S4)*

**A single hypothesis, and a post-hoc one — marked as such.** Registered 2026-10-03. The
mechanism: the first print after the CME maintenance break is set against thin depth, so a
displaced reopen is partly a liquidity artifact that corrects when real depth arrives; the
counterparty is whoever quoted into the thin book. Its closest registered relative is **L02's
absorption arm**, not L03, whose mechanism is a stop sweep. **L02 is not prior evidence against
it** (corrected, §70): L02 tested only the 09:30 cash-open range, on MGC alone, and its own record
calls its 0-of-27 null unable to refute its mechanism. No registered entry ever tested the CME reopen.

**Provenance.** The observation came from U01's fill curve — daily reopens filling more often than a
random walk at small gaps — so this mechanism was written after the effect was seen, though it
predicts the direction independently. Not presented as a fresh hypothesis.

**Blocked at its ceiling, with no threshold chosen.** It fires at most once per daily reopen, so the
count of every valid daily reopen with a nonzero displacement is the largest any threshold could
leave: 2,469 on the index and 1,926 on MGC (1,015 and 901 since 2021), below every floor. The only
threshold on offer was the range where U01's curve showed the excess — a range chosen from a curve —
and it was never needed.

**No forward return was computed.** A real-minus-control return is the S6/S7 comparison, a trial by
the programme's rule, and at a ceiling below every floor it could not change the verdict.

`hypotheses.yaml` (V01) · `reports/v01_reopen_rate.md` · `decisions.md` §69

---

## W04 — Trend Plus Carry, Daily Portfolio  *(RETIRED — run 2026-10-03, t00767)*

**The W-series' one registration.** Time-series momentum (Moskowitz, Ooi & Pedersen 2012) and carry
timing (Koijen, Moskowitz, Pedersen & Vrugt 2018), at equal risk, across one CME market per sector —
NQ, GC, HG, CL, ZN, 6E — traded through their micros at a daily horizon by chained 18:00-to-16:55
session holds (confirmed with the firm). Published parameters, no free ones, **one trial**.

**Pre-registered before the data was purchased**, amended after it arrived and before any price was read (daily UTC bars, a one-session delay, carry from same-bar closes). The decisive statistic is the post-2021 Sharpe net of the
daily round trips, against the unit-consistent multiple-testing bar (~1.39); the economics is the
prop-evaluation EV at that Sharpe. Prior 0.7–1.2, from the papers, labelled optimistic.

`hypotheses.yaml` (W04) · `W_SERIES_CANDIDATES.md` · `decisions.md` §72–§73

**Result (decisions.md §76):** post-2021 net Sharpe −0.42 against 1.31; gross 0.31. Daily re-entry on
the lowest-volatility micros costs 0.73 of Sharpe. Retired on an informative null.

---

## Z02 — Front-Running Rebalancers, Equity Leg  *(REGISTERED)*

Harvey, Mazzoleni & Melone (NBER w33554): pensions and balanced funds rebalance 60/40 portfolios on
calendar dates and thresholds, predictably; next-day equity returns 17 bps lower when equities are
overweight; the published long/short strategy Sharpe ~1.1 over 1997–2023. Replicated to the letter, the
S&P leg alone on MES (the long/short spread counts as hedging in the account), and tested **only on
2023-03-18 onward**, after the paper's sample. One trial; decision rule ruled by the user (§86).

`hypotheses.yaml` (Z02) · `Z_SERIES_CANDIDATES.md` · `decisions.md` §86–§87

---

## Z04 — Macro-Announcement Premium on MES  *(RETIRED — t00769, no premium in 2010–2026)*

Savor & Wilson (2013): stocks earn ~11 bps on FOMC, jobs and CPI days against ~1 bp otherwise — a risk
premium reported to persist to 2023. Long MES on those days only, tested 2010–2026 (after the original
sample); confirmed only if event days beat other days, the net Sharpe is positive and the Tradeify EV at
the posterior is positive. One trial. `hypotheses.yaml` (Z04) · `decisions.md` §96–§97

---

## Z05 — Gold: Long Overnight, Short the New York Day  *(CONFIRMED, marginally — t00770)*

Blose, Gondhalekar & Kort (2018): COMEX gold earns positive returns overnight and negative returns in the
day session (1985–2012). 1 MGC long 18:00–08:20, short 08:20–13:30, long 13:30–16:55 ET; tested 2013–2026.
One trial. `hypotheses.yaml` (Z05) · `decisions.md` §99–§100

## Z06 — Trend Sign Sets the Bracket's Direction  *(RETIRED — t00771, worse than always-long on both)*

Moskowitz, Ooi & Pedersen (2012): the sign of the past 12-month return predicts the next month, in every
one of 58 futures (1985–2009). A follow-on to W04: here the sign only chooses the daily bracket's direction
in the two staking plans (MNQ 09:30–16:00, MGC 03:00–11:30 ET), whose costs are paid either way. Tested
2011-07 → 2026-08; must also beat always-long. One trial. `hypotheses.yaml` (Z06) · `decisions.md` §110

## Z07 — Index Reversal Sets the MNQ Bracket's Direction  *(RETIRED — t00772, does not beat always-long)*

Baltussen, van Bekkum & Da (2019): daily index returns turned negatively autocorrelated after ~1999 as index
products grew (Sharpe 0.67 against MAC(5) on the S&P 500, to 2016). The sign of the MAC(5)-weighted last four
days sets the MNQ 09:30–16:00 bracket's direction (against the move); must beat always-long. Tested 2017–2026.
One trial. `hypotheses.yaml` (Z07) · `decisions.md` §111

## Z08 — Hedger Flow Sets the Commodity Brackets' Direction  *(RETIRED — t00773; gold fails the strict rule, §119)*

Kang, Rouwenhorst & Tang (2020): commodity prices rise the week after commercial hedgers buy and fall after they
sell — hedgers provide liquidity to impatient speculators (1994–2014). The sign of last week's commercial net
change (CFTC COT) sets the direction of the crude (full session) and gold (London) brackets for the next week.
Tested 2015–2026; must beat always-long. One trial. `hypotheses.yaml` (Z08) · `decisions.md` §117

## Z09 — Index Roll Selling: Short Crude on Roll Days  *(RETIRED — t00774; worked to 2020, reversed after)*

Mou (2011): GSCI index funds sell the next-to-expire crude contract on business days 5–9 every month. The
crude plan goes short on those days and long otherwise — the outright, since the spread is not allowed. Tested
2010-06 → 2026-08 under the strict rule. One trial. `hypotheses.yaml` (Z09) · `decisions.md` §120

## Z10 — Gotobi: Importers' Dollar Buying Before the Tokyo Fix  *(RETIRED — t00775; halved, then gone by 2024)*

Japanese importers settle on days divisible by five at the 9:55 JST fix; banks pre-buy dollars, so USD/JPY rises into
9:55 (arXiv 2301.13204, 2018–2020). Long USD/JPY (short 6J) from the 18:00 ET reopen to the fix on gotobi days,
net of 1 bp. Tested 2021–2026 on free spot data under the strict rule. One trial. `hypotheses.yaml` (Z10) · `decisions.md` §122

## Z11 — Month-End FX Hedge Rebalancing at the London Fix  *(RETIRED — t00776; gone since 2013)*

Melvin & Prins (2015): international equity managers reset currency hedges at the month-end 4 p.m. London fix, so
equity outperformance predicts the currency's fall in the hour before it. Long EUR/USD (6E) 15:00→16:00 London on the
month's last weekday when the S&P beat the DAX, short otherwise. Tested 2013–2026 on free data, strict rule. One trial.
`hypotheses.yaml` (Z11) · `decisions.md` §127

## Z12 — The Euro Weakens in European Hours, Strengthens in US Hours  *(RETIRED — t00777; costs absorb it, decayed after 2017)*

Breedon & Ranaldo (2013): currencies depreciate in their own trading hours (local participants buy foreign currency).
EUR/USD short 07:00 London → 08:00 New York, long 08:00 → 16:00 New York, every weekday, net of costs. Tested
2010–2026 (the paper ends 2007) on free data, strict rule. One trial. `hypotheses.yaml` (Z12) · `decisions.md` §128

## D01 — Silver Falls Into the London Fix  *(RETIRED — t00778; 40% of the discovery size, faded after 2021)*

Data-derived (D-series): the 2010–2017 discovery scan found silver's 11:00–12:00 UTC hour — the hour ending at the
12:00 London silver fix, summer and winter — averaging −5.5 bps (t −7.3). Short SI in that hour every weekday, net of
cost; validated once on sealed 2018–2026 data under the strict rule. `hypotheses.yaml` (D01) · `decisions.md` §130

## D02 — AUD Rises Into the Tokyo Fix at Month-End  *(RETIRED — t00779; did not recur out of sample)*

Data-derived (D-series family 2): AUD/USD's 30 minutes before the 09:55 JST Tokyo fix on the month's last weekday averaged
+2.9 bps (t 3.3) in 2010–2017. Long 6A 09:25 → 09:55 JST at month-end, net of cost; validated once on sealed 2018–2026 data
(confirm / watchlist / reject). `hypotheses.yaml` (D02) · `decisions.md` §134

## D03 — USD/CHF falls in the last New York hour on Fridays (20:00-21:00 UTC)  *(INVALIDATED — t00785; quote artefact at the Friday close)*

Data-derived (D-series re-scan on the corrected clock): Fridays, 20:00-21:00 UTC averaged -2.88 bps (t -6.07) in
2010–2017. Short 6S, net of cost; validated once on sealed 2018–2026 data (confirm / watchlist / reject).
`hypotheses.yaml` (D03) · `decisions.md` §143

## D04 — Silver falls 10:00-11:00 UTC  *(WATCHLIST — t00786)*

Data-derived (D-series re-scan on the corrected clock): every weekday, 10:00-11:00 UTC averaged -3.14 bps (t -4.22) in
2010–2017. Short SI, net of cost; validated once on sealed 2018–2026 data (confirm / watchlist / reject).
`hypotheses.yaml` (D04) · `decisions.md` §143

## D05 — GBP rises into the London 4 pm fix at month-end  *(WATCHLIST — t00787)*

Data-derived (D-series re-scan on the corrected clock): the last weekday of each month, the 30 minutes before the WM/R 16:00 London fix averaged +5.63 bps (t +2.84) in
2010–2017. Long 6B, net of cost; validated once on sealed 2018–2026 data (confirm / watchlist / reject).
`hypotheses.yaml` (D05) · `decisions.md` §143

## D06 — DAX falls in the first half hour of Xetra at month-end  *(REJECT — t00788)*

Data-derived (D-series re-scan on the corrected clock): the last weekday of each month, the 30 minutes after the Xetra open 09:00 averaged -8.71 bps (t -2.64) in
2010–2017. Short FDXM, net of cost; validated once on sealed 2018–2026 data (confirm / watchlist / reject).
`hypotheses.yaml` (D06) · `decisions.md` §143

## D07 — Nikkei falls into the Tokyo morning close  *(REJECT — t00789)*

Data-derived (D-series re-scan on the corrected clock): every weekday, the 30 minutes before the Tokyo morning close 11:30 averaged -2.35 bps (t -2.60) in
2010–2017. Short NKD, net of cost; validated once on sealed 2018–2026 data (confirm / watchlist / reject).
`hypotheses.yaml` (D07) · `decisions.md` §143

## D08 — AUD falls after the London 4 pm fix at month-end  *(WATCHLIST — t00790)*

Data-derived (D-series re-scan on the corrected clock): the last weekday of each month, the 30 minutes after the WM/R 16:00 London fix averaged -3.45 bps (t -2.41) in
2010–2017. Short 6A, net of cost; validated once on sealed 2018–2026 data (confirm / watchlist / reject).
`hypotheses.yaml` (D08) · `decisions.md` §143

## D09 — USD/CHF rises after the London 4 pm fix at month-end  *(WATCHLIST — t00791)*

Data-derived (D-series re-scan on the corrected clock): the last weekday of each month, the 30 minutes after the WM/R 16:00 London fix averaged +3.18 bps (t +2.34) in
2010–2017. Long 6S, net of cost; validated once on sealed 2018–2026 data (confirm / watchlist / reject).
`hypotheses.yaml` (D09) · `decisions.md` §143

## D10 — AUD rises into the London 4 pm fix at month-end  *(WATCHLIST — t00792)*

Data-derived (D-series re-scan on the corrected clock): the last weekday of each month, the 30 minutes before the WM/R 16:00 London fix averaged +4.23 bps (t +2.04) in
2010–2017. Long 6A, net of cost; validated once on sealed 2018–2026 data (confirm / watchlist / reject).
`hypotheses.yaml` (D10) · `decisions.md` §143

## D11 — DAX rises after the Xetra closing auction at month-end  *(REJECT — t00793)*

Data-derived (D-series re-scan on the corrected clock): the last weekday of each month, the 30 minutes after the Xetra close auction 17:30 averaged +4.25 bps (t +1.97) in
2010–2017. Long FDXM, net of cost; validated once on sealed 2018–2026 data (confirm / watchlist / reject).
`hypotheses.yaml` (D11) · `decisions.md` §143

## D12 — Nikkei window fades its move from the previous Tokyo close (15:00) to the open (09:00) (all)  *(REJECT — t00794)*

Data-derived (D-series family 3): the Nikkei window (09:00-15:00 Tokyo) traded against its own move from the previous Tokyo close (15:00) to the open (09:00) earned 6.52 bps a day beyond drift
in 2010–2017 (t 3.10). Sets the plan's bracket direction for that account; validated once on sealed 2018–2026 data.
`hypotheses.yaml` (D12) · `decisions.md` §150

## D13 — Gold window follows its move from the previous window's close (11:30 ET) to 03:00 ET (all)  *(WATCHLIST — t00795)*

Data-derived (D-series family 3): the gold window (03:00-11:30 ET) traded in the direction of its own move from the previous window's close (11:30 ET) to 03:00 ET earned 6.10 bps a day beyond drift
in 2010–2017 (t 2.89). Sets the plan's bracket direction for that account; validated once on sealed 2018–2026 data.
`hypotheses.yaml` (D13) · `decisions.md` §150

## D14 — MNQ window fades the previous day's MNQ window (all)  *(WATCHLIST — t00796)*

Data-derived (D-series family 3): the MNQ window (09:30-16:00 ET) traded against the previous day's MNQ window earned 6.15 bps a day beyond drift
in 2010–2017 (t 2.74). Sets the plan's bracket direction for that account; validated once on sealed 2018–2026 data.
`hypotheses.yaml` (D14) · `decisions.md` §150

## D15 — Nikkei window fades its move from the previous Tokyo close (15:00) to the open (09:00) (strong)  *(REJECT — t00797)*

Data-derived (D-series family 3): the Nikkei window (09:00-15:00 Tokyo) traded against its own move from the previous Tokyo close (15:00) to the open (09:00) earned 8.44 bps a day beyond drift
in 2010–2017 (t 2.51). Sets the plan's bracket direction for that account; validated once on sealed 2018–2026 data.
`hypotheses.yaml` (D15) · `decisions.md` §150

## D16 — Gold window follows its move from the previous window's close (11:30 ET) to 03:00 ET (strong)  *(WATCHLIST — t00798)*

Data-derived (D-series family 3): the gold window (03:00-11:30 ET) traded in the direction of its own move from the previous window's close (11:30 ET) to 03:00 ET earned 8.20 bps a day beyond drift
in 2010–2017 (t 2.46). Sets the plan's bracket direction for that account; validated once on sealed 2018–2026 data.
`hypotheses.yaml` (D16) · `decisions.md` §150

## D17 — Crude session fades the same day's gold window (strong)  *(REJECT — t00799)*

Data-derived (D-series family 3): the crude session traded against the same day's gold window earned 17.88 bps a day beyond drift
in 2010–2017 (t 2.31). Sets the plan's bracket direction for that account; validated once on sealed 2018–2026 data.
`hypotheses.yaml` (D17) · `decisions.md` §150

## D18 — Crude session fades the same day's MNQ window (all)  *(REJECT — t00800)*

Data-derived (D-series family 3): the crude session traded against the same day's MNQ window earned 12.54 bps a day beyond drift
in 2010–2017 (t 2.26). Sets the plan's bracket direction for that account; validated once on sealed 2018–2026 data.
`hypotheses.yaml` (D18) · `decisions.md` §150

## D19 — Gold window fades the previous day's gold window (strong)  *(WATCHLIST — t00801)*

Data-derived (D-series family 3): the gold window (03:00-11:30 ET) traded against the previous day's gold window earned 7.95 bps a day beyond drift
in 2010–2017 (t 2.24). Sets the plan's bracket direction for that account; validated once on sealed 2018–2026 data.
`hypotheses.yaml` (D19) · `decisions.md` §150

## D20 — MNQ window fades the previous day's soybean session (strong)  *(REJECT — t00802)*

Data-derived (D-series family 3): the MNQ window (09:30-16:00 ET) traded against the previous day's soybean session earned 6.72 bps a day beyond drift
in 2010–2017 (t 2.11). Sets the plan's bracket direction for that account; validated once on sealed 2018–2026 data.
`hypotheses.yaml` (D20) · `decisions.md` §150

## D21 — Soybean session fades the same day's gold window (all)  *(REJECT — t00803)*

Data-derived (D-series family 3): the soybean session traded against the same day's gold window earned 6.97 bps a day beyond drift
in 2010–2017 (t 2.01). Sets the plan's bracket direction for that account; validated once on sealed 2018–2026 data.
`hypotheses.yaml` (D21) · `decisions.md` §150

## D22 — Gold follows where its overnight session (11:30 -> 03:00 ET) closed within its high-low range (days with |predictor| above its 2010-17 median)  *(WATCHLIST — t00804)*

Data-derived (D-series family 4): gold's 03:00–11:30 ET window traded in that direction earned 7.89 bps a day beyond
drift in 2010–2017 (t 3.39). Sets the plan's gold bracket direction; validated once on sealed 2018–2026 data.
`hypotheses.yaml` (D22) · `decisions.md` §153

## D23 — Gold follows its overnight return (11:30 -> 03:00 ET) (days with overnight volume above its 2010-17 median)  *(WATCHLIST — t00805)*

Data-derived (D-series family 4): gold's 03:00–11:30 ET window traded in that direction earned 7.22 bps a day beyond
drift in 2010–2017 (t 2.75). Sets the plan's gold bracket direction; validated once on sealed 2018–2026 data.
`hypotheses.yaml` (D23) · `decisions.md` §153

## D24 — Gold follows where its overnight session (11:30 -> 03:00 ET) closed within its high-low range (every day)  *(WATCHLIST — t00806)*

Data-derived (D-series family 4): gold's 03:00–11:30 ET window traded in that direction earned 4.60 bps a day beyond
drift in 2010–2017 (t 2.57). Sets the plan's gold bracket direction; validated once on sealed 2018–2026 data.
`hypotheses.yaml` (D24) · `decisions.md` §153

## D25 — Gold follows its last half hour before the window (02:30 -> 03:00 ET) (days with |predictor| above its 2010-17 median)  *(WATCHLIST — t00807)*

Data-derived (D-series family 4): gold's 03:00–11:30 ET window traded in that direction earned 6.68 bps a day beyond
drift in 2010–2017 (t 2.29). Sets the plan's gold bracket direction; validated once on sealed 2018–2026 data.
`hypotheses.yaml` (D25) · `decisions.md` §153

## D26 — Gold follows its overnight return (11:30 -> 03:00 ET) (days the 03:00 price is outside the previous window's high-low range)  *(WATCHLIST — t00808)*

Data-derived (D-series family 4): gold's 03:00–11:30 ET window traded in that direction earned 6.65 bps a day beyond
drift in 2010–2017 (t 2.28). Sets the plan's gold bracket direction; validated once on sealed 2018–2026 data.
`hypotheses.yaml` (D26) · `decisions.md` §153

## D27 — Gold follows its overnight return (11:30 -> 03:00 ET) (days with overnight realised variance above its 2010-17 median)  *(WATCHLIST — t00809)*

Data-derived (D-series family 4): gold's 03:00–11:30 ET window traded in that direction earned 5.53 bps a day beyond
drift in 2010–2017 (t 2.04). Sets the plan's gold bracket direction; validated once on sealed 2018–2026 data.
`hypotheses.yaml` (D27) · `decisions.md` §153

## D28 — Crude Weaker on Mondays  *(WATCHLIST in form only — t00810; did not recur)*

Data-derived (D-series family 5): the only calendar cell of 72 carried (≈3.6 by chance). Short the plan's crude bracket on
Mondays; validated once on sealed 2018–2026 data. `hypotheses.yaml` (D28) · `decisions.md` §156

## D29 — DAX Follows Its First 30 Minutes (every day)  *(REJECT — t00811)*

Data-derived (D-series family 6): the rest of the DAX window (09:00-17:30 Frankfurt) traded in the direction of its first 30 minutes earned
5.98 bps a day beyond drift in 2010–2017 (t 2.64). Validated once on sealed 2018–2026 data.
`hypotheses.yaml` (D29) · `decisions.md` §159

## D30 — NKD Follows Its First 30 Minutes (strong days)  *(WATCHLIST — t00812)*

Data-derived (D-series family 6): the rest of the Nikkei window (09:00-15:00 Tokyo) traded in the direction of its first 30 minutes earned
6.00 bps a day beyond drift in 2010–2017 (t 2.16). Validated once on sealed 2018–2026 data.
`hypotheses.yaml` (D30) · `decisions.md` §159

## D31 — DAX Follows Its First 30 Minutes (strong days)  *(WATCHLIST — t00813)*

Data-derived (D-series family 6): the rest of the DAX window (09:00-17:30 Frankfurt) traded in the direction of its first 30 minutes earned
7.67 bps a day beyond drift in 2010–2017 (t 2.11). Validated once on sealed 2018–2026 data.
`hypotheses.yaml` (D31) · `decisions.md` §159

## D32 — XAGUSD London Window Follows Its Own Overnight Move (strong days)  *(CONFIRM — t00814)*

Data-derived (D-series family 7, from the gold finding): XAGUSD from 03:00 to 11:30 New York traded in the direction of its own overnight move (11:30 -> 03:00 New York) earned
17.40 bps a day beyond drift in 2010–2017 (t 3.60). Validated once on sealed 2018–2026 data.
`hypotheses.yaml` (D32) · `decisions.md` §162

## D33 — XAGUSD London Window Follows Gold's Overnight Move (every day)  *(WATCHLIST — t00815)*

Data-derived (D-series family 7, from the gold finding): XAGUSD from 03:00 to 11:30 New York traded in the direction of gold's overnight move (MGC, 11:30 -> 03:00 New York) earned
12.37 bps a day beyond drift in 2010–2017 (t 3.34). Validated once on sealed 2018–2026 data.
`hypotheses.yaml` (D33) · `decisions.md` §162

## D34 — XAGUSD London Window Follows Gold's Overnight Move (strong days)  *(WATCHLIST — t00816)*

Data-derived (D-series family 7, from the gold finding): XAGUSD from 03:00 to 11:30 New York traded in the direction of gold's overnight move (MGC, 11:30 -> 03:00 New York) earned
18.47 bps a day beyond drift in 2010–2017 (t 3.19). Validated once on sealed 2018–2026 data.
`hypotheses.yaml` (D34) · `decisions.md` §162

## D35 — USDCHF London Window Fades Gold's Overnight Move (every day)  *(REJECT — t00817)*

Data-derived (D-series family 7, from the gold finding): USDCHF from 03:00 to 11:30 New York traded against gold's overnight move (MGC, 11:30 -> 03:00 New York) earned
2.83 bps a day beyond drift in 2010–2017 (t 2.21). Validated once on sealed 2018–2026 data.
`hypotheses.yaml` (D35) · `decisions.md` §162

## D36 — XAGUSD London Window Follows Its Own Overnight Move (every day)  *(WATCHLIST — t00818)*

Data-derived (D-series family 7, from the gold finding): XAGUSD from 03:00 to 11:30 New York traded in the direction of its own overnight move (11:30 -> 03:00 New York) earned
6.67 bps a day beyond drift in 2010–2017 (t 2.20). Validated once on sealed 2018–2026 data.
`hypotheses.yaml` (D36) · `decisions.md` §162

## D37 — Gold Fades Its First 15 Minutes After 08:30 Releases  *(REJECT — t00819)*

Data-derived (D-series family 9). `hypotheses.yaml` (D37) · `decisions.md` §169

## D38 — Gold Fades Its First 5 Minutes After 08:30 Releases  *(REJECT — t00820)*

Data-derived (D-series family 9). `hypotheses.yaml` (D38) · `decisions.md` §169

## D39 — ZN Follows the Previous ES Session  *(WATCHLIST — t00821)*

Data-derived (D-series family 10). `hypotheses.yaml` (D39) · `decisions.md` §172

## D40 — HG Fades the Previous NG Session  *(REJECT — t00822)*

Data-derived (D-series family 10). `hypotheses.yaml` (D40) · `decisions.md` §172

## D41 — ZN Fades the Previous 6J Session  *(WATCHLIST — t00823)*

Data-derived (D-series family 10). `hypotheses.yaml` (D41) · `decisions.md` §172

## D42 — NG Follows the Previous SI Session  *(WATCHLIST — t00824)*

Data-derived (D-series family 10). `hypotheses.yaml` (D42) · `decisions.md` §172

## D43 — ZS Follows the Previous ES Session  *(WATCHLIST — t00825)*

Data-derived (D-series family 10). `hypotheses.yaml` (D43) · `decisions.md` §172

## D44 — GC Follows the Previous ZN Session  *(REJECT — t00826)*

Data-derived (D-series family 10). `hypotheses.yaml` (D44) · `decisions.md` §172

## D45 — RTY Fades the Previous ES Session  *(WATCHLIST — t00827)*

Data-derived (D-series family 10). `hypotheses.yaml` (D45) · `decisions.md` §172

## D46 — ZS Long in Apr  *(WATCHLIST — t00828)*

Data-derived (D-series family 11, seasonality). `hypotheses.yaml` (D46) · `decisions.md` §175

## D47 — ZS Long in Oct  *(WATCHLIST — t00829)*

Data-derived (D-series family 11, seasonality). `hypotheses.yaml` (D47) · `decisions.md` §175

## D48 — NG Short in Oct  *(REJECT — t00830)*

Data-derived (D-series family 11, seasonality). `hypotheses.yaml` (D48) · `decisions.md` §175

## D49 — HG Long in Dec  *(WATCHLIST — t00831)*

Data-derived (D-series family 11, seasonality). `hypotheses.yaml` (D49) · `decisions.md` §175

## D50 — ZC Long in Oct  *(WATCHLIST — t00832)*

Data-derived (D-series family 11, seasonality). `hypotheses.yaml` (D50) · `decisions.md` §175

## D51 — CL Long in Apr  *(WATCHLIST — t00833)*

Data-derived (D-series family 11, seasonality). `hypotheses.yaml` (D51) · `decisions.md` §175

## D52 — HG Short in Mar  *(REJECT — t00834)*

Data-derived (D-series family 11, seasonality). `hypotheses.yaml` (D52) · `decisions.md` §175

## D53 — NQ Fades an Extreme Session Over the Next 5  *(REJECT — t00835)*

Data-derived (D-series family 12). `hypotheses.yaml` (D53) · `decisions.md` §178

## D54 — ES Fades an Extreme Session Over the Next 5  *(REJECT — t00836)*

Data-derived (D-series family 12). `hypotheses.yaml` (D54) · `decisions.md` §178

## D55 — ZN Fades an Extreme Session Over the Next 1  *(REJECT — t00837)*

Data-derived (D-series family 12). `hypotheses.yaml` (D55) · `decisions.md` §178

## D56 — MNQ Long the Midnight Hour  *(REJECT — t00838)*

Data-derived (D-series family 14). `hypotheses.yaml` (D56) · `decisions.md` §183

## D57 — DAX Last Half Hour Follows the Day (strong days)  *(WATCHLIST in form — t00839; faded)*

Data-derived (D-series family 16). `hypotheses.yaml` (D57) · `decisions.md` §188

## D58 — Combined Model for NKD_win  *(WATCHLIST — t00840)*

Data-derived (D-series family 19). `hypotheses.yaml` (D58) · `decisions.md` §195

## D59 — Combined Model for DAX_win  *(WATCHLIST — t00841)*

Data-derived (D-series family 19). `hypotheses.yaml` (D59) · `decisions.md` §195

## D60 — Combined Model for MGC_win  *(WATCHLIST — t00842)*

Data-derived (D-series family 19). `hypotheses.yaml` (D60) · `decisions.md` §195

## D61 — Combined Model for MNQ_win  *(REJECT — t00843)*

Data-derived (D-series family 19). `hypotheses.yaml` (D61) · `decisions.md` §195

## D62 — Combined Model for MCL  *(WATCHLIST — t00844)*

Data-derived (D-series family 19). `hypotheses.yaml` (D62) · `decisions.md` §195

## D63 — Combined Model for ZS  *(REJECT — t00845)*

Data-derived (D-series family 19). `hypotheses.yaml` (D63) · `decisions.md` §195

## D64 — 6E Follows a ZN Shock (next session)  *(WATCHLIST — t00846)*

Data-derived (D-series family 24). `hypotheses.yaml` (D64) · `decisions.md` §208

## D65 — 6E Follows a GC Shock (next session)  *(WATCHLIST — t00847)*

Data-derived (D-series family 24). `hypotheses.yaml` (D65) · `decisions.md` §208

## D66 — ZC Fades a CL Shock (next session)  *(CONFIRM — t00848)*

Data-derived (D-series family 24). `hypotheses.yaml` (D66) · `decisions.md` §208

## D67 — GC Follows a ZN Shock (next session)  *(REJECT — t00849)*

Data-derived (D-series family 24). `hypotheses.yaml` (D67) · `decisions.md` §208

## D68 — ES Follows a ZN Shock (next session)  *(CONFIRM — t00850)*

Data-derived (D-series family 24). `hypotheses.yaml` (D68) · `decisions.md` §208

## D69 — ES Follows a GC Shock (next session)  *(WATCHLIST — t00851)*

Data-derived (D-series family 24). `hypotheses.yaml` (D69) · `decisions.md` §208

## D70 — NG Follows a ES Shock (next session)  *(WATCHLIST — t00852)*

Data-derived (D-series family 24). `hypotheses.yaml` (D70) · `decisions.md` §208

## D71 — HG Follows a ZN Shock (next session)  *(WATCHLIST — t00853)*

Data-derived (D-series family 24). `hypotheses.yaml` (D71) · `decisions.md` §208

## D72 — MGC_win Follows a ZN Shock  *(WATCHLIST — t00854)*

Data-derived (D-series family 25). `hypotheses.yaml` (D72) · `decisions.md` §213

## D73 — MGC_win Follows a 6E Shock  *(REJECT — t00855)*

Data-derived (D-series family 25). `hypotheses.yaml` (D73) · `decisions.md` §213

## D74 — DAX_win Fades a 6E Shock  *(WATCHLIST — t00856)*

Data-derived (D-series family 25). `hypotheses.yaml` (D74) · `decisions.md` §213

## D75 — ES Follows a GC Shock (next3)  *(WATCHLIST — t00857)*

Data-derived (D-series family 26). `hypotheses.yaml` (D75) · `decisions.md` §216

## D76 — ZS Fades a ZN Shock (days2-3)  *(WATCHLIST — t00858)*

Data-derived (D-series family 26). `hypotheses.yaml` (D76) · `decisions.md` §216

## D77 — GC Follows a ES Shock (days2-3)  *(REJECT — t00859)*

Data-derived (D-series family 26). `hypotheses.yaml` (D77) · `decisions.md` §216

## D78 — ES Follows a GC Shock (days2-3)  *(WATCHLIST — t00860)*

Data-derived (D-series family 26). `hypotheses.yaml` (D78) · `decisions.md` §216

## D79 — NQ Follows a Volume Shock (next 3)  *(REJECT — t00861)*

Data-derived (D-series family 27). `hypotheses.yaml` (D79) · `decisions.md` §219

## D80 — ZS Fades a Volume Shock (next 1)  *(WATCHLIST — t00862)*

Data-derived (D-series family 27). `hypotheses.yaml` (D80) · `decisions.md` §219

## D81 — ZW Fades a Volume Shock (next 1)  *(WATCHLIST — t00863)*

Data-derived (D-series family 27). `hypotheses.yaml` (D81) · `decisions.md` §219

## D82 — 6E Fades a Yield-Curve Shock  *(REJECT — t00864)*

Data-derived (D-series family 28). `hypotheses.yaml` (D82) · `decisions.md` §222

## D83 — HG Fades a Yield-Curve Shock  *(REJECT — t00865)*

Data-derived (D-series family 28). `hypotheses.yaml` (D83) · `decisions.md` §222

## D84 — 6J Follows a NQ Shock (next session)  *(CONFIRM — t00866)*

Data-derived (D-series family 29). `hypotheses.yaml` (D84) · `decisions.md` §225

## D85 — 6E Follows a NQ Shock (next session)  *(WATCHLIST — t00867)*

Data-derived (D-series family 29). `hypotheses.yaml` (D85) · `decisions.md` §225

## D86 — NQ Follows a 6J Shock (next session)  *(REJECT — t00868)*

Data-derived (D-series family 29). `hypotheses.yaml` (D86) · `decisions.md` §225

## D87 — 6J Follows a ZC Shock (next session)  *(CONFIRM — t00869)*

Data-derived (D-series family 29). `hypotheses.yaml` (D87) · `decisions.md` §225

## D88 — 6E Follows a RTY Shock (next session)  *(WATCHLIST — t00870)*

Data-derived (D-series family 29). `hypotheses.yaml` (D88) · `decisions.md` §225

## D89 — 6E Follows a SI Shock (next session)  *(CONFIRM — t00871)*

Data-derived (D-series family 29). `hypotheses.yaml` (D89) · `decisions.md` §225

## D90 — ES Follows a 6J Shock (next session)  *(REJECT — t00872)*

Data-derived (D-series family 29). `hypotheses.yaml` (D90) · `decisions.md` §225

## D91 — ZN Follows a NQ Shock (next session)  *(REJECT — t00873)*

Data-derived (D-series family 29). `hypotheses.yaml` (D91) · `decisions.md` §225

## D92 — 6J Follows a RTY Shock (next session)  *(WATCHLIST — t00874)*

Data-derived (D-series family 29). `hypotheses.yaml` (D92) · `decisions.md` §225

## D93 — 6E Follows a HG Shock (next session)  *(REJECT — t00875)*

Data-derived (D-series family 29). `hypotheses.yaml` (D93) · `decisions.md` §225

## D94 — RTY Follows a 6J Shock (next session)  *(REJECT — t00876)*

Data-derived (D-series family 29). `hypotheses.yaml` (D94) · `decisions.md` §225

## D95 — ZW Fades Small Crowding  *(REJECT — t00877)*

Data-derived (D-series family 31). `hypotheses.yaml` (D95) · `decisions.md` §231

## D96 — SI Follows Small Flow  *(REJECT — t00878)*

Data-derived (D-series family 31). `hypotheses.yaml` (D96) · `decisions.md` §231


## D97 — Gbp Fades Move Into Fix  *(REJECT — t00879)*

Data-derived (D-series family 41). `hypotheses.yaml` (D97) · `decisions.md` §253

## D98 — Gbp Fades Strong Move Into Fix  *(REJECT — t00880)*

Data-derived (D-series family 41). `hypotheses.yaml` (D98) · `decisions.md` §253

## D99 — Chf Fades Strong Move Into Fix  *(WATCHLIST — t00881)*

Data-derived (D-series family 41). `hypotheses.yaml` (D99) · `decisions.md` §253

## D100 — Mnq Afternoon Follows Morning Unless Trending  *(WATCHLIST — t00882)*

Data-derived (D-series family 49). `hypotheses.yaml` (D100) · `decisions.md` §272

## D101 — Mnq Day Follows Opening Minute  *(WATCHLIST — t00883)*

Data-derived (D-series family 52). `hypotheses.yaml` (D101) · `decisions.md` §279

## D102 — Dax Fades Credit Shock  *(WATCHLIST — t00884)*

Data-derived (D-series family 57). `hypotheses.yaml` (D102) · `decisions.md` §290

## D103 — Gold Fades Real Yield Shock  *(REJECT — t00885)*

Data-derived (D-series family 63). `hypotheses.yaml` (D103) · `decisions.md` §304

## D104 — Yen Recovers After Gotobi Fix  *(WATCHLIST — t00886)*

Data-derived (D-series family 66). `hypotheses.yaml` (D104) · `decisions.md` §311

## D105 — Mnq Fades Bank Shock  *(WATCHLIST — t00887)*

Data-derived (D-series family 76). `hypotheses.yaml` (D105) · `decisions.md` §332

## D106 — Mnq Fades Tech Shock  *(WATCHLIST — t00888)*

Data-derived (D-series family 77). `hypotheses.yaml` (D106) · `decisions.md` §335

## D107 — 6B Follows Zn Shock  *(WATCHLIST — t00883)*

Data-derived (D-series family 83). `hypotheses.yaml` (D107) · `decisions.md` §348

## D108 — 6A Follows Zn Shock  *(REJECT — t00884)*

Data-derived (D-series family 83). `hypotheses.yaml` (D108) · `decisions.md` §348

## D109 — 6S Follows Nq Shock  *(WATCHLIST — t00885)*

Data-derived (D-series family 83). `hypotheses.yaml` (D109) · `decisions.md` §348

## D110 — 6S Follows Gc Shock  *(WATCHLIST — t00886)*

Data-derived (D-series family 83). `hypotheses.yaml` (D110) · `decisions.md` §348

## D111 — 6B Follows Gc Shock  *(WATCHLIST — t00887)*

Data-derived (D-series family 83). `hypotheses.yaml` (D111) · `decisions.md` §348

## D112 — 6S Follows Zn Shock  *(REJECT — t00888)*

Data-derived (D-series family 83). `hypotheses.yaml` (D112) · `decisions.md` §348

## D113 — 6S Follows Es Shock  *(WATCHLIST — t00889)*

Data-derived (D-series family 83). `hypotheses.yaml` (D113) · `decisions.md` §348

## D114 — 6C Follows Zn Shock  *(WATCHLIST — t00890)*

Data-derived (D-series family 83). `hypotheses.yaml` (D114) · `decisions.md` §348

## D115 — Nkd Follows Strong Tokyo Morning  *(REJECT — t00897)*

Data-derived (D-series family 86). `hypotheses.yaml` (D115) · `decisions.md` §355

## D116 — Dollar Bid Into Gotobi Fix  *(WATCHLIST — t00898)*

Data-derived (D-series family 86). `hypotheses.yaml` (D116) · `decisions.md` §355

## D117 — Gold Fades Strong Move Into Settlement  *(REJECT — t00899)*

Data-derived (D-series family 86). `hypotheses.yaml` (D117) · `decisions.md` §355

## D118 — Euro Firms After Ecb Fix  *(WATCHLIST — t00900)*

Data-derived (D-series family 86). `hypotheses.yaml` (D118) · `decisions.md` §355

## D119 — Gold Follows Long Bond Shock  *(REJECT — t00901)*

Data-derived (D-series family 86). `hypotheses.yaml` (D119) · `decisions.md` §355

## D120 — Gold Follows Credit Bond Shock  *(REJECT — t00902)*

Data-derived (D-series family 86). `hypotheses.yaml` (D120) · `decisions.md` §355

## D121 — Dollar Recovers After Monthend Fix  *(WATCHLIST — t00903)*

Data-derived (D-series family 94). `hypotheses.yaml` (D121) · `decisions.md` §374

## D122 — Zs Falls After Real Weakens  *(CONFIRM — t00904)*

Data-derived (D-series family 97). `hypotheses.yaml` (D122) · `decisions.md` §381

## D123 — Zc Falls After Real Weakens  *(WATCHLIST — t00905)*

Data-derived (D-series family 97). `hypotheses.yaml` (D123) · `decisions.md` §381

## D124 — Copper Falls After Peso Weakens  *(WATCHLIST — t00906)*

Data-derived (D-series family 98). `hypotheses.yaml` (D124) · `decisions.md` §385

## D125 — Crude Falls After Colombian Peso Weakens  *(REJECT — t00907)*

Data-derived (D-series family 100). `hypotheses.yaml` (D125) · `decisions.md` §390

## D126 — Crude Falls After Em Currency Stress  *(REJECT — t00908)*

Data-derived (D-series family 103). `hypotheses.yaml` (D126) · `decisions.md` §397

## D127 — 6E Follows Two Year Shock  *(WATCHLIST — t00909)*

Data-derived (D-series family 108). `hypotheses.yaml` (D127) · `decisions.md` §408

## D128 — 6A Follows Two Year Shock  *(REJECT — t00910)*

Data-derived (D-series family 108). `hypotheses.yaml` (D128) · `decisions.md` §408

## D129 — Nkd Follows Vix3M Shock  *(REJECT — t00911)*

Data-derived (D-series family 111). `hypotheses.yaml` (D129) · `decisions.md` §415

## D130 — Mgc Fades Clpx Shock  *(WATCHLIST — t00912)*

Data-derived (D-series family 111). `hypotheses.yaml` (D130) · `decisions.md` §415

## D131 — Mgc Follows 6Sf Shock  *(WATCHLIST — t00913)*

Data-derived (D-series family 111). `hypotheses.yaml` (D131) · `decisions.md` §415

## D132 — Nkd Follows Lqd Shock  *(REJECT — t00914)*

Data-derived (D-series family 111). `hypotheses.yaml` (D132) · `decisions.md` §415

## D133 — Nkd Follows Gdaxi Shock R  *(REJECT — t00915)*

Data-derived (D-series family 114). `hypotheses.yaml` (D133) · `decisions.md` §428

## D134 — Zs Follows 6Af Shock R  *(REJECT — t00916)*

Data-derived (D-series family 114). `hypotheses.yaml` (D134) · `decisions.md` §428

## D135 — Nkd Follows Xlf Shock R  *(WATCHLIST — t00917)*

Data-derived (D-series family 114). `hypotheses.yaml` (D135) · `decisions.md` §428

## D136 — Cl Follows 6Af Shock R  *(REJECT — t00918)*

Data-derived (D-series family 114). `hypotheses.yaml` (D136) · `decisions.md` §428

## D137 — Dax Follows Plf Shock R  *(REJECT — t00919)*

Data-derived (D-series family 114). `hypotheses.yaml` (D137) · `decisions.md` §428

## D138 — Zs Fades Krwx Shock R  *(WATCHLIST — t00920)*

Data-derived (D-series family 114). `hypotheses.yaml` (D138) · `decisions.md` §428

## D139 — Nkd Fades Btcf Shock R  *(CONFIRM — t00921)*

Data-derived (D-series family 114). `hypotheses.yaml` (D139) · `decisions.md` §428

## D140 — Dax Follows Gcf Shock R  *(REJECT — t00922)*

Data-derived (D-series family 114). `hypotheses.yaml` (D140) · `decisions.md` §428

## D141 — Zs Fades Copx Shock R  *(WATCHLIST — t00923)*

Data-derived (D-series family 114). `hypotheses.yaml` (D141) · `decisions.md` §428

## D142 — Zs Follows Audusdx Shock R  *(WATCHLIST — t00924)*

Data-derived (D-series family 114). `hypotheses.yaml` (D142) · `decisions.md` §428

## D143 — Mnq Fades Hgf Shock R  *(REJECT — t00925)*

Data-derived (D-series family 114). `hypotheses.yaml` (D143) · `decisions.md` §428

## D144 — Zs Fades Clpx Shock R  *(WATCHLIST — t00926)*

Data-derived (D-series family 114). `hypotheses.yaml` (D144) · `decisions.md` §428

## D145 — Zs Follows Fxi Shock R  *(REJECT — t00927)*

Data-derived (D-series family 114). `hypotheses.yaml` (D145) · `decisions.md` §428

## D146 — Dax Follows Znf Shock R  *(WATCHLIST — t00928)*

Data-derived (D-series family 114). `hypotheses.yaml` (D146) · `decisions.md` §428

## D147 — Dax Fades 6Bf Shock R  *(WATCHLIST — t00929)*

Data-derived (D-series family 114). `hypotheses.yaml` (D147) · `decisions.md` §428

## D148 — Dax Follows 6Cf Shock R  *(REJECT — t00930)*

Data-derived (D-series family 114). `hypotheses.yaml` (D148) · `decisions.md` §428

## D149 — Nkd Fades Zsf Shock R  *(WATCHLIST — t00931)*

Data-derived (D-series family 114). `hypotheses.yaml` (D149) · `decisions.md` §428

## D150 — Dax Follows Rubx Shock R  *(WATCHLIST — t00932)*

Data-derived (D-series family 114). `hypotheses.yaml` (D150) · `decisions.md` §428

## D151 — Zs Fades Zmf Shock R  *(CONFIRM — t00933)*

Data-derived (D-series family 114). `hypotheses.yaml` (D151) · `decisions.md` §428

## D152 — Mnq Opening Minute Strong Follow R  *(WATCHLIST — t00934)*

Data-derived (D-series family 115). `hypotheses.yaml` (D152) · `decisions.md` §434

## D153 — Mnq Last Hour Next All Fade R  *(WATCHLIST — t00935)*

Data-derived (D-series family 115). `hypotheses.yaml` (D153) · `decisions.md` §434

## D154 — Zs Short In Expiry Week R  *(REJECT — t00936)*

Data-derived (D-series family 116). `hypotheses.yaml` (D154) · `decisions.md` §437

## D155 — Mnq Fades Trend5 R  *(REJECT — t00937)*

Data-derived (D-series family 117). `hypotheses.yaml` (D155) · `decisions.md` §439

## D156 — Dax Fades Own Shock R  *(WATCHLIST — t00938)*

Data-derived (D-series family 117). `hypotheses.yaml` (D156) · `decisions.md` §439

## D157 — Cl Follows Kre All Alldays  *(REJECT — t00939)*

Data-derived (D-series family 119). `hypotheses.yaml` (D157) · `decisions.md` §444

## D158 — Dax Fades 6Sf Strong Alldays  *(WATCHLIST — t00940)*

Data-derived (D-series family 119). `hypotheses.yaml` (D158) · `decisions.md` §444

## D159 — Cl Follows Kre Strong Alldays  *(WATCHLIST — t00941)*

Data-derived (D-series family 119). `hypotheses.yaml` (D159) · `decisions.md` §444

## D160 — Cl Follows Xop Strong Alldays  *(WATCHLIST — t00942)*

Data-derived (D-series family 119). `hypotheses.yaml` (D160) · `decisions.md` §444

## D161 — Cl Follows Xop All Alldays  *(REJECT — t00943)*

Data-derived (D-series family 119). `hypotheses.yaml` (D161) · `decisions.md` §444

## D162 — Dax Fades 6Ef All Alldays  *(WATCHLIST — t00944)*

Data-derived (D-series family 119). `hypotheses.yaml` (D162) · `decisions.md` §444

## D163 — Nkd Follows Xop All Alldays  *(WATCHLIST — t00945)*

Data-derived (D-series family 119). `hypotheses.yaml` (D163) · `decisions.md` §444

## D164 — Mnq Follows Skew Strong Alldays  *(WATCHLIST — t00946)*

Data-derived (D-series family 119). `hypotheses.yaml` (D164) · `decisions.md` §444

## D165 — Cl Follows Xlf All Alldays  *(REJECT — t00947)*

Data-derived (D-series family 119). `hypotheses.yaml` (D165) · `decisions.md` §444

## D166 — Nkd Follows Ngf All Alldays  *(REJECT — t00948)*

Data-derived (D-series family 119). `hypotheses.yaml` (D166) · `decisions.md` §444

## D167 — Dax Fades 6Cf Strong Alldays  *(WATCHLIST — t00949)*

Data-derived (D-series family 119). `hypotheses.yaml` (D167) · `decisions.md` §444

## D168 — Mnq Fades Zlf Strong Alldays  *(REJECT — t00950)*

Data-derived (D-series family 119). `hypotheses.yaml` (D168) · `decisions.md` §444

## D169 — Dax Fades 6Ef Strong Alldays  *(WATCHLIST — t00951)*

Data-derived (D-series family 119). `hypotheses.yaml` (D169) · `decisions.md` §444

## D170 — Cl Follows Hyg All Alldays  *(REJECT — t00952)*

Data-derived (D-series family 119). `hypotheses.yaml` (D170) · `decisions.md` §444

## D171 — Dax Fades 6Bf All Alldays  *(CONFIRM — t00953)*

Data-derived (D-series family 119). `hypotheses.yaml` (D171) · `decisions.md` §444

## D172 — Cl Follows Nkdf All Alldays  *(REJECT — t00954)*

Data-derived (D-series family 119). `hypotheses.yaml` (D172) · `decisions.md` §444

## D173 — Cl Follows Xlf Strong Alldays  *(REJECT — t00955)*

Data-derived (D-series family 119). `hypotheses.yaml` (D173) · `decisions.md` §444

## D174 — Dax Follows Dxynyb Strong Alldays  *(CONFIRM — t00956)*

Data-derived (D-series family 119). `hypotheses.yaml` (D174) · `decisions.md` §444

## D175 — Dax Fades 6Af Strong Alldays  *(CONFIRM — t00957)*

Data-derived (D-series family 119). `hypotheses.yaml` (D175) · `decisions.md` §444

## D176 — Nkd Fades Gvz All Alldays  *(REJECT — t00958)*

Data-derived (D-series family 119). `hypotheses.yaml` (D176) · `decisions.md` §444

## D177 — Dax Fades 6Sf All Alldays  *(WATCHLIST — t00959)*

Data-derived (D-series family 119). `hypotheses.yaml` (D177) · `decisions.md` §444

## D178 — Nkd Follows Xop Strong Alldays  *(REJECT — t00960)*

Data-derived (D-series family 119). `hypotheses.yaml` (D178) · `decisions.md` §444

## D179 — Cl Follows Eem All Alldays  *(REJECT — t00961)*

Data-derived (D-series family 119). `hypotheses.yaml` (D179) · `decisions.md` §444

## D180 — Zs Follows Bg Strong Alldays  *(REJECT — t00962)*

Data-derived (D-series family 119). `hypotheses.yaml` (D180) · `decisions.md` §444

## D181 — Zs Fades Vix Strong Alldays  *(REJECT — t00963)*

Data-derived (D-series family 119). `hypotheses.yaml` (D181) · `decisions.md` §444

## D182 — Mnq Follows Skew All Alldays  *(WATCHLIST — t00964)*

Data-derived (D-series family 119). `hypotheses.yaml` (D182) · `decisions.md` §444

## D183 — Dax Fades Mxnx All Alldays  *(REJECT — t00965)*

Data-derived (D-series family 119). `hypotheses.yaml` (D183) · `decisions.md` §444

## D184 — Nkd Follows Adm Strong Alldays  *(WATCHLIST — t00966)*

Data-derived (D-series family 119). `hypotheses.yaml` (D184) · `decisions.md` §444

## D185 — Cl Follows Xle Strong Alldays  *(WATCHLIST — t00967)*

Data-derived (D-series family 119). `hypotheses.yaml` (D185) · `decisions.md` §444

## D186 — Cl Follows Hyg Strong Alldays  *(REJECT — t00968)*

Data-derived (D-series family 119). `hypotheses.yaml` (D186) · `decisions.md` §444

## D187 — Mnq Fades Clpx Strong Alldays  *(REJECT — t00969)*

Data-derived (D-series family 119). `hypotheses.yaml` (D187) · `decisions.md` §444

## D188 — Dax Fades 6Jf All Alldays  *(WATCHLIST — t00970)*

Data-derived (D-series family 119). `hypotheses.yaml` (D188) · `decisions.md` §444

## D189 — Mnq Fades Zlf All Alldays  *(REJECT — t00971)*

Data-derived (D-series family 119). `hypotheses.yaml` (D189) · `decisions.md` §444

## D190 — Mnq Fades Inrx All Alldays  *(REJECT — t00972)*

Data-derived (D-series family 119). `hypotheses.yaml` (D190) · `decisions.md` §444

## D191 — Nkd Follows Fxi All Alldays  *(REJECT — t00973)*

Data-derived (D-series family 119). `hypotheses.yaml` (D191) · `decisions.md` §444

## D192 — Nkd Follows Hyg Strong Alldays  *(REJECT — t00974)*

Data-derived (D-series family 119). `hypotheses.yaml` (D192) · `decisions.md` §444

## D193 — Mnq Fades Zsf All Alldays  *(REJECT — t00975)*

Data-derived (D-series family 119). `hypotheses.yaml` (D193) · `decisions.md` §444

## D194 — Cl Follows Eem Strong Alldays  *(REJECT — t00976)*

Data-derived (D-series family 119). `hypotheses.yaml` (D194) · `decisions.md` §444

## D195 — Zs Follows Eem Strong Alldays  *(WATCHLIST — t00977)*

Data-derived (D-series family 119). `hypotheses.yaml` (D195) · `decisions.md` §444

## D196 — Nkd Follows Xle All Alldays  *(REJECT — t00978)*

Data-derived (D-series family 119). `hypotheses.yaml` (D196) · `decisions.md` §444

## D197 — Dax Fades 6Jf Strong Alldays  *(WATCHLIST — t00979)*

Data-derived (D-series family 119). `hypotheses.yaml` (D197) · `decisions.md` §444

## D198 — Dax Follows Krwx All Alldays  *(WATCHLIST — t00980)*

Data-derived (D-series family 119). `hypotheses.yaml` (D198) · `decisions.md` §444

## D199 — Nkd Fades Gvz Strong Alldays  *(REJECT — t00981)*

Data-derived (D-series family 119). `hypotheses.yaml` (D199) · `decisions.md` §444

## D200 — Dax Follows Dxynyb All Alldays  *(WATCHLIST — t00982)*

Data-derived (D-series family 119). `hypotheses.yaml` (D200) · `decisions.md` §444

## D201 — Nkd Follows Gdaxi Week Strong  *(REJECT — t00983)*

Data-derived (D-series family 120). `hypotheses.yaml` (D201) · `decisions.md` §450

## D202 — Nkd Follows 6Ef Week Strong  *(CONFIRM — t00984)*

Data-derived (D-series family 120). `hypotheses.yaml` (D202) · `decisions.md` §450

## D203 — Nkd Follows Fxi Week All  *(WATCHLIST — t00985)*

Data-derived (D-series family 120). `hypotheses.yaml` (D203) · `decisions.md` §450

## D204 — Cl Fades Plf Week Strong  *(REJECT — t00986)*

Data-derived (D-series family 120). `hypotheses.yaml` (D204) · `decisions.md` §450

## D205 — Nkd Follows 6Bf Week All  *(WATCHLIST — t00987)*

Data-derived (D-series family 120). `hypotheses.yaml` (D205) · `decisions.md` §450

## D206 — Nkd Follows Gdaxi Week All  *(REJECT — t00988)*

Data-derived (D-series family 120). `hypotheses.yaml` (D206) · `decisions.md` §450

## D207 — Cl Fades Hef Week Strong  *(REJECT — t00989)*

Data-derived (D-series family 120). `hypotheses.yaml` (D207) · `decisions.md` §450

## D208 — Nkd Follows Fxi Week Strong  *(WATCHLIST — t00990)*

Data-derived (D-series family 120). `hypotheses.yaml` (D208) · `decisions.md` §450

## D209 — Nkd Follows Eem Week Strong  *(WATCHLIST — t00991)*

Data-derived (D-series family 120). `hypotheses.yaml` (D209) · `decisions.md` §450

## D210 — Nkd Follows Eem Week All  *(WATCHLIST — t00992)*

Data-derived (D-series family 120). `hypotheses.yaml` (D210) · `decisions.md` §450

## D211 — Dax Fades Hof Week Strong  *(REJECT — t00993)*

Data-derived (D-series family 120). `hypotheses.yaml` (D211) · `decisions.md` §450

## D212 — Dax Fades Clf Week All  *(REJECT — t00994)*

Data-derived (D-series family 120). `hypotheses.yaml` (D212) · `decisions.md` §450

## D213 — Nkd Fades Vix3M Week All  *(REJECT — t00995)*

Data-derived (D-series family 120). `hypotheses.yaml` (D213) · `decisions.md` §450

## D214 — Nkd Fades Gvz Week Strong  *(REJECT — t00996)*

Data-derived (D-series family 120). `hypotheses.yaml` (D214) · `decisions.md` §450

## D215 — Dax Follows Zbf Week Strong  *(REJECT — t00997)*

Data-derived (D-series family 120). `hypotheses.yaml` (D215) · `decisions.md` §450

## D216 — Nkd Fades Zcf Week Strong  *(WATCHLIST — t00998)*

Data-derived (D-series family 120). `hypotheses.yaml` (D216) · `decisions.md` §450

## D217 — Dax Fades Clf Week Strong  *(REJECT — t00999)*

Data-derived (D-series family 120). `hypotheses.yaml` (D217) · `decisions.md` §450

## D218 — Mnq Fades Kre Week Strong  *(REJECT — t01000)*

Data-derived (D-series family 120). `hypotheses.yaml` (D218) · `decisions.md` §450

## D219 — Nkd Fades Vix Week All  *(WATCHLIST — t01001)*

Data-derived (D-series family 120). `hypotheses.yaml` (D219) · `decisions.md` §450

## D220 — Mnq Fades Rtyf Week Strong  *(REJECT — t01002)*

Data-derived (D-series family 120). `hypotheses.yaml` (D220) · `decisions.md` §450

## D221 — Dax Follows Znf Week All  *(REJECT — t01003)*

Data-derived (D-series family 120). `hypotheses.yaml` (D221) · `decisions.md` §450

## D222 — Nkd Follows 6Bf Week Strong  *(CONFIRM — t01004)*

Data-derived (D-series family 120). `hypotheses.yaml` (D222) · `decisions.md` §450

## D223 — Zs Fades Clpx Week All  *(REJECT — t01005)*

Data-derived (D-series family 120). `hypotheses.yaml` (D223) · `decisions.md` §450

## D224 — Zs Follows Zbf Week All  *(REJECT — t01006)*

Data-derived (D-series family 120). `hypotheses.yaml` (D224) · `decisions.md` §450

## D225 — Nkd Fades Vvix Week All  *(REJECT — t01007)*

Data-derived (D-series family 120). `hypotheses.yaml` (D225) · `decisions.md` §450

## D226 — Mnq Fades Adm Week Strong  *(WATCHLIST — t01008)*

Data-derived (D-series family 120). `hypotheses.yaml` (D226) · `decisions.md` §450

## D227 — Nkd Follows 6Ef Week All  *(CONFIRM — t01009)*

Data-derived (D-series family 120). `hypotheses.yaml` (D227) · `decisions.md` §450

## D228 — Nkd Follows Xly Week Strong  *(WATCHLIST — t01010)*

Data-derived (D-series family 120). `hypotheses.yaml` (D228) · `decisions.md` §450

## D229 — Zs Fades Krwx Week Strong  *(WATCHLIST — t01011)*

Data-derived (D-series family 120). `hypotheses.yaml` (D229) · `decisions.md` §450

## D230 — Nkd Fades Vix3M Week Strong  *(WATCHLIST — t01012)*

Data-derived (D-series family 120). `hypotheses.yaml` (D230) · `decisions.md` §450

## D231 — Nkd Fades Zcf Week All  *(CONFIRM — t01013)*

Data-derived (D-series family 120). `hypotheses.yaml` (D231) · `decisions.md` §450

## D232 — Dax Follows Znf Week Strong  *(REJECT — t01014)*

Data-derived (D-series family 120). `hypotheses.yaml` (D232) · `decisions.md` §450

## D233 — Zs Follows Xlf Week Strong  *(REJECT — t01015)*

Data-derived (D-series family 120). `hypotheses.yaml` (D233) · `decisions.md` §450

## D234 — Nkd Fades Vvix Week Strong  *(REJECT — t01016)*

Data-derived (D-series family 120). `hypotheses.yaml` (D234) · `decisions.md` §450

## D235 — Mnq Fades Eem Week All  *(WATCHLIST — t01017)*

Data-derived (D-series family 120). `hypotheses.yaml` (D235) · `decisions.md` §450

## D236 — Cl Fades Soyb Week Strong  *(REJECT — t01018)*

Data-derived (D-series family 120). `hypotheses.yaml` (D236) · `decisions.md` §450

## D237 — Dax Fades Hof Week All  *(REJECT — t01019)*

Data-derived (D-series family 120). `hypotheses.yaml` (D237) · `decisions.md` §450

## D238 — Nkd Fades Gvz Week All  *(REJECT — t01020)*

Data-derived (D-series family 120). `hypotheses.yaml` (D238) · `decisions.md` §450

## D239 — Zs Fades Clpx Week Strong  *(REJECT — t01021)*

Data-derived (D-series family 120). `hypotheses.yaml` (D239) · `decisions.md` §450

## D240 — Cl Follows Xlf Week All  *(WATCHLIST — t01022)*

Data-derived (D-series family 120). `hypotheses.yaml` (D240) · `decisions.md` §450

## D241 — Nkd Follows Smh Week All  *(WATCHLIST — t01023)*

Data-derived (D-series family 120). `hypotheses.yaml` (D241) · `decisions.md` §450

## D242 — Nkd Fades Dxynyb Week Strong  *(CONFIRM — t01024)*

Data-derived (D-series family 120). `hypotheses.yaml` (D242) · `decisions.md` §450

## D243 — Nkd Follows Smh Week Strong  *(WATCHLIST — t01025)*

Data-derived (D-series family 120). `hypotheses.yaml` (D243) · `decisions.md` §450

## D244 — Cl Follows Xly Week Strong  *(REJECT — t01026)*

Data-derived (D-series family 120). `hypotheses.yaml` (D244) · `decisions.md` §450

## D245 — Nkd Follows Xlf Week Strong  *(WATCHLIST — t01027)*

Data-derived (D-series family 120). `hypotheses.yaml` (D245) · `decisions.md` §450

## D246 — Mnq Fades Smh Week Strong  *(CONFIRM — t01028)*

Data-derived (D-series family 120). `hypotheses.yaml` (D246) · `decisions.md` §450

## D247 — Dax Fades Dfii10 Week All  *(REJECT — t01029)*

Data-derived (D-series family 120). `hypotheses.yaml` (D247) · `decisions.md` §450

## D248 — Dax Fades Dfii10 Week Strong  *(REJECT — t01030)*

Data-derived (D-series family 120). `hypotheses.yaml` (D248) · `decisions.md` §450

## D249 — Nkd Fades Vix Week Strong  *(REJECT — t01031)*

Data-derived (D-series family 120). `hypotheses.yaml` (D249) · `decisions.md` §450

## D250 — Dax Follows Copx Month All  *(REJECT — t01032)*

Data-derived (D-series family 121). `hypotheses.yaml` (D250) · `decisions.md` §456

## D251 — Mnq Fades Adm Month Strong  *(REJECT — t01033)*

Data-derived (D-series family 121). `hypotheses.yaml` (D251) · `decisions.md` §456

## D252 — Nkd Follows Eem Month Strong  *(WATCHLIST — t01034)*

Data-derived (D-series family 121). `hypotheses.yaml` (D252) · `decisions.md` §456

## D253 — Mgc Follows Copx Month All  *(REJECT — t01035)*

Data-derived (D-series family 121). `hypotheses.yaml` (D253) · `decisions.md` §456

## D254 — Zs Fades Clpx Month All  *(REJECT — t01036)*

Data-derived (D-series family 121). `hypotheses.yaml` (D254) · `decisions.md` §456

## D255 — Mgc Follows Idrx Month Strong  *(REJECT — t01037)*

Data-derived (D-series family 121). `hypotheses.yaml` (D255) · `decisions.md` §456

## D256 — Dax Fades Clf Month All  *(WATCHLIST — t01038)*

Data-derived (D-series family 121). `hypotheses.yaml` (D256) · `decisions.md` §456

## D257 — Mnq Fades Clf Month All  *(WATCHLIST — t01039)*

Data-derived (D-series family 121). `hypotheses.yaml` (D257) · `decisions.md` §456

## D258 — Nkd Follows Xlf Month Strong  *(WATCHLIST — t01040)*

Data-derived (D-series family 121). `hypotheses.yaml` (D258) · `decisions.md` §456

## D259 — Nkd Follows Fxi Month All  *(WATCHLIST — t01041)*

Data-derived (D-series family 121). `hypotheses.yaml` (D259) · `decisions.md` §456

## D260 — Zs Fades Krwx Month Strong  *(WATCHLIST — t01042)*

Data-derived (D-series family 121). `hypotheses.yaml` (D260) · `decisions.md` §456

## D261 — Dax Fades Ngf Month Strong  *(WATCHLIST — t01043)*

Data-derived (D-series family 121). `hypotheses.yaml` (D261) · `decisions.md` §456

## D262 — Mnq Follows Ovx Month Strong  *(WATCHLIST — t01044)*

Data-derived (D-series family 121). `hypotheses.yaml` (D262) · `decisions.md` §456

## D263 — Zs Follows Rubx Month All  *(WATCHLIST — t01045)*

Data-derived (D-series family 121). `hypotheses.yaml` (D263) · `decisions.md` §456

## D264 — Nkd Fades Zcf Month All  *(CONFIRM — t01046)*

Data-derived (D-series family 121). `hypotheses.yaml` (D264) · `decisions.md` §456

## D265 — Dax Fades Overnight Usdjpy R  *(REJECT — t01047)*

Data-derived (D-series family 122). `hypotheses.yaml` (D265) · `decisions.md` §459

## D266 — Nkd Follows Fxi Twoday All  *(REJECT — t01048)*

Data-derived (D-series family 123). `hypotheses.yaml` (D266) · `decisions.md` §461

## D267 — Cl Follows Kre Twoday Strong  *(REJECT — t01049)*

Data-derived (D-series family 123). `hypotheses.yaml` (D267) · `decisions.md` §461

## D268 — Cl Fades Zmf Twoday Strong  *(REJECT — t01050)*

Data-derived (D-series family 123). `hypotheses.yaml` (D268) · `decisions.md` §461

## D269 — Cl Follows Kre Twoday All  *(REJECT — t01051)*

Data-derived (D-series family 123). `hypotheses.yaml` (D269) · `decisions.md` §461

## D270 — Cl Fades Zmf Twoday All  *(REJECT — t01052)*

Data-derived (D-series family 123). `hypotheses.yaml` (D270) · `decisions.md` §461

## D271 — Nkd Follows Fxi Twoday Strong  *(WATCHLIST — t01053)*

Data-derived (D-series family 123). `hypotheses.yaml` (D271) · `decisions.md` §461

## D272 — Cl Follows Xlf Twoday All  *(WATCHLIST — t01054)*

Data-derived (D-series family 123). `hypotheses.yaml` (D272) · `decisions.md` §461

## D273 — Nkd Follows Xly Twoday All  *(REJECT — t01055)*

Data-derived (D-series family 123). `hypotheses.yaml` (D273) · `decisions.md` §461

## D274 — Cl Follows Nkdf Twoday All  *(WATCHLIST — t01056)*

Data-derived (D-series family 123). `hypotheses.yaml` (D274) · `decisions.md` §461

## D275 — Nkd Follows Eem Twoday All  *(REJECT — t01057)*

Data-derived (D-series family 123). `hypotheses.yaml` (D275) · `decisions.md` §461

## D276 — Nkd Follows Xly Twoday Strong  *(REJECT — t01058)*

Data-derived (D-series family 123). `hypotheses.yaml` (D276) · `decisions.md` §461

## D277 — Nkd Fades Gvz Twoday Strong  *(WATCHLIST — t01059)*

Data-derived (D-series family 123). `hypotheses.yaml` (D277) · `decisions.md` §461

## D278 — Cl Follows Xop Twoday Strong  *(REJECT — t01060)*

Data-derived (D-series family 123). `hypotheses.yaml` (D278) · `decisions.md` §461

## D279 — Nkd Follows 6Bf Twoday All  *(CONFIRM — t01061)*

Data-derived (D-series family 123). `hypotheses.yaml` (D279) · `decisions.md` §461

## D280 — Nkd Follows Eem Twoday Strong  *(REJECT — t01062)*

Data-derived (D-series family 123). `hypotheses.yaml` (D280) · `decisions.md` §461

## D281 — Cl Follows Xlf Twoday Strong  *(REJECT — t01063)*

Data-derived (D-series family 123). `hypotheses.yaml` (D281) · `decisions.md` §461

## D282 — Nkd Follows Rtyf Twoday Strong  *(REJECT — t01064)*

Data-derived (D-series family 123). `hypotheses.yaml` (D282) · `decisions.md` §461

## D283 — Zs Follows Adm Twoday All  *(REJECT — t01065)*

Data-derived (D-series family 123). `hypotheses.yaml` (D283) · `decisions.md` §461

## D284 — Dax Follows Dxynyb Twoday Strong  *(WATCHLIST — t01066)*

Data-derived (D-series family 123). `hypotheses.yaml` (D284) · `decisions.md` §461

## D285 — Cl Follows Nkdf Twoday Strong  *(WATCHLIST — t01067)*

Data-derived (D-series family 123). `hypotheses.yaml` (D285) · `decisions.md` §461

## D286 — Zs Fades Vix Twoday All  *(REJECT — t01068)*

Data-derived (D-series family 123). `hypotheses.yaml` (D286) · `decisions.md` §461

## D287 — Mnq Fades Zlf Twoday All  *(REJECT — t01069)*

Data-derived (D-series family 123). `hypotheses.yaml` (D287) · `decisions.md` §461

## D288 — Dax Follows Krwx Twoday Strong  *(WATCHLIST — t01070)*

Data-derived (D-series family 123). `hypotheses.yaml` (D288) · `decisions.md` §461

## D289 — Cl Fades Hef Twoday All  *(WATCHLIST — t01071)*

Data-derived (D-series family 123). `hypotheses.yaml` (D289) · `decisions.md` §461

## D290 — Dax Follows Btcusd Twoday All  *(REJECT — t01072)*

Data-derived (D-series family 123). `hypotheses.yaml` (D290) · `decisions.md` §461

## D291 — Nkd Fades Vix3M Twoday All  *(REJECT — t01073)*

Data-derived (D-series family 123). `hypotheses.yaml` (D291) · `decisions.md` §461

## D292 — Dax Follows Vix Twoday Strong  *(WATCHLIST — t01074)*

Data-derived (D-series family 123). `hypotheses.yaml` (D292) · `decisions.md` §461

## D293 — Nkd Follows Adm Twoday Strong  *(WATCHLIST — t01075)*

Data-derived (D-series family 123). `hypotheses.yaml` (D293) · `decisions.md` §461

## D294 — Cl Follows Ovx Twoday All  *(WATCHLIST — t01076)*

Data-derived (D-series family 123). `hypotheses.yaml` (D294) · `decisions.md` §461

## D295 — Nkd Follows Hyg Twoday Strong  *(REJECT — t01077)*

Data-derived (D-series family 123). `hypotheses.yaml` (D295) · `decisions.md` §461

## D296 — Nkd Follows Esf Twoday All  *(REJECT — t01078)*

Data-derived (D-series family 123). `hypotheses.yaml` (D296) · `decisions.md` §461

## D297 — Zs Follows Bg Twoday All  *(WATCHLIST — t01079)*

Data-derived (D-series family 123). `hypotheses.yaml` (D297) · `decisions.md` §461

## D298 — Dax Fades 6Af Twoday All  *(WATCHLIST — t01080)*

Data-derived (D-series family 123). `hypotheses.yaml` (D298) · `decisions.md` §461

## D299 — Cl Follows Xop Twoday All  *(WATCHLIST — t01081)*

Data-derived (D-series family 123). `hypotheses.yaml` (D299) · `decisions.md` §461

## D300 — Cl Fades Soyb Twoday Strong  *(REJECT — t01082)*

Data-derived (D-series family 123). `hypotheses.yaml` (D300) · `decisions.md` §461

## D301 — Nkd Fades Vix3M Twoday Strong  *(REJECT — t01083)*

Data-derived (D-series family 123). `hypotheses.yaml` (D301) · `decisions.md` §461

## D302 — Dax Follows Vix3M Twoday Strong  *(REJECT — t01084)*

Data-derived (D-series family 123). `hypotheses.yaml` (D302) · `decisions.md` §461

## D303 — Zs Follows Adm Twoday Strong  *(WATCHLIST — t01085)*

Data-derived (D-series family 123). `hypotheses.yaml` (D303) · `decisions.md` §461

## D304 — Mnq Follows Krwx Twoday Strong  *(WATCHLIST — t01086)*

Data-derived (D-series family 123). `hypotheses.yaml` (D304) · `decisions.md` §461

## D305 — Nkd Fades Gvz Twoday All  *(REJECT — t01087)*

Data-derived (D-series family 123). `hypotheses.yaml` (D305) · `decisions.md` §461

## D306 — Mnq Fades Xop Twoday All  *(WATCHLIST — t01088)*

Data-derived (D-series family 123). `hypotheses.yaml` (D306) · `decisions.md` §461

## D307 — Nkd Follows Gdaxi Twoday Strong  *(WATCHLIST — t01089)*

Data-derived (D-series family 123). `hypotheses.yaml` (D307) · `decisions.md` §461

## D308 — Cl Follows Dfii10 Twoday All  *(REJECT — t01090)*

Data-derived (D-series family 123). `hypotheses.yaml` (D308) · `decisions.md` §461

## D309 — Dax Fades Nkdf Twoday Strong  *(CONFIRM — t01091)*

Data-derived (D-series family 123). `hypotheses.yaml` (D309) · `decisions.md` §461

## D310 — Nkd Follows Hyg Twoday All  *(WATCHLIST — t01092)*

Data-derived (D-series family 123). `hypotheses.yaml` (D310) · `decisions.md` §461

## D311 — Zs Follows Bg Twoday Strong  *(WATCHLIST — t01093)*

Data-derived (D-series family 123). `hypotheses.yaml` (D311) · `decisions.md` §461

## D312 — Nkd Follows Xlk Twoday All  *(REJECT — t01094)*

Data-derived (D-series family 123). `hypotheses.yaml` (D312) · `decisions.md` §461

## D313 — Nkd Follows Xlf Twoday All  *(REJECT — t01095)*

Data-derived (D-series family 123). `hypotheses.yaml` (D313) · `decisions.md` §461

## D314 — Dax Fades Nqf Twoday All  *(WATCHLIST — t01096)*

Data-derived (D-series family 123). `hypotheses.yaml` (D314) · `decisions.md` §461

## D315 — Cl Fades Hef Twoday Strong  *(REJECT — t01097)*

Data-derived (D-series family 123). `hypotheses.yaml` (D315) · `decisions.md` §461

## D316 — Dax Follows Krwx Twoday All  *(WATCHLIST — t01098)*

Data-derived (D-series family 123). `hypotheses.yaml` (D316) · `decisions.md` §461

## D317 — Fchi Follows Dxy Day Strong  *(WATCHLIST — t01099)*

Data-derived (D-series family 125). `hypotheses.yaml` (D317) · `decisions.md` §467

## D318 — Ks11 Follows Euro Week All  *(WATCHLIST — t01100)*

Data-derived (D-series family 125). `hypotheses.yaml` (D318) · `decisions.md` §467

## D319 — Ks11 Follows Euro Week Strong  *(WATCHLIST — t01101)*

Data-derived (D-series family 125). `hypotheses.yaml` (D319) · `decisions.md` §467

## D320 — Dax Short When Rates Rising R  *(REJECT — t01102)*

Data-derived (D-series family 127). `hypotheses.yaml` (D320) · `decisions.md` §472

## D321 — Cl Follows Crack 5D All  *(REJECT — t01103)*

Data-derived (D-series family 129). `hypotheses.yaml` (D321) · `decisions.md` §476

## D322 — Cl Follows Crack 5D Strong  *(REJECT — t01104)*

Data-derived (D-series family 129). `hypotheses.yaml` (D322) · `decisions.md` §476

## D323 — Cl Follows Rb Cl 5D All  *(WATCHLIST — t01105)*

Data-derived (D-series family 129). `hypotheses.yaml` (D323) · `decisions.md` §476

## D324 — Cl Follows Ho Cl 5D All  *(REJECT — t01106)*

Data-derived (D-series family 129). `hypotheses.yaml` (D324) · `decisions.md` §476

## D325 — Cl Follows Ho Cl 5D Strong  *(REJECT — t01107)*

Data-derived (D-series family 129). `hypotheses.yaml` (D325) · `decisions.md` §476

## D326 — Chf Follows Sp Week R  *(REJECT — t01108)*

Data-derived (D-series family 130). `hypotheses.yaml` (D326) · `decisions.md` §478

## D327 — Cot Speculators Zn Crowding Follow R  *(REJECT — t01109)*

Data-derived (D-series family 133). `hypotheses.yaml` (D327) · `decisions.md` §484

## D328 — Cot Commercial Es Crowding Fade R  *(REJECT — t01110)*

Data-derived (D-series family 133). `hypotheses.yaml` (D328) · `decisions.md` §484

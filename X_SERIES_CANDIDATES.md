> **STATUS 2026-10-03: CLOSED AT X02, NOTHING REGISTERED, NO TRIAL SPENT — `decisions.md` §77.**
> Post-2021 pooled effective n is 255 months (185 on the instruments X01 leaves) against an SR\* floor
> of 404 at 0.2 monthly Sharpe. X03, X04 and X07 repeat or vary on-file W work (W02, W03, W04's
> sleeves); X07 is NOT blocked on data (every expiry is on disk). X01 measured: M6E, micro 10Y and MHG
> excluded on cost. Below this banner, the draft as received.

# X-series — daily-horizon, multi-market

**Status: S1 draft. Nothing registered. No trial spent.**

Universe: NQ, ES, GC, HG, CL, ZN, 10Y, 6E and micro siblings. Daily bars.

---

## Read this first

### An overlap check is mandatory before anything here is registered

The brief references **W04** as an existing entry that modelled positions and waited for
the 18:00 reopen on D+1. A W-series on this data has therefore already begun, and I do
not know its contents. **Every entry below must be checked against the W registry before
registration**, and anything already covered is a repeat, not a candidate. The S-series
found five of nine proposed entries already registered under other letters; assume the
same risk here.

### Why this is structurally different from the eight prior series

**For the first time, the sample arithmetic may work.**

Every prior series needed tens of thousands of events because intraday effects are tiny
relative to intraday noise — the F-series floor was 19,722 events at 60 minutes. At
monthly horizon the ratio inverts. A documented annual Sharpe near 0.8 is roughly 0.23
monthly, and establishing that at 80% power needs on the order of 150 non-overlapping
months. Sixteen years gives ~190 per instrument.

That is marginal rather than unreachable, which is a different situation from every
series before it. **It is also the one thing that could make this series worth running
even if every hypothesis fails** — it would be the first time a null here means "the
effect is absent" rather than "the pipeline could not have seen it."

**Verify it before trusting it.** 190 months at marginal power means the floor must be
computed per entry with the actual effect estimate, not assumed from this paragraph.

### The new binding constraint: the flatten tax

Overnight holding is permitted. Positions must be flat only between 17:00 and 18:00 ET.
So a continuously-held position pays **one round trip per trading day**, roughly 252 a
year, purely to satisfy the rule.

| instrument | round trip | annual drag at 252 flattens |
|---|---|---|
| MNQ | 0.48 bps | ~1.21% |
| MES | 0.65 | ~1.64% |
| MGC | 0.65 | ~1.64% |
| MYM | 0.86 | ~2.17% |
| M2K | 1.62 | ~4.08% |
| M6E | ~1.8 (estimate) | ~4.5% |
| MHG | ~2.5 (estimate) | ~6.3% |
| MCL | 3.41 | ~8.6% |

**These figures are estimates and two are guesses.** The first task below measures them.

The consequence is structural: a strategy returning 8–10% annually is viable on MNQ,
MES and MGC and is not viable on MCL. **The universe shrinks to the cheap instruments,
and the cheap instruments are two equity indices plus gold** — which is poor
diversification and runs into the next constraint.

### The anti-hedging constraint on portfolio construction

The account prohibits opposite positions on the same or correlated products, with
"long ES, short NQ" given as the firm's own example. R04 was closed on this.

Time-series momentum sets each market's direction independently, so **it will
periodically produce exactly that prohibited pair**. Every multi-market entry below
needs a correlation-aware position rule fixed at registration: when two correlated
markets signal opposite directions, one is suppressed, and the suppression rule must be
stated in advance rather than chosen later.

This is not a detail. It systematically removes the positions a long-short construction
exists to take, and the removal is not random with respect to returns.

### Data caveats carried from the brief

Daily bars run midnight to midnight UTC, not the CME trading day. A bar dated D misses
the first 1–2 hours of session D and includes the first 1–2 hours of session D+1, and
its close is the last trade before midnight UTC rather than the settlement price. Bar
change correlates 0.97 with the session change daily and 0.98–0.99 over 21 days.

**Adequate for monthly-horizon work. Not adequate for anything depending on a single
day's close or the reopen.** Any entry below that drifts toward daily decisions needs
1-minute or hourly data instead, and should be blocked rather than approximated.

Look-ahead: a bar closing at 20:00 ET on D is after the 18:00 reopen on D, so a signal
from bar D is tradeable no earlier than 18:00 on D+1. W04 already handles this; every
entry here must.

---

# Class A — measure before registering

---

## X01 — The flatten tax, measured

**Not a hypothesis. No trials. Should run before anything else.**

Four of the eight drag figures above are estimates and two are guesses. The number
decides which instruments can carry a daily-horizon strategy at all, so it should be
measured rather than assumed — the same move that closed nine of thirteen P candidates.

### What to produce
Per instrument, in bps: commission per round turn from the current fee schedule, spread
from quote data or a stated assumption marked as such, and the resulting annual drag at
measured days-in-market rather than at a flat 252.

**The last point matters.** Days-in-market is not 252 for a strategy that is flat part
of the time, and it is a per-entry quantity. Report drag as a function of
days-in-market, not as a single figure.

### What it settles
Which instruments are eligible. If MCL's drag exceeds any plausible expected return,
crude is out of the universe before a hypothesis mentions it, and the same test applies
to copper and euro.

---

## X02 — The monthly-horizon detection floor, measured

**Not a hypothesis. No trials. Decides whether the series is worth running.**

The claim that 190 months is marginally adequate is arithmetic from a remembered Sharpe,
not a measurement. Measure it: non-overlapping monthly return volatility per instrument,
the resulting floor at 80% power for effects of 0.1, 0.2 and 0.3 monthly Sharpe, and the
effective n after pooling across instruments at measured correlation.

**Pooling is where this will be won or lost.** Eight markets at average pairwise ρ of
0.3 carry far fewer than eight instruments' worth of independent information, and the
R-series measured that BTC/ETH at ρ=0.835 bought only 1.05× — so measure ρ here rather
than assuming diversification.

If the pooled effective n is below the floor at a 0.2 monthly Sharpe, the series closes
here and nothing is registered.

---

# Class B — the canonical hypothesis

---

## X03 — Time-series momentum

**Params: 3** | **Cost-eligible instruments only** | **Data on disk**

### Mechanism
The best-evidenced effect available at this horizon, and the mechanism names a
counterparty explicitly: Moskowitz, Ooi & Pedersen document persistence in returns for
1 to 12 months across 58 liquid futures spanning equity index, currency, commodity and
bond markets, partially reversing at longer horizons — and find that **speculators
profit from time series momentum at the expense of hedgers**.

That is a named counterparty with a reason to persist: a hedger transacts to remove
risk, not to express a view, and will keep doing so regardless of the price impact.

It has also been validated out of sample across a century — Hurst, Ooi & Pedersen
extend it to 1880–1984, which postdates nothing and predates the original study by
design.

### Condition
```
for each eligible instrument:
    s = sign of the trailing L-month return, volatility-scaled
    position = s, sized inversely to trailing volatility
    rebalance monthly, entered at 18:00 ET on D+1 after signal computation
    flatten 16:55–18:00 daily, re-entering if the signal is unchanged
    suppress the weaker-conviction leg when two correlated markets signal opposite
```

### Parameters
`L` ∈ {3, 6, 12} months · `vol_window` ∈ {20, 60} days · suppression rule fixed, not swept

Lookbacks are **a priori from the literature**, not optimized. If 12 works and 11 does
not, that is the tell.

### Predicted magnitude
Documented annual Sharpe around 0.8 gross at asset-class level. Against a flatten drag
of 1.2–1.6% on eligible instruments and 10–12% annual volatility, that is roughly a 15%
haircut to returns — survivable, unlike MCL at 8.6%.

### Why it might fail, and this is the serious part
- **A 2025 bootstrap study reports that TSMOM's in-sample advantage collapses out of
  sample, with test-period Sharpe ratios turning negative for nearly all
  parameterizations**, on both ETF and futures datasets. That is a recent, direct,
  out-of-sample failure of the exact strategy, and it should be treated the way the
  overnight drift's 2026 refutation was.
- Published 2012. Fourteen years of post-publication decay, and managed futures is a
  large industry built on it.
- The anti-hedging suppression removes positions non-randomly. A long-short
  construction with its opposite pairs stripped is not the strategy the literature
  tested.
- The operative bar is Sharpe 2.06 with ruin constrained. **Documented TSMOM at 0.8 is
  below it even before costs.**

### The honest statement
This is the strongest-evidenced candidate in nine series and it still does not reach the
operative bar. Its value is establishing whether the effect exists at all on this
universe at adequate power — which no prior series could do — not whether it is
tradeable on this account.

---

## X04 — Momentum selectivity and the turnover trade-off

**Params: 3** | **Builds on X03, registered separately**

### Mechanism
Cost scales with days-in-market, not with the number of signals. So a more selective
rule — in the market only when the trailing signal is strong — pays proportionally less
flatten tax.

The L-series measured the selectivity exponent directly: tightening a condition raises
effect per event but cuts events, and the eff/cost curve kept rising to the tightest
setting swept. **That measurement was made at intraday horizon and has never been tested
at daily horizon**, where the cost structure is completely different because the tax is
per day rather than per trade.

### Condition
```
enter only when |trailing L-month return| exceeds the qth percentile of its own history
otherwise flat, paying no flatten tax
```

### Parameters
`q` ∈ {50, 70, 85} · `L` fixed at X03's best a-priori value · `vol_window` fixed

### Why it is worth separating from X03
If X03 fails on cost and X04 survives, the finding is about the tax rather than the
effect. If both fail, the effect is absent. Those are different results and a combined
test cannot distinguish them.

---

# Class C — other daily-horizon effects

---

## X05 — Long-horizon reversal

**Params: 3** | **Data on disk**

### Mechanism
The same paper documents that persistence at 1–12 months **partially reverses over
longer horizons**, consistent with initial under-reaction followed by delayed
over-reaction. The reversal is the other half of a documented effect rather than a
separate claim.

### Condition
```
s = −sign(trailing L-month return), L in the reversal range
otherwise identical construction to X03
```

### Parameters
`L` ∈ {24, 36, 60} months · `vol_window` ∈ {20, 60} days · hold ∈ {1, 3} months

### Why it might fail
**Sample.** A 60-month lookback on 16 years leaves 11 years of usable signal and perhaps
130 non-overlapping months. This is the entry most likely to fail X02's floor, and it
should be checked against it before registration rather than after.

---

## X06 — Cross-asset lead-lag

**Params: 4** | **Data on disk**

### Mechanism
Information does not arrive in all markets simultaneously. Rate markets reprice growth
and inflation expectations that equities subsequently reflect; the dollar reprices
commodity demand. The lag is a genuine informational sequence rather than a pattern.

The universe is unusually well suited to this: ZN and 10Y for rates, 6E for the dollar,
HG as the growth-sensitive metal, CL for energy, NQ and ES for equities. **This is the
one entry that uses the breadth of the universe rather than treating it as eight
separate tests.**

### Condition
```
for each ordered pair (A, B):
    if A's trailing W-day return exceeds k volatility units
    and B has not moved correspondingly:
        take B in A's direction, hold H days
```

### Parameters
`W` ∈ {5, 10, 21} days · `k` ∈ {1, 1.5, 2} σ · `H` ∈ {5, 10, 21} days · pair set fixed a priori

### Why it might fail
- **This is a scan over ordered pairs.** Eight markets give 56 ordered pairs, and every
  one is a trial. BH within the entry at that k is severe, and the pair set must be
  fixed from the mechanism rather than discovered.
- Lead-lag at daily horizon between the most liquid futures in the world is the first
  thing anyone checks.
- R-series measured that correlated instruments buy far less independent evidence than
  their count suggests. These pairs are correlated by construction — that is the premise.

---

## X07 — Term structure carry ❌ **LIKELY BLOCKED ON DATA**

Carry is the second-best-evidenced daily-horizon futures effect after momentum, and the
mechanism — hedging pressure in the Keynes tradition — names the same counterparty X03
does.

**It needs multiple contract months simultaneously**, and the brief describes front-month
data with a roll. If only the front contract is on disk, carry cannot be computed and
this is blocked on data rather than on arithmetic.

Check before writing anything further. If deferred contracts are available the entry is
worth registering; if not, record it as blocked and state what data would unblock it.

---

# Registration order

| # | id | rationale |
|---|---|---|
| 0 | — | **overlap check against the W-series registry** |
| 1 | X01 | flatten tax measured — decides the eligible universe, no trials |
| 2 | X02 | monthly floor measured — decides whether the series can answer anything, no trials |
| 3 | X03 | best-evidenced candidate in nine series, named counterparty |
| 4 | X04 | separates a cost failure from an effect failure |
| 5 | X06 | uses the universe's breadth, but 56 pairs is a severe multiplicity cost |
| 6 | X05 | check against X02's floor first; likely short on sample |
| — | X07 | check data availability before anything else |

**X01 and X02 cost no trials and should both run before a single registration.** Between
them they determine which instruments are eligible and whether the horizon can support a
verdict at all. Either could close the series.

---

# Honest assessment

**What I expect:** X03 establishes the effect exists at marginal power and falls short of
the operative bar, which is the outcome the literature already predicts at Sharpe 0.8
against a requirement of 2.06. X05 fails on sample. X06 fails on multiplicity. X04 is
the one I would least expect to fail, because it attacks cost rather than searching for
a new effect.

**What would make the series worth having run regardless:** this is the first horizon in
nine series where a null would mean *absence* rather than *invisibility*. Every prior
null carried the caveat "not found by a pipeline never shown to see this size." If X02
confirms the monthly floor is reachable, X03's result — either way — is the first clean
answer the programme has produced about an effect it had adequate power to detect.

**The standing caution:** the 2025 out-of-sample failure of TSMOM is recent, direct, and
on the exact strategy. Treat a positive X03 result with more suspicion than a negative
one, and check the regime split before believing it.

# W-series — daily horizons, reached through chained session holds

**Status: S1–S2 design, 2026-10-03. Nothing registered. No trial spent.** Feasibility measured in
`reports/w_series_feasibility.md` (`reporting/w_series_feasibility.py`), dispersions only — no strategy
return computed. Account of the design: `decisions.md` §72.

---

## 1. The premise the record got wrong

Eight series searched intraday, where a 0.48 bps round trip is the same size as every effect found —
the terminal report's §4 says cost "decided most of what could actually be measured." Its §10 then
files daily and multi-day horizons under **permission**: "an account allowing holds through 17:00 ET
opens daily and multi-day horizons, which this programme could not touch."

**They were reachable all along.** The rule is *flat by 17:00*. A position opened at the 18:00 reopen
and closed at 16:55 never crosses 17:00 (the U01 entry already relies on this). Chaining such session
holds re-creates daily exposure. Measured, not assumed:

| | excluded window (16:55 → reopen) share of day variance | corr(held part, full day) | one round trip / day's SD | if traded every day |
|---|---|---|---|---|
| index, 2021–2026 | 1.6% | 0.992 | 0.34% | 1.21%/yr |
| MGC, 2021–2026 | 1.1% | 0.994 | 0.56% | 1.64%/yr |

**At a daily horizon the cost floor stops binding**: the round trip is ~0.4% of a session's typical move,
against ~100% of it intraday. That is the structural opening this series exists to use.

**Load-bearing premise, to confirm with the firm before anything else:** that an 18:00-to-16:55 hold is
within "flat by 17:00". The record's own wording ("every 24-hour or overnight-into-next-day position")
is ambiguous about a hold that runs overnight inside one CME trading day.

---

## 2. What binds instead — it depends on the objective

**Not margin or contract count.** A prop account permits 20–30 micros regardless of its nominal size
(corrected 2026-10-03 on the user's point; an earlier draft of this analysis framed it as capacity).
What remains is the **$2,000 trailing drawdown**, and what that implies depends on which success
condition governs:

**(a) Under §62's ruled bar** (≤3 $2,000 drawdowns a year, first-year ruin ≤ 10%, max volatility 12.4%):
total risk is pinned near **$391 a day of σ**, whatever the firm permits. One MNQ contract is $847/day
at today's price ($59k notional, 26.9% of the account annualised); one MGC is $538/day. Either alone
exceeds the budget. Diversifying inside it needs contracts small enough to fit several — and a small
contract pays roughly the same dollar commission on a fraction of the movement, so the forced daily
round trip drags Sharpe by `cost × √252 / daily $σ`: **0.04 on MNQ and 0.09 on MGC, but several tenths on
the smallest micros** (illustrative — commissions assumed, the same assumption §71 says to verify).

**(b) Under prop-evaluation economics** — the capital at risk is the evaluation fee, not $50,000; a pass
pays out; a breach costs a reset — **the risk budget is set by expected value per attempt, and large
size can be rational.** R06 (`r-series-research/reports/r06_eval_sizing.md`) models exactly this as a
barrier option and finds interior optima at high volatility. Under (b) standard micros fit, cost drag
stays at 0.04–0.09, and a diversified book of several markets is feasible. **The success condition
becomes EV = P(pass) × payout − fee**, computable with R06's machinery once this account's terms are
known — R06 used 10% structures, not this account's 4% trailing floor locking at +4%. With no edge,
this structure passes ~36.8% of the time at every size (§59): **sizing multiplies an edge; it cannot
supply one.**

**What binds under both: evidence that the edge is real.** That is a property of the strategy's
returns, not of its sizing:

| the multiple-testing bar for a DAILY strategy, N = 760 | annual Sharpe needed |
|---|---|
| unit-consistent, full sample (T = 2,780 sessions) | **0.96** |
| unit-consistent, post-2021 — the half that decides (T = 1,320) | **1.39** |
| the programme's single SR\* (0.1368 per observation) read on daily observations | 2.17 |

SR\* has been one per-observation number built from mostly per-trade intraday Sharpes; read on a daily
observation it is 2.17, which no published daily strategy approaches. The unit-consistent version uses
the null variance of a daily Sharpe at the strategy's own sample size. **Which convention governs is a
decision, not a computation** (§72). Either way the 760 trials already spent are now the main wall —
the price of the search so far, paid by every future hypothesis as §61 said it would be.

---

## 3. The candidates

Every candidate is a published, parameter-free specification, fixed before any return on this data is
seen, at a daily horizon through chained session holds. Priors are from the sources below; where a
figure is derived, the arithmetic is shown.

### W01 — Time-series momentum, MNQ and MGC (data on disk)

**Mechanism.** Under-reaction then delayed over-reaction to information (Moskowitz, Ooi & Pedersen
2012): THE COUNTERPARTY is the slow-moving capital — hedgers and allocators who rebalance on schedules
and so trade against persistent trends. **Specification:** sign of the trailing 12-month return, long
or short, volatility-scaled as in the paper. **Prior: 0.41–0.64.** MOP report 0.3–0.5 per market and
~1.0 across 58; matching those implies an average pairwise strategy correlation of 0.07–0.24, which
for two markets gives 0.41–0.64. *Data on disk.*

### W02 — Time-series momentum, diversified across ~10 micros

The same rule, one market per correlated group (one equity index — never long one index and short
another — gold, crude, Treasury yields, two currencies, and others), so the no-correlated-opposite rule
is never at risk. **Prior: 0.73–0.89** (the same scaling at N = 10). *Needs ohlcv-1d for the added
markets — daily bars, far cheaper than the ~$40 ohlcv-1m pull.*

### W03 — Carry timing, the same micros

**Mechanism.** Carry is the return a futures position earns if prices do not move (Koijen, Moskowitz,
Pedersen & Vrugt 2018); THE COUNTERPARTY is the hedger paying a premium to lay off exposure along the
curve. **The account-compatible form is carry TIMING** — long or short each market on the sign of its
own carry — because the cross-sectional form is long-short within an asset class. **Prior: 0.6–0.9**:
KMPV report carry timing averaging 0.6 per asset class and 0.9 globally; ten markets are bounded above by
the global figure. *Needs every expiry (parent symbology) to read the curve.*

### W04 — Trend plus carry, equal risk

**Prior: 0.77–1.27**, from W02 and W03 combined at an ASSUMED correlation of 0 to 0.5 between the two —
an unsourced range, labelled as such. **The only candidate whose prior reaches any multiple-testing bar**
— the upper half of its range clears the full-sample 0.96; none of it reaches the post-2021 1.39 or §62's
2.06.

### W05 — Volatility-managed equity index

Scale MNQ exposure inversely to recent variance (Moreira & Muir 2017). In-sample Sharpe gains of 50–100%;
**out of sample the managed portfolio does not beat the unmanaged one** (0.42 against 0.46, Cederburg et
al. 2020). **Prior: 0.4–0.5.**

---

## 4. The S2 filter

| | prior Sharpe | full-sample SR\* 0.96 | post-2021 SR\* 1.39 | §62 bar 2.06 | lowest operative row (10%, ≤3 events) 0.80 | data |
|---|---|---|---|---|---|---|
| W01 | 0.41–0.64 | below | below | below | below | on disk |
| W02 | 0.73–0.89 | below | below | below | straddles | purchase |
| W03 | 0.6–0.9 | below | below | below | straddles | purchase (all expiries) |
| **W04** | **0.77–1.27** | **straddles** | below | below | **clears at its upper half** | purchase |
| W05 | 0.4–0.5 | below | below | below | below | on disk |

All priors are from published, pre-decay periods; decay since publication is the stated prior (§59), so
they are optimistic. Daily-chain cost drag (≤0.09 on standard micros under objective (b); more under (a))
comes off them.

---

## 5. What this does and does not overturn

**Overturned:** the record's "end of the road" rests on two premises this series breaks — that cost binds
everywhere (it does not at a daily horizon) and that daily horizons are forbidden (they are reachable by
chained session holds, subject to the firm's confirmation). **No series has ever tested a daily-horizon
strategy.** W04 is the first candidate in nine series whose published prior reaches a multiple-testing
bar on this data.

**Not overturned:** no candidate's prior clears the post-2021 bar the programme says decides, or the §62
success bar. **Nothing here is evidence of an edge** — it is the first design whose prior makes testing
worth a trial.

---

## 6. What is needed to go further, in order

1. **Confirm with the firm** that an 18:00-to-16:55 hold is within "flat by 17:00". Everything rests on it.
2. **Choose the objective** — §62's ruin-constrained bar, or prop-evaluation EV — and, for the latter,
   supply the evaluation's terms: fee, profit target, payout split, reset cost, daily loss limit if any,
   contract limit. R06's barrier machinery then gives the success condition for this account.
3. **Rule on the SR\* convention** for daily strategies (unit-consistent 0.96 / 1.39, or the single 2.17).
4. **For W02–W04: buy ohlcv-1d** for the added markets (parent symbology for W03's curve). Priced once a
   Databento API key exists (`cost_floor_quote.py` can be pointed at it).
5. **Then register W04 alone, as one portfolio-level trial** — fixed published parameters, post-2021
   decisive. A portfolio rule has no location or state to match, so its S6 analogue is the rotation null
   already inside every S7 run (§54): the signal's own firing and clustering kept, its alignment with
   returns destroyed. One trial, not a grid: the cheapest way to find out whether the road is open.

## Sources

- Moskowitz, Ooi & Pedersen (2012), *Time Series Momentum*, JFE —
  [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2089463): 0.3–0.5 per market, ~1.0 across 58.
- Hurst, Ooi & Pedersen, *A Century of Evidence on Trend-Following Investing* —
  [ResearchGate](https://www.researchgate.net/publication/318390566_A_Century_of_Evidence_on_Trend-Following_Investing):
  positive in every decade; the search snippet's "~0.4 net of fees and costs" was ambiguous between per
  market and portfolio, and is not used as a number here.
- Koijen, Moskowitz, Pedersen & Vrugt (2018), *Carry*, JFE —
  [CBS accepted manuscript](https://research.cbs.dk/en/publications/carry-2): carry 0.8 per class and 1.2
  diversified (cross-sectional); carry timing 0.6 per class and 0.9 global — read from the manuscript text.
- Moreira & Muir (2017), *Volatility-Managed Portfolios* —
  [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2659431); Cederburg et al. (2020), *On the
  performance of volatility-managed portfolios*, JFE —
  [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0304405X2030132X): 0.42 managed
  against 0.46 unmanaged out of sample.

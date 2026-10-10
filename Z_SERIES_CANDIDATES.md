# Z-series — decide on external out-of-sample evidence, not on discovery

**Status: Z02 registered and RUN (trial t00768, N 762) — CONFIRMED.** Design: `decisions.md` §86;
registration §87; result §88.

> **[§88] Z02 confirmed out of sample.** 2023-03-18 to 2026-09-11, after the paper's sample: MES leg net
> Sharpe **+0.51** (gross +0.66), beating 98.4% of its rotation null; posterior 0.50 ± 0.28. In the
> Tradeify account, **one MES in the signal's direction: +$410 per $80 evaluation at the posterior**
> (P(pass) 36%; +$161 to +$836 across ±1 SD) — that sizing's Sharpe to be verified on forward data.
>
> **[§89] CORRECTED AND CLOSED FOR THE ACCOUNT.** The +$410 used historical contract sizes; on today's
> MES it is +$110 at the one-MES sizing's own Sharpe (+0.41). Replayed from every start date in real
> order: EV −$5 overall, −$78 for 2023 starts. The effect is real; one MES in this account does not
> carry it. Closed at the user's decision.

---

## 1. Why a different basis

- **Income needs a real edge, and a modest one is worth a lot in this account.** At the right size
  (§73): Sharpe 0.4 ≈ +$250 per $80 evaluation, 0.7 ≈ +$600, 1.0 ≈ +$1,100 — ten to twenty times the
  account-structure value the Y-series measured (§79–§85, roughly $0–80 and uncertain).
- **This programme can no longer discover an edge on its own data.** At N = 761 a claim found by
  searching this history needs a post-2021 Sharpe of ~1.3; no published effect we tested came close.
- **Evidence does not have to come from our data.** An effect published by others, specified exactly as
  published, and confirmed on data its authors never saw, is not a product of our 761 trials. Earlier
  series used the literature only to *nominate* hypotheses and then demanded proof on our own searched
  history — the step that makes moderate effects unreachable here.

**The Z rule: a candidate needs (1) a named, forced counterparty; (2) published evidence with a strong
statistic; (3) as little post-publication history as possible, or post-publication survival; (4) a
replication specified to the letter before any data is touched; and (5) a test on data AFTER the
authors' sample ends.**

## 2. The literature, checked — most published calendar effects decayed

| effect | published evidence | after publication |
|---|---|---|
| Turn-of-the-month, index futures | Ariel 1987; Hensel, Sick & Ziemba | **faded after 1990** (Maberly & Waggoner 2000); a one-day remnant persisted to ~2011 (Carchano & Pardo) |
| Treasury auction cycle | Lou, Yan & Zhang (Sharpe ~1.5 claimed) | **reversed after 2010** in a 2026 HBS working paper; partial elsewhere |
| Pre-FOMC drift | Lucca & Moench 2015 (~49 bps before FOMC) | **disappeared after 2015** (Kurov, Wolfe & Gilbert 2021); contested |
| **Rebalancing front-running** | **Harvey, Mazzoleni & Melone 2025** | **sample ends 2023-03-17 — no post-publication record yet** |

This is the familiar pattern (published anomalies lose roughly a third of their return out of sample and
about half after publication). **The one candidate with a forced counterparty and essentially no
post-publication history is the rebalancing effect.**

## 3. Z01 — front-running institutional rebalancing (the lead candidate)

**Source.** Harvey, Mazzoleni & Melone, *The Unintended Consequences of Rebalancing*, NBER WP 33554
(March 2025, revised January 2026; AFA 2026).

**Mechanism and counterparty.** Pensions and balanced funds hold trillions in 60/40-style portfolios and
rebalance mechanically — on calendar dates (month-end; mature pensions also sell for benefit payments
about four business days before month-end) or when weights drift past a threshold (~2 points). After
equities outperform, they must sell equities and buy bonds, and the trades are predictable. **They keep
doing it because their policies require it**; the authors estimate it costs them ~$16 billion a year.

**What the paper measured (1997-09-10 to 2023-03-17, daily, S&P 500 and 10-year Treasury futures):**
- When equities are overweight, next-day equity returns are **17 bps lower**.
- The trading strategy — long S&P futures and short 10-year futures, or the reverse, sized by the signal
  — returns **10.2% a year at 9.2% volatility: Sharpe 1.11, about 1 after costs**, CAPM/C4/FF5/q-factor
  alphas ~9.5% with t > 4, **skewness +5.2**.
- **Sharpe 0.90 excluding the 2008–09 and 2020 crises.** About 3–5% a year in calm, low-VIX periods,
  15–18% in stressed ones.

**The construction, to the letter (Appendix B and Section 4):**
- Simulate a 60/40 S&P/10-year portfolio from daily futures returns:
  w(t+1) = w(t)(1+R_SP) / [w(t)(1+R_SP) + (1−w(t))(1+R_10Y)].
- **Threshold signal** (B.1): for each δ in 0%, 0.1%, …, 2.5%, a portfolio reset to 60% whenever
  |w − 60%| ≥ δ; signal = drifted weight − 60%; **averaged over the 26 values of δ**.
- **Calendar signal** (B.2): a portfolio reset to 60% on the last business day of each month; signal =
  drifted weight − 60%.
- **Strategy weight** = average of (−Threshold signal / 1.5%) and a modified Calendar signal:
  sign(−Calendar) during the last week of the month; on the first business day of the new month,
  the sign of the Calendar signal four business days before month-end (a reversal); zero otherwise.
- **Strategy return** = weight(t) × (R_SP(t+1) − R_10Y(t+1)).

**Our replication and the test, fixed before any return is computed:**
1. **Data:** the purchased GLBX.MDP3 daily bars for ES and ZN (2010–2026-09-11). They close at 00:00 UTC
   (19:00/20:00 ET), not at settlement; measured on MNQ/MGC to track the session at 0.97 daily (§74).
2. **Construction check (2010-06 to 2023-03-17, inside the paper's sample):** signal properties compared
   with the paper's Table C.1 (Threshold AR(1) 0.61; Calendar AR(1) 0.91). A check that the signals are
   built right — **not** evidence, because the paper already used those years.
3. **The test: 2023-03-18 to 2026-09-11 — about 3.5 years the authors never saw.** About 880 daily
   observations; the standard error of an annual Sharpe at that length is ≈0.54. **One pre-registered
   construction, one trial.**
4. **Execution:** a signal from bar D's close is entered at 20:00 ET (allowed — the account is flat only
   17:00–18:00) and held to 16:55 ET on D+1; the 16:55–20:00 tail of the bar is the approximation.
5. **Costs:** MES and the micro 10-year (X01: $3.07 and $2.72 per round trip), charged on every day the
   weight is nonzero.

**Z02 — the equity leg alone (secondary, pre-registered with Z01).** The same weight applied to MES only.
Noisier (equity volatility ~20% against the spread's ~9%), but it avoids holding equities against bonds
in one account and avoids the costly micro 10-year (excluded on cost in X01).

**What the decision rule must be — a ruling for the user.** The programme's standing bar, SR\* at N = 762
and this test's own length, is ≈1.7 annual — set for claims *found by searching our data*. Z01 was not:
it was specified by others on other data. Proposed instead, fixed before the test runs:
- **Confirm** if the post-2023 Sharpe of the exact construction is **> 0 with the published sign**, and
  the prop-account EV at the **posterior** Sharpe is positive. Posterior: a prior centred at the published
  ~1.0 haircut by half for publication decay (0.5 ± 0.35), updated by the post-2023 result.
- **Reject** if the post-2023 Sharpe is ≤ 0.

**Known risks, stated now:**
- **Calm markets weaken it**: 3–5% a year in low-friction periods, and 2023–2026 was largely calm.
- **Publication**: front-runners now know the signal; the edge may already be competed away.
- **Data**: UTC-day bars instead of settlement; no ES/ZN minute data to verify the 20:00 ET entry. ES and
  ZN 1-hour bars would remove most of this approximation, if worth buying.
- **The firm's rule** on opposite positions in correlated products must be confirmed for long-equity /
  short-bond.

## 4. Honest odds

**Most published edges do not survive.** Z01 is the best-qualified candidate in eleven series: the
strongest mechanism, a forced counterparty, t > 4, positive skew that suits a trailing-drawdown account,
and no post-publication record. Its realistic prior after decay is a Sharpe of ~0.5 — which this account
turns into several hundred dollars per evaluation **if it is real**. The post-2023 test has limited power
(SE ≈ 0.54); it can catch a dead effect, but only weakly confirm a live one. A live confirmation would
still need a forward demo period.

## Sources

- Harvey, Mazzoleni & Melone (2025/2026), [NBER w33554](https://www.nber.org/system/files/working_papers/w33554/w33554.pdf).
- Kurov, Wolfe & Gilbert (2021), [The Disappearing Pre-FOMC Announcement Drift](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3134546).
- Turn-of-the-month: [Carchano & Pardo summary](https://paperswithbacktest.com/strategies/closing-the-question-on-the-continuation-of-turn-of-the-month-effects-evidence-from-the-s-p-index-futures-contract); Maberly & Waggoner via [CXO Advisory](https://www.cxoadvisory.com/calendar-effects/stock-index-futures-calendar-effects/).
- Treasury auctions: [Lou, Yan & Zhang](https://personal.lse.ac.uk/loud/Shocks.pdf); [HBS WP 26-033](https://www.hbs.edu/ris/download.aspx?name=26-033.pdf).

---

## Z03 — the Treasury end-of-month effect (designed, specified, not yet run)

**The lesson from Z02 (§89):** in this account an edge must be large relative to the daily swing on the
days it is held. A modest edge spread over most days loses to the $2,000 trailing floor. So the next
candidate must be **event-concentrated**.

**Literature checked first:** Hartzmark & Solomon (AER 2025), dividend-reinvestment pressure — real but ~6
bps on large payout days, far too small for the account, and it needs CRSP's dividend calendar.
Intraday gamma-hedging momentum (Baltussen et al. 2021) — weakened in the 0DTE era and needs options
positioning data.

**Source.** Hartley & Schwarz, *Predictable End-of-Month Treasury Returns* (Rodney White Center WP 17-19,
November 2019), sample 1990–2018.

**Mechanism and counterparty.** Bond-index trackers extend duration when indices rebalance at month-end,
and insurers — measured directly in the paper — are large net buyers of Treasuries on index rebalancing
dates (window dressing and duration matching). The buying is scheduled and does not depend on price.

**What the paper measured:** long Treasuries only over the last few days of each month; at other times
returns are indistinguishable from zero. 10-year note, last 2 days: Sharpe **0.87** (Table 3); 10-year
**futures**, last 2 days: **+0.14% per month** (Table 8, t ≈ 7); the rest of the month Sharpe 0.04–0.27.

**Specification, fixed now (before any return on our data):**
- **Long ZN (10-year futures), the last 2 business days of each month** — the window most of the paper's
  figures and tables use (Figure 1, Table 4), and the 10-year its headline maturity — not chosen from the
  table's best cell.
- Entry at 20:00 ET after the close of the 3rd-to-last business day; one session re-entry (flat 17:00–18:00);
  exit 16:55 ET on the last business day. Daily bars (UTC close), as in Z02.
- **Test window: 2019-01-01 to 2026-09-11 — after the paper's sample ends (2018).** ~92 months, ~184 held days.
- Cost: ASSUMED $19.60 per ZN round trip (one tick $15.625 + $4 commission) per day held.
- **Decision rule, the same form the user approved for Z02:** confirm if the test Sharpe is > 0 and the
  Tradeify EV at the posterior is positive; prior Normal(0.44, 0.35) — the published 0.87 halved for decay.

**Account check, done BEFORE the test** (real ZN event-day returns with drift removed, Tradeify's rules,
the drift then imposed; no return of the strategy computed):

| 1 ZN | P(pass) | EV per $80 | median trading days to pass |
|---|---|---|---|
| no edge | 22% | −$22 | 489 |
| prior, Sharpe 0.44 | **49%** | **+$202** | 493 |
| published, 0.87 | 75% | +$760 | 433 |

With 2 ZN: +$180 / +$692, ~170 days to pass. **Concentrating the edge into 2 days a month lifts the pass
rate to 49–75% if it is real — what Z02 lacked — at the cost of time: about two years to pass with one
contract, eight months with two.**

**Open before it runs:** whether Tradeify allows ZN (or the micro 10-year yield contract) in this account.

> **[§91] NOT RUN.** The user needs a pass and a payout within 1–2 months; Z03 would take ~8–24 months to
> pass. Computed: a 50% chance of a payout within 42 trading days needs an annual Sharpe of about 5.

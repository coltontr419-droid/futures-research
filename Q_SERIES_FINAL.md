# Q-series — the final futures series

Status: **S1 draft.** Nothing registered. Every entry owes S2 magnitude,
S2 scale invariance, S3 measured rate, S5 variance gate, S6 control.

> **REVIEWED 2026-09-13 — `reports/decisions.md` §59.** Nothing registered, no trial spent. The draft
> text is preserved as written; corrections are inserted where they apply, marked **[§59]**, so
> what was proposed and what was found stay distinguishable. Measurements: `reports/q_series_s1.json`,
> `reports/q_series_s2.json`, `reports/q09_drawdown.json`.
>
> **The four findings that change the series:**
> 1. **Three candidates are already in the registry.** Q01 is **F02** (run, 144 trials,
>    `stage1_uninformative`), Q03 is **F12** (excluded), Q04 falls under F12's exclusion note, and the
>    unconditional drift Q01 builds on is **F13** (excluded). Neither Q document knew.
> 2. **Q01 and Q02 are one bet, not a low-ρ pair.** Their conditioners correlate at Spearman
>    **+0.972** (post-2021 **+0.991**), and Q01 firing implies Q02 is long on **100%** of nights —
>    an identity, not an estimate. "Opposite sign" is wrong: both are long after a down close.
> 3. **The magnitude filter leaves no clean primary.** Q02, Q03, Q05 and Q06 sit below their
>    post-2021 BH bars; Q01 alone straddles, and it is a re-test of F02 on data F02 has already seen.
> 4. **The drawdown premise was assumed, not confirmed.** The corrected rule is in §59 and in the
>    handoff; its arithmetic removes the case for putting sizing ahead of edges.

---

## The target, decomposed

Goal as stated: 1–5% per month, with 4% losses rare.

For a strategy at Sharpe S sized to annual vol σ, P(ever hitting drawdown D)
≈ exp(−2SD/σ). Setting D = 4% and requiring that probability near 5%:

| monthly target | annual | Sharpe required |
|---|---|---|
| 1% | 12% | **2.12** |
| 2% | 24% | 3.00 |
| 3% | 36% | 3.67 |
| 5% | 60% | 4.74 |

**The upper half of the range is not reachable.** Sharpe 3.7–4.7 is
institutional HFT territory, not a retail futures account. The honest target
is **1%/month with the drawdown constraint respected**, and even that needs
Sharpe 2.12.

> **[§59]** This table is the STATIC-floor formula. The confirmed rule trails the peak until +4%, then
> locks at breakeven, so it applies only after the lock. See `q09_drawdown.py` and §59 for both phases.

At the programme's measured per-trade SD of 64.7 bps and ~2,000 trades/year,
Sharpe 2.12 requires a **4.50 bps net edge** — against a five-series maximum
observed effect of 5.0 bps, which had the wrong sign and a refuted mechanism.

> **[§59]** 64.7 bps is the §45 anchor — **the SE-scaling constant of a real-minus-placebo difference at
> 180 minutes** (64.7/√4052 = 1.016, L12's own bootstrap SE), not a per-trade SD. §57 recorded what
> happens when that constant is reused for a different statistic. The Q-series S2 below uses the
> window SDs measured directly on NQ instead.

### The structural consequence

| each Sharpe | k=3 | k=4 | k=6 |
|---|---|---|---|
| 1.0, ρ=0 | 1.73 | 2.00 | 2.45 |
| 1.0, ρ=0.1 | 1.58 | 1.75 | 2.00 |
| 1.0, ρ=0.3 | 1.37 | 1.45 | 1.55 |

One edge at Sharpe 2.1 has never been found in five series. **Four to six
edges at Sharpe ~1.0 with ρ ≤ 0.1 reaches the same place.** That is the only
structural route left, and it requires a design change: the series must be
built as a portfolio from the start, with cross-correlation measured and
registered, not as isolated hypotheses tested one at a time.

Event and calendar edges are the natural material for this, because they
fire on different days and are structurally low-ρ. Intraday state signals
are not — they all load on the same market conditions.

> **[§59] The first pair offered as portfolio material is not independent.** Q01 and Q02 condition on
> the same 15:30–16:00 price change (Spearman +0.972) and take the same side on every Q01 night. And
> after the magnitude filter, four of the five predictable candidates sit below their post-2021 bar, so
> the portfolio has no material to build from on data now on disk.

---

## A warning that should shape expectations

The best-documented large anomaly in this exact instrument class was
**publicly declared dead two months ago by the authors who found it.**

Boyarchenko, Larsen & Whelan (NY Fed Staff Report 917) documented the
"overnight drift": almost the entire US equity premium earned in a one-hour
window, 2:00–3:00am ET, when European markets open — ~3.6% annualized over
1998–2019, statistically significant on every day of the week and in 9 of 12
months. Mechanism: dealer inventory risk from end-of-day order imbalances,
derived from Grossman-Miller (1988), with the testable prediction that drift
is larger after sell-offs.

In July 2026, Liberty Street Economics published *The Disappearing Overnight
Drift*: **that window has averaged close to zero since 2021.**

> **[§59] The programme already acted on this, on 2026-08-28.** The unconditional version is registered
> as **F13** and EXCLUDED on exactly this ground; the conditional version was registered as **F02** and
> run on 2026-09-02. F13's entry reads: *"Recorded so it is not rediscovered."* The Q draft is the
> rediscovery that entry exists to prevent.

This is the R01 decay pattern at institutional scale. It is the single most
important prior for this series: effects large enough to hit the target are
exactly the effects that attract capital once published. Every candidate
below must be tested on post-2021 data separately, and an era split is
mandatory rather than optional.

---

## Class A — inventory and liquidity provision

### Q01 — conditional overnight drift, post-selloff
**S1.** The unconditional drift is dead, but the *mechanism* may not be.
Boyarchenko et al. show drift is compensation for dealers absorbing
end-of-day order imbalance, and is largest following market sell-offs
(bottom-tercile imbalance). If dealers still bear inventory risk after large
sell-offs, the conditional effect can survive even though the unconditional
one has been competed away. Who pays: investors demanding immediacy at the
close. Why they persist: end-of-day liquidation is mandated by mandates and
margin, not chosen.
**Condition.** Long MNQ/MES from ~01:45 ET, exit ~03:15, only on nights
following a bottom-tercile end-of-day signed-volume day.
**Data.** On hand. End-of-day imbalance proxied from the last 30m of RTH
price change per unit volume — a proxy, and it must be registered as one.
**n.** ~1/3 of ~1,500 sessions = ~500 events.
**Why it leads the list.** It is the only candidate here whose mechanism
comes from a Fed staff report with a formal model and a stated conditional
prediction — and where the unconditional version dying is *evidence for the
mechanism*, since arbitrage should compete away the unconditional part first.

> **[§59] Q01 IS F02.** `order_imbalance_conditional_overnight_reversal`: Boyarchenko, Larsen & Whelan,
> conditional on a selloff proxy, long in the Europe window 01:30–04:00. Run 2026-09-02 across 144
> cells, `stage1_uninformative` — every cell below its swept range, 0 nominal separations against 7.2
> expected. **87.1% of F02's (k=1) firings are Q01 firings.** Consequences:
> - **F02's 144 trials stay in N.** A re-registration is permitted (F02 was not retired) but adds to N.
> - **The data on disk is not out of sample for Q01.** F02 recorded MNQ post-2021 `sell_imb` at +3.27
>   bps as "the one directionally consistent result, and it is not evidence". Registering Q01 now would
>   re-test the family F02 already looked at. The NQ data ends 2026-08-27; **a clean Q01 test needs
>   data after that date.**
>
> **[§59] MES is not on disk.** `data/continuous` holds MGC, MNQ, NQ and the NQ/MNQ splice only.
>
> **[§59] The proxy measures illiquidity, not imbalance.** Dividing by volume ranks a heavy-volume selloff
> — the largest imbalance — below a thin one. Measured on NQ: its Spearman with a bulk-volume-
> classification imbalance ratio is **0.792**, against **0.774** for the raw last-30m return, so the
> division adds nothing. It is also not scale invariant: median |Δp/V| halves from 2010 to 2026 while
> the ratio stays at 0.10–0.14. P03 retired this construction at S7 (0.86% of the excess reverted
> within 15 minutes). The better proxy available from OHLCV is the BVC ratio; true signed imbalance
> needs aggressor-side data, which is not on disk (`trades` is null, no `tbbo`).
>
> **[§59] n.** The NQ lineage carries Q01 on **3,559** sessions with the 01:45–03:15 window, not ~1,500 —
> but the post-2021 era that decides has **478 firings against 908 other nights**, whatever the lineage.
>
> **[§59] S2: STRADDLES** — estimated 0–3 bps post-2021 against a bar of 2.81–3.89. At cost at the low
> end, and the overnight spread is unmeasured.

### Q02 — end-of-day imbalance reversal
**S1.** Same mechanism, opposite window. If dealers absorb imbalance into
the close, the closing print is displaced from fair value and the
displacement reverses.
**Condition.** Fade the last-30m RTH move, hold into the Globex session.
**n.** ~1,500. Naturally low-ρ against Q01 (different window, opposite sign).

> **[§59] "Hold into the Globex session" violates the 17:00 ET hard exit** (CLAUDE_FUTURES.md), so the
> condition as written is not executable on this account. The compliant holds are 16:00–16:59, which is
> continuous only from mid-2021 — **the 16:15–16:30 window holds 0–4 sessions a year before 2021** — or
> 16:00–16:14 across all eras.
>
> **[§59] Not low-ρ against Q01, and not opposite sign.** Fading a down close is LONG; Q01 is long after
> a down close. Q01's conditioner correlates with Q02's signal at **+0.972** (post-2021 **+0.991**), and
> Q01 firing implies Q02 long on **100%** of nights, because Q01's threshold is itself negative in
> 99.1% of sessions. The windows are disjoint in time, so their P&L correlation is not forced to one —
> but it cannot be assumed near zero, and both take the same exposure on the same selloff days.
>
> **[§59] S2: BELOW.** Estimated 0–0.96 bps (P03's measured reversal fraction up to its own 6.8% bar,
> times the measured 14.1 bps median last-30m move) against 1.44–1.99 (16:00–16:59) or 1.04–1.43
> (16:00–16:14).

---

## Class B — scheduled events

### Q03 — pre-FOMC drift
**S1.** Lucca & Moench documented large excess equity returns in the 24
hours before scheduled FOMC announcements. Mechanism candidates include
pre-announcement risk-premium resolution and dealer positioning ahead of a
known volatility event.
**Magnitude.** Historically very large relative to any cost floor.
**n.** 8/year — **~48 events over six years.** Far below any BH bar.
**Verdict.** Economics-only, significance limb waived at registration, per
the L12 rule. And it has been public since 2015, so post-2021 must be
reported separately and prominently.

> **[§59] Q03 IS F12, EXCLUDED 2026-08-28 on two grounds, either sufficient:** ~128 events over the sample,
> and a 24-hour hold from 14:00 the prior day **crosses the 17:00 ET hard exit**. F12 notes that a
> truncated version is a different hypothesis needing its own registration. The only compliant
> truncation is intraday on the announcement day. No FOMC calendar is on disk.
>
> **[§59] S2: BELOW.** The 09:30–14:00 truncation, estimated 0–25 bps post-2021 on ~46 events against a bar
> of 30.6–42.5 (using the unconditional window SD, which understates FOMC days and so the bar). **The
> economics-only waiver does not rescue it:** at ~46 events the economic estimate itself carries an
> interval wider than the effect — N10's reasoning (§45).

### Q04 — macro release windows
**S1.** CPI, NFP, and FOMC create scheduled, known volatility events.
Dealers widen and reduce inventory ahead; the pre-event book is thin.
**n.** ~2–3/week, ~800 over six years. Marginal.
**Use.** Better as an *exclusion* than an edge — see Q11.

> **[§59] Already covered by F12's exclusion note:** *"THE SAME EXCLUSION APPLIES TO CPI, NFP AND EVERY OTHER
> SCHEDULED RELEASE: ~200 observations maximum over the sample, below the gate. Do not register them
> individually."* **S2: cannot be predicted** — it names a condition, not a trade, and has no direction.

---

## Class C — flow calendar

### Q05 — turn-of-month
**S1.** Retirement contributions, index fund inflows, and pension rebalancing
cluster mechanically at month boundaries. The flow is calendar-driven and
price-insensitive, which is the cleanest "who pays and why they persist"
answer available: the payer is a payroll system, and it cannot stop.
**Condition.** Long the last N and first M sessions of each month.
**n.** ~72 month-ends over six years, ~500 sessions if N+M = 7.
**Note.** Widely known. Post-2021 split mandatory.

> **[§59] n.** The NQ lineage carries **195 months** and **3,428** sessions, not ~72 — but post-2021 is **68
> months, 476 TOM sessions against 911 others**, whatever the lineage. A session hold must end by
> 16:59; 18:00→16:00 is used, because bars after 16:15 do not exist before 2015.
>
> **[§59] S2: BELOW.** Estimated 0–10 bps a session post-2021 (recalled, unverified turn-of-month
> literature) against a bar of 16.4–22.7. The full-sample bar, 9.2–12.8, is reachable only at the top
> of the range, and it sits in the era Q10 discounts. The N/M split must be pre-registered or k rises.

### Q06 — day-of-week overnight seasonality
**S1.** French & Roll and subsequent work document weekday structure in
overnight returns, with Monday overnight distinct. Mechanism is weekend
inventory and information accumulation.
**n.** ~300/weekday over six years.
**Risk.** Five weekdays × two sessions = 10 cells before any parameter. High
k, and the single easiest place in this list to overfit. Pre-register which
day and why, or don't register it.

> **[§59] S2: BELOW, even pre-registered.** Monday 18:00→09:30 only: estimated 0–3 bps against a post-2021 bar of
> 10.6–14.7 (273 Mondays against 1,167 other nights). As written, with 10 cells, the bar is 15.2–21.1.

### Q07 — roll-window flow
**S1.** Quarterly roll forces index-tracking and calendar-spread flow on a
known schedule. Uses the **672 calendar-spread files already on disk and
never parsed.**
**n.** 24 rolls over six years. Economics-only.

> **[§59] S2: cannot be predicted** — no direction is stated for the outright, and roll flow is largely
> calendar-spread flow. ~65 rolls over 2010–2026, ~22 post-2021. The spread files are still discarded
> at parse (§54).

---

## Class D — sizing and risk, which the drawdown constraint makes primary

### Q08 — volatility-managed sizing
**S1.** Moreira & Muir show that scaling exposure by inverse recent realized
volatility improves Sharpe across equity factors, because volatility is
persistent while expected return is not. **This is not a signal — it is a
sizing rule, and it is the single most direct lever on the 4% constraint.**
Halving exposure when realized vol doubles cuts drawdown roughly in
proportion while leaving the edge intact.
**Register as.** A measurement applied to whatever survives, not a
standalone hypothesis. Test it on the combined portfolio, not per-edge.
**Why it may matter more than any edge here.** At Sharpe 2.1, the difference
between P(−4%) = 5% and P(−4%) = 37% is entirely a sizing choice. Getting
sizing right is worth more than a marginal edge.

> **[§59] Sizing multiplies an edge; it cannot substitute for one.** Under the confirmed rule, a strategy with
> no edge reaches the +4% lock with probability **exp(−1) = 36.8% at every size** — sizing moves nothing.
> Q08 has nothing to act on until something survives.

### Q09 — drawdown-aware position scaling
**S1.** Not an anomaly. If the account has a hard 4% rule, expected
time-to-ruin is a function of sizing and edge, and it can be computed rather
than guessed. Register the computation, pre-register the sizing rule, and
never revise it after a losing stretch.
**Note.** R04 closed on account permission — the account prohibits opposite
positions on correlated products. Check the drawdown rule's exact definition
(daily vs trailing vs static) **before** sizing anything, since it changes
the calculation entirely.

> **[§59] Done at S1, and the note above was exactly right.** The rule was confirmed with the firm: trailing
> from 4% below start until the peak reaches +4%, then static at breakeven. `q09_drawdown.py` computes
> both phases, verified by Monte Carlo. It costs no trial.

---

## Class E — contamination and exclusion

### Q10 — post-2021 regime split as a standing gate
**S1.** Not a hypothesis. Given the overnight drift's disappearance, every
Q-series candidate must report 1998–2020 and 2021–present separately, and a
candidate that only works pre-2021 is dead regardless of its full-sample
statistics.
**Make this an S8 requirement in STAGES.md**, not a per-entry note.

> **[§59] Proposed, not adopted here.** §53 already runs an era split on every S7 result by default; Q10 would
> fix the break at 2021 and make the post-2021 half decisive. That changes the method, so it is left for
> decision. The S2 filter below applies it, so its effect is visible. Note the sample: NQ starts
> 2010, so "pre-2021" here is 2010–2020, not 1998–2020.

### Q11 — event-window exclusion
**S1.** Test whether excluding FOMC, CPI and NFP windows improves every other
edge. Scheduled events inject variance that is not the mechanism any of these
hypotheses claim.
**Value.** Cheap, and directly serves the drawdown constraint — most large
single-day losses cluster on event days.

> **[§59]** Contingent on a live primary — the P02/P10 case (§54). No event calendar is on disk.

### Q12 — cross-edge correlation matrix
**S1.** The portfolio route needs ρ ≤ 0.1 to work. **Measure the
cross-correlation of every surviving edge's daily P&L before combining
anything.** If ρ turns out to be 0.3, the combination gives Sharpe 1.45
rather than 2.00 and the target is missed even with four working edges.
**This is the load-bearing measurement of the entire series** and it cannot
be done until at least three edges survive. Register it now so it is not
skipped later.

> **[§59] Part of it could be done before any edge survives, and it already failed once.** The CONDITIONERS of
> Q01 and Q02 were measured without a trial: Spearman +0.972. Conditioner correlation is necessary
> evidence, not sufficient, but it disqualified the first pair before either was run.

---

## Recommended order

1. **Q01** — the strongest mechanism in the list, and the only one where the
   published effect dying is consistent with the mechanism surviving.
2. **Q02** — same mechanism, different window, structurally low-ρ against Q01.
3. **Q05** — the cleanest "who pays and cannot stop" answer available.
4. **Q08** — sizing, applied to whatever survives.
5. **Q12** — the correlation matrix, once three edges exist.
6. **Q10, Q11** — standing gates, not hypotheses.
7. Everything else only if the first three produce something.

> **[§59] SUPERSEDED — see §59, "Ordering".** Q01 is a re-test of F02 on data F02 has seen, and a clean test
> needs data after 2026-08-27. Q02 duplicates Q01's conditioner and sits below its bar. Q05 sits below
> its post-2021 bar. No candidate is registrable as a primary on data now on disk.

## What would make this series a success

Not a promotion. **Three edges at Sharpe ~1.0 with measured ρ ≤ 0.1**, which
combine to ~1.6–1.7 and support roughly 0.7%/month within the drawdown
constraint. That is short of the stated target and it is the realistic best
case.

If Q01, Q02 and Q05 all come back null — which the base rate says is the
likely outcome — then six series have searched this space and the correct
conclusion is that no edge accessible at this cost structure and account
size exists in intraday and calendar futures signals. That is a real
finding, and it should be written as one.

> **[§59] The filter got most of the way there without running anything.** Q02 and Q05 are below their post-2021
> bars at S2, and Q01 cannot be tested cleanly on disk data. Whether to write this up as that finding, or
> to wait for data after 2026-08-27 and test Q01 once, is a decision this review does not take.

# Y-series — the evaluation is the edge

**Status: S1 design, 2026-10-09. Y01 measured (two computation records, m00134–m00135). Nothing
registered. No trial spent; N 761, SR\* 0.1368.** Account of the design: `decisions.md` §79.

---

## 1. Why a different kind of series

Ten series searched for a market edge. What the record established:

- **No market effect cleared its bar.** The best published candidate, trend + carry (W04), ran at
  −0.42 net against 1.31 (§76). Every intraday effect sat at or below a ~0.5 bps cost floor (§4, §71).
- **The search itself is now the wall.** At N = 761, a new market-prediction claim on this data needs a
  post-2021 Sharpe of ~1.3 (§73). Each further trial raises it for everything after.
- **One result was never followed up.** §73's prop-evaluation EV found that **this account's evaluation
  is worth more than its $80 fee at ZERO edge** under the soft daily limit — the firm absorbs losses
  beyond the fee, so the payoff is option-like. It was computed on a Student-t model and read only as
  "EV is not evidence of an edge" (§73 finding 2). It is also a source of value in its own right.

**The Y-series takes the account's payoff structure as the thing to exploit**, not a market prediction.
That changes the statistics: a claim about the rules, tested with drift removed, is not a market
hypothesis, does not need to clear SR\*, and spends no trial.

---

## 2. Why the number is what it is — and its ceiling

At zero drift the evaluation is a game against a martingale. Two facts fix its value:

1. **P(pass) does not depend on size.** For continuous paths, scaling a position only changes the
   game's speed, not its outcome: P(reach the +$2,000 lock before a $2,000 trailing drawdown) = e⁻¹, then
   P(+$1,000 before −$2,000) = ⅔, so **P(pass) ≈ 0.245 at any size** (§59). Measured on real paths:
   22–25% in every cell.
2. **The funded account's withdrawals are bounded.** Expected final equity plus expected withdrawals
   equals the $50,000 start. An account that never locks ends at its peak − $2,000 (expected peak gain
   given no lock ≈ $836); one that locks ends at the $50,000 floor. So
   E[withdrawals] ≈ 0.632 × ($2,000 − $836) ≈ **$736**, and

   **EV ≈ 0.245 × 0.9 × $736 − $80 ≈ +$82 per evaluation**, before gaps, costs and time limits.

**This is a structural constant, not a tunable edge.** No sizing or timing rule can move P(pass) much
at zero drift. What moves EV: **drift** (a real premium, or cost as a negative one), **overshoot**
(gaps through the floor are the firm's loss), **the fee**, and **the payout rules**.

---

## 3. Y01 — measured on real MNQ paths

`reports/y01_structure_ev.md` (`reporting/y01_structure_ev.py`). 2,638 complete sessions, 2015-11-20 to
2026-08-27, rescaled to one MNQ at today's $59,204 notional, **drift removed per era**; intraday
trailing floor on each minute's low; soft $1,000 daily limit; $2.32 round trip. Engine validated first:
0.247 against the closed form 0.245 — **after a validation failure that was itself a finding**: an
un-demeaned pool's residual drift of ~$20/day (annual Sharpe ~0.5) moved P(pass) from 0.22 to 0.29.

| window, MNQ | daily $σ (post-2021) | EV per $80, 2015–20 | EV per $80, post-2021 |
|---|---|---|---|
| RTH 09:30–16:00, 2 | 1,397 | +119 | **+127** |
| RTH, 1 | 698 | +85 | +117 |
| full 18:00–16:55, 2 | 1,679 | +75 | +105 |
| full, 1 | 839 | +71 | +61 |
| overnight 18:00–09:30, 1–3 | 459–1,377 | +5 to +60 | +31 to +66 |
| full, 1, + external premium (Sharpe 0.3) | 839 | +131 | +115 |

**Positive in every cell, in both eras.** Monte Carlo error is about ±$10 per cell, so the ranking
among the top cells is not reliable; the sign is. RTH is the most consistent window.

### Sensitivity, post-2021 (`reports/y01_sensitivity.md`)

| | imposed Sharpe −0.30 | −0.15 | 0 | +0.15 | +0.30 |
|---|---|---|---|---|---|
| RTH, 2 MNQ | **+77** | +100 | +122 | +153 | +188 |
| full, 1 MNQ | +13 | +35 | +75 | +76 | +92 |

Cost from $0 to $4.64 per round trip moves RTH-2 from +136 to +118. **The RTH policy survives a
bear-market drift and doubled cost.**

### The shape that matters most: it is a lottery with positive expectation

| RTH, 2 MNQ, zero drift | outlay | P(net > 0) | median | 95th pct | mean |
|---|---|---|---|---|---|
| 10 evaluations | $800 | 26% | −$800 | +$11,240 | +$1,226 |
| 20 | $1,600 | 43% | −$1,600 | +$16,780 | +$2,445 |
| 40 | $3,200 | **59%** | +$2,061 | +$23,922 | +$4,935 |

**Most evaluations lose the fee, and most funded accounts pay little.** The expectation is carried by a
minority of accounts that lock and run. A small budget most likely loses all of it.

---

## 4. The candidates

**Y01 — structure EV on real paths. MEASURED** (above).

**Y02 — the firm's full rulebook. BLOCKING; needs the user.** Every figure above assumes rules that were
never supplied, and several common prop rules would cut the EV directly:
- **consistency rules** (no single day above X% of profit) — a large-σ policy reaches the target in few
  days and could violate them;
- **payout caps, minimums, frequency, and a maximum number of payouts** before the funded account closes;
- **funded-account lifetime and inactivity rules**; **evaluation time limit** (252 sessions assumed);
- **whether the trailing floor is intraday (assumed) or end-of-day** — end-of-day is more forgiving;
- **minimum trading days**, **scaling plans** (contract limits that start below 30), **news restrictions**.
Each becomes a switch in the Y01 engine, and the EV is recomputed under the actual rulebook. **Nothing
should be traded before this is done.**

**Y03 — the operating policy, fixed in advance. Design only.** RTH 09:30–16:00, 2 MNQ, one entry and one
exit per session, long (Y04), flat outside the window. Chosen as the cell positive in both eras with the
smallest sensitivity to drift and cost — not by searching further, which §2 says cannot help much.

**Y04 — a long tilt from an external prior. Design only.** At zero edge, direction is free; choosing long
costs nothing in expectation and collects the equity premium if it exists (prior: century-scale US
equity premium, Sharpe ~0.3, labelled as an assumption, never estimated from this data). Downside
bounded by the sensitivity table: still +$77 at an imposed Sharpe of −0.3.

**Y05 — forward demo test. The verification.** Run Y03 on a demo or simulated account under the real
rules for a fixed number of evaluations, recording pass rate, days to resolve, fills and costs, and
compare with Y01's predictions. Forward data is new — not on file — so it is a measurement, not a trial,
and it is the only way to check the rules and execution the engine cannot see.

**Y06 — bankroll. Computed (above).** The decision is how many evaluations to fund, knowing the median
outcome loses the outlay below ~40.

**Y07 — an edge overlay. Deferred, not searched.** Any genuine edge multiplies EV (§73: Sharpe 1.0 at
small size ≈ +$1,100 per evaluation). The Y-series does not need one and does not search for one.

---

## 5. What this does not claim

- **Not a market edge.** The EV comes from the payout structure. If the firm changes the rules, it moves.
- **Not a high pass rate.** About one evaluation in four passes, by construction.
- **Not low variance.** See §3: positive expectation, very skewed outcome.
- **Within the rules only.** Nothing here relies on prohibited behaviour. Holding opposite positions across
  accounts to manufacture a pass is typically prohibited and is excluded outright.

## 6. Next, in order

1. **Y02:** supply the firm's full rulebook; recompute EV under it.
2. **Y05:** forward demo test of the Y03 policy under the real rules.
3. **Y06:** choose a budget with the skew in view.

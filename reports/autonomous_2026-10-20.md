# Autonomous session — 2026-10-20

Running log of leads searched and tests run while the user is away. Leads needing logins/API keys are tabled (listed at the end).
Rules in force: legitimate counterparties only; must start on ~$100-200 and scale far past $2k/month (capacity screened first);
protocol before any price/outcome comparison; strict edge rule (§119) with §133 watchlist; no droplet changes.

## Findings

### 1. Forward evidence for the deployed futures rules and the watchlist (no trial)
- `a48_forward`: 6 rule sessions since deployment (NKD dollar-week, FDXM DAX-dollar): recorded −$1,557; rule minus opposite side
  −$2,006; the §463 review trigger needs 40 sessions — far too early to judge.
- `a49_watchlist` (forward data after the sealed window): 14 of 23 watchlist rules positive (≈ chance). Standout: **D728 MGC fades
  its own 60-day trend (strong days): forward n 28, +35.5 bps, t +3.00**; sibling D727 (all days) t +1.73. With 23 rules tracked one
  t≈3 can be chance → keep watching (the §133 path), not adoption. D659 (MGC follows CNY) t −2.20 — failing forward.

### 2. ForecastEx favourite/long-shot bias (§757-758) — closed
Every ForecastEx trade ≥ 24 h before expiry (2.4k events, 160M contracts): buying NO on long shots −4.4¢ (t −7.8), YES on favourites
−3.2¢ (t −6.1). A category subset looked positive by contract weight but is negative event by event (a few big NFL trades). Nothing.

### 3. Kalshi combos as a REQUESTER (correlated same-game parlays) (§759) — closed
Makers price same-game correlation (executed ≈ 1.23× the independent product; crypto same-window 2.56×). Buyers lost ~all premium
on 208 settled sports same-game parlays. No buyer edge.

### 4. Early read of the demo bot (a18 --review, read-only) — IMPORTANT for the Oct-25 review
35 finished tickets: TAKE 11 / STOP 23 / time exit 1 vs expected 15.1 / 18.3 / 1.6 (chi-square p ≈ 0.28).
**Shadow P&L −$11,007 vs expected −$814 ± $6,076 (z −1.68)** — every product negative (FDXM −$800, MCL −$1,800, MGC −$1,800,
MNQ −$2,000, NKD −$1,607, ZS −$3,000). Not yet conclusive (≈ 1-in-11 by chance) but adverse. Execution matches (median gap $2.56 a
ticket); 3 recorded readings disagree with the replay (2 on FDXM's DAX-cash proxy, 1 MGC). Dollar rules forward: 6 sessions, NKD
+$200 vs other side, FDXM −$2,206; trigger needs 40 sessions. Accounts: 13 evaluations bought, 0 passes so far.

### 5. Kalshi sports game-winner favourite/long-shot bias (K10, §756/762) — closed (trial t01539)
Downloaded every settled NFL/NBA/MLB/NHL/NCAAF game market. Discovery (pre-2025-10) thin: long-shot NO −1.2¢; favourite YES +3.8¢
(t 1.69) → registered as one sealed test: **−1.7¢, t −1.15 over 556 games → REJECT.** Game lines are calibrated.

### 6. Does the Tradeify plan survive if the edges are zero? (context for the adverse demo) — yes, structurally
From A85 at today's $116 price (sides randomised per session, 6 seeds, live rules): **5 × 50K Select Daily, 3 NKD + 2 FDXM: zero-edge
mean +$4,582 per 4-month run on 2021-26 paths, +$2,692 on 2010-20** (Growth −$4,181 / −$3,337; Lightning +$1,492 / +$1,945). The
payout structure is a free option: even with no edge the plan expects ≈ $0.7-1.1k a month (high variance). The demo's −$11k is market
P&L per ticket; it does not include this account-structure value. The decision at the review is therefore "edge or no edge", not
"profit or loss" — a zero-edge plan is still positive but small.

### 7. ★ Zero-edge value across prop firms (A90, §763) — the most useful finding so far
Each firm's own rules, random trade directions (no edge at all), per 4-month run: **Tradeify +$5.5k (2021-26 paths) / +$3.8k
(2010-20); Lucid Daily +$3.4k / +$2.9k; TPT PRO +$2.5k / +$2.2k;** MFF −$2.9k; Phidias −$4.5k. Tradeify + Lucid + TPT ≈ **+$11.5k
a run ≈ $2.9k a month with zero edge**, scaling across firms rather than capital. Catches: Lucid/TPT churn ~$10k of eval fees a run
(cash buffer needed), fees/rules must be re-checked at today's prices, results across firms correlate if the same sides are traded.
Needs the user (accounts, money) → tabled for the user's decision.
- Follow-up at TODAY's prices: Lucid (≈$129.50) improves to +$4.8k / +$3.7k; TPT ($170/month + activation) falls to ≈ 0 → drop TPT.
  Tradeify + Lucid ≈ +$10.3-10.5k per 4-month run with zero edge (P(net>0) 67%), **but the cash low is median −$6.7k, 5% −$13.6k,
  worst −$18.9k** — it needs a ~$7-14k bankroll, not $100-200. Real, structural, legit; a bankroll decision for the user.
- LucidPro's actual 2026 terms (EOD drawdown, no eval consistency, $2k payout cap) make it BETTER than the survey assumed: zero-edge
  **+$9.6k a run, P(net>0) 73%, cash low median −$2.6k (5%: −$7.0k)** — like Tradeify. Realistic range +$4.8-9.1k (40% best-day
  payout rule not modelled). **Tradeify + LucidPro ≈ +$10-15k per 4-month run with zero edge ≈ $2.5-3.6k a month.** Needs: verify
  LucidPro terms at checkout, a bankroll (~$5k median, ~$14k bad-case for both), the user's decision. Tabled for the user.
- At Lucid, NKD×5 beats the mixed set at zero edge: +$11.0k / +$7.9k a run (vs +$9.1k / +$5.9k).
- More firms (§764): **TradeDay Quick Pay EOD 50K ($79): zero-edge +$6.2k (50% split) to +$9.6k per run; P(net>0) 80%; cash low
  median −$2.0k (5%: −$5.9k)** — the best cash profile. Topstep ≈ −$0.7k (50%-per-payout cap), Alpha Futures −$4.4k (−$1.4k with
  a promo) → no. **Total across Tradeify + LucidPro + TradeDay ≈ +$21-26k per 4-month run ≈ $5-6.5k a month with ZERO edge.**
  Main risk: my translation of each firm's rules (from third-party summaries). Signs more reliable than dollars.
- Bulenox −$4.7k (no); Elite Trader Funding −$7.8k at list, +$4.9k only at its 70%-off promo price (fragile).

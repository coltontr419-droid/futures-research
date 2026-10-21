# Prep for the 2026-10-25 review (written 2026-10-21)

The launch decision rests on one question: **do the deployed rules have an edge, and does the plan pay even if they don't?**

## 1. The demo (a18 --review, refreshed 2026-10-21) — adverse, not yet conclusive
- 41 finished tickets; outcome mix vs history chi-square p ≈ 0.33. Shadow P&L **−$11,065** vs expected −$875 ± $6,576 (z −1.55).
- By product: FDXM **+$400** (3/3/1); NKD −$2,865 (2 take / 5 stop); MNQ −$3,000; MGC −$2,800; ZS −$2,000; MCL −$800.
- Execution: median gap $+1 a ticket (mean −$41); 3 of 41 readings disagree with the replay (2 on FDXM's DAX-cash proxy).
- Dollar rules on the demo (A48): 8 sessions, signed +213 bps but recorded −$1,615 (NKD rule side −$2,000) — trigger at 40 sessions.
- The plan trades NKD + FDXM: together −$2,465 of the −$11,065.

## 2. The deployed rules on unseen data since 2026-09-01 (A91, §768) — the right sign, at research size
| rule | research | forward (n) | t |
|---|---|---|---|
| D171 DAX fades the pound (all) | +7.6 bps | +6.5 (35) | 0.67 |
| D174 DAX follows the dollar index (strong) | +10.9 | +20.5 (14) | 1.66 |
| D175 DAX fades the Aussie (strong) | +11.3 | +4.4 (10) | 0.26 |
| D227 NKD follows the euro week (all) | +5.9 | +1.8 (35) | 0.11 |
Four of four positive (refreshed 2026-10-21 with data to 10-20); none significant alone; D227 (the NKD rule) weakened from +5.4 to +1.8 bps — watch it. (A48's ticket-level record since deployment: 6 sessions, too few.)

## 3. If the rules had zero edge — the plan still pays (A85/A90, §763-766; **CORRECTED for V2 payouts §805**)
- **V2 payout rules (min($1,250, 2× profit since last payout, above the $2,100 buffer)):** plan mean per 4-month run 2025 starts
  **+$11.9k** (was +$21.3k), 2021-26 **+$8.0k** (was +$12.0k), 2010-20 +$3.4k; zero edge **+$4.2k / +$2.4k** (was +$4.6k / +$2.7k).
  The figures below are the old model's.
- 5 × 50K Tradeify Select Daily, 3 NKD + 2 FDXM, $116, live rules, sides randomised: **≈ +$4.6-5.5k per 4-month run** on 2021-26
  paths (+$2.7-3.8k on 2010-20); P(net>0) ≈ 71%; cash low median ≈ −$2.6k, 5% ≈ −$7.4k.
- The planned mix is already near the zero-edge best (NKD×5 +$5.9k; 3+2 +$5.5k; the demo's 5-product mix only +$2.5k).
- Tradeify is the **only** one of ~14 modelled firm/plan combinations whose structure pays with no edge (consistency and
  payout-gating rules sink the others) — and LucidPro loses even WITH the plan's edges (−$5.6k a run, §770).

## 4. Execution
- Limit entries one tick better LOSE to market entries (A92, §769: adverse selection > the saved tick) — keep market entries.

## Decisions for the review
0. **V2 payouts (§805-806):** all plan dollar figures are lower; under V2 the mix 2 NKD + 3 FDXM edges out 3 + 2 (2025 +$13.1k vs +$11.9k, p10 +$2.5k vs −$0.1k; 2010-20 +$4.6k vs +$3.4k). Switch? The one-NKD launch is barely changed: 2nd payout median 46 sessions (was 42), cash low median −$837 (A102, §807). 50K stays (100K under V2: zero edge −$2.3k, §808). Payout timing: request the max allowed every eligible day (§809).
   **Funded stop ≈ 0.7× (§811, §814)?** A108: every factor 0.6-0.9× beats the current 1.0×; 0.7× 2025 +$19.9k (94%), 2021-26 +$13.3k,
   2010-20 +$4.3k vs current +$11.9k / +$8.0k / +$3.4k; **zero edge +$4.8k / +$3.0k vs +$4.2k / +$2.4k — better with or without an edge.** **DEPLOYED 2026-10-21 (§815).** Caveat §817: the zero-edge differences between stop settings are within noise (seed SE ≈ $0.8k), so
   the gain is plausible, not proven; no harm found. Earlier 0.75× notes: Under V2: 2025 +$19.1k vs +$11.9k, 2021-26 +$11.4k vs +$8.0k, but 2010-20 +$3.1k vs +$3.4k and
   zero edge +$3.8k vs +$4.1k — it pays only if the dollar rules keep their edge; best of six variants. With all 6 zero-edge seeds the 3 + 2 / 0.75× zero edge is +$4.2k (= current) — leading candidate (A107); but by year it gains in 5/6 years 2021-26 and only 3/11 years 2010-20 (edge-dependent).
   Bot V2 payout suggestions: **deployed 2026-10-21** (§813).
1. Launch on 3 NKD + 2 FDXM as planned? (Supported by §2 and §3; the demo's losses sit mostly in products the plan drops.)
2. Keep the dollar rules (A48 trigger at 40 sessions still pending)?
3. Budget: keep ≈ $4-5k available for evaluation fees before payouts (A67; zero-edge 5% low ≈ −$7.4k).
4. Watchlist: gold D727/D728 — re-check ~2026-11-20 (forward t 3.0 but one repeated stance).

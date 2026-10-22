# Prep for the 2026-10-25 review (rewritten 2026-10-21 evening)

The launch decision rests on one question: **do the deployed rules have an edge, and does the plan pay even if they don't?**

## 1. The demo (a18 --review, refreshed 2026-10-21) — adverse, not yet conclusive
- 41 finished tickets; outcome mix vs history chi-square p ≈ 0.33. Shadow P&L **−$11,065** vs expected −$875 ± $6,576 (z −1.55).
- By product: FDXM **+$400** (3/3/1); NKD −$2,865 (2 take / 5 stop); MNQ −$3,000; MGC −$2,800; ZS −$2,000; MCL −$800.
  The plan trades only NKD + FDXM: together −$2,465 of the −$11,065.
- Execution: median gap $+1 a ticket (mean −$41); 3 of 41 readings disagree with the replay (2 on FDXM's DAX-cash proxy).
- Dollar rules on the demo (A48): 8 sessions, signed +213 bps but recorded −$1,615 (NKD rule side −$2,000) — trigger at 40 sessions.

## 2. The deployed rules on unseen data since 2026-09-01 (A91, refreshed to 10-20) — right sign, small samples
| rule | research | forward (n) | t |
|---|---|---|---|
| D171 DAX fades the pound (all) | +7.6 bps | +6.5 (35) | 0.67 |
| D174 DAX follows the dollar index (strong) | +10.9 | +20.5 (14) | 1.66 |
| D175 DAX fades the Aussie (strong) | +11.3 | +4.4 (10) | 0.26 |
| D227 NKD follows the euro week (all) | +5.9 | +1.8 (35) | 0.11 |

Four of four positive; none significant alone; **D227 (the NKD rule) has weakened from +5.4 to +1.8 bps — watch it.**

## 3. What the plan earns — corrected for Tradeify's V2 payout rule (decisions.md 805-819)
**V2 (50K Select Daily bought after 2026-09-01):** a payout request is at most min($1,250, 2× the profit since the last payout,
balance − the $2,100 buffer), ≥ $250. The old model let any payout to $1,250 through, so **every earlier dollar figure was too high**.

Plan as deployed today — 5 × 50K, 3 NKD + 2 FDXM, $116, live rules, **funded stop 0.7×** (mean net per 4-month run):

| | 2025 starts | 2021-26 | 2010-20 | zero edge (2021-26 / 2010-20) |
|---|---|---|---|---|
| **deployed (V2, stop 0.7×)** | **+$19.9k (94%)** | **+$13.3k** | **+$4.3k** | **+$4.8k / +$3.0k** |
| V2, old stop 1.0× | +$11.9k (89%) | +$8.0k | +$3.4k | +$4.2k / +$2.4k |
| old payout model (for reference) | +$21.3k | +$12.0k | +$4.8k | +$4.6k / +$2.7k |

- **The tighter funded stop:** paired test on the same paths +$5.3k a run on 2021-26 (90% CI +$2.9k..+$7.4k), +$0.9k on 2010-20 (CI
  −$0.8k..+$2.6k); zero-edge differences are within noise. Plausible improvement, no harm found — the live record decides (§814-818).
- **Replay noise:** nearby settings move results by several thousand dollars (live-phase timing, §817) — read every figure as ± that.
- **Settled under V2:** keep 3 NKD + 2 FDXM (paired tests: no mix dominates, §819); 50K stays (100K zero edge negative, §808); Select
  Daily beats Flex, Lightning and Growth (§810, §812); request the maximum allowed payout every day it is ≥ $250 (§809).
- **Your launch (one NKD account to two payouts):** barely changed by V2 — 2nd payout median 46 sessions, cash low median −$837 (§807).
- Tradeify is still the only modelled firm whose structure pays with no edge (§763-770).

## 4. Already done (2026-10-21, with your OK)
- Bot payout suggestions follow V2 (§813); bot funded stop 0.7× (§815). Backups in /opt/futures-bot/backup-2026-10-21.
- Launch checklist updated (V2 rules, payout timing, stop, expectations).

## Decisions for the review
1. Launch on 3 NKD + 2 FDXM as planned? (Supported by §2-3; the demo's losses sit mostly in products the plan drops.)
2. Keep the dollar rules (A48 trigger at 40 sessions still pending)? D227 is the weakest.
3. Budget: keep ≈ $4-5k available for evaluation fees before payouts (A67; cash low 95th pct ≈ −$2.2k on the one-NKD launch).
4. Watchlist: gold D727/D728 — re-check ~2026-11-20.

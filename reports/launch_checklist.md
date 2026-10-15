# Real-money launch checklist

For use after the 10-25 demo review. Everything here is what the demo and the replays already assume; if any of it can't be
followed, the dollar estimates don't apply. (decisions.md 583)

Commands below run from the repo folder: `cd ~/futures-research` first (Claude runs them during reviews; you don't have to).

## 1. Before buying anything — decide at the 10-25 review

- [ ] Demo review run: `.venv/bin/python -m futuresres.reporting.a18_demo_check --review`
- [ ] Dollar rules: keep or revert? (review section "The dollar rules, forward"; revert if the first 40 rule sessions are negative)
- [ ] Which accounts (up to 5 at once). The options and their 4-month replays on 2025 starts:
  - **Now:** MNQ, MGC, MCL, NKD, FDXM: +$17,500 a 4-month run
  - **B:** 2×NKD + 2×FDXM + MNQ: +$26,100, but the duplicate accounts win and lose together
  - **C:** 3×NKD + 2×FDXM: +$32,000, the most concentrated
- [ ] Fifth market: MCL or **ZB** (30-year bonds, 4 contracts)? ZB made the book steadier over 2010–26 (P(net > 0) 85 → 92% and
  96 → 99%) but $484 less on 2025 starts (decisions.md 611). Needs Tradeify to permit ZB and a bot ticket.
- [ ] Buying order if not all at once: **NKD and FDXM first** (they carry the rules and pay out most often: NKD 95%, FDXM 92% of 2025
  starts), then MNQ, then MGC and MCL. ZS stays demo-only.
- [ ] Tradeify 50K Daily rules still as modelled (you confirmed 2026-10-15): $80 evaluation, target +$3,000, end-of-day trailing
  drawdown $2,000, evaluation daily loss limit $1,000, consistency 40% (best day ≤ 40% of total profit); funded: drawdown $2,000
  locking at $50,000, daily loss limit $1,000, payouts capped at $1,250 until the 3rd, 90% split. **If any of these change, stop and
  have the models re-run first.**

## 2. Every day

**4:30 PM CT — the alert.** For each ticket in the embed, stage one **scheduled bracket order**:

| field | from the embed |
|---|---|
| product, side, contracts | as shown |
| release (entry) time | the ticket's entry time, CT |
| take / stop | the ticket's take and stop distances (points), attached as a bracket to the fill |
| close (release to flatten) | the ticket's exit time, CT |

Current windows (CT, until the clocks change — **always use the times in the alert**; Europe's clocks change Oct 25 and the US's on Nov 1,
so the FDXM and NKD times move by an hour around then):

| product | entry | close |
|---|---|---|
| MCL | 5:00 PM | 3:55 PM next day |
| NKD | 7:00 PM | 1:00 AM |
| ZS (demo only) | 7:00 PM | 1:15 PM next day |
| MGC | 2:00 AM | 10:30 AM |
| FDXM | 2:00 AM | 10:30 AM |
| MNQ | 8:30 AM | 3:00 PM |

- [ ] Every close time is **before 4:00 PM CT**. No position may cross the 4:00–5:00 PM break.
- [ ] Never long and short the same product at once.
- [ ] If a ticket says no trade (account failed / finished), stage nothing for it.

**~1:45–1:58 AM CT — the FDXM re-check** posts every night. If it @mentions you with **side changed** and you're awake, change the staged
FDXM order before 2:00 AM. If you're asleep, the 4:30 PM side stands — the estimates already assume it.

**After each window — `!eod <PRODUCT> <balance>`** with the platform's balance. With real fills there's nothing to read off a chart. If the
bot answers ⚠️ (its replay disagrees), check the fill; resend with `confirm` only if the platform really shows it.

## 3. When something happens

- **Account breached:** buy a new $80 evaluation for that product, send `!new <PRODUCT>`. Don't change the plan after a loss —
  the replays include the losing runs.
- **Evaluation passed:** nothing to do — the bot sees it from your `!eod` and switches the account to the funded phase.
- **Payout received:** `!payout <PRODUCT> <amount>` so the bot's balance and the review stay right.
- **Missed a ticket** (order not staged, platform down): record it with `!skipped <PRODUCT>`; don't trade it late.
- **Bot didn't post the 4:30 alert:** don't guess tickets — skip the day and tell me.

## 4. Stop / review triggers

- [ ] **Dollar rules** — `.venv/bin/python -m futuresres.reporting.a48_forward` (at least every few weeks): first 40 rule sessions negative → propose reverting.
- [ ] **Fills** — the review's execution table: if real results trail the replay by more than ~$50 a ticket over 20+ tickets, costs are
  worse than modelled; re-run the replays with them (ZS first — its brackets are only 20–40 ticks).
- [ ] **Monthly** — the review plus the watchlist forward test (`.venv/bin/python -m futuresres.reporting.a49_watchlist`).
- [ ] **Any Tradeify rule or fee change** — stop and re-run before the next ticket.

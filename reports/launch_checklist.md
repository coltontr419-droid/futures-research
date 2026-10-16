# Real-money launch checklist — 5 × 50K Tradeify, 3 NKD + 2 FDXM

For use after the 10-25 demo review. Everything here is what the replays assume; if any of it can't be followed, the dollar estimates
don't apply. (decisions.md 583; rewritten 2026-10-16 for the chosen plan, decisions.md 627–638.)

Commands below run from the repo folder: `cd ~/futures-research` first (Claude runs them during reviews; you don't have to).

## 1. Ask Tradeify first (send to support — the plan depends on the answers)

1. **Copy-trading across your own accounts:** "May I place the same trade (same instrument, same direction, same time) in several of my
   own 50K Select Daily accounts — for example three NKD accounts with identical orders?" *(the plan's three NKD and two FDXM accounts
   take identical trades; if not allowed, the mix falls back to one account per market — about +$5.5k a four-month run instead of +$11k)*
2. **Moving to live — please confirm:** live after 3 payouts on one account or 10 payouts in total; at the move, accounts that have
   requested a payout go live (up to 5) and every other account is closed; the 50K live account starts at $0 with a $2,000 trailing
   drawdown that locks at $0 once it is up $2,000; no daily loss limit; daily withdrawals of profit above trading capital at 80/20; no new
   evaluations while any live account is open; after the last live account is lost, a cool-off of up to 4 weeks. *(the models use exactly
   these; also ask what a 100K live account starts with, for later)*
3. **Evaluation re-buys:** "Is there any limit on how often I can buy a new 50K Select Daily evaluation after failing one (about one
   every 6–7 trading days per account), and is $80 the price that will apply?" *(the plan buys about 39 evaluations per four months)*
4. **Products and data:** NKD (CME Nikkei, USD) and FDXM (Eurex Mini-DAX) on your platform, the real-time data each needs (you found
   Eurex is $14 a month), and the round-trip commission for NKD and FDXM.
5. **Scheduled orders:** your platform keeps a staged bracket order with a release time and a close time overnight.

## 2. Before buying — decide at the 10-25 review

- [ ] Demo review run: `.venv/bin/python -m futuresres.reporting.a18_demo_check --review`
- [ ] Dollar rules: keep or revert? (the review's "dollar rules, forward" section; revert if the first 40 rule sessions are negative)
- [ ] Tradeify's answers above match the models — if any rule differs, have the models re-run before buying.
- [ ] Rules as modelled (50K Select Daily): $80 evaluation, target +$3,000, end-of-day trailing drawdown $2,000, evaluation consistency
  40% (best day ≤ 40% of profit), funded drawdown $2,000 locking at $50,000, payouts daily capped at $1,250, 90% split.

**What to expect** (four-month runs; replays with the live rules and one tick of slippage a side; decisions.md 623–635):
- about **+$11,000** on average for runs started in 2025 (all positive; bad case about +$3,000); about +$8,000 across all 2021–26 starts
  (86% positive); if the dollar rules stop working, roughly +$5,000 (the 2010–20 case)
- about **39 evaluations bought** (~$3,100), first move to live around **day 25**, 1–2 moves per four months, about **25 trading days in
  cool-off**, about $12,600 of funded payouts and $2,500 of live payouts
- most evaluations fail — that is how the plan works (a fast staking game), not a sign something is wrong
- two ticks of slippage a side would cut the result by about 40% — watch the first weeks' fills

## 3. Launch day — set up the bot (Claude does this with you)

1. Claude backs up the demo's state, moves the demo files aside, adds `BOT_ACCOUNTS=NKD,NKD2,NKD3,FDXM,FDXM2` to the bot's `.env` on the
   droplet and restarts it.
2. For each account send `!set <ACCOUNT> eval 50000 50000` (e.g. `!set NKD2 eval 50000 50000`) so every account starts clean.
3. The next 4:30 PM CT alert shows five tickets: NKD, NKD2, NKD3 (identical) and FDXM, FDXM2 (identical).

## 4. Every day

**4:30 PM CT — the alert.** For each ticket, stage one **scheduled bracket order** in that account:

| field | from the embed |
|---|---|
| account, product, side, contracts | as shown (e.g. **NKD2**: SELL 1 NKD) |
| release (entry) time | the ticket's entry time, CT |
| take / stop | the ticket's take and stop distances in ticks, as a bracket on the fill |
| close (release to flatten) | the ticket's exit time, CT |

Current windows (CT — **always use the times in the alert**; Europe's clocks change Oct 25 and the US's on Nov 1, so these move by an
hour around then):

| product | entry | close |
|---|---|---|
| NKD (3 accounts) | 7:00 PM | 1:00 AM |
| FDXM (2 accounts) | 2:00 AM | 10:30 AM |

- [ ] Every close is before 4:00 PM CT; never long and short the same product at once; no hedging across products or firms.
- [ ] A ticket that says no trade (account failed / finished): stage nothing for it.

**~1:45–1:58 AM CT — the FDXM re-check** posts every night. If it @mentions you with **side changed** and you're awake, change both
staged FDXM orders before 2:00 AM; if asleep, the 4:30 PM side stands (the estimates assume it).

**After each window — `!eod <ACCOUNT> <balance>`** with the platform's balance (e.g. `!eod NKD3 50850`). If the bot answers ⚠️, check the
fill; resend with `confirm` only if the platform really shows it (it stays quiet when its replay was within 3 ticks).

## 5. When something happens

- **Account breached:** buy a new $80 evaluation for it and send `!new <ACCOUNT>`. Don't change the plan after a loss — the replays
  include the losing runs.
- **Evaluation passed:** nothing to do — the bot sees it from `!eod`.
- **Payout received:** `!payout <ACCOUNT> <amount>`.
- **Moved to live:** tell Claude the same day — the bot does not model live accounts yet; the live-account plan (withdraw above $2k, or
  build to a larger cushion first, decisions.md 629) is decided then.
- **Missed a ticket:** `!skipped <ACCOUNT>`; don't trade it late. **No 4:30 PM alert:** don't guess tickets; skip the day and tell Claude.

## 6. Stop / review triggers

- [ ] **Dollar rules** — `.venv/bin/python -m futuresres.reporting.a48_forward` every few weeks: first 40 rule sessions negative → propose
  reverting. (An automatic switch-off was tested and is not needed: the rules helped these accounts even before 2021, decisions.md 639.)
- [ ] **Fills** — if real fills trail the tickets by more than ~1 tick a trade over 20+ trades, costs are worse than modelled; re-run.
- [ ] **Monthly** — the review plus the watchlist forward test (`.venv/bin/python -m futuresres.reporting.a49_watchlist`).
- [ ] **Any Tradeify rule or fee change** — stop and re-run before the next ticket.

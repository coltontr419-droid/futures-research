# Real-money launch checklist — 5 × 50K Tradeify, 3 NKD + 2 FDXM

For use after the 10-25 demo review. Everything here is what the replays assume; if any of it can't be followed, the dollar estimates
don't apply. (decisions.md 583; rewritten 2026-10-16 for the chosen plan, decisions.md 627–638.)

Commands below run from the repo folder: `cd ~/futures-research` first (Claude runs them during reviews; you don't have to).

## 1. Tradeify's answers (2026-10-16, decisions.md 640)

- [x] Copy-trading across your own accounts — **allowed** (3 NKD + 2 FDXM with identical trades is fine).
- [x] Live-account rules — **as modelled** (verbatim from Tradeify's FAQ); a 100K live account starts at $0 with the evaluation's drawdown.
- [x] Evaluation re-buys — **no limit** on how many or how often.
- [x] Staged orders survive overnight but **may not survive the 5–6 PM ET close** → stage them **after 5:00 PM CT** (see section 4).
- [x] Commissions (Tradovate's published all-in rates): NKD $5.88–7.28 and FDXM $2.04–3.56 a round trip per contract — checked against
  the models: no change to the estimate (decisions.md 641).
- [x] Real-time data: NKD already real-time; Eurex (FDXM) $14 a month (user, 2026-10-16).

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

**Your start (2026-10-16):** one NKD account until it has two payouts (typically ~2 months; ~7 evaluations; cash at risk ~$500, worst
~$1,800), then the five-account run. At the switch, **take account #1's third payout normally** even though it moves you to live — holding
it costs more than it saves (decisions.md 644–646).


1. Claude backs up the demo's state, moves the demo files aside, adds `BOT_ACCOUNTS=NKD,NKD2,NKD3,FDXM,FDXM2` to the bot's `.env` on the
   droplet and restarts it.
2. For each account send `!set <ACCOUNT> eval 50000 50000` (e.g. `!set NKD2 eval 50000 50000`) so every account starts clean.
3. The next 4:30 PM CT alert shows five tickets: NKD, NKD2, NKD3 (identical) and FDXM, FDXM2 (identical).

## 4. Every day

**4:30 PM CT — the alert; stage after 5:00 PM CT.** The alert comes during the 4–5 PM CT close, and orders placed then may not survive
it — wait for the 5:00 PM CT reopen, then for each ticket stage one **scheduled bracket order** in that account (NKD enters at 7:00 PM, so
there are two hours):

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

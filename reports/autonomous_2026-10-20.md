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
- Funded Futures Family −$6.5k, Top One −$2.9k. **Zero-edge firm survey done (12 models): positive = Tradeify, LucidPro, TradeDay
  (+ Elite Trader Funding only on promo); negative = MFF, TPT, Phidias, Topstep, Alpha, Bulenox, FFF, Top One.** The winners share:
  low fee, end-of-day drawdown, payouts without big buffers/consistency gates, high split.
- **Portfolio (A90c, §765): Tradeify + LucidPro + TradeDay together, zero edge, same signals: mean +$22.8k per 4-month run
  (median +$16.1k, 74% profitable, p10 −$18.1k, p90 +$62.5k) on 2021-26 paths; mean +$15.8k (median +$4.2k, 60%) on 2010-20.
  Cash low median −$9.3k, 5% −$22.5k.** ≈ $4-5.7k/month average with NO edge — big swings, needs a ~$10-25k bankroll.
- If each firm trades an INDEPENDENT signal (different rule/market): mean +$20.7k, median +$18.1k, 79% profitable, p10 only −$6.6k
  (2021-26); 2010-20 mean +$10.9k, 70% profitable. → Split the deployed rules across firms rather than copying one signal.

### 7b. ⚠ CORRECTION to item 7 (§766) — the multi-firm zero-edge result does NOT hold
Modelling the rules I had first left out reverses it: **TradeDay 2.0** (5-day minimum, 30% evaluation consistency) → **−$2.9k a run**;
**LucidPro** (funded payouts need best day ≤ 40% of the cycle profit) → **−$5.2k a run**. The bracket strategy's big winning days
break consistency rules, which kills the option value. **Only Tradeify (+$5.5k a run at zero edge, rules confirmed with you) is
positive.** The "+$16-23k a run across firms" figures above are withdrawn. Takeaway: a firm's consistency/payout-gating rules decide
whether the structure pays; Tradeify's Select Daily is unusual in passing.
- Also checked: LucidPro at smaller size (still negative), LucidFlex (−$1.4k to −$3.6k). **Final: Tradeify Select Daily is the only
  firm (of ~14 plan models) whose structure pays with zero edge.** A second firm would need a real edge to be worth it.
- Tradeify mix at zero edge: NKD×5 +$5.9k ≈ the plan's 3 NKD + 2 FDXM +$5.5k > 2+3 +$5.2k ≫ the demo's 5-product mix +$2.5k.
  The planned launch mix is right even if the edges are zero.

### 8. (2026-10-21) Deployed dollar rules forward since 2026-09-01 (A91, §768) — encouraging
D171 DAX-fades-pound +5.8 bps (n 34), D174 DAX-follows-dollar +20.5 (n 14), D175 DAX-fades-Aussie +4.4 (n 10), D227 NKD-follows-euro
week +5.4 (n 34) — all four positive, near research size; none significant alone yet. The demo's −$11k is mostly bracket noise plus
products the launch plan doesn't use.

### 9. (2026-10-21) More screens — all closed
- Kalshi crypto perps funding carry (§767): ≈ 11-33% a year funding, ~15% a year on capital → capital-bound.
- Tradeify account cap: 5 funded in any mix (+ ≤ 15 evals / 30 days) — no extra structural room.
- Limit entries one tick better (A92, §769): lose to market entries (adverse selection > saved tick) → keep market entries.
- LucidPro with real rules loses even WITH the plan's edges (§770): −$5.6k a run → no second firm without checking consistency rules.
- FanDuel Predicts sports moved to Crypto.com (no public prices, 2% fee); NFL props for non-playing players settle at fair price, not
  NO (no inactive-list edge).
- Player props (K11, provisional, §771): the "retail over-bets overs" idea is wrong in sign; cheap rushing-yards props (20-35¢) hit
  more than priced (+6.7¢, n 320) — narrow; registered as K11b (buy cheap YES) for one sealed test after the download.
- Review prep written: `reports/review_2026-10-25_prep.md`.

### 10. (2026-10-20 afternoon) K11c registered (§772) + three screens closed
- Cheap-YES props, discovery after costs (NFL rushing yards, 6 h lead): +3.0¢ a contract per game, t 0.91 — weaker than the
  mid-based calibration (+6.7¢); fades by 3 h before close; NHL goals negative. K11c (all sports, year-round) downloading now.
- Prop-ladder monotonicity arbitrage (bid on a higher strike above the ask on a lower one, same hour): 11 hits in 1.08 M pairs, almost
  all < 1¢ → closed.
- Near-certain in-game contracts (ask 90-99¢, last 4 h): game winners fair (−1.8¢ to +1.8¢, no t > 1.6); prop asks at 90-99¢ are
  stale quotes on markets that settle NO → closed.
- Novig (CFTC DCM, June 2026; zero pre-game fees) — site behind an AWS CAPTCHA, GraphQL allow-listed → no automated reads; ProphetX
  API needs keys → tabled (needs the user's login; capacity also unverified).
- A93 (§773) running: Kalshi × Polymarket US on the same NBA player props (124 matched on the first game; first sweep best net −0.3¢,
  books near-identical → likely the same market makers on both venues). Result after ~6 h of sweeps.
- Polymarket US internal consistency (NBA/NHL/NFL, all open events): winning-margin / exact-margin / race-to buckets — sum of asks
  1.14-2.20, sum of bids ≤ 0.98; no prop-ladder violations → no riskless structure. Closed.
- K13 (§774-775, esports favourite/underdog before start) registered; amended before outcomes after finding Kalshi's listed start
  times can be hours wrong (KC-C9 market closed before its own listed start). Provisional discovery (LoL/CS2/Dota): favourite_YES
  −2.4¢ (t −0.87), underdog_YES −1.7¢ — fair pricing minus costs; rest of the titles downloading.
- Esports in-play (A94, §776): stale-price value swept in fast moves on LoL matches median $427 / mean $1.3k / max $5.3k a match;
  one historical alignment: Kalshi's sweep 6.0 s after Riot's frame time. Live recorder scheduled for 2026-10-22 12:00Z (EMEA
  Masters) and 2026-10-23 17:00Z → (Worlds, 8 matches).
- Pinnacle (guest odds API) vs Kalshi esports pre-match: 52 matched sides; Kalshi within ~1¢ of Pinnacle's no-vig on the big LoL
  matches; only 2 sides > 2¢ after fee, both on thin books (≈ $1-2k volume) → a few dollars a day. Closed.
- Polymarket US has no price history or trades endpoint (closed events only) → no backtests there.
- (afternoon, after a laptop restart wiped the scratchpad: all jobs resumed detached; recorder scheduler recreated)
- K14 (§777-778) closed at discovery: following Valorant in-play moves −2.48¢ after costs (t −3.95), −0.36¢ before costs — the
  screen's positive value came from choosing moves by their later size.
- Market-making markout (Valorant, 610 matches): makers lose BEFORE fees pre-match (−3.0¢ > 1 h before, −1.3¢ last hour; in-play
  −0.24¢) — informed takers pick off quotes. Closed.
- Pinnacle vs Kalshi soccer (909 Pinnacle 1X2 matchups × 817 Kalshi 3-way events → 960 matched sides): 6 sides > 2¢ after fee, the
  large ones mismatched markets (Pinnacle margin 10-11%). Kalshi soccer — small leagues included — sits on the sharp line. Closed.
- Pinnacle vs Kalshi NBA player props (main lines, 198 matched, 171 with ≤ 5¢ spread): Kalshi mid − Pinnacle no-vig −0.15¢ mean,
  0.00¢ median; no side > 2¢ after fee. Kalshi props sit on the sharp main line; the cheap alternate rungs (K11c) have no Pinnacle
  counterpart. Closed for main lines.
- Infrastructure: the laptop container restarted twice (scratchpad wiped, jobs killed). Background jobs now live in
  `scripts/jobs/*.sh` and run as systemd user services `futres-{k11c,k13,a93,a94}` (lingering on → they start with the container).
- Kalshi × Polymarket US midterm races (19 Senate/governor sides matched by slug): best combined net +0.7¢ (Georgia R), locked to
  2026-11-03 — capital-bound, tiny. Prices near identical (e.g. Texas 63/64 vs 62/63). Closed.
- A93 matching bug fixed (Polymarket's 2-letter team codes); tonight's two games now match 245 props; the only > 0 nets sit on dust
  (0.08-contract offers).
- A95 closed (§781): BTC 15-min last-minute takers net ≈ −$1.1k a market (median), taker edge −0.1…−0.7¢; book tracks BRTI better than a
  Coinbase proxy ($4 median error) — the firms there run BRTI replicas.
- K13 closed (§780). K11c listing now cached on disk (restarts were re-listing MLB forever).
- Alternate prop rungs vs a Poisson fit to Pinnacle's main line (NBA REB/AST/3PT, 413 rungs): Kalshi tails sit 1-2¢ above Poisson on
  cheap rungs and 2.6-3¢ below on dear ones — the expected sign of over-dispersion, so model-dependent; outcomes (K11c) decide.
- (CORRECTED §788: the "$526k matched" figure was resting liquidity, not trades.)
- **LEAD — A96 (§782-783): ProphetX vs Pinnacle.** ProphetX (CFTC DCM, 48 states incl. TX per reviews; 2% of net winnings) has a
  keyless public order-book API. Snapshots after the 2% fee: a handful of sides +2-8% vs Pinnacle's no-vig (mostly NCAAF underdogs,
  some NFL favourites), $15-950 behind each; NFL spreads/totals ($250k-1.3M staked a game) near fair so far. Forward paper bets
  scored on closing-line value now recording (service futres-a96, every 20 min); first evaluation once ≥ 150 bets have closed.
- A93 closed (§784). Other TX venues: DraftKings Predictions 403, Fanatics Markets and OG behind Cloudflare challenges → skipped
  (user rule: blocked automated reads).
- Kalshi vs Pinnacle, days ahead: NCAAF median −2.13% (§785), tennis median −2.27% (198 sides; > +2% only on name collisions with
  tournament-winner markets) — Kalshi's sports books sit on the sharp line everywhere checked. ProphetX is the outlier.
- K11b retired unrun (§785). K11c / K13 jobs gated: sealed downloads only if discovery carries.
- K11c closed (§789): cheap props −1.13¢ after costs (522 games); only MLB/WNBA lean positive.
- Maker side of Kalshi NFL game markets (§790): makers lose vs the pre-game closing price in every size bucket → quoting (incl. fee-free
  Polymarket US) closed.
- ProphetX: "totalStake" is resting liquidity, not volume (§788 corrects §786). Soccer "moneyline" there is 2-way (no draw) — not
  comparable with Pinnacle 1X2 without more mapping; dropped (10 sides).
- Running (systemd user services): futres-a96 (ProphetX vs Pinnacle paper bets, closing-line value), futres-a97 (ProphetX websocket
  +EV episodes: lifetime/capacity), futres-a94 (LoL race recordings 10-22 / 10-23).

### 11. (overnight 2026-10-21, user away; ≤ 3 small runs at a time)
- ProphetX NBA player props vs Pinnacle main lines (614 offers): median −6.3%, 3 offers ≥ +2% ($487) → closed.
- ProphetX alternate spreads/totals vs Pinnacle's own alternate lines (748 offers, NFL/NBA/NHL): median −3.3%, none ≥ +2% → closed.
  ProphetX's softness is confined to a few long-shot moneylines; A96 likely small even if its closing-line value is positive.
- Reality-TV elimination markets (Big Brother, DWTS, AGT, Love Island): only Aug-Oct on Kalshi, ~1-4 M contracts a month total →
  seasonal (user rule) → closed without data.
- Golf matchups (ProphetX vs Pinnacle): Pinnacle had not posted this week's matchups yet — retry before Thursday's round 1.
- A94 readout script written (`esports/a94_analyse.py`). Review prep refreshed: A91 to 10-20 (D227 weaker), demo 41 tickets.
- ProphetX × Kalshi riskless pairs (56 moneyline pairs, same event, both fees): best −1.9% → none. Closed.
- ProphetX tennis by tier (A96 rows): median EV ATP −2.2%, WTA −2.6%, Challenger −3.5%, ITF −12.3%; only ~19 distinct sides ever ≥ +2%.
  A96's first 3 closed paper bets (tennis): closing-line EV +7.9% — n far too small. A97 now streams tennis too (§791).

### 12. Morning brief (2026-10-21 ~14:00Z) — nothing profitable confirmed
- **ProphetX taking (A96/A97) — the only live lead, now much weaker.** The long-shot "edges" (tennis, NCAAF +280…+4,300) are a
  proportional-devig artifact: 8 closed tennis paper bets score +16.3% closing-line EV proportional but **−18.0% with power devig**
  (§792). What remains is near-even-money NBA spreads/totals: A97 sees ≈ $15k + $26k a day of stake at ≥ +2% (EV×stake ≈ $360 +
  $750/day, extrapolated from < 1 day), lifetimes minutes, a quarter taken within 10 s (contested). Their closing-line value is scored
  from tonight at their own line (§793). Decision needs ≥ 150 bets (≈ 1-2 weeks).
- Closed overnight: ProphetX NBA props (median −6.3%), ProphetX alternate lines (−3.3%), ProphetX × Kalshi riskless pairs (none),
  ProphetX tennis by tier (−2…−12%), reality-TV markets (seasonal). Golf matchups: Pinnacle not posted yet.
- Review prep refreshed: A91 deployed rules 4/4 positive to 10-20 but D227 (NKD) weaker (+1.8 bps); demo 41 tickets −$11,065
  (z −1.55), NKD −$2,865, FDXM +$400.
- Needs the user: ProphetX market-maker programme contact (§786/788) — only if the user wants it; A94 LoL race records 10-22/10-23.
- Golf matchups: Pinnacle's guest API carries no golf matchups (only single top-N props) — no anchor; closed.

### 13. (2026-10-21 afternoon, user back; ≤ 3 runs; desk research alongside)
- K15 (§795/799/801) not carried: non-sports favourite_YES +2.4¢ (t 1.09), longshot_NO −0.9¢, 24 h out; wide books.
- K16 (§796/802) not carried: maker long-shot sales −3.0¢ per event (t −2.89) — insurance-seller profile; the trade-weighted maker profits
  in the literature are one giant market (Sep Fed decision, 46 M contracts).
- K17 (§797/800) not carried: political favourites a week before resolution, 61 markets, −9.9¢ a week (t −1.36).
- Fed decision markets: tails at 0-1¢ (nothing to sell); the hold/hike split is CME-anchored ("public data vs liquid market") — closed.
- Kalshi fee check: almost every non-sports series charges takers only (makers free); Basic API tier 10 writes/s.

### 14. (2026-10-21 late afternoon) Tradeify V2 payout correction and plan re-checks (§805-812)
- V2 payouts (min($1,250, 2× profit since last payout, above the $2,100 buffer), ≥ $250): plan 2025 +$11.9k (was +$21.3k), 2021-26 +$8.0k
  (was +$12.0k), zero edge +$4.2k (was +$4.6k). Launch (one NKD to two payouts) barely changed. 50K stays (100K zero edge negative), Daily
  beats Flex / Lightning / Growth, request every eligible day. Review candidates: 2 NKD + 3 FDXM (§806); funded stop 0.75× (§811, A107:
  3 + 2 / 0.75× 2025 +$19.1k, zero edge +$4.2k, but edge-dependent by year). Bot payout suggestions fixed for V2 locally (needs deploy OK).

### Search backlog (open)
- A98 Kalshi lag vs Pinnacle moves, A99 Kalshi lag vs ProphetX moves — evening data (NBA pre-tip); A97 NBA closing-line check tonight.
- A94 LoL race — 10-22 06:45 CT (EMEA) and 10-23 11:45 CT (Worlds).
- A96 ProphetX paper bets — running to 150 bets (lead mostly dead: §792, §803).
- Tabled for the user: ProphetX market-maker programme; Novig (CAPTCHA); GRID esports data (application).

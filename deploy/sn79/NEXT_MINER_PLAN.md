# Next miner — plan after x1 + x2 were pruned (11-13, §1428–§1439)

## What killed them
1. Dynamic maker fees (105–140 bp, per book, set by the miner maker/taker mix) netted at 0.005 from every maker fill → making credit ≈ 0 for half the field (§1428/§1429).
   x1 was paid only from making → pruned ≈ 11 AM. Fees do not touch SKILL.
2. x2's start burst on 256 books lost money → score 0 for its whole 24-h protection → $0 pay at protection end → pruned within minutes (§1416/§1439).
3. Presence: we quote on ≈ 25 books at a time vs the fleet's ≈ 192 (pace bucket stop-go); one-sided books earn no making and no inventory control (§1435). Not yet fixed.
4. Response time 0.41 s vs 0.15 s (our compute; §1436).

## Before registering (no spending until these are done)
- [ ] Offline pacer replay on the saved tape: why ≈ 90% of books stay blocked; target ≥ 150 books with resting orders at the same $/book (fleet pattern).
- [ ] Fee-aware quoting: read accounts[book].fees maker_fee_rate each round; widen/skip where 0.005 × rate eats the edge.
- [ ] Speed build (§1436): lazy event objects, cached per-book config, skip _predict when unused → target ≤ 0.25 s.
- [ ] Start budget: pace_start small (e.g. 20k) so the first hours are not a money-losing burst; settle with a positive score ≥ 6 h before protection ends.
- [ ] needrestart exclusion on the box (/etc/needrestart/conf.d/mvtrx.conf) — already on the lab (§1430).

## Settings to start from (agent dc5e46b0 + the above)
- $300: mk_vol_size 0.044, mk_vol_inside 3, fund_mv 1.0 (cap 2) — the only change with a replicated skill gain (§1432).
- $30: mk_low_size 0.033, mk_low_lad "1", mk_low_lad_size 0.033 (+23–25% edge $, §1427/§1432).
- 4-dec: touch + one deep order (mk_dec_touch 1, deep 0.27, size 0.09) — keep (≈ 10× credit per unit once fees fall).
- Not proven: mk_vol_jump / mk_vol_lean_only (§1439 no gain), mk_low_touch_min (untested), mk_skip_dec (keep 0).
- NO taking (memory feedback-no-skill-on-makers).

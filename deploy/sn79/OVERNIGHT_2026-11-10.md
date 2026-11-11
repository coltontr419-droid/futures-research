# MVTRX overnight queue — 11-10 → 11-11 (user-approved: any x3 changes/tests; no spending/keys)

## Deep dive (§1380): why x3 earns $141/mo vs the $212 field median
1. The field median is lifted by SKILL miners: skill-only median $288, skill+making $198, **making-only $170** (n 106). x3 is making-only and sits mid-pack
   among makers (rank 47 of 88 by live making credit). Making-only pay ≈ $0.335 per making point; the field median needs ≈ 632 (x3 ≈ 330 → 1.9×).
2. Top making-only miners (UIDs 48, 178, 119, 117, 5, 146; making 1,000–1,345, pay $250–350) have the SAME quality as x3 (R/C 0.60–0.68 vs 0.60)
   but **3× its captured volume** (2,200–2,500 vs 737 in the last 3 sim h) and better balance (two-sided 0.85–0.90 of captured vs 0.79).
   UID 216 (our copy target) is a low-volume, high-quality miner — not a top earner among makers.
3. Their volume comes in BURSTS ($50–106k per book per sim hour for 2–3 sim h, then $3–15k), and resting orders keep filling past the $500k cap
   (the cap drops new placements only): UID 119 traded > $500k on 26 books within 9.2 sim h of our tape. x3 paces steadily at ≈ $18k/book/sim h and is
   blocked by its own token bucket on 103–111 of 128 books at any moment (24-h ledger median $296k of its $450k budget).
4. So the gap = volume (biggest; bounded by our cap-safety rule) × balance × quality. Tests tonight target quality and balance (live, no cap risk).
   Volume options need the user's yes (pacing rule): (a) pace_cap 450k → 490k (+≈ 9% volume, still under the cap); (b) burst timing study.

## Queue (each: 4 half-hours, whole-miner credit vs UID 216 first, per fill second; scheduler: sh /opt/mvtrx/abtest_sched.sh)
Pay estimates assume pay ∝ making credit (x3 now ≈ $141/mo).
| # | When (CT) | Test (A vs B) | Why | Est. if it wins |
|---|---|---|---|---|
| T1 fm11 | 9:10–11:10 PM | fundamental MOVE lean on $300 (fund_mv 0.5, 10 s, cap 1) vs off | Δf predicts the next $300 mid (+0.16/−0.14 spread); targets the $300 adverse move | quality +0.03–0.06 → +5–10% → **+$7–14/mo** |
| — | ≈ 11:20 PM | gated restart onto agent 23320fda (adds fund_scope); keeps the live params after the T1 decision | | |
| T2 calmfund | 11:45 PM–1:45 AM | level lean on CALM books only (fund 0.3, fund_cap 0.5, fund_scope 1) vs off | fc10: calm +1.75 ± 0.65 bp/fill (2.7 w); calm side flips ≈ 5×/sim h so it should not pin inventory | +5–8% → **+$7–11/mo** |
| T3 | 2:00–4:00 AM | if T1 won: dose fund_mv 1.0 vs 0.5 · else: skew 8 vs 5 | dose / balance | +2–5% (**+$3–7**) / −3…+7% (**±$5–10**) |
| T4 | 4:15–6:15 AM | skew 8 vs 5 (if not run in T3) else fund_mv window 20 s vs 10 s | balance: x3 two-sided 0.79 vs top makers 0.85–0.90 | −3…+7% → **±$5–10/mo** |
| T5 | 6:30–8:30 AM | confirmation: all overnight winners (A) vs the 9 PM base (B) | total gain, pooled | sum of the above: realistic **+10–25% → $155–175/mo** |
Honest ceiling: quality/balance alone cannot reach the $212 median (making-only median is $170); volume or skill is needed beyond that.

## Decision steps (one-shot prompts ≈ 11:17 PM, 1:52 AM, 4:07 AM, 6:22 AM, 8:37 AM)
Registration check → read → decide (rule 2 for ties) → APPLY winner via liveswitch_<name>.sh APPLY → schedule the next row with abtest_sched.sh
(BASE = the current live_params_64.json body) → log § + lesson → commit/push → update the brief cron's TEST line. Morning summary at 8:37 AM:
MORNING_2026-11-11.md (every test, result, decision, pay before/after).

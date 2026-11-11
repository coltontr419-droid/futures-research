# MVTRX overnight queue — 11-10 → 11-11 (user-approved: any x3 changes/tests; no spending/keys)

## CORRECTION (§1382): the 'top makers' below are 0.4–1.1-day-old start-up UIDs — VOID as copy targets. Settled makers (≥ 7 d) median $178, max $219; real target UID 46.

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
   Volume: pace_cap 490k FAILS the cap attacks (worst $506k / $532k); 455k passes by $2k; 450k is the safe maximum → NO change (§1381, user asked for 490k).
   Burst timing (burst.py): top makers do NOT trade more in fast markets; they avoid the tightest $300/4-dec spreads (→ T4).

## Queue (each: 4 half-hours, whole-miner credit vs UID 216 first, per fill second; scheduler: sh /opt/mvtrx/abtest_sched.sh)
Pay estimates assume pay ∝ making credit (x3 now ≈ $141/mo).
| # | When (CT) | Test (A vs B) | Why | Est. if it wins |
|---|---|---|---|---|
| T1 fm11 | 9:10–11:10 PM | fundamental MOVE lean on $300 (fund_mv 0.5, 10 s, cap 1) vs off | Δf predicts the next $300 mid (+0.16/−0.14 spread); targets the $300 adverse move | quality +0.03–0.06 → +5–10% → **+$7–14/mo** |
| — | ≈ 11:20 PM | gated restart onto agent 23320fda (adds fund_scope); keeps the live params after the T1 decision | | |
| T2 profile46 | 11:45 PM–1:45 AM | COPY SETTLED UID 46's QUOTING (§1382): $300 inside 0, size 0.022, ladder 1:2:4:7 @0.027; calm ladder 1:2:3 @0.02; 4-dec inside 0, size 0.009, deep 0.27 — vs current | UID 46 (7.9 d) trades x3's dollars but captures 2× (smaller orders spread over depth) | up to +40–80% credit if it reproduces 46; realistic **+$15–40/mo** |
| T2b calmfund | after T2 (T3 slot) | calm-only capped level lean | calm +1.75 bp/fill earlier | **+$7–11/mo** |
| T3 | 2:00–4:00 AM | if T1 won: dose fund_mv 1.0 vs 0.5 · else: skew 8 vs 5 | dose / balance | +2–5% (**+$3–7**) / −3…+7% (**±$5–10**) |
| T4 vtm6 | 4:15–6:15 AM | COPY THE TOP MAKERS' SPREAD CHOICE: no $300 touch order when the spread < 6 ticks (≈ ≤ 2 bp; mk_vol_touch_min 6) vs 0 | top makers put 32% of $300 notional at ≤ 2 bp spreads vs x3 45% (burst.py, §1381) and earn 10–37% more capture per $ | +3–6% → **+$4–8/mo** |
| T5 | 6:30–8:30 AM | confirmation: all overnight winners (A) vs the 9 PM base (B) | total gain, pooled | sum of the above: realistic **+10–25% → $155–175/mo** |
Honest ceiling: quality/balance alone cannot reach the $212 median (making-only median is $170); volume or skill is needed beyond that.

## Decision steps (one-shot prompts ≈ 11:17 PM, 1:52 AM, 4:07 AM, 6:22 AM, 8:37 AM)
Registration check → read → decide (rule 2 for ties) → APPLY winner via liveswitch_<name>.sh APPLY → schedule the next row with abtest_sched.sh
(BASE = the current live_params_64.json body) → log § + lesson → commit/push → update the brief cron's TEST line. Morning summary at 8:37 AM:
MORNING_2026-11-11.md (every test, result, decision, pay before/after).

## REVISED ORDER (9:55 PM, §1382)
- T1 fm11 9:10–11:10 PM → decide 11:17 + gated restart onto 23320fda.
- T2 **profile46** 11:45 PM–1:45 AM → decide 1:52 AM. A = '"mk_vol_inside": 5→0, "mk_vol_size": 0.022, "mk_vol_lad": "1:2:4:7", "mk_vol_lad_size": 0.027, "mk_calm_lad": "1:2:3", "mk_calm_lad_size": 0.02, "mk_dec_inside": 0, "mk_dec_size": 0.009, "mk_dec_deep": 0.27'
  B = the 9 PM quoting '"mk_vol_inside": 5, "mk_vol_size": 0.034, "mk_vol_lad": "2:5:10:20", "mk_vol_lad_size": 0.07, "mk_calm_lad": "1:2:4", "mk_calm_lad_size": 0.036, "mk_dec_inside": 1, "mk_dec_size": 0.09, "mk_dec_deep": 0.27'.
  Also check the fill-depth match to UID 46 (in spreads, per group) and fill counts per arm.
- T3 calmfund 2:00–4:00 AM (ABBA) → decide 4:07 AM. profile46 result: tie → $300+calm adopted, 4-dec kept (§1384). ALL remaining tests ABBA (order bias, §1384).
- T4 skew8 4:15–6:15 AM (ABBA) — fm11 lost, calmfund lost (§1386). Fundamental-lean line closed. (vtm6 dropped — its basis was the start-up UIDs.)
- T5 confirm 6:30–8:30 AM (ABBA, started §1387): all winners vs the 9 PM base (fund/fund_cap/fund_scope/fund_mv 0, skew 5, mk_vol_touch_min 0 + the B quoting above).

## EXTENSION (user 11:55 PM: away until ≈ 10–11 AM; any changes/tests OK except registering; tests 2 h unless 4 h truly needed)
- T6 8:45–10:45 AM: chosen at 8:37 from the results (best open lead: refine whichever group gained most in profile46, e.g. 4-dec depth/size or $300 ladder; else calm fund lean dose).
- Final read + summary ≈ 10:50 AM → MORNING_2026-11-11.md updated (the 8:37 draft is written first).

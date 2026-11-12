# x3 test queue (user 11-12 ≈ 1 AM: laptop stays open; 2-h tests, extend only if needed; decide, apply on x3, start the next)
x3 = UID 64 = test subject; reference UID 46 only; makers stay making-only; NEVER change x1 (UID 27) or later miners (replicate only after a clear,
repeated win / the user's OK). Goal: lift x3 above the prune line (≈ 1.2× now) — scaling adds new miners that hit the settled ones.

## How each step works (one-shot decision prompt ≈ 7 min after a test ends)
1. Registration check (x3=64 x1=27); pay for both (mypay.py).
2. Read /opt/mvtrx/ab_read_<name>.txt (flash line first: > 3× apart → void, keep proven; per fill vs 46; whole-miner if readable) and its edge-per-$ rows
   (abgrp.sh, appended ≈ 6 min after the read). DECIDING read: x3 edge per $ in the changed book group, A vs B (pool the two A and two B windows by $):
   clear win = edge per $ up ≥ ≈ 20% AND edge $ not down AND per fill not clearly worse → APPLY A on x3 (liveswitch_<name>.sh APPLY, verify).
   Promising but noisy (thin 4-dec windows, < ≈ 60 fills per arm) → EXTEND: re-run the same test 2 more hours (name <name>b) and pool.
   Else keep proven (B).
3. Start the next queue item at the next :00/:20/:40 ≥ 5 min ahead: `sh /opt/mvtrx/abtest_sched.sh <name> "<UTC start>" ABBA '<x3 live params minus the
   tested keys>' '<A>' '<B>' "<description>"` + `systemd-run --unit mvtrx-grp-<name> --on-calendar "<read time + 3 min> UTC" /bin/sh /opt/mvtrx/abgrp.sh <name>`.
4. CronCreate a one-shot decision prompt ≈ 7 min after the new test ends (copy of this step, pointing at this file).
5. Log a § + lesson, commit/push, update the brief cron's TEST line, mark the item below.

## Queue (in order) — NEW-REGIME (256 books) ITEMS FIRST (user 11-12 ≈ 1:20 AM, memory feedback-new-regime-priority.md)
When x3 shows a clear win on the 256-book layout → APPLY the same live params to x1 too (user pre-approved for 256-book layout fixes), log, tell the user.
regime46.py (§1404, new sim): $30 books — 46 at the touch on all 64, never ahead, $1.8k fills, edge +4.4 bp vs ours ahead 67–79% (4-dec pattern), $4.5k,
+2.9 bp on 39–46 books; new 4-dec 192–255 — ours $2.8M each at +0.9 bp vs 46 $0.14M deep (≈ 200–500 ticks) at +2.6 bp; $300 0–127 — 46 depth ≈ 3 ticks +1.5 bp vs ours ≈ 1 tick +1.1.
0. bmap — DONE §1406: CLEAR WIN ($30 books: x3 178–180 fills / $196k / edge $56–58 per half-hour vs 5–8 / $16–29k / $3–6; edge per $ +2.9 vs +1.7–2.0) → applied to x3 AND x1 (x1 restarted onto 12372763, 3:40 AM).
1. decdeep — RAN 3:50–5:50 AM: TOO THIN (x3 4-dec fills 9–27 per half-hour — the new 4-dec books are pace-blocked after their start burst) → kept B; RE-RUN when the 4-dec budget has refilled (later 11-12) — new 4-dec books 192–255 deep-only: A '"mk_dec_touch": 0, "mk_dec_deep2": 0.6' vs B '"mk_dec_touch": 1, "mk_dec_deep2": 0' (we pour ≈ $2.8M at +0.9 bp there).
2. vlad — DONE §1408: tie ($300 edge/$ +1.35 vs +1.22 bp, edge $ 42 vs 44; $30 +2.88 vs +3.00) → kept 1:2:4:7 — $300 ladder deeper (46 depth ≈ 3 ticks): A '"mk_vol_lad": "2:4:7:12"' vs B '"mk_vol_lad": "1:2:4:7"' — now covers 0–191 under the new map.
3. decdeep1 — 4-dec deep order further: A '"mk_dec_deep": 0.5' vs B '"mk_dec_deep": 0.27'.
4. vtouch — RUNNING 8:30–10:30 AM (decision 10:40) — $300-ladder touch half size: A '"mk_vol_size": 0.011' vs B '"mk_vol_size": 0.022'.
5. vladsz — ladder size: A '"mk_vol_lad_size": 0.04' vs B 0.027.  6. decsz — 4-dec size: A '"mk_dec_size": 0.06' vs B 0.09.
(Every test after bmap runs ON the bmap winner's map. Skip items made moot; add items from the reads. 9:37 AM collision check in between.)

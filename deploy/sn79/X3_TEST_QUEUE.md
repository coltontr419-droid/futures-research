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

## Queue (in order)
1. decdeep — 4-dec deep-only: A '"mk_dec_touch": 0, "mk_dec_deep2": 0.6' vs B '"mk_dec_touch": 1, "mk_dec_deep2": 0'. RUNNING 1:10–3:10 AM.
2. vtouch — $300 touch order half size: A '"mk_vol_size": 0.011' vs B '"mk_vol_size": 0.022' (more paced budget to the deep ladder).
3. decdeep1 — 4-dec deep order further: A '"mk_dec_deep": 0.5' vs B '"mk_dec_deep": 0.27' (UID 46 4-dec depth p75 0.47 spreads).
4. vlad — $300 ladder deeper: A '"mk_vol_lad": "2:4:7:12"' vs B '"mk_vol_lad": "1:2:4:7"'.
5. vladsz — $300 ladder orders larger: A '"mk_vol_lad_size": 0.04' vs B '"mk_vol_lad_size": 0.027'.
6. decsz — 4-dec order size: A '"mk_dec_size": 0.06' vs B '"mk_dec_size": 0.09'.
(Skip an item if an earlier win makes it moot; add items from what the reads show. The 9:37 AM collision check / x2 go-no-go runs in between.)

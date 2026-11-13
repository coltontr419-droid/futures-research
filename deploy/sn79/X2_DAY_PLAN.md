# x2's 24-hour protected test day (user 11-12 ≈ 12:30 PM CT; rule: never crash a settled miner — memory feedback-never-crash-settled.md)

x2 starts on agent 7d4dd4f5 (adds a "low" book group = the $30 books 128–191 with its own size/ladder knobs; identical behaviour by default) and the proven base
(x1's params + book_map "calm:63-101;low:128-191;dec:192-255", $30 knobs pinned to the current values). Everything below is a LIVE switch on x2 only — no restarts.

| # | Hours after start | Test (A vs B) | Why / what would make it a win |
|---|---|---|---|
| 1 | 0.5–2.5 | new 4-dec books deep-only (no touch, deep 0.27 + 0.6) vs touch + one deep | both miners LOSE money there at the touch; UID 46 trades them deep (+2.6 bp). Runs first while x2's 4-dec budget is fresh |
| 2 | 2.5–4.5 | 4-dec order size $1.5k vs $4.5k | UID 46 trades them small; less money at risk per fill |
| 3 | 4.5–6.5 | 4-dec deep order 0.5 vs 0.27 spreads back | UID 46's depth p75 ≈ 0.47 spreads |
| 4 | 6.5–8.5 (7:01–9:01 PM CT) | RE-RUN of test 1 (dec4b) | test 1 ran inside the start burst; deep-only looked promising (+1.14 vs +0.74 bp) — user 11-12 5:40 PM |
| 5 | 8.5–10.5 | $30 books touch $1.8k vs $1.1k | UID 46's fill size there; +45% edge per $ for 46 |
| 6 | 10.5–12.5 | $30 books ladder 1:2:3 vs 1:2:4:7 | a tick is 3.4 bp on $30 books — 7 ticks back may be too deep |
| 7 | 12.5–14.5 | $30 books ladder orders $2.25k vs $1.35k | more of the budget on the best group |
| 8 | 14.5–16.5 | $300 books touch $1.8k vs $1.1k | UID 46 fill size on $300 |
| 9 | 16.5–18.5 (5:01–7:01 AM CT) | $30 books "46 shape": touch $0.55k + ladder 1:2:3 at $1.8k vs base | §1421: 46/98 earn skill on $30 books with more fills one tick back; replaces the calm-pattern test ($300 books pay least per unit) |
| — | dropped | inventory lean 3 vs 5 | moved to the next miner's test day to keep ≥3 h clean before protection ends |
| 10 | ≈ 18.75–20.75 | CONFIRMATION: all clear winners together vs the base | decided from tests 1–9 |
| — | ≈ 20.75–24 | x2 settles on the best proven setup, no changes | clean scoring window before protection ends |

Each test: 2 h ABBA (30-min blocks), read + edge-per-$ read written on the server; decided on edge per $ AND edge $ in the changed group (flash-skewed reads void).
Inconclusive tests are re-run (extended) only after all 9 have run. Clear winners on knobs x1 already has → x1 by live switch; winners on the new $30 knobs
reach x1 only at a future planned restart (x1 runs 12372763 in memory).
Start: `sh /opt/mvtrx/start_x2.sh <uid>` (registration check, agent swap on disk, our_uids, schedules all 9 tests from start + 30 min, starts mvtrx-x2).

From §1421 every test from dec4b on also gets a per-arm SKILL read (skill_ab.py, validator alpha loop, appended ≈ 12 min after the test ends).

## §1423 (11-12 ≈ 8:30 PM CT): tests 5–9 REPLACED by fleet-copy tests (target = SKILL, copy the 5F1F2JMu core pure makers 216/40/52/134; reference 252)
| # | CT | Test (A vs B) | Why |
|---|---|---|---|
| 5 | 9:01–11:01 PM | fmv1: fundamental-move lean 1.0 (cap 2 spreads) vs off | core makers: 47% of $300 $ filled right after the fundamental moved their way, 3% against (us 10% / 13%); price after fill +0.35 bp vs us −0.65 |
| 6 | 11:01 PM–1:01 AM | vfleet: $300 orders $2.2k + one tick inside when spread ≥ 3 ticks vs $1.1k, never inside | core: avg $300 fill $2.2k (us $0.85k), ≈ 33% of $ inside the spread (us 0%) |
| 7 | 1:01–3:01 AM | low30f: $30 touch $1.6k + one level 1 tick back $1.6k vs base 1:2:4:7 | core: 21–24% of $30 $ one tick back (us 3–4%), edge +3.8 bp (us +2.8), half our volume per book |
| 8 | 3:01–5:01 AM | fmv2: lean 2.0 (cap 3) vs off | dose check |
| 9 | 5:01–7:01 AM | fleet: all three together vs base | preview of the confirmation |
Judged on the per-arm SKILL block + price move after the fill FIRST, pay-weighted edge $ second. lowsz / lowlad / lowls / vsz / low46 cancelled.

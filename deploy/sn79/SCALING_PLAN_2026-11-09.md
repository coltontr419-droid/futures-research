# MVTRX scaling plan (draft, 2026-11-09 ≈ 6:50 AM CT) — for the user's decision

## Pay today ($/month per UID, chain emission × the earnings-log formula; TAO $217.82)
| Who | Pay |
|---|---|
| **x3 (UID 64, 10.8 h old)** | **$183** (rank 166 of 256) |
| Prune line (lowest unprotected UID) | $128 (next: $131, $133, $137, $140) → x3 = **1.43×** the line |
| Field (250 paid UIDs) | p10 $133 · median $216 · p75 $285 · p90 $349 |
| Fleet 5F1F2JMu, all 41 UIDs | total **$9,736/mo** · top $506 · median $232 · bottom $0 (brand-new UIDs) |
| Fleet, 0–1 day old (4) | $0 – $229 (median $27) |
| Fleet, 1–3 days old (13) | $257 – $506 (median $317) ← their head-start period |
| Fleet, 3–7 days old (7) | $147 – $193 (median $169) ← after the head start leaves the window |
| Fleet, 14+ days old (16) | $182 – $298 (median $231) ← settled, long-lived |

**What this says:**
- At under 11 hours old, x3 already earns about what the fleet's settled UIDs earn at the bottom ($182) and 0.79× the fleet median.
- The fleet's own life cycle: high for days 1–3 (head start), a dip around days 3–7 (≈ $170), then settling ≈ $230. x3 should follow the same curve —
  expect a dip (today ≈ 10–11 AM in the live score; days 3–7 in pay). At ≈ $170 vs a line ≈ $128–140 that is ≈ 1.2–1.3× — survivable, not comfortable.
- The fleet earns ≈ $9.7k/month with 41 UIDs ≈ $237 per UID on average. That is the realistic ceiling per UID for this strategy class.

## Costs
- Registration ≈ 0.117 TAO ≈ **$25** per UID (one-time; again if a UID is pruned).
- Lab box (4 vCPU / 8 GB, ≈ $48/mo) fits ≈ 15–20 more miners (each ≈ 180 MB RAM, ≈ 7% of a core). Beyond that, another box ≈ $48/mo per ≈ 18 UIDs.
- Wallet now 0.0138 TAO → every registration needs a top-up.

## What scaling could earn (if new UIDs perform like x3 / the fleet)
| UIDs | At $170 (dip level) | At $230 (settled) | Boxes | One-time registration |
|---|---|---|---|---|
| 1 (x3) | $170 | $230 | 1 (have) | done |
| 5 | $850 | $1,150 | 1 | ≈ $100 |
| 10 | $1,700 | $2,300 | 1 | ≈ $225 |
| 20 | $3,400 | $4,600 | 2 (+$48/mo) | ≈ $475 |
| 45 | $7,650 | $10,350 | 3 (+$96/mo) | ≈ $1,100 |
Caveats (corrected 7:00 AM after the user's point): all 256 slots are always full, so a new UID REPLACES the pruned, lowest-paid miner (≈ $128) — most of
its pay comes from that slot, not from our other UIDs. Shares are proportional, so a better replacement dilutes everyone slightly: ≈ +$72 on a ≈ $62k pool ≈
0.1% per new UID; ≈ 5% per UID at 45 UIDs. Real risks: (1) our own identical makers compete for the same fills (the fleet runs 41 identical UIDs at ≈ $237
each, so it works at that size; our makers are volume-capped; unproven for us beyond 2–3) and (2) the prune line creeps up as our UIDs take the bottom slots.
Each UID must survive its first 24 h on its own.

## Proposed order (your call)
1. **Gate:** x3 survives past protection (≈ 7:46 PM today) AND holds ≥ 1.3× the prune line through its dip (watch for 2–3 days).
2. **Step 1:** one more UID per day (the one-miner-per-day rule), same setup (the x1 unit is ready, with live reload), each judged at 6 h / 24 h vs the line.
3. **Step 2:** once 3 UIDs have held ≥ 1.3× for several days, add 5 at a time until the box is full (≈ 15–20), then a second box.
4. Keep improving the $300 gap with live-reload tests on one UID at a time (no restarts) — every 0.5 bp kept per fill lifts every UID.

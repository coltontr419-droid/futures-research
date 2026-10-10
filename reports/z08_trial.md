# Z08 — hedger flow (CFTC COT) sets the commodity brackets' direction: the trial

## MCL — **REJECT**

2864 sessions, 2015-01-01 → 2026-08-27; long in 53%.

- Sign × window: Sharpe **+0.17** (mean +3.03 bps) — needs > 0: True.
- Always long: Sharpe +0.23 (mean +4.11 bps) — must beat it: False.
- Window mean after hedgers bought +6.79 bps; after they sold +1.14 bps.
- Posterior +0.23 ± 0.21 — needs > 0: True.

| period | sessions | signal Sharpe | always-long Sharpe |
|---|---|---|---|
| 2015-20 | 1473 | +0.03 | -0.13 |
| 2021-26 | 1391 | +0.36 | +0.71 |

Outcome injection: 0.3 planted, recovered 0.30 (SD 0.29); P(estimate > 0) 84%.

## MGC — **CONFIRM**

2578 sessions, 2015-01-26 → 2026-08-27; long in 50%.

- Sign × window: Sharpe **+0.42** (mean +2.05 bps) — needs > 0: True.
- Always long: Sharpe +0.36 (mean +1.75 bps) — must beat it: True.
- Window mean after hedgers bought +3.77 bps; after they sold -0.30 bps.
- Posterior +0.36 ± 0.21 — needs > 0: True.

| period | sessions | signal Sharpe | always-long Sharpe |
|---|---|---|---|
| 2015-20 | 1195 | -0.08 | +0.74 |
| 2021-26 | 1383 | +0.79 | +0.09 |

Outcome injection: 0.3 planted, recovered 0.30 (SD 0.30); P(estimate > 0) 84%.

Gold, not decisive — the same rule on the full-session daily GC return: Sharpe +0.39 (always long +0.59), 2948 sessions.

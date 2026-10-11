# Z10 — gotobi: long USD/JPY into the Tokyo fix (strict rule): the trial

**Decision: REJECT.** 316 gotobi events, 2021-01-05 → 2026-09-30.

- 18:00 ET → 9:55 JST: gross **+1.49 bps**, net +0.49 (SD 13.0); t **+0.67** (needs > 1.645): False; net win rate 51%.
- Placebo: random non-gotobi sets **92.8th** pct; calendar shifted ±1–4 days **50th** pct (both need ≥ 95): False.
- Posterior net mean +0.60 bps (zero prior +0.32): True.
- Non-gotobi days, same window: +0.56 bps gross. The paper's 03:00 JST window (not tradable): +2.15 bps gross.
- Running count: 10 Z market-tests.

| period | events | net bps | t |
|---|---|---|---|
| 2021-23 | 159 | +0.87 | +0.88 |
| 2024-26 | 157 | +0.10 | +0.09 |

Outcome injection: 0.8 bp planted, recovered 0.81 (SD 0.84); power of the strict t at that size 24%.

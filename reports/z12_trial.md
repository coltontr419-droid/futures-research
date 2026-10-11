# Z12 — EUR/USD: short in European hours, long in US hours (strict rule): the trial

**Decision: REJECT.** 4231 weekdays, 2010-01-04 → 2026-09-30.

- Morning short (07:00 LDN → 08:00 NY) gross +1.26 bps; afternoon long (08:00 → 16:00 NY) gross +0.40 bps; legs' net Sharpe +0.26 / -0.16.
- Day, net of 1.6 bps: **+0.06 bps** (SD 47.6); t **+0.09** (needs > 1.645): False; annual net Sharpe +0.02.
- Placebo: the schedule shifted by each other hour: real at the **87th** pct (needs ≥ 95): False.
- Posterior Sharpe +0.18 (zero prior +0.02): True.
- Running count: 12 Z market-tests.

| period | days | net bps/day | net Sharpe | morning short gross | afternoon long gross |
|---|---|---|---|---|---|
| 2010-17 | 2040 | +1.40 | +0.41 | +1.93 | +1.07 |
| 2018-26 | 2191 | -1.18 | -0.45 | +0.63 | -0.21 |

Outcome injection: net Sharpe 0.6 planted, recovered 0.60 (SD 0.24); power of the strict t at that size 80%.

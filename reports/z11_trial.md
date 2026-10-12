# Z11 — month-end FX hedge rebalancing at the London fix, EUR/USD (strict rule): the trial

**Decision: REJECT.** 158 month-ends, 2013-01-31 → 2026-09-30.

- 15:00 → 16:00 London, signed by S&P − DAX: gross **+0.83 bps**, net -0.17 (SD 22.8); t **-0.09** (needs > 1.645): False; net win rate 49%; slope +0.10 bps per 1%.
- Placebos: the 5 weekdays before month-end **60th** pct; signal permuted across months **63.3th** pct (both need ≥ 95): False.
- Posterior net mean +0.69 bps (zero prior -0.12): True.
- Running count: 11 Z market-tests.

| period | events | net bps | t |
|---|---|---|---|
| 2013-19 | 84 | +0.10 | +0.05 |
| 2020-26 | 74 | -0.47 | -0.15 |

Outcome injection: 3.0 bps planted, recovered 2.99 (SD 1.25); power of the strict t at that size 79%.

# Z11 — month-end FX hedge rebalancing at the London fix, EUR/USD (strict rule): the trial

**Decision: REJECT.** 158 month-ends, 2013-01-31 → 2026-09-30.

- 15:00 → 16:00 London, signed by S&P − DAX: gross **-0.92 bps**, net -1.92 (SD 17.9); t **-1.34** (needs > 1.645): False; net win rate 41%; slope +0.05 bps per 1%.
- Placebos: the 5 weekdays before month-end **20th** pct; signal permuted across months **30.2th** pct (both need ≥ 95): False.
- Posterior net mean -1.00 bps (zero prior -1.56): False.
- Running count: 11 Z market-tests.

| period | events | net bps | t |
|---|---|---|---|
| 2013-19 | 84 | -0.19 | -0.12 |
| 2020-26 | 74 | -3.88 | -1.59 |

Outcome injection: 3.0 bps planted, recovered 3.03 (SD 1.16); power of the strict t at that size 82%.

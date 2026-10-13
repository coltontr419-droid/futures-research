# D35 — usdchf London window fades gold's overnight move (every day): the validation trial

**Decision: REJECT.** 2083 days, 2018-01-02 → 2026-08-27 (sealed until registration).

- Demeaned (skill beyond drift): **-0.12 bps** a day, t -0.14; hit rate 48%.
- (a) Against always-long over the same window, raw: **+0.58 bps**, t **+0.46** (needs > 1.645): False.
- (b) Placebo, predictor shifted ±2…±11 days: real at the **40th** pct (needs ≥ 95): False.
- (c) Posterior +0.28 bps (prior Normal(1.41, 1.41)): True. (d) 2021–26 alone +0.72: True.
- Discovery (2010–17): -2.83 bps, t -2.21, n 1363. Z and D market-test number 47.

| period | days | demeaned bps | t | vs always-long bps |
|---|---|---|---|---|
| 2018-20 | 740 | -1.65 | -1.34 | -0.93 |
| 2021-26 | 1343 | +0.72 | +0.65 | +1.41 |

Outcome injection: 1.41 bp planted, recovered 1.44; power of the strict t 53%.

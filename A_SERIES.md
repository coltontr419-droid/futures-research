# A-series — play the account optimally

**Status: A01–A03 computed, 2026-10-09. No trial spent (no market claim: zero edge throughout).**
`decisions.md` §93. Code: `reporting/a01_game.py` (the solver), `reporting/a02_real.py` (real paths).

## The idea

Every earlier strategy was a market strategy, sized simply. None asked **how to stake within the rules**.
With no edge, the evaluation is a fair game: on average the balance stays where it started, so the pass
rate depends on **where you fail when you fail**. Fail at the initial $48,000 floor rather than after
climbing, and the pass rate rises (ceiling 40% at zero edge). Tradeify's rules — a floor that trails
end-of-day balances only, a soft $1,000 daily limit, a 40% consistency cap, payouts from $52,000 — make
the account a game that can be solved exactly.

## A01 — the solved game (fair odds, no costs)

Each day choose a bracket: profit target +W, stop −L (L ≤ $1,000; odds fair on the stop actually
reachable). Dynamic programming over (balance, end-of-day peak, best day), then the funded account
(balance, peak/lock, payouts taken).

- **Evaluation: max P(pass) 30%, almost all within 10 trading days** (passive trading ~19%). First move:
  **+$1,200 / −$1,000** — the target at exactly the consistency limit, the stop at the daily limit.
- Funded account: P(first payout) 48% within ~5 days.
- Whole path: P(payout within 84 days) 14.5%; EV +$245 per $80 attempt.

## A02 — on real MNQ minute paths (drift removed; costs; stops gapping; neither-hit days)

| one attempt, Tradeify (user's terms) | passive 1 MNQ | **solved, 2 MNQ** | 3 MNQ | 5 MNQ |
|---|---|---|---|---|
| P(pass) | 19% | **23%** | 22% | 19% |
| P(payout within 84 days) | 7% | **8%** | 7% | 7% |
| EV per $80 | +$89 | **+$123** | +$109 | +$85 |
| median days to pass / first payout | ~20 / long | **7 / 12** | 5 / 8 | 5 / 6 |

Real markets erase most of the solver's gain on a single attempt — **but each attempt now resolves in one
to two weeks.**

## A03 — back-to-back attempts for 4 months (the user's window)

A failed account is replaced next day by a new $80 evaluation.

| 84 trading days | passive 1 MNQ (replay) | **solved 2 MNQ (resampled)** | **solved 2 MNQ (real history replayed from every start date)** |
|---|---|---|---|
| P(at least one payout) | 32% | 53% | **61%** |
| median day of first payout | 55 | 36 | 38 |
| attempts (fees) | 6.1 ($487) | 9.8 ($783) | 10.3 ($824) |
| **mean net after fees** | +$84 | +$763 | **+$675** |
| P(net > 0) | 24% | 43% | 45% |
| net 10th / 50th / 90th pct | −$640 / −$400 / +$2,161 | −$1,040 / −$320 / +$4,047 | −$960 / −$229 / +$3,798 |

3 MNQ replayed: −$51 mean net. **2 MNQ is the size.**

## What it is, and is not

- **No market edge.** The gain comes entirely from staking within the rules. It does not depend on
  predicting anything, and nothing here was tuned to the market's direction (drift removed).
- **A positive average with a negative median.** In 4 months a majority get a payout, but slightly fewer
  than half finish net ahead after fees; the average is lifted by the right tail.
- **Assumptions:** Tradeify Select Daily as the user confirmed; $80 per evaluation; $2.32 per MNQ round
  trip; stop fills at the minute bar's low when it gaps; any withdrawal above $52,000 counts as a payout.
- **To check before money:** that Tradeify's terms permit bracket trading of this kind (most firms do; some
  prohibit "gambling-style" behaviour); actual commission; how stops fill in fast markets. **A forward demo
  of the exact policy is the next step.**

## A04 — route 1, a portfolio of parallel accounts (decisions.md §94)

Four lanes that move almost independently (daily correlations +0.02 to +0.08), payouts reinvested,
12 months replayed in real order: **mean net positive (+$2,043 from $800; +$4,230 from $1,600), but
68–84% of runs lose the whole budget.** Each attempt is a long-odds, thin-edge bet (~8% at a ~$1,000–1,500
payout for $80); Kelly sizing wants ~$4,000–8,000 of reserve per concurrent account. **Route 1 does not
scale at zero edge.** The solver stays as the tool for staking a real edge (route 2).

## A05 — real bracket odds (decisions.md §102)

Re-solved with each bracket's real outcome distribution from 2015–2020, tested on 2021–2026: **worse**
(43% payout in 4 months, −$8, against A01's 61%, +$675). The training years were calmer relative to today's
contract value — 57% of brackets ended at the close untouched — so the learned policy fitted the wrong
regime. The fair-odds policy is the robust one.

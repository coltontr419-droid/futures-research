# Autonomous session — 2026-10-20

Running log of leads searched and tests run while the user is away. Leads needing logins/API keys are tabled (listed at the end).
Rules in force: legitimate counterparties only; must start on ~$100-200 and scale far past $2k/month (capacity screened first);
protocol before any price/outcome comparison; strict edge rule (§119) with §133 watchlist; no droplet changes.

## Findings

### 1. Forward evidence for the deployed futures rules and the watchlist (no trial)
- `a48_forward`: 6 rule sessions since deployment (NKD dollar-week, FDXM DAX-dollar): recorded −$1,557; rule minus opposite side
  −$2,006; the §463 review trigger needs 40 sessions — far too early to judge.
- `a49_watchlist` (forward data after the sealed window): 14 of 23 watchlist rules positive (≈ chance). Standout: **D728 MGC fades
  its own 60-day trend (strong days): forward n 28, +35.5 bps, t +3.00**; sibling D727 (all days) t +1.73. With 23 rules tracked one
  t≈3 can be chance → keep watching (the §133 path), not adoption. D659 (MGC follows CNY) t −2.20 — failing forward.

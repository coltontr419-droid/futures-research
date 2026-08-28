# futures-research

MNQ / MGC intraday strategy research. Spec: [`CLAUDE_FUTURES.md`](./CLAUDE_FUTURES.md).
Catalog: [`FUTURES_STRATEGY_HYPOTHESES.md`](./FUTURES_STRATEGY_HYPOTHESES.md).
Registry: [`hypotheses.yaml`](./hypotheses.yaml).

Successor to the crypto research project, which resolved ten hypotheses, promoted zero, and
closed on cost rather than statistics: every measured effect was smaller than an 8 bps
commission floor. **MNQ's floor is 0.48 bps.** That is the reason this repo exists.

## Setup

    python -m venv .venv
    .venv/Scripts/python -m pip install -e ".[dev]"
    .venv/Scripts/python -m pytest -q

`.env` holds the Databento credentials and is gitignored; see `.env.example` for the keys.

## What is here so far

| | |
|---|---|
| `session/calendar.py` | DST-aware session mapper — built first, deliberately |
| `stats/` | trial log, Deflated Sharpe, PBO via CSCV |
| `integrity/` | §7 integrity checks and synthetic generators |
| `signals/stage1.py` | Stage 1 evaluator, including the corrected signed-exposure path |
| `signals/staged.py` | two-instrument staged runner |

**Not built yet:** the downloader, the roll handler, the validators, any hypothesis runner.

## Two things carried over that are NOT yet valid here

Both were measured against crypto's return distribution. Index futures have roughly an order
of magnitude less kurtosis, so both must be **re-measured before any Stage 1 result is
quotable** — see CLAUDE_FUTURES.md §4 and build-order step 8.

- the Stage 1 bootstrap α calibration (`COVERAGE_CALIBRATION` in `signals/stage1.py`)
- the detection floor, 0.1592× one-minute volatility (§7)

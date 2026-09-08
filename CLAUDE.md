# futures-research — working agreements

The research spec is `CLAUDE_FUTURES.md`. This file holds operational rules that apply
regardless of what is being measured.

## Push policy

At the end of every task that modified tracked files: verify no .env, credential, or data/
files are staged, then commit with a descriptive message and push to origin. Report the
commit hash. If the push fails or the remote has diverged, say so plainly — never force-push.

### Notes specific to this repo

**There is currently no `origin`.** As of 2026-09-08 no GitHub repository exists for this
project — an authenticated listing of the account returned only `r-series-research`,
`polymarket-diagnostic` and `polymarket-tracker`. Until a remote is created the commit half
of this policy applies and the push half cannot; say so rather than reporting a push that
did not happen.

**What must never be staged here.** `.gitignore` already covers all of it, but the policy
above is the second line of defence, not the first:

- `.env` — carries the Databento FTP credentials. History is not practically deletable once
  pushed.
- `data/` — 548 MB of GLBX.MDP3 extracts across `raw/`, `parquet/` and `continuous/`.
  Reproducible from the vendor, so it is regenerable rather than precious.

**What must always be committed.** `trials.jsonl` and `measurements.jsonl` are *not* data.
They are the append-only record of what has been spent against the multiple-testing budget,
and N is unverifiable without them. `trials.superseded-2026-09-02.jsonl` is the pre-migration
archive and is kept for the same reason. See `CLAUDE_FUTURES.md` §6 and
`reports/decisions.md` §16.

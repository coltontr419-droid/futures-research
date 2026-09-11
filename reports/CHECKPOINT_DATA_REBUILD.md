# Checkpoint — data rebuild, 2026-09-10

Written at a hard stop. **Read this before running anything in `data/`.**

## Where it stands

The laptop had no market data at all; `data/` is gitignored by design and the continuous
series existed only on the Windows PC. This rebuilds them from the Databento batch.

| step | status |
|---|---|
| FTP fetch | **DONE** — 806/806 files `[verified]` against the manifest, 216 MB |
| `parse` | **DONE** — 211 outrights, 672 spreads, 0 unrecognised, 166 MB |
| `roll` MNQ | **DONE** — 29 rolls / 1,893 sessions / 0 contested → 2,540,069 bars |
| `roll` MGC | **DONE** — 80 rolls / 4,093 sessions / **196 contested** → 3,547,109 bars |
| `roll` NQ | **FAILING — OOM, twice. This is the blocker.** |
| `splice` | not started; needs NQ |
| `level_rates` (L11) | not started; needs the spliced series |
| L02/L03/L04 Stage 1 | not started |

**`data/continuous/MGC.parquet` and `MNQ.parquet` exist and are good.**
**`NQ.parquet` does not exist, so `NQ_MNQ_spliced.parquet` cannot be built.**

`parse` REPRODUCED `reports/batch_contents.md` BYTE-IDENTICALLY. That is the strongest
evidence available that the rebuilt raw data is the same input the original run used, so
anything derived from it is comparable to the committed reports.

## The blocker, precisely

NQ is the largest product: 5,971,960 bars, 71 outright contracts. Its roll CALENDAR builds
fine every time — `65 rolls over 4,190 sessions, 0 contested`, printed before the kill. The
kill is in the WRITE.

Two OOM kills, both kernel-confirmed via dmesg:

```
Out of memory: Killed process 12486 (python) total-vm:4786716kB, anon-rss:879560kB
Out of memory: Killed process 17235 (python) total-vm:3247772kB, anon-rss:823896kB
```

The machine has 2.7 GB total and ~1.1 GB available. Both kills land near 820-880 MB RSS.

### What was already tried, and did not work

1. **Per-product processes.** `--products MNQ` alone still OOMed on the ORIGINAL eager path
   at 826 MB, even though MNQ is the SMALLEST product. Isolation is not the issue.
2. **The streaming rewrite** (`scan_product`, `daily_volume_streaming`, `sink_continuous`).
   This FIXED MNQ and MGC — both now complete comfortably. NQ still dies.
3. **`engine="streaming"` named explicitly** on `sink_parquet`, plus `POLARS_MAX_THREADS=2`.
   The default is `engine="auto"`, which had been choosing the in-memory path. Naming it did
   NOT save NQ. **This was the last thing tried and it is unverified as an improvement** —
   it may have helped and still not been enough, or done nothing. MNQ and MGC were written
   BEFORE this change, so they are not evidence either way.

### What to try next, in order

1. **Eliminate the global `.sort("ts_event")`.** It is the obvious remaining hog and it is
   avoidable: the front month advances monotonically and exactly one contract is front per
   session, so contract slices in expiry order are ALREADY in timestamp order. Write each
   contract's front-month slice in expiry order and concatenate, sorting only within a
   slice. This changes how the order is achieved, not what it is - and a test must pin the
   result identical to the eager `continuous_series` on a fixture.
2. **`POLARS_MAX_THREADS=1`** and a smaller `sink_parquet` row-group size.
3. **Split NQ by date range**, write two parquets, concatenate lazily.

### Do NOT

- Do not "fix" this by dropping NQ. The spliced series exists precisely so index hypotheses
  get sixteen years instead of seven (`CLAUDE_FUTURES.md` §3); MNQ alone starts 2019-05-06.
- Do not back-adjust or stitch across the join to make the data smaller.

## Uncommitted state — NONE. Everything below is pushed.

Working tree clean at the commit that carries this file.

**The DATA is not in git and never will be** (`/data/` is gitignored, correctly). If this
machine is wiped, the 216 MB batch must be re-fetched. It is cheap: ~5 minutes, and the
loader is idempotent, so re-running costs nothing for files already present.

## Credentials

`.env` was written this session with working Databento FTP credentials, `chmod 600`,
confirmed gitignored at `.gitignore:3` and invisible to `git status`. **The user stated they
would reset these credentials afterwards**, so assume `.env` is STALE and ask rather than
debugging a login failure.

Batch job: `GLBX-20260828-BGTLBSWWFV` at `/93SVXHJF/` on `ftp.databento.com` — MNQ, NQ, MGC,
`ohlcv-1m`, csv, 2010-06-06 to 2026-08-27. A second batch `GLBX-20260909-3YHRELQ8JL` holds
MES and is not needed here.

## Two defects found and NOT yet fixed

1. **`batch_ftp` raises on this batch after downloading it successfully.** Its identity
   check requires a `definition` schema or `symbology.json`; this batch ships neither. But
   every CSV row carries its `symbol` in the last column (`map_symbols: true`), which is the
   identity source `parse.py` is written against and documents at length. The check does not
   know about that third source. **It fails SAFE** — it refuses rather than proceeding
   wrongly — and the data it had already fetched was complete and verified, so this did not
   block the rebuild. It will stop the next person who fetches a CSV `map_symbols` batch.
   Same shape as r-series D5.
2. **MGC has 196 contested sessions** against 0 for MNQ and 0 for NQ. Contested means the
   raw volume argmax flipped back to the expiring contract and the monotonic guard held the
   front where it was. That is the guard working as designed, not a defect - but 196 is not
   a rounding error and it belongs in the write-up rather than passed over silently.

## What this unblocks when NQ lands

`splice` → `level_rates` (~64 min, picks up L11's firing rate and placebo match) → L02/L03/
L04 Stage 1 on MGC at H=180, 72 trials, N 684 → 756, SR\* 0.1356 → 0.1368. Then the L-series
closes. See `decisions.md` §39 and the L-series closeout plan.

**`level_rates` is the next thing sized for hardware we do not have** (~64 min, peaks near
1 GB on the PC). Expect it to need the same treatment as `roll` did.

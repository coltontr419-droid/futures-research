"""Backfill trials that were spent before the log was wired in.

    python -m futuresres.reporting.backfill

WHAT IS BEING REPAIRED. `stats/trials.py` existed, its tests passed, and no runner called
it. F03, F04 and F07 ran and their per-cell results were written to `reports/f*_cells.json`
while the append-only log stayed empty. This reconstructs those records from the output
files so N has a verifiable source.

RECONSTRUCTED RECORDS ARE WEAKER THAN NATIVE ONES AND ARE MARKED SO. Their timestamps are
this backfill's, not the run's. Their ordering within a run is whatever the output file
happens to hold. And nothing proves the output file was not edited between the run and now —
which is precisely the property an append-only hash chain exists to provide and which these
records, by construction, cannot have. They count toward N because a look at the data is a
look at the data. They do not count as evidence that the log was being kept.

WHY FIRING-RATE MEASUREMENTS GO IN A SEPARATE LOG. `reports/firing_rates.json` holds 102
rows, and it is tempting to append them here so that everything lives in one file. That
would be wrong. N exists to deflate a Sharpe for the number of chances a candidate had to
look good by accident, and a firing-rate measurement has no Sharpe and could never produce a
candidate: it counts how often a condition triggers, computing no return series at all.
Adding those rows would raise SR* — making the bar stricter, which sounds safe, but a bar
set by a category error is not conservative, it is just wrong. They are chained into
`measurements.jsonl` instead, with the same machinery and the same guarantees, and
`catalog_status.md` reports both counts separately. Recorded in `reports/decisions.md` §16.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Final

from futuresres.signals.logged_run import Recorder
from futuresres.stats.trials import Trial, TrialLog

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
REPORTS: Final[Path] = ROOT / "reports"
TRIAL_LOG: Final[Path] = ROOT / "trials.jsonl"
MEASUREMENT_LOG: Final[Path] = ROOT / "measurements.jsonl"

DATE_RANGE: Final[tuple[str, str]] = ("2010-01-01", "2026-08-28")

#: When each run actually happened, for the note. The record's own timestamp is this
#: backfill's and cannot be anything else.
RUN_DATES: Final[dict[str, str]] = {
    "F03": "2026-09-01", "F04": "2026-09-01", "F07": "2026-09-02",
}


def backfill_trials(log: TrialLog, only: set[str] | None = None) -> dict[str, int]:
    written: dict[str, int] = {}
    already = {t.hypothesis_id for t in log.read_all()}
    for path in sorted(REPORTS.glob("f*_cells.json")):
        hid = path.stem.split("_")[0].upper()
        if only and hid not in only:
            continue
        if hid in already:
            print(f"  {hid}: already in the log, skipping")
            continue
        cells = json.loads(path.read_text(encoding="utf-8"))
        rec = Recorder(
            hid, log, "reconstructed", DATE_RANGE,
            note=f"backfilled from {path.name}; run {RUN_DATES.get(hid, 'unknown')}; "
                 f"timestamps are the backfill's, not the run's",
        )
        rec.record(cells)
        written[hid] = rec.written
        print(f"  {hid}: {rec.written} trials reconstructed from {path.name}")
    return written


def backfill_measurements(log: TrialLog) -> int:
    path = REPORTS / "firing_rates.json"
    if not path.exists():
        return 0
    if len(log) > 0:
        print("  measurements: already logged, skipping")
        return 0
    rows = json.loads(path.read_text(encoding="utf-8"))
    for row in rows:
        log.append(Trial(
            trial_id=log.next_id("m"),
            hypothesis_id=row["hypothesis"],
            params={"cell": row["cell"], "horizon": row["horizon"]},
            symbol=row["product"],
            date_range=DATE_RANGE,
            status="completed",
            sharpe=None,
            trade_count=row["independent"],
            note=("provenance=reconstructed; kind=measurement; NOT a trial and NOT counted "
                  "in N - counts condition firings, computes no return series and could "
                  f"never produce a candidate; firings={row['firings']}; {row['note'][:120]}"),
        ))
    print(f"  measurements: {len(rows)} firing-rate rows chained into {log.path.name}")
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.reporting.backfill")
    ap.add_argument("--only", nargs="*", help="restrict to these hypothesis ids")
    args = ap.parse_args(argv)

    trials = TrialLog(TRIAL_LOG)
    print(f"trial log holds {len(trials)} records before backfill")
    written = backfill_trials(trials, set(args.only) if args.only else None)

    measurements = TrialLog(MEASUREMENT_LOG)
    n_meas = backfill_measurements(measurements)

    print(f"\ntrials.jsonl:       {len(trials)} records "
          f"(+{sum(written.values())} this run), chain "
          f"{'OK' if trials.verify_chain().ok else 'BROKEN'}")
    print(f"measurements.jsonl: {len(measurements)} records (+{n_meas} this run), chain "
          f"{'OK' if measurements.verify_chain().ok else 'BROKEN'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

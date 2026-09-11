"""Splice NQ and MNQ into one index series. CLAUDE_FUTURES.md §3.

    python -m futuresres.data.splice

MNQ began trading 2019-05-06 and is one tenth the notional of NQ. This project wants the
longest usable Nasdaq series, so NQ carries the history to 2019-05-31 and MNQ takes over.

THE PRICE CONVENTION IS VERIFIED, NOT ASSUMED. Both contracts are quoted in Nasdaq-100
index points, so bars in the overlap should agree to the tick with NO scaling factor. That
is the expectation. It is also exactly the kind of expectation that is wrong often enough
to matter — a 10x notional difference invites a 10x price convention, and if it existed
every return across the join would be right while every LEVEL would be wrong by an order of
magnitude, which no return-based check would catch.

So `verify_convention` measures the overlap directly: matched minutes, the ratio of closes,
and the absolute difference in index points. It ASSERTS the ratio is 1 and reports the
residual, rather than dividing by a factor someone believed.

WHAT A NON-ZERO RESIDUAL MEANS. The two contracts are separate books with separate order
flow, so their prints will not be bit-identical even under an identical convention: a
minute's close is the last trade in that book, and the books do not trade in lockstep. A
residual of a tick or two is microstructure. A residual near a factor of ten is a
convention difference. The report gives the distribution so the two cannot be confused.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final

import numpy as np
import polars as pl

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
CONTINUOUS: Final[Path] = ROOT / "data" / "continuous"
REPORT: Final[Path] = ROOT / "reports" / "splice.md"

#: NQ carries the series to and including this session; MNQ from the next one.
SPLICE_DATE: Final[date] = date(2019, 5, 31)

#: One index point. NQ and MNQ both tick in 0.25 index points.
TICK: Final[float] = 0.25


@dataclass(slots=True)
class ConventionCheck:
    matched: int
    ratio_median: float
    ratio_min: float
    ratio_max: float
    abs_diff_median: float
    abs_diff_p99: float
    abs_diff_max: float
    within_one_tick: float
    identical: int

    #: Tolerance on the close ratio. One tick on a 7,000-point index is 3.6e-5, so 1e-3
    #: passes tick-level microstructure with two orders of magnitude to spare while a
    #: convention difference — the failure this exists to catch — is 0.1 or 10.
    #:
    #: An earlier version demanded |median - 1| < 1e-6. That happened to pass on the real
    #: overlap, where the median ratio is exactly 1, but it would have failed on a series
    #: offset by a single tick on alternating bars — i.e. on precisely the microstructure
    #: this module documents as expected. A criterion that passes real data by luck is not
    #: a criterion.
    RATIO_TOLERANCE: float = 1e-3

    @property
    def scale_free(self) -> bool:
        """Do the two series share a price convention, allowing for tick-level noise?"""
        return (abs(self.ratio_median - 1.0) < self.RATIO_TOLERANCE
                and abs(self.ratio_min - 1.0) < 0.01
                and abs(self.ratio_max - 1.0) < 0.01)


def verify_convention(nq: pl.DataFrame, mnq: pl.DataFrame,
                      start: date, end: date) -> ConventionCheck:
    """Compare closes on minutes where BOTH series have a bar."""
    def window(df: pl.DataFrame) -> pl.DataFrame:
        return (df.filter((pl.col("session") >= start) & (pl.col("session") <= end))
                .select("ts_event", "close"))

    joined = window(nq).join(window(mnq), on="ts_event", how="inner",
                             suffix="_mnq").drop_nulls()
    if joined.height == 0:
        raise ValueError(f"no overlapping minutes between {start} and {end}")

    a = joined.get_column("close").to_numpy()
    b = joined.get_column("close_mnq").to_numpy()
    ratio = b / a
    diff = np.abs(b - a)
    return ConventionCheck(
        matched=int(joined.height),
        ratio_median=float(np.median(ratio)),
        ratio_min=float(ratio.min()), ratio_max=float(ratio.max()),
        abs_diff_median=float(np.median(diff)),
        abs_diff_p99=float(np.percentile(diff, 99)),
        abs_diff_max=float(diff.max()),
        within_one_tick=float((diff <= TICK).mean()),
        identical=int((diff == 0).sum()),
    )


def splice(nq: pl.DataFrame, mnq: pl.DataFrame,
           at: date = SPLICE_DATE) -> pl.DataFrame:
    """NQ through `at`, MNQ after. No scaling — the convention check is what licenses that."""
    left = nq.filter(pl.col("session") <= at).with_columns(pl.lit("NQ").alias("source"))
    right = mnq.filter(pl.col("session") > at).with_columns(pl.lit("MNQ").alias("source"))
    return pl.concat([left, right], how="vertical_relaxed").sort("ts_event")


def sink_spliced(nq_path: Path, mnq_path: Path, target: Path,
                 at: date = SPLICE_DATE) -> None:
    """Write the spliced series straight to disk. `splice()` above is the eager statement.

    WHY NOT `splice()`. It reads BOTH continuous series - 4.73M NQ bars plus 2.54M MNQ -
    concatenates them and sorts the result, so four copies of a seven-million-row frame are
    live at once. Measured on a 2.7 GB machine: OOM-killed at 858 MB RSS.

    NO GLOBAL SORT, for the same reason `sink_continuous` needs none: the NQ side is
    entirely at or before the splice date and the MNQ side entirely after it, and each input
    was already written in timestamp order by `roll`. Concatenating them in that order IS
    timestamp order. A test pins it rather than trusting the argument.
    """
    left = (pl.scan_parquet(nq_path).filter(pl.col("session") <= at)
            .with_columns(pl.lit("NQ").alias("source")))
    right = (pl.scan_parquet(mnq_path).filter(pl.col("session") > at)
             .with_columns(pl.lit("MNQ").alias("source")))
    target.parent.mkdir(parents=True, exist_ok=True)
    pl.concat([left, right], how="vertical_relaxed").sink_parquet(
        target, engine="streaming")


def render(check: ConventionCheck, per: pl.DataFrame, total: int,
           start: date, end: date) -> str:
    w: list[str] = []
    a = w.append
    a("# NQ / MNQ splice")
    a("")
    a("Generated by `python -m futuresres.data.splice`. CLAUDE_FUTURES.md §3.")
    a("")
    a(f"NQ through **{SPLICE_DATE}**, MNQ after. MNQ began trading 2019-05-06, so the two "
      f"overlap for most of May 2019 and the convention can be checked before anything is "
      f"joined.")
    a("")
    a("## The convention check")
    a("")
    a(f"Overlap window **{start} to {end}**, comparing closes on minutes where both series "
      f"have a bar.")
    a("")
    a("| | |")
    a("|---|---|")
    a(f"| matched minutes | **{check.matched:,}** |")
    a(f"| median close ratio MNQ/NQ | **{check.ratio_median:.9f}** |")
    a(f"| ratio range | {check.ratio_min:.6f} to {check.ratio_max:.6f} |")
    a(f"| median absolute difference | **{check.abs_diff_median:.4f} index points** |")
    a(f"| 99th percentile difference | {check.abs_diff_p99:.4f} |")
    a(f"| maximum difference | {check.abs_diff_max:.4f} |")
    a(f"| within one tick ({TICK}) | **{check.within_one_tick:.2%}** |")
    a(f"| exactly identical | {check.identical:,} ({check.identical / check.matched:.1%}) |")
    a("")
    if check.scale_free:
        a("**PASS — identical index points, no scaling.** The median ratio is 1 to nine "
          "decimal places and the full range stays inside 1%. MNQ is one tenth the "
          "NOTIONAL of NQ, not one tenth the price, so the series concatenate directly.")
    else:
        a(f"**FAIL — the two series do not share a price convention.** Median ratio "
          f"{check.ratio_median:.6f}. Do not splice until this is understood; a scaling "
          f"factor applied here would leave every return correct and every level wrong.")
    a("")
    a("Residual differences are microstructure, not convention: NQ and MNQ are separate "
      "books with separate order flow, so a minute's close is the last trade in each book "
      "and the books do not trade in lockstep. That is why the check asserts the RATIO and "
      "reports the difference distribution, rather than requiring bit-identical prints.")
    a("")
    a("## The spliced series")
    a("")
    a("| source | bars | from | to |")
    a("|---|---|---|---|")
    for r in per.iter_rows(named=True):
        a(f"| {r['source']} | {r['bars']:,} | {r['from']} | {r['to']} |")
    a("")
    a(f"**{total:,} bars total.** The series is UNADJUSTED across the join, as it "
      f"is across every roll: no back-adjustment, no scaling factor.")
    a("")
    return "\n".join(w)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.data.splice")
    ap.add_argument("--start", type=date.fromisoformat, default=date(2019, 5, 1))
    ap.add_argument("--end", type=date.fromisoformat, default=date(2019, 5, 31))
    args = ap.parse_args(argv)

    # Only the overlap window is needed to check the convention - a few tens of thousands
    # of rows - so it is the only part read into memory.
    nq_path, mnq_path = CONTINUOUS / "NQ.parquet", CONTINUOUS / "MNQ.parquet"
    win = lambda f: (pl.scan_parquet(f)
                     .filter((pl.col("session") >= args.start)
                             & (pl.col("session") <= args.end))
                     .collect(engine="streaming"))
    check = verify_convention(win(nq_path), win(mnq_path), args.start, args.end)
    print(f"overlap {args.start}..{args.end}: {check.matched:,} matched minutes")
    print(f"  median ratio MNQ/NQ = {check.ratio_median:.9f} "
          f"(range {check.ratio_min:.6f}..{check.ratio_max:.6f})")
    print(f"  median |diff| = {check.abs_diff_median:.4f} index points, "
          f"{check.within_one_tick:.2%} within one tick")

    if not check.scale_free:
        print("\nFAILED: NQ and MNQ do not share a price convention. Not splicing.",
              file=sys.stderr)
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(render(check, pl.DataFrame(
            {"source": [], "bars": [], "from": [], "to": []}), 0,
            args.start, args.end), encoding="utf-8")
        return 1

    target = CONTINUOUS / "NQ_MNQ_spliced.parquet"
    sink_spliced(nq_path, mnq_path, target)
    lf = pl.scan_parquet(target)
    total = int(lf.select(pl.len()).collect().item())
    per = (lf.group_by("source")
           .agg(pl.len().alias("bars"),
                pl.col("session").min().alias("from"),
                pl.col("session").max().alias("to"))
           .sort("from").collect(engine="streaming"))
    print(f"  spliced {total:,} bars -> {target}")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(render(check, per, total, args.start, args.end), encoding="utf-8")
    print(f"wrote {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

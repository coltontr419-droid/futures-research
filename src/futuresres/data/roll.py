"""Front-month determination and the roll calendar. CLAUDE_FUTURES.md §3.

    python -m futuresres.data.roll

THE RULE, from §3, and none of the three clauses is optional.

  1. FRONT MONTH BY VOLUME CROSSOVER. The front contract is whichever has the most volume on
     a given trading day. When the next expiry's daily volume first exceeds the current
     front's, that day is the roll.
  2. UNADJUSTED, PER CONTRACT. Nothing is back-adjusted. A back-adjusted series shifts
     historical prices by accumulated roll gaps, which corrupts every level-based condition
     (a round number, a prior day's high) and changes what a percentage return means.
  3. THE CROSSOVER SESSION IS DROPPED ENTIRELY. Not stitched, not interpolated — removed.
     On that session liquidity sits in both contracts at different prices, so any return
     computed across the join is an artifact of the join. Dropping one session per roll
     costs ~64 sessions over sixteen years and removes an entire class of phantom result.

THE ROLL IS MONOTONIC BY CONSTRUCTION. Daily volume is noisy near a roll and the raw argmax
can flip back to the expiring contract for a session. A continuous series that rolls forward
and then backward would double-count a price gap, so once the front has advanced it never
returns — and any session where the raw argmax disagrees is recorded as a `contested`
session rather than silently smoothed away.

SESSIONS ARE CME TRADING DAYS, NOT CALENDAR DAYS. The trading day runs 18:00 ET to 17:00 ET,
so the Sunday-evening open belongs to Monday's session. `session.calendar.cme_trading_day`
is the single source of that mapping; deriving it here from a UTC date would put every
overnight bar in the wrong session and shift every roll by a day.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Final

import polars as pl

from futuresres.data.parse import MONTH_NUMBER
from futuresres.session.calendar import ET

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
DEFAULT_PARQUET: Final[Path] = ROOT / "data" / "parquet"
REPORT: Final[Path] = ROOT / "reports" / "roll_calendar.md"


@dataclass(frozen=True, slots=True)
class Roll:
    """One front-month transition."""

    session: date
    from_contract: str
    to_contract: str
    from_volume: int
    to_volume: int

    @property
    def margin(self) -> float:
        total = self.from_volume + self.to_volume
        return (self.to_volume - self.from_volume) / total if total else 0.0


@dataclass(slots=True)
class RollCalendar:
    product: str
    rolls: list[Roll] = field(default_factory=list)
    front_by_session: dict[date, str] = field(default_factory=dict)
    contested: list[date] = field(default_factory=list)
    sessions: int = 0

    @property
    def dropped_sessions(self) -> set[date]:
        return {r.session for r in self.rolls}


def expiry_key(contract: str) -> tuple[int, int]:
    """(year, month number) from a canonical code like `NQZ2015`. Sort order for expiries."""
    year = int(contract[-4:])
    month = contract[-5]
    return year, MONTH_NUMBER[month]


def add_session(bars: pl.DataFrame) -> pl.DataFrame:
    """Attach the CME trading day. 18:00 ET or later belongs to the NEXT session."""
    local = pl.col("ts_event").dt.convert_time_zone(str(ET))
    return bars.with_columns(
        pl.when(local.dt.hour() >= 18)
        .then(local.dt.date() + pl.duration(days=1))
        .otherwise(local.dt.date())
        .alias("session")
    )


def daily_volume(bars: pl.DataFrame) -> pl.DataFrame:
    """(session, contract, volume, bars) per trading day."""
    return (
        add_session(bars)
        .group_by(["session", "contract"])
        .agg(pl.col("volume").sum().alias("volume"), pl.len().alias("bars"))
        .sort(["session", "volume"], descending=[False, True])
    )


def build_calendar(product: str, volumes: pl.DataFrame) -> RollCalendar:
    """Walk the sessions in order, advancing the front month on a volume crossover."""
    cal = RollCalendar(product=product)
    front: str | None = None
    front_rank: tuple[int, int] | None = None

    for (session,), day in volumes.group_by(["session"], maintain_order=True):
        day = day.sort("volume", descending=True)
        rows = list(day.iter_rows(named=True))
        if not rows:
            continue
        cal.sessions += 1
        leader = rows[0]["contract"]
        leader_rank = expiry_key(leader)

        if front is None:
            front, front_rank = leader, leader_rank
            cal.front_by_session[session] = front
            continue

        if leader == front:
            cal.front_by_session[session] = front
            continue

        # The raw argmax disagrees with the current front. Only advance — never go back to
        # an earlier expiry, which would re-cross a price gap already crossed.
        if leader_rank > front_rank:
            from_vol = next((r["volume"] for r in rows if r["contract"] == front), 0)
            cal.rolls.append(Roll(session=session, from_contract=front,
                                  to_contract=leader,
                                  from_volume=int(from_vol),
                                  to_volume=int(rows[0]["volume"])))
            front, front_rank = leader, leader_rank
        else:
            cal.contested.append(session)
        cal.front_by_session[session] = front
    return cal


def continuous_series(bars: pl.DataFrame, cal: RollCalendar) -> pl.DataFrame:
    """The front-month series: unadjusted, per contract, crossover sessions removed."""
    sessioned = add_session(bars)
    front = pl.DataFrame({
        "session": list(cal.front_by_session),
        "front": list(cal.front_by_session.values()),
    }).with_columns(pl.col("session").cast(sessioned.schema["session"]))
    joined = sessioned.join(front, on="session", how="inner")
    dropped = list(cal.dropped_sessions)
    return (
        joined.filter(pl.col("contract") == pl.col("front"))
        .filter(~pl.col("session").is_in(dropped))
        .drop("front")
        .sort("ts_event")
    )


# ── streaming path ───────────────────────────────────────────────────────────
# WHY THIS EXISTS. The eager path below reads every contract of a product, concatenates
# them, then joins, filters and SORTS - so up to four copies of a multi-million-row frame
# are live at once. On a 2.7 GB machine that is an OOM kill, measured: MNQ, the SMALLEST
# product at 3.86M bars, was killed by the kernel at 826 MB RSS (exit 137).
#
# The eager functions are KEPT AND STILL TESTED. They are the readable statement of what
# the roll IS, and the streaming versions below must agree with them bar for bar - a test
# pins that on a small fixture. This is a change to HOW the series is computed and to
# nothing about WHAT it is.


def scan_product(parquet: Path, product: str) -> pl.LazyFrame:
    """Every contract of one product, unmaterialised."""
    root = parquet / f"symbol={product}"
    if not any(root.glob("contract=*/bars.parquet")):
        raise FileNotFoundError(f"no parquet for {product} under {parquet}")
    return pl.scan_parquet(root / "contract=*/bars.parquet")


def daily_volume_streaming(parquet: Path, product: str) -> pl.DataFrame:
    """(session, contract, volume, bars) per trading day, without loading the bars.

    The result is one row per (session, contract) - a few thousand rows - so it is safe to
    materialise. It is the whole input `build_calendar` needs.
    """
    return (
        add_session(scan_product(parquet, product))
        .group_by(["session", "contract"])
        .agg(pl.col("volume").sum().alias("volume"), pl.len().alias("bars"))
        .sort(["session", "volume"], descending=[False, True])
        .collect(engine="streaming")
    )


def sink_continuous(parquet: Path, product: str, cal: RollCalendar,
                    target: Path) -> None:
    """Write the front-month series straight to disk, never holding it in memory.

    Identical semantics to `continuous_series`: keep only the front contract's bars for each
    session, drop the crossover sessions entirely, output ordered by timestamp.

    NO GLOBAL SORT, AND THAT IS THE POINT. A `.sort("ts_event")` over the whole product was
    the last thing holding NQ (5.97M bars) in memory, and it was OOM-killed twice at ~880 MB
    even with `engine="streaming"`. The sort is AVOIDABLE rather than merely expensive:

      * the front month advances MONOTONICALLY (`build_calendar` never goes back), so each
        contract is front for one CONTIGUOUS run of sessions;
      * exactly one contract is front per session, so the runs do not overlap;
      * sessions are CME trading days, so every bar of session N precedes every bar of N+1.

    Therefore concatenating the contracts in EXPIRY ORDER, each sorted within itself, is the
    same ordering a global sort produces - and each per-contract sort is a few tens of
    thousands of rows instead of millions. `test_streaming_roll_matches_eager` pins the two
    against each other rather than leaving that argument untested.
    """
    dropped = cal.dropped_sessions
    by_contract: dict[str, list] = {}
    for session, contract in cal.front_by_session.items():
        if session not in dropped:
            by_contract.setdefault(contract, []).append(session)

    parts: list[pl.LazyFrame] = []
    for contract in sorted(by_contract, key=expiry_key):
        f = parquet / f"symbol={product}" / f"contract={contract}" / "bars.parquet"
        if not f.exists():
            continue
        parts.append(
            add_session(pl.scan_parquet(f))
            .filter(pl.col("session").is_in(by_contract[contract]))
            .sort("ts_event")
        )
    if not parts:
        raise FileNotFoundError(f"no front-month contracts found for {product}")

    target.parent.mkdir(parents=True, exist_ok=True)
    pl.concat(parts, how="vertical").sink_parquet(target, engine="streaming")


def load_product(parquet: Path, product: str) -> pl.DataFrame:
    files = sorted((parquet / f"symbol={product}").glob("contract=*/bars.parquet"))
    if not files:
        raise FileNotFoundError(f"no parquet for {product} under {parquet}")
    return pl.concat([pl.read_parquet(f) for f in files], how="vertical_relaxed")


def render_report(calendars: dict[str, RollCalendar]) -> str:
    w: list[str] = []
    a = w.append
    a("# Roll calendar")
    a("")
    a("Generated by `python -m futuresres.data.roll`. CLAUDE_FUTURES.md §3.")
    a("")
    a("Front month by **volume crossover**, series **unadjusted per contract**, and the "
      "**crossover session dropped entirely** — not stitched. Sessions are CME trading days "
      "(18:00 ET to 17:00 ET), so the Sunday-evening open belongs to Monday.")
    a("")
    for product, cal in sorted(calendars.items()):
        a(f"## {product}")
        a("")
        a(f"- **{len(cal.rolls)} rolls** across {cal.sessions:,} sessions")
        a(f"- **{len(cal.dropped_sessions)} sessions dropped** at the crossovers")
        a(f"- {len(cal.contested)} contested sessions (raw volume leader was an EARLIER "
          f"expiry than the established front; the front was held rather than moved back)")
        a("")
        if cal.rolls:
            gaps = [
                (cal.rolls[i + 1].session - cal.rolls[i].session).days
                for i in range(len(cal.rolls) - 1)
            ]
            if gaps:
                a(f"- roll spacing: min {min(gaps)}d, median "
                  f"{sorted(gaps)[len(gaps) // 2]}d, max {max(gaps)}d")
            a("")
        a("| session | from | to | volume out | volume in | margin |")
        a("|---|---|---|---|---|---|")
        for r in cal.rolls:
            a(f"| {r.session} | {r.from_contract} | {r.to_contract} | "
              f"{r.from_volume:,} | {r.to_volume:,} | {r.margin:+.1%} |")
        a("")
        if cal.contested:
            a(f"<details><summary>{len(cal.contested)} contested sessions</summary>")
            a("")
            a(", ".join(str(d) for d in cal.contested[:60]))
            if len(cal.contested) > 60:
                a(f" ... and {len(cal.contested) - 60} more")
            a("")
            a("</details>")
            a("")
    return "\n".join(w)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.data.roll")
    ap.add_argument("--parquet", type=Path, default=DEFAULT_PARQUET)
    ap.add_argument("--products", nargs="*", default=["MNQ", "NQ", "MGC"])
    ap.add_argument("--write-continuous", action="store_true")
    args = ap.parse_args(argv)

    calendars: dict[str, RollCalendar] = {}
    for product in args.products:
        # STREAMING, NOT EAGER - see the note above `scan_product`. The eager path holds
        # four copies of the frame and is an OOM kill on a small machine.
        vol = daily_volume_streaming(args.parquet, product)
        cal = build_calendar(product, vol)
        calendars[product] = cal
        print(f"{product}: {len(cal.rolls)} rolls over {cal.sessions:,} sessions, "
              f"{len(cal.contested)} contested", flush=True)
        if args.write_continuous:
            target = args.parquet.parent / "continuous" / f"{product}.parquet"
            sink_continuous(args.parquet, product, cal, target)
            n = pl.scan_parquet(target).select(pl.len()).collect().item()
            print(f"  wrote {target} ({n:,} bars)", flush=True)

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(render_report(calendars), encoding="utf-8")
    print(f"wrote {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

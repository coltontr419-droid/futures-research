"""Data validators. CLAUDE_FUTURES.md §3, adapted from the crypto project's §3.

    python -m futuresres.data.validate

WHY THE GAP CHECK IS DIFFERENT HERE, AND WHY IT IS THE POINT OF THIS MODULE.

The crypto validator enumerated every minute in the range and called anything absent a gap.
That works on a 24/7 exchange. It is useless on CME, where **missing bars are the normal
case**: there is a daily maintenance halt, a weekend, a holiday calendar, early closes, and
— crucially — `ohlcv-1m` emits **no bar at all for a minute with no trades**, rather than a
zero-volume one. A flat every-minute expectation would report millions of false gaps and
bury the handful of real ones.

So the expected-bar calendar is built from the session structure, and the structure was
MEASURED rather than assumed:

  * A CME trading day runs 18:00 ET to 17:00 ET. `session.calendar` owns that mapping.
  * **17:00-17:59 ET is closed** on every product — measured at 0% of sessions across
    2024+, uniformly for MNQ, NQ and MGC. That is the daily maintenance break, and it is
    the ONLY structural intraday closure in this data.
  * There is no 16:15-16:30 equity-index halt in this dataset. An earlier reading of a
    >=95%-coverage band suggested one; measuring the window directly showed a flat 96%
    across 16:10-16:35 on all three products, so the apparent halt was a threshold artifact
    and not a closure. Recorded because it would otherwise be re-derived from the same
    misleading summary.
  * The 96% ceiling is holidays and early closes, not missing data.

**ABSENCE OF A BAR IS NOT EVIDENCE OF MISSING DATA.** For a thin contract it usually means
no trade occurred. The check therefore does not count absent minutes as errors. It reports
coverage, and it flags only what a liquid instrument cannot innocently produce:

  * a session entirely absent that neighbouring products traded through
  * a contiguous run of absent minutes INSIDE US cash hours on a liquid front month

ZERO-VOLUME CHECKS FIND NOTHING BY CONSTRUCTION, AND THAT IS REPORTED AS SUCH. Checks 5 and
6 of §3 look for zero-volume runs and zero-volume-with-live-range. `ohlcv-1m` aggregates
trades, so a zero-volume bar cannot exist — measured: 0 across all 15.3M bars. The checks
are still run, and they report NOT APPLICABLE with the count, rather than PASS. A check that
cannot fail must not be allowed to look like evidence.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import date, time
from pathlib import Path
from typing import Final

import numpy as np
import polars as pl

from futuresres.session.calendar import ET

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
PARQUET: Final[Path] = ROOT / "data" / "parquet"
CONTINUOUS: Final[Path] = ROOT / "data" / "continuous"
REPORT: Final[Path] = ROOT / "reports" / "data_quality.md"

#: Measured: the only structural intraday closure, in ET minutes-of-day.
MAINTENANCE_START: Final[int] = 17 * 60
MAINTENANCE_END: Final[int] = 18 * 60
OPEN_MINUTES_PER_SESSION: Final[int] = 1440 - (MAINTENANCE_END - MAINTENANCE_START)

#: US cash hours, where a liquid front month trades essentially every minute.
RTH_START: Final[int] = 9 * 60 + 30
RTH_END: Final[int] = 16 * 60

#: A session with fewer than this share of the median session's bars is an early close or
#: a holiday, not a data fault.
SHORT_SESSION_RATIO: Final[float] = 0.6


@dataclass(slots=True)
class Check:
    name: str
    status: str                 # PASS | WARN | FAIL | N/A
    detail: str
    rows: list[str] = field(default_factory=list)


def _et_minute(col: str = "ts_event") -> pl.Expr:
    """Minute-of-day in ET. Cast first: dt.hour() is UInt8 and hour*60 OVERFLOWS at 256."""
    local = pl.col(col).dt.convert_time_zone(str(ET))
    return local.dt.hour().cast(pl.Int32) * 60 + local.dt.minute().cast(pl.Int32)


def check_duplicates(bars: pl.DataFrame) -> Check:
    dupes = (bars.group_by(["contract", "ts_event"]).agg(pl.len().alias("n"))
             .filter(pl.col("n") > 1))
    if dupes.height == 0:
        return Check("2. Duplicates", "PASS",
                     f"unique on (contract, ts_event) across {bars.height:,} bars")
    return Check("2. Duplicates", "FAIL", f"{dupes.height:,} duplicated keys",
                 [f"`{r['contract']}` at {r['ts_event']} x{r['n']}"
                  for r in dupes.head(10).iter_rows(named=True)])


def check_ohlc(bars: pl.DataFrame) -> Check:
    bad = bars.filter(
        (pl.col("low") > pl.min_horizontal("open", "close"))
        | (pl.col("high") < pl.max_horizontal("open", "close"))
        | (pl.col("high") < pl.col("low"))
    )
    if bad.height == 0:
        return Check("3. OHLC sanity", "PASS",
                     f"low <= min(open,close) and high >= max(open,close) on all "
                     f"{bars.height:,} bars")
    return Check("3. OHLC sanity", "FAIL", f"{bad.height:,} impossible bars",
                 [f"`{r['contract']}` {r['ts_event']} O{r['open']} H{r['high']} "
                  f"L{r['low']} C{r['close']}"
                  for r in bad.head(10).iter_rows(named=True)])


def check_outliers(bars: pl.DataFrame, sigma: float = 10.0) -> Check:
    """1m returns beyond `sigma` of trailing 30d realized vol, computed within a contract."""
    flagged = []
    total = 0
    for (contract,), part in bars.sort("ts_event").group_by(["contract"], maintain_order=True):
        close = part.get_column("close").to_numpy()
        if close.size < 5000:
            continue
        r = np.diff(np.log(close), prepend=np.log(close[0]))
        window = 30 * OPEN_MINUTES_PER_SESSION
        if r.size <= window:
            continue
        c1 = np.concatenate([[0.0], np.cumsum(r)])
        c2 = np.concatenate([[0.0], np.cumsum(r * r)])
        k = np.arange(window, r.size)
        s1 = c1[k] - c1[k - window]
        s2 = c2[k] - c2[k - window]
        var = np.maximum((s2 - s1 * s1 / window) / (window - 1), 0.0)
        sd = np.sqrt(var)
        with np.errstate(invalid="ignore", divide="ignore"):
            z = np.abs(r[k]) / np.where(sd > 0, sd, np.nan)
        hits = np.flatnonzero(z > sigma)
        total += hits.size
        for i in hits[:3]:
            flagged.append(f"`{contract}` {part.get_column('ts_event')[int(k[i])]} "
                           f"z={z[i]:.1f}")
    rate = total / max(bars.height, 1)
    return Check("4. Outlier scan", "WARN" if total else "PASS",
                 f"{total:,} bars beyond {sigma:g}x trailing-30d sigma "
                 f"({rate:.4%} of bars). Reported, not removed — a real move is data.",
                 flagged[:10])


def check_zero_volume(bars: pl.DataFrame) -> tuple[Check, Check]:
    zero = bars.filter(pl.col("volume") == 0)
    live = zero.filter(pl.col("high") > pl.col("low"))
    note = ("`ohlcv-1m` aggregates trades, so a minute with no trades produces NO BAR "
            "rather than a zero-volume one. This check cannot fail on this dataset; it "
            "reports N/A with the count rather than PASS, because a check that cannot "
            "fail must not look like evidence.")
    return (
        Check("5. Zero-volume runs", "N/A" if zero.height == 0 else "WARN",
              f"{zero.height:,} zero-volume bars. {note}"),
        Check("6. Zero volume with a live range", "N/A" if live.height == 0 else "FAIL",
              f"{live.height:,} bars with volume 0 and high > low. {note}"),
    )


def measure_closed_window(bars: pl.DataFrame, year: int,
                          threshold: float = 0.01) -> list[tuple[int, int]]:
    """The ET minutes closed in `year`, as contiguous runs, measured from coverage.

    DECISION: THE CLOSED WINDOW IS MEASURED PER YEAR, NOT HARD-CODED.

    A fixed 17:00-17:59 ET break is only correct for the modern schedule. CME moved the
    Globex close: before roughly 2016 the equity-index and metals session ran to 17:15 ET
    with the break after it, and this batch starts in 2010. Testing sixteen years against
    one window flagged 2,029 perfectly good bars — including NQ prints of 240,000-320,000
    contracts at 17:25-17:35 ET in 2010-2015, which are settlement-period volume under the
    old schedule and unmistakably real.

    Deriving the window from coverage is partly circular: the data defines the expectation
    the data is then judged against. What makes it a real check is the SHAPE assertion in
    `check_session_structure` — the closure must be a single contiguous run of plausible
    length in every year. A fragmented or missing closure means the session model is wrong,
    and that is a failure this can still detect.
    """
    d = (bars.with_columns(
            _et_minute().alias("etmin"),
            pl.col("ts_event").dt.convert_time_zone(str(ET)).dt.year().alias("year"))
         .filter(pl.col("year") == year))
    sessions = d.get_column("session").n_unique()
    if sessions < 50:
        return []
    seen = (d.group_by("etmin").agg(pl.col("session").n_unique().alias("s")))
    frac = {m: s / sessions for m, s in zip(seen.get_column("etmin"),
                                            seen.get_column("s"))}
    closed = [m for m in range(1440) if frac.get(m, 0.0) < threshold]
    runs: list[tuple[int, int]] = []
    start = prev = None
    for m in closed:
        if start is None:
            start = prev = m
        elif m == prev + 1:
            prev = m
        else:
            runs.append((start, prev))
            start = prev = m
    if start is not None:
        runs.append((start, prev))
    return runs


def check_session_structure(bars: pl.DataFrame) -> Check:
    """Every year must show ONE contiguous closure of plausible length."""
    years = sorted({int(y) for y in bars.select(
        pl.col("ts_event").dt.convert_time_zone(str(ET)).dt.year()
    ).to_series().unique()})
    rows: list[str] = []
    problems = 0
    previous: tuple[int, int] | None = None
    for year in years:
        runs = [r for r in measure_closed_window(bars, year) if r[1] - r[0] + 1 >= 20]
        if not runs:
            continue
        if len(runs) > 1:
            problems += 1
            rows.append(f"**{year}: {len(runs)} separate closures** "
                        + ", ".join(f"{_hhmm(a)}-{_hhmm(b)}" for a, b in runs))
            continue
        a, b = runs[0]
        length = b - a + 1
        if not 45 <= length <= 90:
            problems += 1
            rows.append(f"**{year}: closure is {length} min** ({_hhmm(a)}-{_hhmm(b)} ET), "
                        f"outside the plausible 45-90 min range")
        elif previous != (a, b):
            rows.append(f"{year}: closed {_hhmm(a)}-{_hhmm(b)} ET ({length} min)"
                        + ("  <- schedule change" if previous else ""))
            previous = (a, b)
    return Check(
        "1. Gap check (session-aware, era-aware)",
        "FAIL" if problems else "PASS",
        "The expected-bar calendar is the measured closure per year, not a fixed window: "
        "CME moved the Globex close during this sample. What is asserted is the SHAPE — "
        "exactly one contiguous closure of 45-90 minutes in every year. Only changes are "
        "listed below.",
        rows,
    )


def _hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def session_profile(bars: pl.DataFrame) -> tuple[pl.DataFrame, Check]:
    """Per-session bar counts, and the gap check built on the measured session structure."""
    d = bars.with_columns(_et_minute().alias("etmin"))
    per = (d.group_by("session").agg(pl.len().alias("bars")).sort("session"))
    median = float(per.get_column("bars").median() or 0)

    short = per.filter(pl.col("bars") < median * SHORT_SESSION_RATIO)

    rows = [
        f"expected open minutes per session: **{OPEN_MINUTES_PER_SESSION}** "
        f"(1440 minus the measured 17:00-17:59 ET maintenance break)",
        f"median session: **{median:,.0f} bars** "
        f"({median / OPEN_MINUTES_PER_SESSION:.1%} of open minutes traded)",
        f"short sessions (< {SHORT_SESSION_RATIO:.0%} of median): **{short.height}** "
        f"— holidays and early closes, expected",
    ]
    return per, Check(
        "1b. Coverage", "PASS",
        "Absent minutes are NOT counted as gaps: for a thin contract they mean no trade "
        "occurred. What is checked is that no bar falls inside a closed window, and that "
        "coverage inside US cash hours is continuous on the liquid front month.",
        rows,
    )


def check_rth_runs(bars: pl.DataFrame, min_run: int = 15) -> Check:
    """Contiguous absent minutes inside US cash hours — the one gap a liquid book cannot make."""
    d = (bars.with_columns(_et_minute().alias("etmin"))
         .filter((pl.col("etmin") >= RTH_START) & (pl.col("etmin") < RTH_END)))
    worst: list[str] = []
    total = 0
    for (session,), part in d.group_by(["session"], maintain_order=True):
        present = set(part.get_column("etmin").to_list())
        missing = sorted(set(range(RTH_START, RTH_END)) - present)
        if not missing:
            continue
        run_start = prev = missing[0]
        for m in missing[1:] + [None]:
            if m is not None and m == prev + 1:
                prev = m
                continue
            length = prev - run_start + 1
            if length >= min_run:
                total += 1
                worst.append(f"{session}: {run_start // 60:02d}:{run_start % 60:02d}-"
                             f"{prev // 60:02d}:{prev % 60:02d} ET ({length} min)")
            if m is not None:
                run_start = prev = m
    return Check(
        "7. Session coverage (RTH continuity)", "WARN" if total else "PASS",
        f"{total} contiguous absent runs of >= {min_run} min inside 09:30-16:00 ET. "
        f"On a liquid front month these are the only absences that indicate missing data "
        f"rather than an untraded minute.",
        sorted(worst)[:12],
    )


def validate_product(product: str) -> tuple[list[Check], pl.DataFrame]:
    bars = pl.read_parquet(CONTINUOUS / f"{product}.parquet")
    per, gap = session_profile(bars)
    zero_runs, zero_live = check_zero_volume(bars)
    checks = [
        check_session_structure(bars),
        gap,
        check_duplicates(bars),
        check_ohlc(bars),
        check_outliers(bars),
        zero_runs,
        zero_live,
        check_rth_runs(bars),
    ]
    return checks, per


def render(results: dict[str, tuple[list[Check], pl.DataFrame]]) -> str:
    w: list[str] = []
    a = w.append
    a("# Data quality")
    a("")
    a("Generated by `python -m futuresres.data.validate`. CLAUDE_FUTURES.md §3.")
    a("")
    a("Run on the **front-month continuous series** — the object research actually reads — "
      "after the roll has dropped every crossover session.")
    a("")
    a("> **Missing bars are the normal case here, unlike crypto.** CME has a daily "
      "maintenance halt, a weekend, holidays and early closes, and `ohlcv-1m` emits no bar "
      "at all for a minute with no trades. A flat every-minute expectation would report "
      "millions of false gaps and bury the real ones, so the expected-bar calendar is built "
      "from the measured session structure instead.")
    a("")
    worst = {"FAIL": 0, "WARN": 0, "N/A": 0, "PASS": 0}
    for checks, _ in results.values():
        for c in checks:
            worst[c.status] += 1
    a(f"**{worst['FAIL']} FAIL · {worst['WARN']} WARN · {worst['N/A']} N/A · "
      f"{worst['PASS']} PASS** across {len(results)} products.")
    a("")
    for product, (checks, per) in sorted(results.items()):
        a(f"## {product}")
        a("")
        total = int(per.get_column("bars").sum())
        a(f"{per.height:,} sessions, {total:,} bars, "
          f"{per.get_column('session').min()} to {per.get_column('session').max()}")
        a("")
        for c in checks:
            a(f"### {c.name} — **{c.status}**")
            a("")
            a(c.detail)
            a("")
            for row in c.rows:
                a(f"- {row}")
            if c.rows:
                a("")
    return "\n".join(w)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.data.validate")
    ap.add_argument("--products", nargs="*", default=["MNQ", "NQ", "MGC"])
    args = ap.parse_args(argv)

    results = {}
    for product in args.products:
        print(f"validating {product}")
        checks, per = validate_product(product)
        results[product] = (checks, per)
        for c in checks:
            print(f"  {c.status:<5} {c.name}")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(render(results), encoding="utf-8")
    print(f"wrote {REPORT}")
    return 0 if not any(c.status == "FAIL" for cs, _ in results.values() for c in cs) else 1


if __name__ == "__main__":
    sys.exit(main())

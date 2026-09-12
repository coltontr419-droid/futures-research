"""The authoritative firing rates. Measured on real data; nothing declared. §5, §7.

    python -m futuresres.reporting.measured_rates

WHY THIS REPLACES THE DECLARED TABLE. `reports/decisions.md` §21: F02 declared one firing
per session, the gate cleared it on that basis, and the run produced 106-707 events per cell
against a predicted 4,006-4,125. Wrong by a factor of forty. The declared figure counted the
OPPORTUNITY - one imbalance reading per session per window - while the condition only
TRIGGERS when `|imb| > k*sigma`, on 6-23% of rows, and then a mandatory regime split halved
the remainder again.

§13's repair could not have caught that. It checked that every hypothesis had a declared
**or** measured rate. It could not check whether a declared rate was *correct*, because a
declaration is exactly the thing a test has no independent source for. So declarations no
longer gate anything: they are recorded as estimates, and the gate reads only this file.

WHAT "MEASURED" MEANS HERE, precisely, because the word is doing a lot of work:

  * the condition's THRESHOLD is applied - k*sigma, k*ATR, breakout confirmation - so the
    count is of triggers, not of opportunities
  * any MANDATORY REGIME SPLIT is applied, and the WORST era is what gates, because a
    hypothesis that must be evaluated in two eras has to be powered in both
  * the count is per Stage 1 CELL, so a scanned dimension that is also a grid axis is
    divided out
  * for a hypothesis that has already run, the count comes from its own cell file - the
    strongest measurement available, since it is what the pipeline actually produced

STILL NOT A STATISTIC. This computes no return series, no p-value, and spends no trial. It
is a property of the condition and the data.

F09 IS NOT THRESHOLD-GATED, and an earlier note in this project said it was. Its condition
enters at S-15min on every session with no filter at all, so its rate is bounded only by
data availability. It is measured anyway - under the new rule everything is - and the
correction is recorded rather than left standing.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Final

import numpy as np
import polars as pl
import yaml

from futuresres.reporting.firing_rates import (
    SMALLEST_RESOLVING,
    cap_independent,
    f05_rates,
    f08_rates,
    f10_rates,
    f11_rates,
    load_1m,
    rolling_pct_prior,
    span_minutes,
)
from futuresres.session.calendar import ET

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
REPORTS: Final[Path] = ROOT / "reports"
REGISTRY: Final[Path] = ROOT / "hypotheses.yaml"
CACHE: Final[Path] = REPORTS / "measured_rates.json"
REPORT: Final[Path] = REPORTS / "measured_rates.md"

CONTINUOUS: Final[Path] = ROOT / "data" / "continuous"
SERIES: Final[dict[str, str]] = {"MNQ": "NQ_MNQ_spliced", "MGC": "MGC"}

RTH_OPEN: Final[int] = 9 * 60 + 30
RTH_CLOSE: Final[int] = 16 * 60
LOOKBACK: Final[int] = 20
VOL_WINDOW: Final[int] = 250

#: Hypotheses the catalog requires to be evaluated in separate eras. Only F02 carries one,
#: and it comes from F13's exclusion note rather than F02's own fields - which is exactly
#: why the gate never saw it.
MANDATORY_SPLIT: Final[dict[str, date]] = {"F02": date(2021, 1, 1)}

#: Settlement times for F09, in ET minutes-of-day.
SETTLEMENT: Final[dict[str, int]] = {"MNQ": 15 * 60, "MGC": 13 * 60 + 30}


@dataclass(slots=True)
class Rate:
    hypothesis: str
    product: str
    cell: str
    horizon: int
    firings: int
    independent: int
    per_session: float
    source: str
    note: str


# ----------------------------------------------------------------- daily frame
def load_daily(product: str) -> pl.DataFrame:
    """Per-session RTH OHLC plus the 10:00 ET price, for F01 and F06."""
    bars = pl.read_parquet(CONTINUOUS / f"{SERIES[product]}.parquet")
    local = pl.col("ts_event").dt.convert_time_zone(str(ET))
    f = bars.with_columns(
        (local.dt.hour().cast(pl.Int32) * 60
         + local.dt.minute().cast(pl.Int32)).alias("mod"),
        local.dt.date().alias("day"),
    ).filter((pl.col("mod") >= RTH_OPEN) & (pl.col("mod") < RTH_CLOSE))
    return (f.group_by("day").agg(
        pl.col("high").max().alias("hi"),
        pl.col("low").min().alias("lo"),
        pl.col("close").last().alias("close"),
        pl.col("close").filter(pl.col("mod") == 10 * 60).first().alias("at_1000"),
        pl.len().alias("bars"),
    ).sort("day").filter(pl.col("bars") >= 60))


def f06_vol_filter(daily_vol: np.ndarray) -> np.ndarray:
    """F06's vol_filter, SETTLED 2026-09-02: realised vol above the trailing-20 MEDIAN.

    The registered condition said "vol_filter in {none, >median}" and named neither the
    quantity nor the lookback, which left the event count - and therefore whether F06's
    routes were open - undetermined. It is now: this session's realised volatility against
    the MEDIAN REALISED VOLATILITY OVER THE TRAILING 20 SESSIONS, strictly prior. One
    lookback, matching the 20 sessions used everywhere else in this catalog.
    """
    return daily_vol > rolling_pct_prior(np.nan_to_num(daily_vol), LOOKBACK, 50)


def f01_vol_filter(returns: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(passes_median, passes_p66) for F01 ONLY. STILL UNDECIDED.

    F01 has the same gap F06 had, and it has NOT been settled - only F06's was. The reading
    below is a measurement convenience so F01 can be counted at all, not a registered
    choice. F01 is `blocked_insufficient_events` and will not run, so nothing rests on it;
    if it is ever revived this must be decided first. See decisions.md §28.
    """
    n = returns.size
    vol = np.full(n, np.nan)
    for i in range(LOOKBACK, n):
        vol[i] = returns[i - LOOKBACK:i].std(ddof=1)
    med = rolling_pct_prior(np.nan_to_num(vol), VOL_WINDOW, 50)
    p66 = rolling_pct_prior(np.nan_to_num(vol), VOL_WINDOW, 66)
    with np.errstate(invalid="ignore"):
        return vol > med, vol > p66


# ----------------------------------------------------------------- F01
def f01_rates(product: str, horizons: list[int], span: int) -> list[Rate]:
    """|r1| > k*ATR(20d), r1 measured previous close -> 10:00 ET. Then a vol filter."""
    d = load_daily(product).drop_nulls("at_1000")
    close = d.get_column("close").to_numpy()
    hi, lo = d.get_column("hi").to_numpy(), d.get_column("lo").to_numpy()
    at10 = d.get_column("at_1000").to_numpy()
    n = close.size
    prev = np.concatenate([[np.nan], close[:-1]])
    tr = np.maximum(hi, prev) - np.minimum(lo, prev)
    atr = np.full(n, np.nan)
    for i in range(LOOKBACK, n):
        atr[i] = np.nanmean(tr[i - LOOKBACK:i])
    with np.errstate(invalid="ignore"):
        r1 = np.abs(at10 - prev)
    rets = np.diff(np.log(close), prepend=np.log(close[0]))
    pass_med, pass_p66 = f01_vol_filter(rets)

    out: list[Rate] = []
    for k in (0.0, 0.5, 1.0):
        with np.errstate(invalid="ignore"):
            base = np.isfinite(r1) & np.isfinite(atr) & (r1 > k * atr)
        for vf, mask in (("none", np.ones(n, bool)),
                         (">median", pass_med), (">p66", pass_p66)):
            fires = int((base & mask).sum())
            for h in horizons:
                out.append(Rate("F01", product, f"k={k} vol={vf}", h, fires,
                                cap_independent(fires, span, h), fires / max(n, 1),
                                "condition",
                                f"{n:,} sessions; entry_time is a grid axis so a cell "
                                f"fires at most once a session"))
    return out


# ----------------------------------------------------------------- F06
def f06_rates(product: str, horizons: list[int], span: int) -> list[Rate]:
    """Opening range over W minutes, then a close beyond the boundary (1 or 2 closes)."""
    bars = pl.read_parquet(CONTINUOUS / f"{SERIES[product]}.parquet")
    local = pl.col("ts_event").dt.convert_time_zone(str(ET))
    f = bars.with_columns(
        (local.dt.hour().cast(pl.Int32) * 60
         + local.dt.minute().cast(pl.Int32) - RTH_OPEN).alias("m"),
        local.dt.date().alias("day"),
    ).filter((pl.col("m") >= 0) & (pl.col("m") < RTH_CLOSE - RTH_OPEN))

    days = f.get_column("day").to_numpy()
    mins = f.get_column("m").to_numpy().astype(np.int64)
    closes = f.get_column("close").to_numpy().astype(float)
    sessions = np.unique(days)
    width = RTH_CLOSE - RTH_OPEN
    grid = np.full((sessions.size, width), np.nan)
    grid[np.searchsorted(sessions, days), mins] = closes

    # Realised volatility per session, from that session's own RTH minute returns - which
    # is what "realised volatility" means. Then compared against the trailing-20 median.
    daily_vol = np.full(sessions.size, np.nan)
    for i, row in enumerate(grid):
        px = row[np.isfinite(row)]
        if px.size > 2:
            daily_vol[i] = np.diff(np.log(px)).std(ddof=1)
    pass_med = f06_vol_filter(daily_vol)

    out: list[Rate] = []
    for W in (5, 15, 30):
        rng_hi = np.nanmax(grid[:, :W], axis=1)
        rng_lo = np.nanmin(grid[:, :W], axis=1)
        after = grid[:, W:]
        with np.errstate(invalid="ignore"):
            beyond = (after > rng_hi[:, None]) | (after < rng_lo[:, None])
        beyond = np.where(np.isfinite(after), beyond, False)
        one = beyond.any(axis=1)
        two = (beyond[:, :-1] & beyond[:, 1:]).any(axis=1)
        for confirm, mask in (("1 close", one), ("2 closes", two)):
            for vf, vmask in (("none", np.ones(sessions.size, bool)),
                              (">median", pass_med)):
                fires = int((mask & vmask).sum())
                for h in horizons:
                    out.append(Rate("F06", product, f"W={W} {confirm} vol={vf}", h, fires,
                                    cap_independent(fires, span, h),
                                    fires / max(sessions.size, 1), "condition",
                                    f"{sessions.size:,} sessions"))
    return out


# ----------------------------------------------------------------- F09
def f09_rates(product: str, horizons: list[int], span: int) -> list[Rate]:
    """Enter at S-15min every session. NO threshold - the rate is bounded by data only."""
    df = load_1m(product)
    s = SETTLEMENT[product]
    mod = df.get_column("mod").to_numpy()
    day = df.get_column("day").to_numpy()
    close = df.get_column("close").to_numpy()
    n_sessions = np.unique(day).size

    out: list[Rate] = []
    for pre_window in (30, 60):
        have_entry = set(day[mod == s - 15])
        have_pre = set(day[mod == s - pre_window])
        usable = have_entry & have_pre
        # a flat pre-move carries no direction, so it cannot fire
        idx_e = {d: c for d, c, m in zip(day, close, mod) if m == s - 15}
        idx_p = {d: c for d, c, m in zip(day, close, mod) if m == s - pre_window}
        fires = sum(1 for d in usable if idx_e[d] != idx_p[d])
        for h in horizons:
            out.append(Rate("F09", product, f"pre_window={pre_window}", h, fires,
                            cap_independent(fires, span, h), fires / max(n_sessions, 1),
                            "condition",
                            f"{n_sessions:,} sessions; NOT threshold-gated - bounded by "
                            f"data availability and by a flat pre-move only"))
    return out


# ----------------------------------------------------------------- already run
CELL_FILES: Final[dict[str, str]] = {
    "F02": "f02_cells.json", "F03": "f03_cells.json", "F04": "f04_cells.json",
    "F07": "f07_cells.json", "F14": "f14_cells.json",
}


def rates_from_cells(hid: str, horizons: list[int], spans: dict[str, int]) -> list[Rate]:
    """The strongest measurement available: what the pipeline actually produced."""
    path = REPORTS / CELL_FILES[hid]
    if not path.exists():
        return []
    rows = json.loads(path.read_text(encoding="utf-8"))
    split = MANDATORY_SPLIT.get(hid)
    out: list[Rate] = []
    for product in sorted({r["product"] for r in rows}):
        sub = [r for r in rows if r["product"] == product]
        by_h: dict[int, list[dict]] = {}
        for r in sub:
            by_h.setdefault(int(r.get("hold") or horizons[0]), []).append(r)
        for h, cells in sorted(by_h.items()):
            worst = min(c["events"] for c in cells)
            note = (f"from {path.name}: {len(cells)} cells, worst {worst:,} events")
            if split:
                note += (f"; MANDATORY REGIME SPLIT at {split} applied - the worst era is "
                         f"what gates, because a hypothesis evaluated in two eras must be "
                         f"powered in both")
            out.append(Rate(hid, product, f"worst of {len(cells)} cells", h, worst,
                            min(worst, spans[product] // max(h, 1)),
                            float("nan"), "cell file", note))
    return out


LEVEL_RATES: Final[Path] = REPORTS / "level_rates.json"


def rates_from_level_rates(hid: str) -> list[Rate]:
    """L-series rates, routed from `level_rates.json` into the gate's file.

    THE L-SERIES HAD NO ENTRY IN `measured_rates.json` AT ALL until this existed, so the
    scheduling gate could not pass ANY L hypothesis. That was invisible for as long as every
    L entry was `schedulable: false` - the gate skips those - and it surfaced the moment one
    was scheduled. Two halves of the record that never met, the same shape as decisions.md 36.

    This ROUTES a measurement, it does not create one. The numbers come from
    `reporting.level_rates`, measured on real data over both products, and `independent` is
    the non-overlapping count that module computes per horizon. Nothing here is declared.
    """
    if not LEVEL_RATES.exists():
        return []
    payload = json.loads(LEVEL_RATES.read_text(encoding="utf-8"))
    out: list[Rate] = []
    for r in payload.get("rates", []):
        if r["hypothesis"] != hid:
            continue
        ind = r.get("independent") or {}
        for h in r["horizons"]:
            n_ind = ind.get(str(h), ind.get(h))
            if n_ind is None:
                # An older level_rates.json predates the independence column. Skip rather
                # than substitute the firing count - overlapping entries are one observation
                # counted many times, and passing them off as independent is exactly the
                # overstatement the gate exists to prevent. Re-run reporting.level_rates.
                continue
            out.append(Rate(hid, r["product"], r["cell"], int(h), int(r["firings"]),
                            int(n_ind), float("nan"), "level_rates",
                            "routed from reports/level_rates.json; non-overlapping at this "
                            "horizon"))
    return out


def measure_all() -> list[Rate]:
    registry = {e["id"]: e for e in yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))}
    frames = {p: load_1m(p) for p in ("MNQ", "MGC")}
    spans = {p: span_minutes(f) for p, f in frames.items()}
    rates: list[Rate] = []

    for hid, entry in registry.items():
        if entry["status"] == "excluded":
            continue
        horizons = list(entry["horizon_minutes"])
        products = [str(s).upper() for s in entry.get("symbols") or []]
        print(f"  {hid} ...", flush=True)
        if hid in CELL_FILES:
            rates += rates_from_cells(hid, horizons, spans)
            continue
        if hid.startswith("L"):
            rates += rates_from_level_rates(hid)
            continue
        for product in products:
            if product not in frames:
                continue
            df, span = frames[product], spans[product]
            if hid == "F01":
                rates += f01_rates(product, horizons, span)
            elif hid == "F05":
                rates += [Rate("F05", r.product, r.cell, r.horizon, r.firings,
                               r.independent, r.per_session, "condition", r.note)
                          for r in f05_rates(product, df, span)]
            elif hid == "F06":
                rates += f06_rates(product, horizons, span)
            elif hid == "F09":
                rates += f09_rates(product, horizons, span)
            elif hid == "F10":
                rates += [Rate("F10", r.product, r.cell, r.horizon, r.firings,
                               r.independent, r.per_session, "condition", r.note)
                          for r in f10_rates(product, df, span)]
            elif hid == "F11":
                rates += [Rate("F11", r.product, r.cell, r.horizon, r.firings,
                               r.independent, r.per_session, "condition", r.note)
                          for r in f11_rates(product, df, span)]
        if hid == "F08":
            rates += [Rate("F08", r.product, r.cell, r.horizon, r.firings,
                           r.independent, r.per_session, "condition", r.note)
                      for r in f08_rates(frames, min(spans.values()))]
    return rates


def status_for(product: str, horizon: int, lo: int, hi: int) -> tuple[str, int]:
    need = SMALLEST_RESOLVING.get((product, _proxy(horizon)), 0)
    if lo >= need:
        return "RESOLVABLE", need
    if hi < need:
        return "BELOW SWEPT RANGE", need
    return "MIXED", need


def _proxy(h: int) -> int:
    return min((1, 60, 180), key=lambda m: abs(math.log(h / m)))


def render(rates: list[Rate]) -> str:
    from futuresres.reporting.detectability import DECLARED_ESTIMATE

    w: list[str] = []
    a = w.append
    a("# Measured firing rates — the only input the gate accepts")
    a("")
    a("Generated by `python -m futuresres.reporting.measured_rates`. "
      "CLAUDE_FUTURES.md §5, §7; `reports/decisions.md` §21, §22.")
    a("")
    a("**Nothing here is Stage 1 and nothing here spends a trial.** These are counts of how "
      "often each condition triggers on real data.")
    a("")
    a("Declared rates no longer gate anything. §21: F02 declared one firing per session, the "
      "gate cleared it on that basis, and the run produced 106-707 events per cell against a "
      "predicted 4,006-4,125. No test could have caught it, because a declaration has no "
      "independent source to check against. A hypothesis absent from this file is "
      "**unschedulable**.")
    a("")

    a("## What was applied")
    a("")
    a("| | |")
    a("|---|---|")
    a("| threshold | applied — `k*sigma`, `k*ATR`, breakout confirmation, so the count is of "
      "TRIGGERS not opportunities |")
    a(f"| mandatory regime split | applied for {', '.join(sorted(MANDATORY_SPLIT))}, with "
      "the **worst era** gating: a hypothesis evaluated in two eras must be powered in both |")
    a("| grain | per Stage 1 cell, so a scanned dimension that is also a grid axis is "
      "divided out |")
    a("| already-run hypotheses | taken from their own cell files — the strongest "
      "measurement available, because it is what the pipeline actually produced |")
    a("")

    a("## Declared against measured")
    a("")
    a("| hypothesis | declared estimate | worst measured cell | source |")
    a("|---|---|---|---|")
    for hid in sorted({r.hypothesis for r in rates}):
        sub = [r for r in rates if r.hypothesis == hid]
        worst = min(r.independent for r in sub)
        dec = DECLARED_ESTIMATE.get(hid)
        a(f"| {hid} | " + (f"{dec:g}/session" if dec is not None else "none") + " | "
          f"{worst:,} | {sub[0].source} |")
    a("")
    a("The declared column is kept only so the gap stays visible. It gates nothing.")
    a("")

    a("## Per hypothesis, against the swept range")
    a("")
    a("| hypothesis | product | horizon | measured (min-max) | swept range needs | status |")
    a("|---|---|---|---|---|---|")
    for hid in sorted({r.hypothesis for r in rates}):
        for product in sorted({r.product for r in rates if r.hypothesis == hid}):
            for horizon in sorted({r.horizon for r in rates
                                   if r.hypothesis == hid and r.product == product}):
                sub = [r for r in rates if r.hypothesis == hid
                       and r.product == product and r.horizon == horizon]
                lo = min(r.independent for r in sub)
                hi = max(r.independent for r in sub)
                st, need = status_for(product, horizon, lo, hi)
                rng = f"{lo:,}" if lo == hi else f"{lo:,} - {hi:,}"
                a(f"| {hid} | {product} | {horizon}m | {rng} | {need:,} | "
                  + (f"**{st}**" if st == "RESOLVABLE" else st) + " |")
    a("")

    a("## Every cell")
    a("")
    a("| hypothesis | product | cell | horizon | firings | independent | source |")
    a("|---|---|---|---|---|---|---|")
    for r in sorted(rates, key=lambda r: (r.hypothesis, r.product, r.horizon, r.cell)):
        a(f"| {r.hypothesis} | {r.product} | {r.cell} | {r.horizon}m | {r.firings:,} | "
          f"{r.independent:,} | {r.source} |")
    a("")
    return "\n".join(w)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.reporting.measured_rates")
    ap.add_argument("--check", action="store_true",
                    help="measure and compare against the cached file without writing; "
                         "exits 1 if they disagree")
    args = ap.parse_args(argv)

    print("measuring firing rates on real data (no trial is spent)")
    rates = measure_all()
    payload = [asdict(r) for r in rates]

    if args.check:
        if not CACHE.exists():
            print("no cached measured_rates.json to check against")
            return 1
        cached = json.loads(CACHE.read_text(encoding="utf-8"))
        same = json.dumps(cached, sort_keys=True, default=str) == json.dumps(
            payload, sort_keys=True, default=str)
        print("cache matches a fresh measurement" if same
              else "CACHE DISAGREES with a fresh measurement")
        return 0 if same else 1

    CACHE.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    REPORT.write_text(render(rates), encoding="utf-8")
    print(f"{len(rates)} rows measured across "
          f"{len({r.hypothesis for r in rates})} hypotheses")
    print(f"wrote {CACHE.name} and {REPORT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

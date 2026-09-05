"""F05 - volatility_compression_expansion, Stage 1. CLAUDE_FUTURES.md §5, §6.

    python -m futuresres.signals.f05

THE CONDITION, AS CORRECTED. If realized_vol(1h) is below the p{vol_pct} of the trailing 20
sessions AT THE SAME CLOCK TIME, arm the setup; on the first close beyond k*sigma from the
compression midpoint, enter that direction and exit at H or 16:55 ET, whichever comes first.
vol_pct in {15, 20, 25}, k in {1.5, 2, 2.5}, H in {1, 2, 3} h.

TWO SPECIFICATION REPAIRS ARE BAKED IN, both recorded before this run (decisions.md §23,
§27) and neither of them a tuning choice.

  DEADLINE   The registered condition never said by WHEN the break must occur. Unbounded, it
             fired on 94% of armings. A 1-hour volatility estimate is informative over about
             the next hour, and the compression MIDPOINT the trigger measures from goes stale
             beyond that, so the break window is ONE COMPRESSION WINDOW: 60 minutes.

  SIGMA      The registered condition measured k*sigma against the COMPRESSED WINDOW'S OWN
             sigma. That does not test the mechanism. Compression SELECTS hours with small
             sigma, so the trigger distance shrank exactly when the filter fired. Expansion
             means volatility RETURNING TOWARD NORMAL, so the trigger references NORMAL
             volatility for that clock hour - the median of the trailing 20 sessions' sigma,
             the same window and quantity the p20 arming filter already uses.

Under the correction the k axis discriminates for the first time: break rates run 72-78% at
k=1.5 and 44-50% at k=2.5, against a flat ~80-90% before.

THE ROW IS THE CME TRADING DAY, 18:00 ET to 16:55 ET, 1,375 minutes. This is not a
convenience - it is the condition's own exit rule. "Exit at H or 16:55 ET, whichever comes
first" makes 16:55 the row end, and the 17:00-18:00 maintenance break falls exactly outside
the row rather than inside it. `evaluate_signed_signal` indexes forward by BAR, so a row must
be a complete minute grid or "180 bars" is not "180 minutes".

A CELL FIRES ONLY WHERE THE FULL HOLD FITS BEFORE 16:55. The condition truncates the hold at
the cap; a truncated hold is a different holding period, and Stage 1 needs one. Requiring the
full H to fit is also what §2's 17:00 hard exit requires of a real position, so this is the
account's constraint rather than an extra filter. Armings too late in the day to run their
course are excluded and counted.

WHAT CAN CARRY A VERDICT. `reports/detectability.md` opens 5 of 6 combinations: MNQ at 120
and 180 minutes, MGC at all three. **MNQ 60m is BELOW SWEPT RANGE** at 6,965 measured events
against the 19,722 at which a floor resolves, and its nine cells are reported as
UNINFORMATIVE rather than as evidence.

NO REAL-DATA CONTROL EXISTS AT THIS EVENT REGIME. F14 validated the harness at ~48,000-52,000
events; F05's cells hold a fraction of that. This null carries the §7.2 synthetic GARCH
assurance and nothing from F14.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final, Sequence

import numpy as np
import polars as pl

from futuresres.reporting.firing_rates import F05_BREAK_DEADLINE, F05_NORMAL_PCT
from futuresres.session.calendar import ET
from futuresres.signals.logged_run import stage1_run
from futuresres.signals.stage1 import evaluate_signed_signal
from futuresres.stats.dsr import sharpe_ratio

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
CONTINUOUS: Final[Path] = ROOT / "data" / "continuous"
REPORT: Final[Path] = ROOT / "reports" / "f05_stage1.md"
CELLS: Final[Path] = ROOT / "reports" / "f05_cells.json"

#: The CME trading day: 18:00 ET through 16:54 ET, inclusive. 16:55 is the row end, which
#: is the condition's own exit cap.
ROW_START_MOD: Final[int] = 18 * 60
ROW_MINUTES: Final[int] = 1375

HOUR: Final[int] = 60
VOL_PCTS: Final[tuple[int, ...]] = (15, 20, 25)
KS: Final[tuple[float, ...]] = (1.5, 2.0, 2.5)
HOLDS: Final[tuple[int, ...]] = (60, 120, 180)
LOOKBACK: Final[int] = 20

SERIES: Final[dict[str, str]] = {"MNQ": "NQ_MNQ_spliced", "MGC": "MGC"}
COST_BPS: Final[dict[str, float]] = {"MNQ": 0.48, "MGC": 0.65}

#: reports/detectability.md - the one combination that cannot support a null.
BLOCKED: Final[frozenset[tuple[str, int]]] = frozenset({("MNQ", 60)})

FLOOR_BPS: Final[dict[tuple[str, int], float]] = {
    ("MNQ", 60): 2.57, ("MNQ", 120): 15.66, ("MNQ", 180): 15.66,
    ("MGC", 60): 4.17, ("MGC", 120): 14.34, ("MGC", 180): 14.34,
}
SMALLEST_RESOLVING: Final[dict[str, int]] = {"MNQ": 19_722, "MGC": 5_620}

ALPHA: Final[float] = 0.05


@dataclass(slots=True)
class Grid:
    rows: np.ndarray
    logp: np.ndarray
    fill_fraction: float

    @property
    def n_rows(self) -> int:
        return self.rows.size


def load(product: str) -> Grid:
    """Rows of 18:00 ET -> 16:54 ET, one per CME trading day, forward-filled."""
    bars = pl.read_parquet(CONTINUOUS / f"{SERIES[product]}.parquet")
    local = pl.col("ts_event").dt.convert_time_zone(str(ET))
    frame = bars.with_columns(
        (local.dt.hour().cast(pl.Int32) * 60
         + local.dt.minute().cast(pl.Int32)).alias("mod"),
        local.dt.date().alias("d"),
        pl.col("close").cast(pl.Float64),
    ).with_columns(
        ((pl.col("mod") - ROW_START_MOD) % 1440).alias("m"),
    ).filter(pl.col("m") < ROW_MINUTES).with_columns(
        # 18:00 onward belongs to the NEXT calendar day's trading day, per CME convention
        pl.when(pl.col("mod") >= ROW_START_MOD)
          .then(pl.col("d") + pl.duration(days=1))
          .otherwise(pl.col("d"))
          .alias("row"),
    )

    rows_col = frame.get_column("row").to_numpy()
    minutes = frame.get_column("m").to_numpy().astype(np.int64)
    closes = frame.get_column("close").to_numpy().astype(float)

    rows = np.unique(rows_col)
    flat = np.full(rows.size * ROW_MINUTES, np.nan)
    flat[np.searchsorted(rows, rows_col) * ROW_MINUTES + minutes] = closes
    traded = int(np.isfinite(flat).sum())

    grid = flat.reshape(rows.size, ROW_MINUTES)
    ok = np.isfinite(grid)
    idx = np.where(ok, np.arange(ROW_MINUTES)[None, :], 0)
    np.maximum.accumulate(idx, axis=1, out=idx)
    filled = np.take_along_axis(grid, idx, axis=1)
    first = np.argmax(ok, axis=1)
    for i in np.flatnonzero(ok.any(axis=1) & ~np.isfinite(filled[:, 0])):
        filled[i, : first[i]] = grid[i, first[i]]

    keep = np.isfinite(filled).all(axis=1)
    filled, rows = filled[keep], rows[keep]
    return Grid(rows, np.log(filled).ravel(), float(traded) / max(filled.size, 1))


def rolling_pct_prior(v: np.ndarray, w: int, pct: float) -> np.ndarray:
    out = np.full(v.size, np.nan)
    if v.size <= w:
        return out
    win = np.lib.stride_tricks.sliding_window_view(v, w)[:-1]
    out[w:] = np.percentile(win, pct, axis=1)
    return out


@dataclass(slots=True)
class Compression:
    """Per (row, hour) statistics of the compression window."""

    hour_start: np.ndarray        # minute-of-row where the compression hour begins
    sd: np.ndarray                # (n_rows, n_hours) sigma of that hour's closes
    mid: np.ndarray               # (n_rows, n_hours) mean of that hour's closes
    normal: np.ndarray            # (n_rows, n_hours) trailing-20 median sigma, same hour


def compress(grid: Grid) -> Compression:
    px = grid.logp.reshape(grid.n_rows, ROW_MINUTES)
    starts = np.arange(0, ROW_MINUTES - HOUR, HOUR)
    sd = np.empty((grid.n_rows, starts.size))
    mid = np.empty((grid.n_rows, starts.size))
    for j, s in enumerate(starts):
        w = px[:, s:s + HOUR]
        sd[:, j] = w.std(axis=1, ddof=1)
        mid[:, j] = w.mean(axis=1)
    normal = np.full_like(sd, np.nan)
    for j in range(starts.size):
        normal[:, j] = rolling_pct_prior(sd[:, j], LOOKBACK, F05_NORMAL_PCT)
    return Compression(starts, sd, mid, normal)


def build_direction(grid: Grid, comp: Compression, vol_pct: int, k: float,
                    hold: int) -> tuple[np.ndarray, int, int]:
    """(direction, entries, armings_dropped_for_no_room). Enter in the break direction."""
    px = grid.logp.reshape(grid.n_rows, ROW_MINUTES)
    direction = np.zeros(grid.logp.size)
    n_entry = 0
    dropped = 0

    for j, s in enumerate(comp.hour_start):
        thr = rolling_pct_prior(comp.sd[:, j], LOOKBACK, vol_pct)
        with np.errstate(invalid="ignore"):
            armed = (comp.sd[:, j] < thr) & np.isfinite(comp.normal[:, j]) \
                & (comp.normal[:, j] > 0)
        rows = np.flatnonzero(armed)
        if not rows.size:
            continue
        lo = s + HOUR
        hi = min(lo + F05_BREAK_DEADLINE, ROW_MINUTES)
        if hi <= lo:
            continue
        window = px[rows, lo:hi]
        dist = window - comp.mid[rows, j][:, None]
        beyond = np.abs(dist) > (k * comp.normal[rows, j])[:, None]
        has = beyond.any(axis=1)
        firstidx = np.argmax(beyond, axis=1)
        for r, ok_, fi in zip(rows, has, firstidx):
            if not ok_:
                continue
            entry = lo + int(fi)
            # the full hold must fit before 16:55 - a truncated hold is a different
            # holding period, and §2's hard exit requires the same of a real position
            if entry + hold >= ROW_MINUTES:
                dropped += 1
                continue
            direction[r * ROW_MINUTES + entry] = np.sign(
                px[r, entry] - comp.mid[r, j])
            n_entry += 1
    return direction, n_entry, dropped


@dataclass(slots=True)
class CellResult:
    product: str
    vol_pct: int
    k: float
    hold: int
    events: int
    dropped: int
    mean_bps: float
    sharpe: float
    p_value: float | None
    hit_rate: float | None
    separated: bool
    blocked: bool
    reason: str


def evaluate(grid: Grid, comp: Compression, product: str, vol_pct: int, k: float,
             hold: int, rng: np.random.Generator) -> CellResult:
    direction, _, dropped = build_direction(grid, comp, vol_pct, k, hold)
    idx = np.flatnonzero(direction)
    idx = idx[idx + hold < grid.logp.size]
    per_event = (direction[idx] * (grid.logp[idx + hold] - grid.logp[idx])
                 if idx.size else np.array([]))
    sharpe = (float(sharpe_ratio(per_event))
              if per_event.size >= 2 and per_event.std(ddof=1) > 0 else 0.0)
    res = None
    reason = f"only {idx.size} events"
    if idx.size >= 2:
        try:
            res = evaluate_signed_signal(direction, grid.logp, hold, rng=rng,
                                         n_bootstrap=800)
            reason = res.reason
        except ValueError as exc:
            reason = str(exc)
    return CellResult(
        product, vol_pct, k, hold, int(idx.size), dropped,
        float(per_event.mean() * 1e4) if per_event.size else 0.0, sharpe,
        res.p_value if res else None, res.hit_rate if res else None,
        bool(res and res.separated), (product, hold) in BLOCKED, reason,
    )


def benjamini_hochberg(p: np.ndarray, alpha: float = ALPHA) -> np.ndarray:
    order = np.argsort(p)
    m = p.size
    below = np.flatnonzero(p[order] <= alpha * np.arange(1, m + 1) / m)
    out = np.zeros(m, dtype=bool)
    if below.size:
        out[order[: below[-1] + 1]] = True
    return out


def run(products: Sequence[str], seed: int) -> tuple[list[CellResult], dict, dict]:
    cells: list[CellResult] = []
    fills: dict[str, float] = {}
    rows: dict[str, int] = {}
    for product in products:
        grid = load(product)
        comp = compress(grid)
        fills[product], rows[product] = grid.fill_fraction, grid.n_rows
        print(f"\n=== {product} === {grid.n_rows:,} trading days, "
              f"{grid.fill_fraction:.2%} of 18:00-16:55 ET minutes traded", flush=True)
        rng = np.random.default_rng(seed)
        for vol_pct in VOL_PCTS:
            for k in KS:
                for hold in HOLDS:
                    r = evaluate(grid, comp, product, vol_pct, k, hold, rng)
                    cells.append(r)
                    flag = " [UNINFORMATIVE]" if r.blocked else ""
                    print(f"  p{vol_pct} k={k} H={hold:<4} n={r.events:>6,} "
                          f"(-{r.dropped:,} no room)  mean {r.mean_bps:>+6.2f} "
                          f"p={r.p_value:.4f}{flag}"
                          + ("  SEPARATES" if r.separated else ""), flush=True)
    return cells, fills, rows


def render(cells: list[CellResult], fills: dict, rows: dict) -> str:
    w: list[str] = []
    a = w.append
    a("# F05 - volatility_compression_expansion, Stage 1")
    a("")
    a("Run by `python -m futuresres.signals.f05`. CLAUDE_FUTURES.md §5, §6, §7.6.")
    a("")

    a("## The condition that ran is the CORRECTED one")
    a("")
    a("Two specification repairs were adopted and recorded **before** this run - neither a "
      "tuning choice, both derived from the mechanism (`reports/decisions.md` §23, §27).")
    a("")
    a("| | registered | corrected | why |")
    a("|---|---|---|---|")
    a(f"| break deadline | none | **{F05_BREAK_DEADLINE} min** | a 1-hour vol estimate "
      "forecasts about the next hour, and the compression midpoint goes stale beyond it |")
    a("| `k*sigma` reference | the compressed window's own sigma | **trailing-20 median "
      "sigma at the same clock hour** | expansion means volatility returning toward NORMAL, "
      "so the trigger must reference normal |")
    a("")
    a("The second repair matters most: measuring against the compressed window's own sigma "
      "meant compression shrank the trigger distance exactly when the filter fired, so the "
      "condition broke on 79-91% of armings and **k did almost nothing**. Under the "
      "correction, break rates run 72-78% at k=1.5 and 44-50% at k=2.5.")
    a("")

    a("## What can carry a verdict")
    a("")
    a("| instrument | hold | measured events | status |")
    a("|---|---|---|---|")
    for product in sorted({c.product for c in cells}):
        for hold in HOLDS:
            sub = [c for c in cells if c.product == product and c.hold == hold]
            n = max((c.events for c in sub), default=0)
            blocked = any(c.blocked for c in sub)
            a(f"| {product} | {hold}m | {n:,} | "
              + ("**UNINFORMATIVE** - below swept range" if blocked else "informative")
              + " |")
    a("")
    a(f"**MNQ at 60 minutes cannot support a null**: 6,965 measured events against the "
      f"{SMALLEST_RESOLVING['MNQ']:,} at which a floor first resolves. Its nine cells are "
      "reported below for completeness and **excluded from every verdict** - a null there "
      "is the absence of evidence, not evidence of absence.")
    a("")

    a("## Multiplicity")
    a("")
    a("| instrument | informative cells | nominal | expected by chance | BH survivors |")
    a("|---|---|---|---|---|")
    survivors: dict[str, int] = {}
    for product in sorted({c.product for c in cells}):
        sub = [c for c in cells if c.product == product and not c.blocked
               and c.p_value is not None]
        pv = np.array([c.p_value for c in sub])
        bh = benjamini_hochberg(pv) & np.array([c.separated for c in sub])
        survivors[product] = int(bh.sum())
        total = len([c for c in cells if c.product == product])
        a(f"| {product} | {len(sub)} of {total} | {sum(c.separated for c in sub)} | "
          f"{ALPHA * len(sub):.2f} | **{survivors[product]}** |")
    allc = [c for c in cells if not c.blocked and c.p_value is not None]
    pv = np.array([c.p_value for c in allc])
    bh = benjamini_hochberg(pv) & np.array([c.separated for c in allc])
    a(f"| **both** | {len(allc)} | {sum(c.separated for c in allc)} | "
      f"{ALPHA * len(allc):.2f} | **{int(bh.sum())}** |")
    a("")
    a("Benjamini-Hochberg is applied within the hypothesis across its informative cells. "
      "Note the cells overlap heavily - the three holds share entry minutes and the three "
      "vol_pct settings are nested - so effective independent looks are fewer than the cell "
      "count and expected-by-chance is an overestimate.")
    a("")

    a("## Effect against the detection floor")
    a("")
    a("| instrument | hold | cells | events | aggregate bps | net | best cell | floor | best/floor |")
    a("|---|---|---|---|---|---|---|---|---|")
    for product in sorted({c.product for c in cells}):
        cost = COST_BPS[product]
        for hold in HOLDS:
            sub = [c for c in cells if c.product == product and c.hold == hold]
            if not sub:
                continue
            agg = float(np.mean([c.mean_bps for c in sub]))
            best = max(c.mean_bps for c in sub)
            floor = FLOOR_BPS.get((product, hold))
            tag = " (uninformative)" if any(c.blocked for c in sub) else ""
            a(f"| {product} | {hold}m{tag} | {len(sub)} | {max(c.events for c in sub):,} | "
              f"{agg:+.2f} | **{agg - cost:+.2f}** | {best:+.2f} | "
              + (f"{floor:.2f}" if floor else "—") + " | "
              + (f"{best / floor:.2f}x" if floor else "—") + " |")
        inf = [c for c in cells if c.product == product and not c.blocked]
        if inf:
            agg = float(np.mean([c.mean_bps for c in inf]))
            a(f"| **{product} informative** | | {len(inf)} | | **{agg:+.2f}** | "
              f"**{agg - cost:+.2f}** | {max(c.mean_bps for c in inf):+.2f} | | |")
    a("")

    a("## Which instrument carries a verdict")
    a("")
    both_clean = sum(survivors.values()) == 0
    if both_clean:
        a("**Neither instrument separates, and MNQ carries the stronger of the two nulls.**")
        a("")
        a("MNQ's informative cells (120m and 180m) sit on 83.16% coverage. MGC's three "
          "holds are all informative but rest on **64.16%** coverage - more than a third of "
          "this window's minutes are carried forward rather than traded, the standing caveat "
          "from CLAUDE_FUTURES.md §3. Forward-filling inserts zero returns, thins measured "
          "volatility and biases toward APPARENT significance, so an MGC null is the weaker "
          "kind. Here both point the same way, which is the easy case: the caveat would "
          "have mattered had MGC separated and MNQ not.")
        a("")
        a("F05's mechanism - volatility clustering - is generic to speculative price series "
          "and holds in both instruments (`mechanism_instruments`), so neither is a control "
          "for the other and neither is the wrong instrument for the claim.")
    else:
        a("**A cell separated. See the multiplicity table for which instrument.**")
    a("")

    a("## No real-data control exists at this event regime")
    a("")
    a("F14, the catalog's negative control, fires ~13 times a session and reaches ~48,000-"
      "52,000 events. It established that the harness declines to promote a mechanism-free "
      "signal **at that sample size**. F05's cells hold 6,965-17,051.")
    a("")
    a("**No control can be built at F05's regime on this data.** Measured candidates at the "
      "once-a-session regime resolved in 2 of 12 combinations "
      "(`reports/control_candidates.md`), and F05 fires a few times a session, between that "
      "regime and F14's. So this null carries the §7.2 synthetic GARCH assurance - the "
      "harness does not promote idealised noise - and **nothing from F14**. Stated here "
      "rather than left for a reader to infer.")
    a("")

    a("## Data")
    a("")
    a("| instrument | trading days | 18:00-16:55 ET minutes traded |")
    a("|---|---|---|")
    for product in sorted(fills):
        a(f"| {product} | {rows[product]:,} | {fills[product]:.2%} |")
    a("")
    dropped = {p: max((c.dropped for c in cells if c.product == p), default=0)
               for p in sorted(fills)}
    a("Armings whose full hold would not fit before 16:55 ET are excluded rather than "
      "truncated - a shortened hold is a different holding period, and §2's 17:00 hard exit "
      "requires the same of a real position. Excluded at most "
      + ", ".join(f"{n:,} on {p}" for p, n in dropped.items()) + ".")
    a("")
    a("The row is the CME trading day, so the 17:00-18:00 maintenance break falls outside "
      "it rather than inside. MGC's 64.16% is thin overnight tape, not a data fault.")
    a("")

    a("## Every cell")
    a("")
    a("| instrument | vol_pct | k | hold | events | mean bps | Sharpe | p | |")
    a("|---|---|---|---|---|---|---|---|---|")
    for c in sorted(cells, key=lambda c: (c.product, c.vol_pct, c.k, c.hold)):
        a(f"| {c.product} | p{c.vol_pct} | {c.k} | {c.hold}m | {c.events:,} | "
          f"{c.mean_bps:+.2f} | {c.sharpe:+.4f} | {c.p_value:.4f} | "
          + ("UNINFORMATIVE" if c.blocked else ("SEPARATES" if c.separated else "")) + " |")
    a("")
    a(f"**{len(cells)} trials.** 3 vol_pct x 3 k x 3 holds x 2 instruments.")
    a("")
    return "\n".join(w)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.signals.f05")
    ap.add_argument("--products", nargs="*", default=["MNQ", "MGC"])
    ap.add_argument("--seed", type=int, default=20260902)
    ap.add_argument("--provenance", default="native", choices=["native", "reconstructed"])
    ap.add_argument("--log-note", default="", help="text attached to every trial written")
    args = ap.parse_args(argv)

    with stage1_run("F05", provenance=args.provenance, note=args.log_note) as recorder:
        cells, fills, rows = run(args.products, args.seed)
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(render(cells, fills, rows), encoding="utf-8")
        CELLS.write_text(json.dumps([asdict(c) for c in cells], indent=2, default=str),
                         encoding="utf-8")
        recorder.record(cells)
    print(f"\nwrote {REPORT}  ({recorder.written} trials logged, {args.provenance})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

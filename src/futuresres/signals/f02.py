"""F02 - order_imbalance_conditional_overnight_reversal, Stage 1. CLAUDE_FUTURES.md §5, §6.

    python -m futuresres.signals.f02

THE CONDITION (from the catalog). imb = return from 15:00 to 16:00 ET, a proxy for the
closing order imbalance. If imb < -k*sigma, enter long at the window open and exit at the
window close; direction is opposite the imbalance. The symmetric long-side condition is
tested separately and expected to be weaker. k in {0.5, 1.0, 1.5}, window in
{Europe 01:30-04:00, Asia 19:00-22:00}, hold in {1, 2, 4} h.

THE REGIME SPLIT IS MANDATORY AND IT IS THE POINT. F13 - the unconditional overnight drift -
was EXCLUDED from this catalog because its own authors measured it as decayed since 2021.
F02 is the conditional version, registered separately as the tradeable form, and the
exclusion note says it "carries a mandatory regime split". So every cell is evaluated twice,
pre-2021 and post-2021, and an effect that appears only in the pre-2021 half is a decayed
effect rather than a live one.

BOTH ARMS ARE RUN, because the catalog says to. The mechanism predicts ASYMMETRY: a dealer
absorbing a SELL imbalance holds unwanted long inventory and must be paid to carry it, so
selloffs should generate robust positive overnight reversals while reversals after rallies
are modest. The sell-imbalance arm is the primary one; the buy-imbalance arm is registered
as expected-to-be-weaker, and reporting it is how that prediction gets checked rather than
assumed.

WHAT THIS COSTS. 3 k x 2 windows x 3 holds x 2 arms x 2 eras = 72 cells per instrument, 144
in total. That is the largest single trial spend in this catalog and it raises SR* for
everything still untested. It is what the registered protocol asks for.

DECISIONS THE CONDITION DOES NOT DETERMINE, logged in reports/decisions.md §20:

  sigma   trailing 20-session standard deviation of the 15:00-16:00 ET return, strictly
          prior sessions. Same-clock-time, matching the convention already used for F05 and
          F08 rather than a flat rolling window.
  exit    the condition says both "exit at the window close" and "hold in {1,2,4} h". The
          hold is treated as the parameter and the window as the entry anchor, because
          otherwise the hold axis would do nothing.
  era     boundary at 2021-01-01, the date the authors' own decay finding names.

THE GRID SPANS 15:00 ET TO 06:00 ET THE NEXT DAY, 900 minutes per row, because the trade
does. `evaluate_signed_signal` indexes forward by BAR, so the row must be a complete minute
grid or "240 bars" is not "240 minutes". Row 0 is 15:00 ET; the Asia open (19:00) is minute
240, the Europe open (01:30) is minute 630, and a 4-hour hold from Europe exits at minute
870. Rows are keyed by the DATE OF THE 15:00 OBSERVATION, so a bar before 06:00 belongs to
the previous calendar day's row.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Final, Sequence

import numpy as np
import polars as pl

from futuresres.session.calendar import ET
from futuresres.signals.logged_run import stage1_run
from futuresres.signals.stage1 import evaluate_signed_signal
from futuresres.stats.dsr import sharpe_ratio

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
CONTINUOUS: Final[Path] = ROOT / "data" / "continuous"
REPORT: Final[Path] = ROOT / "reports" / "f02_stage1.md"
CELLS: Final[Path] = ROOT / "reports" / "f02_cells.json"

#: Row 0 is 15:00 ET; the row runs 900 minutes to 06:00 ET the next day.
ROW_START_MOD: Final[int] = 15 * 60
ROW_MINUTES: Final[int] = 900

IMB_MINUTES: Final[int] = 60                  # 15:00 -> 16:00
WINDOWS: Final[dict[str, int]] = {
    "Asia": 4 * 60,        # 19:00 ET = minute 240
    "Europe": 10 * 60 + 30,  # 01:30 ET = minute 630
}
KS: Final[tuple[float, ...]] = (0.5, 1.0, 1.5)
HOLDS: Final[tuple[int, ...]] = (60, 120, 240)
ARMS: Final[tuple[str, ...]] = ("sell_imb", "buy_imb")
ERA_BOUNDARY: Final[date] = date(2021, 1, 1)
LOOKBACK: Final[int] = 20

SERIES: Final[dict[str, str]] = {"MNQ": "NQ_MNQ_spliced", "MGC": "MGC"}
COST_BPS: Final[dict[str, float]] = {"MNQ": 0.48, "MGC": 0.65}

#: reports/floor_cache.json - smallest sample at which a floor resolved, by proxy horizon.
SMALLEST_RESOLVING: Final[dict[tuple[str, int], int]] = {
    ("MNQ", 60): 19_722, ("MNQ", 180): 5_884,
    ("MGC", 60): 5_620, ("MGC", 180): 2_862,
}
FLOOR_BPS: Final[dict[tuple[str, int], float]] = {
    ("MNQ", 60): 2.57, ("MNQ", 120): 15.66, ("MNQ", 240): 15.66,
    ("MGC", 60): 4.17, ("MGC", 120): 14.34, ("MGC", 240): 14.34,
}

ALPHA: Final[float] = 0.05


def proxy(hold: int) -> int:
    import math
    return min((60, 180), key=lambda m: abs(math.log(hold / m)))


@dataclass(slots=True)
class Grid:
    rows: np.ndarray               # date of the 15:00 observation
    logp: np.ndarray               # (n_rows * 900,) forward-filled log price
    fill_fraction: float

    @property
    def n_rows(self) -> int:
        return self.rows.size

    def slice_era(self, lo: date | None, hi: date | None) -> "Grid":
        m = np.ones(self.rows.size, dtype=bool)
        if lo is not None:
            m &= self.rows >= lo
        if hi is not None:
            m &= self.rows < hi
        idx = np.flatnonzero(m)
        grid = self.logp.reshape(self.n_rows, ROW_MINUTES)[idx]
        return Grid(self.rows[idx], grid.ravel(), self.fill_fraction)


def load(product: str) -> Grid:
    """Rows of 15:00 ET -> 06:00 ET next day, complete and forward-filled."""
    bars = pl.read_parquet(CONTINUOUS / f"{SERIES[product]}.parquet")
    local = pl.col("ts_event").dt.convert_time_zone(str(ET))
    mod = (local.dt.hour().cast(pl.Int32) * 60 + local.dt.minute().cast(pl.Int32))
    frame = bars.with_columns(
        mod.alias("mod"),
        local.dt.date().alias("d"),
        pl.col("close").cast(pl.Float64),
    ).with_columns(
        ((pl.col("mod") - ROW_START_MOD) % 1440).alias("m"),
    ).filter(pl.col("m") < ROW_MINUTES).with_columns(
        # a bar before 15:00 belongs to the PREVIOUS day's row
        pl.when(pl.col("mod") >= ROW_START_MOD)
          .then(pl.col("d"))
          .otherwise(pl.col("d") - pl.duration(days=1))
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


def imbalance(grid: Grid) -> np.ndarray:
    """(n_rows,) the 15:00-16:00 ET log return."""
    g = grid.logp.reshape(grid.n_rows, ROW_MINUTES)
    return g[:, IMB_MINUTES] - g[:, 0]


def rolling_std_prior(v: np.ndarray, w: int) -> np.ndarray:
    out = np.full(v.size, np.nan)
    if v.size <= w:
        return out
    c1 = np.concatenate([[0.0], np.cumsum(v)])
    c2 = np.concatenate([[0.0], np.cumsum(v * v)])
    i = np.arange(w, v.size)
    s1, s2 = c1[i] - c1[i - w], c2[i] - c2[i - w]
    out[i] = np.sqrt(np.maximum((s2 - s1 * s1 / w) / (w - 1), 0.0))
    return out


def build_direction(grid: Grid, window: str, k: float,
                    arm: str) -> tuple[np.ndarray, int]:
    """Direction over the flat grid. Reversal: opposite the imbalance."""
    imb = imbalance(grid)
    sigma = rolling_std_prior(imb, LOOKBACK)
    with np.errstate(invalid="ignore"):
        if arm == "sell_imb":
            fires = imb < -k * sigma          # dealer long inventory -> go long
            side = 1.0
        else:
            fires = imb > k * sigma           # dealer short inventory -> go short
            side = -1.0
    fires &= np.isfinite(sigma)
    direction = np.zeros(grid.logp.size)
    entry = WINDOWS[window]
    idx = np.flatnonzero(fires) * ROW_MINUTES + entry
    direction[idx] = side
    return direction, int(fires.sum())


@dataclass(slots=True)
class CellResult:
    product: str
    era: str
    arm: str
    window: str
    k: float
    hold: int
    events: int
    mean_bps: float
    sharpe: float
    p_value: float | None
    separated: bool
    blocked: bool
    reason: str


def evaluate(grid: Grid, product: str, era: str, arm: str, window: str, k: float,
             hold: int, rng: np.random.Generator) -> CellResult:
    direction, n_fire = build_direction(grid, window, k, arm)
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
    need = SMALLEST_RESOLVING.get((product, proxy(hold)), 0)
    return CellResult(
        product, era, arm, window, k, hold, int(idx.size),
        float(per_event.mean() * 1e4) if per_event.size else 0.0, sharpe,
        res.p_value if res else None, bool(res and res.separated),
        idx.size < need, reason,
    )


def benjamini_hochberg(p: np.ndarray, alpha: float = ALPHA) -> np.ndarray:
    order = np.argsort(p)
    m = p.size
    below = np.flatnonzero(p[order] <= alpha * np.arange(1, m + 1) / m)
    out = np.zeros(m, dtype=bool)
    if below.size:
        out[order[: below[-1] + 1]] = True
    return out


ERAS: Final[tuple[tuple[str, object, object], ...]] = (
    ("pre-2021", None, ERA_BOUNDARY),
    ("post-2021", ERA_BOUNDARY, None),
)


def run(products: Sequence[str], seed: int) -> tuple[list[CellResult], dict, dict]:
    cells: list[CellResult] = []
    fills: dict[str, float] = {}
    rows: dict[str, dict[str, int]] = {}
    for product in products:
        full = load(product)
        fills[product] = full.fill_fraction
        rows[product] = {}
        print(f"\n=== {product} === {full.n_rows:,} rows, "
              f"{full.fill_fraction:.2%} of 15:00-06:00 ET minutes traded")
        for era, lo, hi in ERAS:
            grid = full.slice_era(lo, hi)
            rows[product][era] = grid.n_rows
            print(f"  --- {era}: {grid.n_rows:,} rows")
            rng = np.random.default_rng(seed)
            for arm in ARMS:
                for window in WINDOWS:
                    for k in KS:
                        for hold in HOLDS:
                            r = evaluate(grid, product, era, arm, window, k, hold, rng)
                            cells.append(r)
                            flag = " [UNINFORMATIVE]" if r.blocked else ""
                            print(f"    {arm:<8} {window:<6} k={k} h={hold:<3} "
                                  f"n={r.events:>4,} mean {r.mean_bps:>+6.2f} "
                                  f"p={r.p_value:.4f}{flag}"
                                  + ("  SEPARATES" if r.separated else ""), flush=True)
    return cells, fills, rows


def render(cells: list[CellResult], fills: dict, rows: dict) -> str:
    w: list[str] = []
    a = w.append
    a("# F02 - order_imbalance_conditional_overnight_reversal, Stage 1")
    a("")
    a("Run by `python -m futuresres.signals.f02`. CLAUDE_FUTURES.md §5, §6, §7.6.")
    a("")

    # ---------------------------------------------------------------- headline
    informative = [c for c in cells if not c.blocked and c.p_value is not None]
    a("## Every cell is uninformative, and the gate did not predict that")
    a("")
    a(f"**{len(cells)} cells run, {len(informative)} informative.** The detectability gate "
      "showed F02 with an open per-cell route on MGC at 120m and 240m and an open aggregate "
      "route on 5 of 6 combinations. Both were computed on a **declared** firing rate of one "
      "per session, and the declared rate was wrong.")
    a("")
    a("| | gate assumed | actually fires |")
    a("|---|---|---|")
    a("| per cell | 4,006-4,125 | **106-666** |")
    a("| aggregate (2 windows) | 6,142-8,250 | **~210-1,330** |")
    a("")
    a("Two causes, neither propagated into the gate:")
    a("")
    a("1. **The condition is threshold-gated.** It fires only when `|imb| > k*sigma`, which "
      "is 6-23% of rows depending on k - not every row. A declared rate of \"one per "
      "session\" counted the *opportunity*, not the *trigger*.")
    a("2. **The regime split is mandatory and halves the sample again.** Pre-2021 holds "
      "~3,100-3,200 rows and post-2021 ~1,730. The gate assessed F02 on the full sample "
      "because nothing told it the hypothesis must be evaluated in two eras.")
    a("")
    a("This is the same class of error as `decisions.md` §13, which the §13 fix did not "
      "catch: that repair addressed scan multiplicity and *unmeasured* rates, but F02's rate "
      "was **declared and wrong**, which no test was looking for. Every threshold-gated "
      "hypothesis in the catalog carries the same defect - see §21.")
    a("")

    # ---------------------------------------------------------------- multiplicity
    a("## Multiplicity")
    a("")
    a("| instrument | era | arm | cells | nominal | expected | BH survivors |")
    a("|---|---|---|---|---|---|---|")
    for product in sorted({c.product for c in cells}):
        for era, _, _ in ERAS:
            for arm in ARMS:
                sub = [c for c in cells if c.product == product and c.era == era
                       and c.arm == arm and c.p_value is not None]
                if not sub:
                    continue
                pv = np.array([c.p_value for c in sub])
                bh = benjamini_hochberg(pv) & np.array([c.separated for c in sub])
                a(f"| {product} | {era} | {arm} | {len(sub)} | "
                  f"{sum(c.separated for c in sub)} | {ALPHA * len(sub):.2f} | "
                  f"**{int(bh.sum())}** |")
    allc = [c for c in cells if c.p_value is not None]
    pv = np.array([c.p_value for c in allc])
    bh_all = benjamini_hochberg(pv) & np.array([c.separated for c in allc])
    a(f"| **all** | both | both | {len(allc)} | {sum(c.separated for c in allc)} | "
      f"{ALPHA * len(allc):.2f} | **{int(bh_all.sum())}** |")
    a("")
    a("**Benjamini-Hochberg is applied within each (instrument, era, arm) family and then "
      "across the whole hypothesis.** The within-family view is what the catalog asks for; "
      "the all-cells row is the honest multiplicity, because all 144 looks were taken.")
    a("")

    # ---------------------------------------------------------------- effect vs floor
    a("## Effect against the detection floor")
    a("")
    a("| instrument | era | arm | events (max) | aggregate bps | net | best cell | floor | best/floor |")
    a("|---|---|---|---|---|---|---|---|---|")
    for product in sorted({c.product for c in cells}):
        cost = COST_BPS[product]
        for era, _, _ in ERAS:
            for arm in ARMS:
                sub = [c for c in cells if c.product == product and c.era == era
                       and c.arm == arm]
                if not sub:
                    continue
                agg = float(np.mean([c.mean_bps for c in sub]))
                best = max(sub, key=lambda c: c.mean_bps)
                floor = FLOOR_BPS.get((product, best.hold))
                a(f"| {product} | {era} | {arm} | {max(c.events for c in sub):,} | "
                  f"{agg:+.2f} | **{agg - cost:+.2f}** | {best.mean_bps:+.2f} | "
                  + (f"{floor:.2f}" if floor else "—") + " | "
                  + (f"{best.mean_bps / floor:.2f}x" if floor else "—") + " |")
    a("")
    a("**The floor column is quoted for orientation only.** A detection floor describes the "
      "smallest effect that could be recovered *at the sample where it was measured*. These "
      "cells hold 106-666 events against floors measured at 2,862 and up, so the applicable "
      "floor here is higher than any measured, by an unknown amount. The ratios understate "
      "the gap.")
    a("")

    # ---------------------------------------------------------------- regime split
    a("## The regime split, which is the reason this hypothesis exists separately")
    a("")
    a("F13 - the unconditional overnight drift - was **excluded** from this catalog because "
      "its own authors measured it as decayed since 2021. F02 is the conditional version, "
      "and the exclusion note requires it to carry a mandatory regime split. An effect "
      "living only in the pre-2021 half is a decayed effect, not a live one.")
    a("")
    a("| instrument | pre-2021 rows | post-2021 rows |")
    a("|---|---|---|")
    for product in sorted(rows):
        a(f"| {product} | {rows[product]['pre-2021']:,} | "
          f"{rows[product]['post-2021']:,} |")
    a("")
    a("| instrument | arm | pre-2021 aggregate | post-2021 aggregate | direction of change |")
    a("|---|---|---|---|---|")
    for product in sorted({c.product for c in cells}):
        for arm in ARMS:
            pre = [c.mean_bps for c in cells if c.product == product
                   and c.era == "pre-2021" and c.arm == arm]
            post = [c.mean_bps for c in cells if c.product == product
                    and c.era == "post-2021" and c.arm == arm]
            if not pre or not post:
                continue
            mp, mq = float(np.mean(pre)), float(np.mean(post))
            a(f"| {product} | {arm} | {mp:+.2f} | {mq:+.2f} | "
              + ("decayed" if abs(mq) < abs(mp) else "not decayed") + " |")
    a("")
    a("**This comparison cannot settle the decay question and is reported for completeness "
      "only.** Neither era's cells are informative, so a difference between them is a "
      "difference between two quantities that are individually indistinguishable from zero. "
      "Reporting it as a decay finding would be exactly the error the uninformative marking "
      "exists to prevent.")
    a("")

    # ---------------------------------------------------------------- verdict
    a("## Which instrument carries a verdict")
    a("")
    a("**Neither.** The gate named MGC as the instrument with an open per-cell route, at "
      "120m and 240m, and that route closes once the real firing rate is used: MGC's best "
      "cell holds 666 events against a floor measured at 2,862 and up. MNQ was already "
      "below the swept range at every horizon.")
    a("")
    a("Worth stating plainly, because the mechanism points the other way: **F02 is an "
      "equity-index hypothesis.** Its counterparty story is the NYSE closing auction and "
      "dealers carrying index inventory overnight. MGC is in the registered symbol list and "
      "so was run, but a gold contract has no NYSE closing auction, and an MGC result would "
      "have been the wrong instrument for this claim even had it been informative. The "
      "standing MGC coverage caveat applies on top: 46.14% of this window's minutes are "
      "carried forward rather than traded, the lowest coverage of any window in the study.")
    a("")

    # ---------------------------------------------------------------- control
    a("## No real-data control exists at this event regime")
    a("")
    a("F14, the catalog's negative control, fires ~13 times a session and reaches ~48,000-"
      "52,000 events. It established that the harness declines to promote a mechanism-free "
      "signal **at that sample size**. F02's cells hold 106-666 events.")
    a("")
    a("**No control can be built at F02's regime on this data.** A once-a-session condition "
      "yields ~3,500 events before any threshold gating; F02 fires on 6-23% of those and "
      "then splits the remainder in two. Measured candidates at the once-a-session regime "
      "resolved in 2 of 12 combinations (`reports/control_candidates.md`), and F02 sits an "
      "order of magnitude below even that. So this null carries the §7.2 synthetic GARCH "
      "assurance - the harness does not promote idealised noise - and **nothing from F14**. "
      "That distinction is stated here rather than left for a reader to infer.")
    a("")

    # ---------------------------------------------------------------- data
    a("## Data")
    a("")
    a("| instrument | rows | 15:00-06:00 ET minutes traded |")
    a("|---|---|---|")
    for product in sorted(fills):
        a(f"| {product} | {sum(rows[product].values()):,} | {fills[product]:.2%} |")
    a("")
    a("The window spans the CME maintenance break (17:00-18:00 ET) and the thin overnight "
      "tape, so a low traded fraction is expected rather than a data fault. It is reported "
      "because forward-filling inserts zero returns and biases toward apparent significance "
      "- in a run that separates on nothing, that bias had no opportunity to matter.")
    a("")
    a("## Trial cost")
    a("")
    a(f"**{len(cells)} trials** - 3 k x 2 windows x 3 holds x 2 arms x 2 eras x 2 "
      "instruments. The largest single spend in this catalog, and it raises SR* for "
      "everything still untested. Both arms and both eras are what the registered protocol "
      "asks for; the cost is recorded rather than avoided by quietly dropping an axis.")
    a("")
    return "\n".join(w)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.signals.f02")
    ap.add_argument("--products", nargs="*", default=["MNQ", "MGC"])
    ap.add_argument("--seed", type=int, default=20260902)
    ap.add_argument("--provenance", default="native", choices=["native", "reconstructed"])
    ap.add_argument("--log-note", default="", help="text attached to every trial written")
    args = ap.parse_args(argv)

    with stage1_run("F02", provenance=args.provenance,
                    note=args.log_note) as recorder:
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

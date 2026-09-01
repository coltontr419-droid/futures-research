"""F03 - half_hour_periodicity, Stage 1. CLAUDE_FUTURES.md §5 Stage 1.

    python -m futuresres.signals.f03

THE CONDITION (from the catalog). For each half-hour slot s in the RTH session,
hist = mean return of slot s over the trailing N days. If |hist| > threshold and the
trailing t-stat is significant, enter at the slot open in sign(hist) direction and exit at
the slot close. N in {10, 20, 40} days, threshold in {0.5, 1.0, 1.5} x slot sigma, all 13
RTH slots.

WHY THIS ONE IS WORTH RUNNING. `reports/detectability.md` clears it on both instruments —
it is one of the few that does. It fires 13 times a session rather than once, so it reaches
53,625 usable events on MNQ and 52,078 on MGC, comfortably above the samples where the
detection floor resolves (2.57 bps on MNQ, 4.17 on MGC). Most of the catalog is blocked by
event rate; this is not.

ENTRY AND EXIT ARE THE SLOT BOUNDARIES, so the trade return IS that slot's return on that
day. There is no exit rule to tune and no path dependence: a 30-minute time exit, which is
what §9 says to prefer.

THE SESSION GRID IS REINDEXED AND FORWARD-FILLED WITHIN RTH. `evaluate_signed_signal`
indexes the forward window by BAR, not by minute, so on a series with untraded minutes "30
bars" would not be "30 minutes" and slot boundaries would drift. Each RTH session is
therefore reindexed to exactly 390 one-minute bars with the last trade carried forward. The
fill fraction is measured and reported rather than assumed harmless — forward-filling
inserts zero returns, which thins measured volatility, and a low fill rate would inflate
apparent significance.

MULTIPLICITY IS THE WHOLE PROBLEM HERE AND THE CATALOG SAYS SO. 13 slots x 3 N x 3
thresholds is 117 cells per instrument. At alpha = 0.05 that is 5.9 hits by chance before
any effect exists. Benjamini-Hochberg is applied WITHIN the hypothesis, and the aggregate
across slots is reported next to the best slot, because a single profitable slot among
thirteen is what selection looks like.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Final, Sequence

import numpy as np
import polars as pl

from futuresres.session.calendar import ET
from futuresres.signals.stage1 import evaluate_signed_signal
from futuresres.stats.dsr import sharpe_ratio

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
CONTINUOUS: Final[Path] = ROOT / "data" / "continuous"
REPORT: Final[Path] = ROOT / "reports" / "f03_stage1.md"
CELLS: Final[Path] = ROOT / "reports" / "f03_cells.json"

RTH_START_MIN: Final[int] = 9 * 60 + 30          # 09:30 ET
RTH_MINUTES: Final[int] = 390                    # to 16:00 ET
SLOT_MINUTES: Final[int] = 30
N_SLOTS: Final[int] = RTH_MINUTES // SLOT_MINUTES  # 13

LOOKBACKS: Final[tuple[int, ...]] = (10, 20, 40)
THRESHOLDS: Final[tuple[float, ...]] = (0.5, 1.0, 1.5)

#: MNQ hypotheses read the spliced NQ+MNQ series — §3 built it so index work gets sixteen
#: years rather than seven, and F03 needs the sessions.
SERIES: Final[dict[str, str]] = {"MNQ": "NQ_MNQ_spliced", "MGC": "MGC"}

#: §4, round trip, commission plus estimated spread.
COST_BPS: Final[dict[str, float]] = {"MNQ": 0.48, "MGC": 0.65}

#: reports/calibration.md — the measured floor at this horizon, in bps.
FLOOR_BPS: Final[dict[str, float]] = {"MNQ": 2.57, "MGC": 4.17}

ALPHA: Final[float] = 0.05


@dataclass(slots=True)
class Grid:
    """The RTH session grid: complete, gap-free, one row per session."""

    sessions: np.ndarray            # date per session
    logp: np.ndarray                # (n_sessions * 390,) forward-filled log price
    fill_fraction: float            # share of minutes carried forward rather than traded

    @property
    def n_sessions(self) -> int:
        return self.sessions.size

    def slot_returns(self) -> np.ndarray:
        """(n_sessions, 13) log return from each slot's open to its close."""
        grid = self.logp.reshape(self.n_sessions, RTH_MINUTES)
        opens = grid[:, ::SLOT_MINUTES]                       # first minute of each slot
        closes = grid[:, SLOT_MINUTES - 1::SLOT_MINUTES]      # last minute of each slot
        return closes - opens

    def slot_open_index(self, slot: int) -> np.ndarray:
        """Flat indices of every session's open bar for `slot`."""
        return np.arange(self.n_sessions) * RTH_MINUTES + slot * SLOT_MINUTES


def load(product: str) -> Grid:
    """Reindex to a complete RTH minute grid, forward-filling untraded minutes."""
    bars = pl.read_parquet(CONTINUOUS / f"{SERIES[product]}.parquet")
    local = pl.col("ts_event").dt.convert_time_zone(str(ET))
    rth = bars.with_columns(
        (local.dt.hour().cast(pl.Int32) * 60
         + local.dt.minute().cast(pl.Int32) - RTH_START_MIN).alias("m"),
        local.dt.date().alias("day"),
    ).filter((pl.col("m") >= 0) & (pl.col("m") < RTH_MINUTES))

    # Columns are extracted separately: a mixed-dtype `.to_numpy()` on the frame coerces
    # dates to float and the session lookup then fails on a float key.
    days = rth.get_column("day").to_numpy()
    minutes = rth.get_column("m").to_numpy().astype(np.int64)
    closes = rth.get_column("close").to_numpy().astype(float)

    sessions = np.unique(days)
    session_index = np.searchsorted(sessions, days)

    flat = np.full(sessions.size * RTH_MINUTES, np.nan)
    flat[session_index * RTH_MINUTES + minutes] = closes
    traded = int(np.isfinite(flat).sum())

    # Forward-fill WITHIN each session. A session's leading gap takes its first trade;
    # carrying across a session boundary would import the previous day's close.
    grid = flat.reshape(sessions.size, RTH_MINUTES)
    ok = np.isfinite(grid)
    idx = np.where(ok, np.arange(RTH_MINUTES)[None, :], 0)
    np.maximum.accumulate(idx, axis=1, out=idx)
    filled = np.take_along_axis(grid, idx, axis=1)
    # rows whose first minutes never traded still hold NaN; back-fill those from the first
    first = np.argmax(ok, axis=1)
    has_any = ok.any(axis=1)
    for i in np.flatnonzero(has_any & ~np.isfinite(filled[:, 0])):
        filled[i, : first[i]] = grid[i, first[i]]

    keep = np.isfinite(filled).all(axis=1)
    filled, sessions = filled[keep], sessions[keep]
    return Grid(sessions, np.log(filled).ravel(),
                float(traded) / max(filled.size, 1))


def build_direction(grid: Grid, slot: int, lookback: int, threshold: float,
                    t_stat_form: bool) -> np.ndarray:
    """Direction array over the flat RTH grid for one (slot, N, threshold) cell.

    `t_stat_form` selects between the two readings of the catalog's threshold — see
    `THRESHOLD_READING` in the report. Strictly trailing: session d uses sessions
    d-N .. d-1, never d itself.
    """
    slots = grid.slot_returns()[:, slot]
    n = slots.size
    direction = np.zeros(grid.logp.size)
    if n <= lookback + 1:
        return direction

    c1 = np.concatenate([[0.0], np.cumsum(slots)])
    c2 = np.concatenate([[0.0], np.cumsum(slots * slots)])
    d = np.arange(lookback, n)
    s1 = c1[d] - c1[d - lookback]
    s2 = c2[d] - c2[d - lookback]
    hist = s1 / lookback
    var = np.maximum((s2 - s1 * s1 / lookback) / (lookback - 1), 0.0)
    sigma = np.sqrt(var)

    scale = sigma / np.sqrt(lookback) if t_stat_form else sigma
    with np.errstate(invalid="ignore", divide="ignore"):
        fires = (scale > 0) & (np.abs(hist) > threshold * scale)

    entries = grid.slot_open_index(slot)[d[fires]]
    direction[entries] = np.sign(hist[fires])
    return direction


@dataclass(slots=True)
class CellResult:
    product: str
    slot: int
    lookback: int
    threshold: float
    events: int
    mean_bps: float
    sharpe: float
    p_value: float | None
    hit_rate: float | None
    separated: bool
    reason: str


def evaluate(grid: Grid, product: str, slot: int, lookback: int, threshold: float,
             t_stat_form: bool, rng: np.random.Generator) -> CellResult:
    direction = build_direction(grid, slot, lookback, threshold, t_stat_form)
    idx = np.flatnonzero(direction)
    idx = idx[idx + SLOT_MINUTES - 1 < grid.logp.size]
    per_event = (direction[idx]
                 * (grid.logp[idx + SLOT_MINUTES - 1] - grid.logp[idx])) if idx.size else np.array([])
    sharpe = (float(sharpe_ratio(per_event))
              if per_event.size >= 2 and per_event.std(ddof=1) > 0 else 0.0)
    res = None
    reason = f"only {idx.size} events"
    if idx.size >= 2:
        try:
            res = evaluate_signed_signal(direction, grid.logp, SLOT_MINUTES - 1, rng=rng,
                                         n_bootstrap=800)
            reason = res.reason
        except ValueError as exc:
            reason = str(exc)
    return CellResult(
        product, slot, lookback, threshold, int(idx.size),
        float(per_event.mean() * 1e4) if per_event.size else 0.0, sharpe,
        res.p_value if res else None, res.hit_rate if res else None,
        bool(res and res.separated), reason,
    )


def benjamini_hochberg(p: np.ndarray, alpha: float = ALPHA) -> np.ndarray:
    order = np.argsort(p)
    m = p.size
    below = np.flatnonzero(p[order] <= alpha * np.arange(1, m + 1) / m)
    out = np.zeros(m, dtype=bool)
    if below.size:
        out[order[: below[-1] + 1]] = True
    return out


def firing_probe(grid: Grid, product: str) -> dict:
    """Both readings of the threshold, measured. See the decision in the report."""
    out: dict[str, dict] = {}
    for label, t_form in (("literal (x slot sigma)", False), ("t-stat (x standard error)", True)):
        counts = []
        for lookback in LOOKBACKS:
            for threshold in THRESHOLDS:
                total = sum(
                    int(np.count_nonzero(
                        build_direction(grid, s, lookback, threshold, t_form)))
                    for s in range(N_SLOTS)
                )
                counts.append(total)
        out[label] = {"min": min(counts), "max": max(counts),
                      "median": int(np.median(counts))}
    return out


#: THE THRESHOLD READING — a decision, measured rather than assumed.
#:
#: The catalog says "threshold in {0.5, 1.0, 1.5} x slot sigma" AND "the trailing t-stat is
#: significant". Taken literally the first clause compares a MEAN OF N DAYS against a
#: ONE-DAY sigma, which at N=40 and threshold=1.5 demands 9.5 standard errors. Measured
#: firing counts across all 13 slots and all nine (N, threshold) cells:
#:
#:     literal   hist vs threshold*sigma            min 0      median 40      max 6,818
#:     t-stat    hist vs threshold*sigma/sqrt(N)    min 5,756  median 14,818  max 29,465
#:
#: The literal reading is vacuous — a median of 40 events across 13 slots and ~3,500
#: sessions is not a hypothesis anyone could test. It also makes the second clause
#: redundant, since 9.5 standard errors is already "significant" by any standard.
#:
#: DECIDED: the t-stat reading. The threshold is on the standard error of the trailing mean,
#: which is what makes the two clauses one clause and what the Heston-Korajczyk-Sadka
#: methodology the catalog cites actually does. Recorded because it changes the hypothesis
#: being tested; the literal reading stays available via --literal.
T_STAT_FORM: Final[bool] = True


def run(products: Sequence[str], t_stat_form: bool, seed: int) -> list[CellResult]:
    out: list[CellResult] = []
    for product in products:
        grid = load(product)
        print(f"\n=== {product} === {grid.n_sessions:,} sessions, "
              f"{grid.fill_fraction:.2%} of RTH minutes traded")
        rng = np.random.default_rng(seed)
        for lookback in LOOKBACKS:
            for threshold in THRESHOLDS:
                for slot in range(N_SLOTS):
                    out.append(evaluate(grid, product, slot, lookback, threshold,
                                        t_stat_form, rng))
                block = out[-N_SLOTS:]
                p_min = min((c.p_value for c in block if c.p_value is not None),
                            default=float("nan"))
                print(f"  N={lookback:<3} thr={threshold:<4} "
                      f"{sum(c.events for c in block):>7,} events over 13 slots, "
                      f"min p={p_min:.4f}, {sum(c.separated for c in block)} nominal hits")
    return out


def render(cells: list[CellResult], fills: dict[str, float], sessions: dict[str, int],
           t_stat_form: bool) -> str:
    w: list[str] = []
    a = w.append
    per_instrument = N_SLOTS * len(LOOKBACKS) * len(THRESHOLDS)
    a("# F03 - half_hour_periodicity, Stage 1")
    a("")
    a("Run by `python -m futuresres.signals.f03`. CLAUDE_FUTURES.md section 5 Stage 1, 6.")
    a("")
    a(f"- **Grid:** 13 RTH slots x 3 lookbacks x 3 thresholds = {per_instrument} cells per "
      f"instrument, {len(cells)} total")
    a("- **Instruments:** MNQ (spliced NQ+MNQ) and MGC")
    a("- **Horizon:** 30 minutes. Entry at the slot open, exit at the slot close, so the "
      "trade return IS that slot's return that day - a time exit, per section 9")
    a("")

    a("## The threshold reading - a decision")
    a("")
    a("The catalog writes the threshold as \"x slot sigma\" but also requires a significant "
      "trailing t-stat. Read literally, the first clause compares a mean of N days against a "
      "ONE-DAY sigma: at N=40, threshold=1.5 that demands 9.5 standard errors. Measured "
      "across all 13 slots and all nine (N, threshold) cells:")
    a("")
    a("| reading | min events | median | max |")
    a("|---|---|---|---|")
    a("| literal, mean vs `threshold * sigma` | 0 | **40** | 6,818 |")
    a("| t-stat, mean vs `threshold * sigma/sqrt(N)` | 5,756 | **14,818** | 29,465 |")
    a("")
    a("**The literal reading is vacuous** - 40 events across 13 slots and ~3,500 sessions is "
      "not a testable hypothesis, and it renders the t-stat clause redundant. "
      + ("The **t-stat reading** is used below."
         if t_stat_form else "The **literal** reading is used below."))
    a("")

    a("## Data caveat")
    a("")
    a("| instrument | sessions | RTH minutes actually traded |")
    a("|---|---|---|")
    for prod in sorted(fills):
        a(f"| {prod} | {sessions[prod]:,} | **{fills[prod]:.2%}** |")
    a("")
    a("The RTH grid is reindexed to exactly 390 minutes per session with the last trade "
      "carried forward, because the evaluator indexes its forward window by BAR - on a "
      "series with untraded minutes, \"30 bars\" would not be \"30 minutes\" and every slot "
      "boundary would drift.")
    a("")
    a("**MGC trades only ~71% of RTH minutes, so nearly three in ten of its bars are carried "
      "rather than traded.** Forward-filling inserts zero returns, which thins measured "
      "volatility and can inflate apparent significance. The MGC result below must be read "
      "with that in mind. MNQ at 98% needs no such qualification.")
    a("")

    for product in sorted({c.product for c in cells}):
        sub = [c for c in cells if c.product == product]
        scored = [c for c in sub if c.p_value is not None and np.isfinite(c.p_value)]
        p = np.array([c.p_value for c in scored])
        bh = benjamini_hochberg(p) & np.array([c.separated for c in scored])
        cost = COST_BPS[product]
        floor = FLOOR_BPS[product]

        a(f"## {product}")
        a("")
        a("### Multiplicity")
        a("")
        a("| | |")
        a("|---|---|")
        a(f"| cells scored | {len(scored)} of {len(sub)} |")
        a(f"| **nominal separations** | **{sum(c.separated for c in scored)}** |")
        a(f"| expected by chance at alpha={ALPHA} | **{ALPHA * len(scored):.1f}** |")
        a(f"| **BH survivors at FDR {ALPHA}** | **{int(bh.sum())}** |")
        a(f"| smallest p | {p.min():.4f} (BH rank-1 threshold {ALPHA / len(scored):.6f}) |")
        a("")

        a("### Per slot, and the selection check")
        a("")
        a(f"Cost floor **{cost} bps**; measured detection floor **{floor} bps** "
          f"(`reports/calibration.md`).")
        a("")
        a("| slot | ET window | events | gross bps | **net bps** | best cell gross | nominal hits |")
        a("|---|---|---|---|---|---|---|")
        for slot in range(N_SLOTS):
            cs = [c for c in sub if c.slot == slot]
            gross = float(np.mean([c.mean_bps for c in cs])) if cs else 0.0
            best = max((c.mean_bps for c in cs), default=0.0)
            start = RTH_START_MIN + slot * SLOT_MINUTES
            end = start + SLOT_MINUTES
            a(f"| {slot} | {start // 60:02d}:{start % 60:02d}-{end // 60:02d}:{end % 60:02d} "
              f"| {sum(c.events for c in cs):,} | {gross:+.2f} | **{gross - cost:+.2f}** | "
              f"{best:+.2f} | {sum(c.separated for c in cs)} |")
        agg = float(np.mean([c.mean_bps for c in sub]))
        best_all = max(c.mean_bps for c in sub)
        a(f"| **ALL SLOTS** | 09:30-16:00 | {sum(c.events for c in sub):,} | "
          f"**{agg:+.2f}** | **{agg - cost:+.2f}** | {best_all:+.2f} | "
          f"{sum(c.separated for c in sub)} |")
        a("")
        a(f"**Aggregate across all {len(sub)} cells: {agg:+.2f} bps gross, {agg - cost:+.2f} "
          f"net of the {cost} bps cost floor.** The best single cell reaches "
          f"{best_all:+.2f} gross. The gap between those two numbers is the size of the "
          f"selection effect, and the aggregate is the one nobody chose after the fact.")
        a("")
        if bh.sum():
            a("### Cells surviving BH")
            a("")
            a("| slot | N | threshold | events | gross bps | net bps | vs floor | p |")
            a("|---|---|---|---|---|---|---|---|")
            for c, keep in zip(scored, bh):
                if not keep:
                    continue
                a(f"| {c.slot} | {c.lookback} | {c.threshold} | {c.events:,} | "
                  f"{c.mean_bps:+.2f} | **{c.mean_bps - cost:+.2f}** | "
                  f"{c.mean_bps / floor:.2f}x | {c.p_value:.5f} |")
            a("")
    return "\n".join(w)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.signals.f03")
    ap.add_argument("--products", nargs="*", default=["MNQ", "MGC"])
    ap.add_argument("--seed", type=int, default=20260830)
    ap.add_argument("--literal", action="store_true",
                    help="use the literal 'x slot sigma' threshold (fires ~40 times)")
    args = ap.parse_args(argv)

    t_form = not args.literal
    grids = {prod: load(prod) for prod in args.products}
    fills = {k: g.fill_fraction for k, g in grids.items()}
    sessions = {k: g.n_sessions for k, g in grids.items()}

    cells = run(args.products, t_form, args.seed)

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(render(cells, fills, sessions, t_form), encoding="utf-8")
    CELLS.write_text(json.dumps([asdict(c) for c in cells], indent=2, default=str),
                     encoding="utf-8")
    print(f"\nwrote {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

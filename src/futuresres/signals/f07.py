"""F07 - gold_session_specific_momentum, Stage 1. CLAUDE_FUTURES.md §5 Stage 1, §6.

    python -m futuresres.signals.f07

THE CONDITION (from the catalog). For MGC, regress the last-half-hour return on each of the
first 12 half-hour returns separately and identify which slot predicts, if any. Compare
against MNQ's slot structure. slot in {1..12}, hold in {30, 60, 90} min.

READ THE DETECTABILITY REPORT BEFORE READING ANY NUMBER BELOW. Under the corrected gate
(`reports/detectability.md`, `reports/decisions.md` §13) **F07 has no route to a verdict at
any level, on either instrument.** Every number this module produces is descriptive. None of
it is evidence for or against the mechanism.

    per cell    ~4,000 events against a swept range starting at 19,722 - BELOW SWEPT RANGE
    aggregate   ~4,000 events - BELOW SWEPT RANGE

WHY THE AGGREGATE DOES NOT RESCUE IT, WHEN IT RESCUES F03. A scan whose cells are
individually underpowered can usually pool them: F03's 13 half-hour slots are 13 DISJOINT
trades, so its pooled series really does hold 13x the observations and its aggregate is
powered even though no single cell is. F07 cannot do this. Its 12 slots are twelve
PREDICTORS OF ONE TARGET - the catalog regresses the LAST half-hour on each of the first
twelve - so every cell enters on the same 15:30 minute of the same session. Pooling them
stacks twelve correlated readings of one ~4,000-session sample rather than accumulating
48,000 independent ones. Counting that overlap as sample would be the same error the gate
was just corrected for, one level up.

IT IS RUN ANYWAY, AND THE TRIALS ARE COUNTED. The looks happen, so they enter N: 72 cells
against the catalog's shared multiple-testing budget, raising SR* for every hypothesis still
untested. That cost is real and is recorded rather than hidden by declining to log it. What
is NOT recorded is a verdict, because the sample cannot support one.

is_scan: true. Per the registry, a positive result here is a LEAD requiring re-registration
as its own hypothesis with its own pre-committed grid - never a candidate to promote. Under
the gate above, this run cannot even produce a lead.

THE REDESIGN THAT WOULD MAKE IT TESTABLE is recorded in the report: enter at the CLOSE of
slot s and hold h minutes, rather than always entering at 15:30. That makes the 12 positions
disjoint, restores a ~48,000-event aggregate, and moves F07 from unresolvable to resolvable.
It is a different hypothesis from the catalog's and would need registering as one.

THE WINDOW IS 09:30-17:10 ET. `evaluate_signed_signal` indexes its forward window by BAR, so
the series must be a complete minute grid or "90 bars" is not "90 minutes". The window spans
the first slot open through the longest hold's exit (15:30 + 90 = 17:00) and nothing else.
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

from futuresres.session.calendar import ET
from futuresres.signals.stage1 import evaluate_signed_signal
from futuresres.stats.dsr import sharpe_ratio

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
CONTINUOUS: Final[Path] = ROOT / "data" / "continuous"
REPORT: Final[Path] = ROOT / "reports" / "f07_stage1.md"
CELLS: Final[Path] = ROOT / "reports" / "f07_cells.json"

WINDOW_START: Final[int] = 9 * 60 + 30       # 09:30 ET
WINDOW_MINUTES: Final[int] = 460             # through 17:10 ET
SLOT_MINUTES: Final[int] = 30
N_SLOTS: Final[int] = 12                     # 09:30 -> 15:30
ENTRY_MINUTE: Final[int] = N_SLOTS * SLOT_MINUTES   # 360 = 15:30 ET

HOLDS: Final[tuple[int, ...]] = (30, 60, 90)

SERIES: Final[dict[str, str]] = {"MNQ": "NQ_MNQ_spliced", "MGC": "MGC"}
COST_BPS: Final[dict[str, float]] = {"MNQ": 0.48, "MGC": 0.65}

#: sigma per bar at each hold, from reports/kurtosis.md.
SIGMA_BPS: Final[dict[tuple[str, int], float]] = {
    ("MNQ", 30): 21.4, ("MNQ", 60): 30.4, ("MNQ", 90): 37.2,
    ("MGC", 30): 18.2, ("MGC", 60): 26.2, ("MGC", 90): 33.5,
}

#: reports/detectability.md. EVERY combination is below the swept range, per-cell AND
#: aggregate, so this is a constant rather than a lookup - and it is deliberately not a
#: dict, so that nothing here can accidentally read as "some cells are informative".
ALL_COMBINATIONS_BLOCKED: Final[bool] = True
SMALLEST_RESOLVING_N: Final[int] = 19_722

ALPHA: Final[float] = 0.05


@dataclass(slots=True)
class Grid:
    sessions: np.ndarray
    logp: np.ndarray
    fill_fraction: float

    @property
    def n_sessions(self) -> int:
        return self.sessions.size

    def slot_returns(self) -> np.ndarray:
        """(n_sessions, 12) boundary-to-boundary log return of each half-hour slot."""
        grid = self.logp.reshape(self.n_sessions, WINDOW_MINUTES)
        bounds = grid[:, : ENTRY_MINUTE + 1 : SLOT_MINUTES]      # 13 boundaries
        return np.diff(bounds, axis=1)


def load(product: str) -> Grid:
    """Complete 09:30-17:10 ET minute grid, forward-filled within each session."""
    bars = pl.read_parquet(CONTINUOUS / f"{SERIES[product]}.parquet")
    local = pl.col("ts_event").dt.convert_time_zone(str(ET))
    win = bars.with_columns(
        (local.dt.hour().cast(pl.Int32) * 60
         + local.dt.minute().cast(pl.Int32) - WINDOW_START).alias("m"),
        local.dt.date().alias("day"),
    ).filter((pl.col("m") >= 0) & (pl.col("m") < WINDOW_MINUTES))

    days = win.get_column("day").to_numpy()
    minutes = win.get_column("m").to_numpy().astype(np.int64)
    closes = win.get_column("close").to_numpy().astype(float)

    sessions = np.unique(days)
    flat = np.full(sessions.size * WINDOW_MINUTES, np.nan)
    flat[np.searchsorted(sessions, days) * WINDOW_MINUTES + minutes] = closes
    traded = int(np.isfinite(flat).sum())

    grid = flat.reshape(sessions.size, WINDOW_MINUTES)
    ok = np.isfinite(grid)
    idx = np.where(ok, np.arange(WINDOW_MINUTES)[None, :], 0)
    np.maximum.accumulate(idx, axis=1, out=idx)
    filled = np.take_along_axis(grid, idx, axis=1)
    first = np.argmax(ok, axis=1)
    for i in np.flatnonzero(ok.any(axis=1) & ~np.isfinite(filled[:, 0])):
        filled[i, : first[i]] = grid[i, first[i]]

    keep = np.isfinite(filled).all(axis=1)
    filled, sessions = filled[keep], sessions[keep]
    return Grid(sessions, np.log(filled).ravel(), float(traded) / max(filled.size, 1))


def build_direction(grid: Grid, slot: int) -> np.ndarray:
    """Continuation on slot `slot`, entered at 15:30 ET. Zero where the slot did not move."""
    slots = grid.slot_returns()[:, slot]
    direction = np.zeros(grid.logp.size)
    entries = np.arange(grid.n_sessions) * WINDOW_MINUTES + ENTRY_MINUTE
    direction[entries] = np.sign(slots)
    return direction


@dataclass(slots=True)
class CellResult:
    product: str
    slot: int
    slot_label: str
    hold: int
    events: int
    mean_bps: float
    sharpe: float
    p_value: float | None
    hit_rate: float | None
    separated: bool
    blocked: bool
    reason: str


def slot_label(slot: int) -> str:
    start = WINDOW_START + slot * SLOT_MINUTES
    end = start + SLOT_MINUTES
    return f"{start // 60:02d}:{start % 60:02d}-{end // 60:02d}:{end % 60:02d}"


def evaluate(grid: Grid, product: str, slot: int, hold: int,
             rng: np.random.Generator) -> CellResult:
    direction = build_direction(grid, slot)
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
        product, slot, slot_label(slot), hold, int(idx.size),
        float(per_event.mean() * 1e4) if per_event.size else 0.0, sharpe,
        res.p_value if res else None, res.hit_rate if res else None,
        bool(res and res.separated), ALL_COMBINATIONS_BLOCKED, reason,
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
    sessions: dict[str, int] = {}
    for product in products:
        grid = load(product)
        fills[product] = grid.fill_fraction
        sessions[product] = grid.n_sessions
        print(f"\n=== {product} === {grid.n_sessions:,} sessions, "
              f"{grid.fill_fraction:.2%} of 09:30-17:10 ET minutes traded")
        rng = np.random.default_rng(seed)
        for slot in range(N_SLOTS):
            for hold in HOLDS:
                r = evaluate(grid, product, slot, hold, rng)
                cells.append(r)
                print(f"  slot {slot + 1:>2} {r.slot_label} hold={hold:<3} "
                      f"n={r.events:>5,}  mean {r.mean_bps:>+6.2f} bps  "
                      f"p={r.p_value:.4f}" if r.p_value is not None else
                      f"  slot {slot + 1:>2} {r.slot_label} hold={hold:<3}  {r.reason}")
    return cells, fills, sessions


def render(cells: list[CellResult], fills: dict, sessions: dict) -> str:
    w: list[str] = []
    a = w.append
    a("# F07 - gold_session_specific_momentum, Stage 1")
    a("")
    a("Run by `python -m futuresres.signals.f07`. CLAUDE_FUTURES.md §5 Stage 1, §6.")
    a("")
    a("## Nothing below is evidence")
    a("")
    a("Under the corrected detectability gate (`reports/detectability.md`, "
      "`reports/decisions.md` §13) **F07 has no route to a verdict at any level, on either "
      "instrument.** Every figure in this report is descriptive.")
    a("")
    a("| level | usable events | smallest sample that resolved a floor | status |")
    a("|---|---|---|---|")
    for product in sorted(sessions):
        a(f"| {product} per cell | ~{sessions[product]:,} | {SMALLEST_RESOLVING_N:,} | "
          f"**BELOW SWEPT RANGE** |")
    for product in sorted(sessions):
        a(f"| {product} aggregate | ~{sessions[product]:,} | {SMALLEST_RESOLVING_N:,} | "
          f"**BELOW SWEPT RANGE** |")
    a("")
    a("### Why the aggregate does not rescue it, when it rescues F03")
    a("")
    a("A scan whose cells are individually underpowered can usually pool them. F03's 13 "
      "half-hour slots are **disjoint trades** - 09:30-10:00 is a different window from "
      "10:00-10:30 - so its pooled series really does hold 13x the observations, and its "
      "aggregate is powered even though no single cell is.")
    a("")
    a("F07 cannot do this. Its 12 slots are **twelve predictors of one target**: the catalog "
      "regresses the LAST half-hour on each of the first twelve, so every cell enters on the "
      "same 15:30 minute of the same session. Pooling stacks twelve correlated readings of "
      "one ~4,000-session sample rather than accumulating 48,000 independent ones. Counting "
      "that overlap as sample would repeat, one level up, exactly the error the gate was "
      "just corrected for.")
    a("")
    a("### What it cost to learn that")
    a(f"")
    a(f"**{len(cells)} trials.** The looks happened, so they enter N and raise SR* for every "
      "hypothesis still untested. Recording the cost is the point; declining to log it "
      "would be the dishonest option.")
    a("")

    a("## Data")
    a("")
    a("| instrument | sessions | 09:30-17:10 ET minutes traded |")
    a("|---|---|---|")
    for product in sorted(fills):
        a(f"| {product} | {sessions[product]:,} | **{fills[product]:.2%}** |")
    a("")
    a("The standing MGC caveat (CLAUDE_FUTURES.md §3) applies as always: forward-filling "
      "inserts zero returns and biases toward apparent significance. Here it changes "
      "nothing, because no MGC number is being read as evidence in the first place.")
    a("")

    for product in sorted({c.product for c in cells}):
        sub = [c for c in cells if c.product == product]
        usable = [c for c in sub if c.p_value is not None]
        cost = COST_BPS[product]
        a(f"## {product} - descriptive only")
        a("")
        if not usable:
            a("No cell produced a statistic.")
            a("")
            continue
        p = np.array([c.p_value for c in usable])
        bh = benjamini_hochberg(p) & np.array([c.separated for c in usable])
        a("| | |")
        a("|---|---|")
        a(f"| cells | {len(sub)} (all uninformative) |")
        a(f"| nominal separations | {sum(c.separated for c in usable)} |")
        a(f"| expected by chance at alpha={ALPHA} | {ALPHA * len(usable):.1f} |")
        a(f"| BH survivors at FDR {ALPHA} | {int(bh.sum())} |")
        a(f"| smallest p | {p.min():.4f} |")
        a("")
        a("| hold | cells | events | aggregate bps | net bps | best cell | best slot |")
        a("|---|---|---|---|---|---|---|")
        for hold in HOLDS:
            cs = [c for c in sub if c.hold == hold]
            if not cs:
                continue
            agg = float(np.mean([c.mean_bps for c in cs]))
            best = max(cs, key=lambda c: c.mean_bps)
            a(f"| {hold}m | {len(cs)} | {max(c.events for c in cs):,} | {agg:+.2f} | "
              f"**{agg - cost:+.2f}** | {best.mean_bps:+.2f} | {best.slot_label} |")
        agg_all = float(np.mean([c.mean_bps for c in usable]))
        best_all = max(usable, key=lambda c: c.mean_bps)
        a(f"| **ALL** | {len(usable)} | | **{agg_all:+.2f}** | **{agg_all - cost:+.2f}** | "
          f"{best_all.mean_bps:+.2f} | {best_all.slot_label} |")
        a("")
        a(f"Best cell {best_all.mean_bps:+.2f} bps at {best_all.slot_label}, hold "
          f"{best_all.hold}m. **No floor is quoted against it**, because no floor was "
          f"resolved at this sample size - that is what BELOW SWEPT RANGE means. Quoting a "
          f"ratio here would invent the denominator.")
        a("")

    a("## The redesign that would make F07 testable")
    a("")
    a("Enter at the **close of slot s** and hold h minutes, instead of always entering at "
      "15:30. That makes the 12 positions disjoint, restores a ~48,000-event aggregate, and "
      "moves F07 from unresolvable to resolvable at the aggregate level.")
    a("")
    a("It is **a different hypothesis from the catalog's**. The catalog's F07 is specifically "
      "the Gao-style claim that gold's session has a different *anchor slot* for the "
      "last-half-hour move than equities do; the redesign tests whether slot-by-slot "
      "momentum exists at all. Running it would require registering it as its own entry with "
      "its own pre-committed grid, and it would carry its own trial cost.")
    a("")
    return "\n".join(w)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.signals.f07")
    ap.add_argument("--products", nargs="*", default=["MGC", "MNQ"])
    ap.add_argument("--seed", type=int, default=20260902)
    args = ap.parse_args(argv)

    cells, fills, sessions = run(args.products, args.seed)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(render(cells, fills, sessions), encoding="utf-8")
    CELLS.write_text(json.dumps([asdict(c) for c in cells], indent=2, default=str),
                     encoding="utf-8")
    print(f"\nwrote {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

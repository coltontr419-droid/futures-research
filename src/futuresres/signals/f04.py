"""F04 - lbma_auction_flow, Stage 1. CLAUDE_FUTURES.md §5 Stage 1, §6.

    python -m futuresres.signals.f04

THE CONDITION (from the catalog). For each LBMA auction, converted from London local time to
ET with DST handling: pre = return over [T - pre_window, T]. Test whether pre predicts
[T, T + hold]. Test both continuation and reversion; the mechanism predicts temporary impact
reverting once the auction clears. auction in {AM, PM} tested separately, pre_window in
{15, 30, 60} min, hold in {30, 60, 120} min.

THE DST CONVERSION IS THE POINT, AND IT IS NOT COSMETIC. The auctions are 10:30 and 15:00
LONDON. Measured through `session.calendar`:

    normal weeks      AM 05:30 ET      PM 10:00 ET
    divergence weeks  AM 06:30 ET      PM 11:00 ET

Europe and the US shift on different dates, so for about four weeks a year a fixed ET offset
puts every auction an hour wrong — roughly 8% of observations, silently, in a hypothesis
whose entire content is what happens at one specific minute.

BOTH DIRECTIONS ARE ONE TEST, NOT TWO. The catalog asks for continuation and reversion. They
are exact negations: `evaluate_signed_signal` on -d returns the same p-value with the mean
shift negated, which `test_flipping_every_direction_flips_the_shift` asserts. So the grid is
run once in the REVERSION direction the mechanism predicts, and the continuation reading is
its sign flip. Running both would double the trial count to buy nothing.

Grid: 2 auctions x 3 pre_windows x 3 holds = 18 cells per instrument.

WHICH COMBINATIONS CANNOT SUPPORT A NULL. `reports/detectability.md` blocks MNQ at the 30
and 60 minute holds — the condition fires twice a business day, reaching 8,250 events
against the 19,722 at which a floor first resolves for MNQ at that horizon. Those six cells
are reported as UNINFORMATIVE, not as evidence. MGC is unblocked across its whole range and
is where the mechanism lives: the LBMA fixes gold, not the Nasdaq.

THE WINDOW IS 04:00-14:00 ET, NOT THE WHOLE SESSION. `evaluate_signed_signal` indexes its
forward window by BAR, so the series must be a complete minute grid or "120 bars" is not
"120 minutes". Gridding the entire 1,380-minute CME session would forward-fill a great deal
of thin overnight tape; this window covers the AM auction less its longest pre-window
(04:30) through the PM auction plus its longest hold (13:00) and nothing else. The fill
fraction is measured and reported per instrument.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Final, Sequence

import numpy as np
import polars as pl

from futuresres.session.calendar import ET, LONDON
from futuresres.signals.logged_run import stage1_run
from futuresres.signals.stage1 import evaluate_signed_signal
from futuresres.stats.dsr import sharpe_ratio

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
CONTINUOUS: Final[Path] = ROOT / "data" / "continuous"
REPORT: Final[Path] = ROOT / "reports" / "f04_stage1.md"
CELLS: Final[Path] = ROOT / "reports" / "f04_cells.json"

#: LBMA electronic auctions, in LONDON local time. Converted per date, never offset.
AUCTIONS: Final[dict[str, time]] = {"AM": time(10, 30), "PM": time(15, 0)}

PRE_WINDOWS: Final[tuple[int, ...]] = (15, 30, 60)
HOLDS: Final[tuple[int, ...]] = (30, 60, 120)

#: Analysis window in ET minutes-of-day: 04:00 through 14:00.
WINDOW_START: Final[int] = 4 * 60
WINDOW_MINUTES: Final[int] = 10 * 60

SERIES: Final[dict[str, str]] = {"MNQ": "NQ_MNQ_spliced", "MGC": "MGC"}
COST_BPS: Final[dict[str, float]] = {"MNQ": 0.48, "MGC": 0.65}

#: sigma per bar at each hold, from reports/kurtosis.md (30m interpolated from the table).
SIGMA_BPS: Final[dict[tuple[str, int], float]] = {
    ("MNQ", 30): 21.4, ("MNQ", 60): 30.4, ("MNQ", 120): 43.0,
    ("MGC", 30): 18.2, ("MGC", 60): 26.2, ("MGC", 120): 39.0,
}

#: Floor MULTIPLE from the nearest measured horizon (reports/calibration.md). The multiple
#: is measured; the bps figure below is that multiple times the ACTUAL hold's sigma, which
#: is stated because the two horizons are not the same.
FLOOR_MULTIPLE: Final[dict[tuple[str, int], float | None]] = {
    ("MNQ", 30): None, ("MNQ", 60): None, ("MNQ", 120): 0.3,
    ("MGC", 30): 0.3, ("MGC", 60): 0.1592, ("MGC", 120): 0.3,
}

#: reports/detectability.md — combinations whose usable sample is below the smallest
#: sample at which a floor resolved. A null from these is uninformative.
BLOCKED: Final[frozenset[tuple[str, int]]] = frozenset({("MNQ", 30), ("MNQ", 60)})

ALPHA: Final[float] = 0.05


@dataclass(slots=True)
class Grid:
    sessions: np.ndarray
    logp: np.ndarray
    fill_fraction: float

    @property
    def n_sessions(self) -> int:
        return self.sessions.size


def load(product: str) -> Grid:
    """Complete 04:00-14:00 ET minute grid, forward-filled within each session."""
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


def auction_minute(day: date, auction: str) -> int | None:
    """Minute-of-window for the auction on `day`, via London local time. None if outside.

    `day` may arrive as a numpy datetime64 from the session array; it is coerced first
    because `datetime.combine` silently accepts nothing else.
    """
    if isinstance(day, np.datetime64):
        day = day.astype("datetime64[D]").astype(date)
    london = datetime.combine(day, AUCTIONS[auction], LONDON)
    et = london.astimezone(ET)
    if et.date() != day:
        return None
    m = et.hour * 60 + et.minute - WINDOW_START
    return m if 0 <= m < WINDOW_MINUTES else None


def build_direction(grid: Grid, auction: str, pre_window: int,
                    hold: int) -> tuple[np.ndarray, int]:
    """(direction over the flat grid, auctions used). Reversion: opposite the pre-move."""
    direction = np.zeros(grid.logp.size)
    used = 0
    prices = grid.logp.reshape(grid.n_sessions, WINDOW_MINUTES)
    for i, day in enumerate(grid.sessions):
        m = auction_minute(day, auction)
        if m is None or m - pre_window < 0 or m + hold >= WINDOW_MINUTES:
            continue
        pre = prices[i, m] - prices[i, m - pre_window]
        if pre == 0.0:
            continue
        direction[i * WINDOW_MINUTES + m] = -np.sign(pre)   # reversion
        used += 1
    return direction, used


@dataclass(slots=True)
class CellResult:
    product: str
    auction: str
    pre_window: int
    hold: int
    events: int
    mean_bps: float
    sharpe: float
    p_value: float | None
    hit_rate: float | None
    separated: bool
    blocked: bool
    reason: str


def evaluate(grid: Grid, product: str, auction: str, pre_window: int, hold: int,
             rng: np.random.Generator) -> CellResult:
    direction, _ = build_direction(grid, auction, pre_window, hold)
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
        product, auction, pre_window, hold, int(idx.size),
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
    sessions: dict[str, int] = {}
    for product in products:
        grid = load(product)
        fills[product] = grid.fill_fraction
        sessions[product] = grid.n_sessions
        print(f"\n=== {product} === {grid.n_sessions:,} sessions, "
              f"{grid.fill_fraction:.2%} of 04:00-14:00 ET minutes traded")
        rng = np.random.default_rng(seed)
        for auction in AUCTIONS:
            for pre_window in PRE_WINDOWS:
                for hold in HOLDS:
                    r = evaluate(grid, product, auction, pre_window, hold, rng)
                    cells.append(r)
                    flag = " [BLOCKED]" if r.blocked else ""
                    print(f"  {auction} pre={pre_window:<3} hold={hold:<4} "
                          f"n={r.events:>5,}  mean {r.mean_bps:>+6.2f} bps  "
                          f"p={r.p_value:.4f}{flag}"
                          + ("  SEPARATES" if r.separated else ""))
    return cells, fills, sessions


def render(cells: list[CellResult], fills: dict, sessions: dict) -> str:
    w: list[str] = []
    a = w.append
    a("# F04 - lbma_auction_flow, Stage 1")
    a("")
    a("Run by `python -m futuresres.signals.f04`. CLAUDE_FUTURES.md section 5 Stage 1, 6.")
    a("")
    a("- **Grid:** 2 auctions x 3 pre-windows x 3 holds = 18 cells per instrument, "
      f"{len(cells)} total")
    a("- **Direction:** reversion, the direction the mechanism predicts. Continuation is "
      "its exact sign flip - same p-value, negated mean - so running both would double the "
      "trial count and buy nothing.")
    a("")

    a("## The auctions are converted, not offset")
    a("")
    a("| | normal weeks | DST divergence weeks |")
    a("|---|---|---|")
    a("| AM (10:30 London) | 05:30 ET | **06:30 ET** |")
    a("| PM (15:00 London) | 10:00 ET | **11:00 ET** |")
    a("")
    a("Europe and the US shift on different dates, so for roughly four weeks a year - about "
      "8% of observations - a fixed ET offset would place every auction an hour wrong, in a "
      "hypothesis whose whole content is what happens at one specific minute. The conversion "
      "runs through `session.calendar`.")
    a("")

    a("## Which combinations can carry a verdict")
    a("")
    a("| instrument | hold | usable events | status |")
    a("|---|---|---|---|")
    for product in sorted({c.product for c in cells}):
        for hold in HOLDS:
            cs = [c for c in cells if c.product == product and c.hold == hold]
            ev = max((c.events for c in cs), default=0)
            blocked = any(c.blocked for c in cs)
            a(f"| {product} | {hold}m | {ev:,} | "
              + ("**UNINFORMATIVE** - below the swept range" if blocked
                 else "informative") + " |")
    a("")
    a("**MNQ at 30 and 60 minutes cannot support a null.** The condition fires twice a "
      "business day, reaching ~8,250 events against the 19,722 at which a floor first "
      "resolves for MNQ at that horizon (`reports/detectability.md`). Those six cells are "
      "reported below for completeness and are **excluded from every verdict**: a null "
      "there is the absence of evidence, not evidence of absence.")
    a("")
    a("**MGC is unblocked across its whole range, and is where the mechanism lives.** The "
      "LBMA fixes the price of gold. MNQ is included because the catalog lists it, not "
      "because anyone expects a London gold auction to move the Nasdaq - it functions as a "
      "control on the confound rather than as a second test of the mechanism.")
    a("")

    a("## Data caveat - the standing MGC one")
    a("")
    a("| instrument | sessions | 04:00-14:00 ET minutes traded |")
    a("|---|---|---|")
    for product in sorted(fills):
        a(f"| {product} | {sessions[product]:,} | **{fills[product]:.2%}** |")
    a("")
    a("Per the standing caveat in CLAUDE_FUTURES.md section 3, MGC's thin tape means nearly "
      "three minutes in ten are carried forward rather than traded. Forward-filling inserts "
      "zero returns, thinning measured volatility and biasing toward apparent significance - "
      "so **an MGC null is weaker evidence than the same null on MNQ**. That matters "
      "directly here, because MGC is the instrument that would have to carry a positive "
      "verdict.")
    a("")

    for product in sorted({c.product for c in cells}):
        sub = [c for c in cells if c.product == product]
        usable = [c for c in sub if not c.blocked and c.p_value is not None]
        cost = COST_BPS[product]

        a(f"## {product}")
        a("")
        a("### Multiplicity")
        a("")
        if not usable:
            a("**No informative cells.** Every combination is below the swept range.")
            a("")
            continue
        p = np.array([c.p_value for c in usable])
        bh = benjamini_hochberg(p) & np.array([c.separated for c in usable])
        a("| | |")
        a("|---|---|")
        a(f"| informative cells | {len(usable)} of {len(sub)} "
          f"({len(sub) - len(usable)} excluded as uninformative) |")
        a(f"| **nominal separations** | **{sum(c.separated for c in usable)}** |")
        a(f"| expected by chance at alpha={ALPHA} | **{ALPHA * len(usable):.1f}** |")
        a(f"| **BH survivors at FDR {ALPHA}** | **{int(bh.sum())}** |")
        a(f"| smallest p | {p.min():.4f} (BH rank-1 threshold {ALPHA / len(usable):.6f}) |")
        a("")

        a("### Effect against the detection floor")
        a("")
        a(f"Cost floor **{cost} bps**.")
        a("")
        a("| hold | cells | events | aggregate bps | net bps | best cell | floor bps | best vs floor |")
        a("|---|---|---|---|---|---|---|---|")
        for hold in HOLDS:
            cs = [c for c in sub if c.hold == hold]
            if not cs:
                continue
            agg = float(np.mean([c.mean_bps for c in cs]))
            best = max(c.mean_bps for c in cs)
            mult = FLOOR_MULTIPLE.get((product, hold))
            sigma = SIGMA_BPS.get((product, hold))
            floor = mult * sigma if (mult and sigma) else None
            tag = " (uninformative)" if any(c.blocked for c in cs) else ""
            a(f"| {hold}m{tag} | {len(cs)} | {max(c.events for c in cs):,} | "
              f"{agg:+.2f} | **{agg - cost:+.2f}** | {best:+.2f} | "
              + (f"{floor:.2f}" if floor else "not measured") + " | "
              + (f"{best / floor:.2f}x" if floor else "—") + " |")
        agg_all = float(np.mean([c.mean_bps for c in usable]))
        best_all = max(c.mean_bps for c in usable)
        a(f"| **ALL informative** | {len(usable)} | | **{agg_all:+.2f}** | "
          f"**{agg_all - cost:+.2f}** | {best_all:+.2f} | | |")
        a("")
        a(f"**Aggregate across the {len(usable)} informative cells: {agg_all:+.2f} bps "
          f"gross, {agg_all - cost:+.2f} net.** Best single cell {best_all:+.2f} gross. "
          f"The floor column uses the measured multiple from the nearest swept horizon "
          f"times this hold's own sigma, so it is an estimate at 30 and 120 minutes where "
          f"no floor was swept directly.")
        a("")
    return "\n".join(w)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.signals.f04")
    ap.add_argument("--products", nargs="*", default=["MGC", "MNQ"])
    ap.add_argument("--seed", type=int, default=20260901)
    ap.add_argument("--provenance", default="native", choices=["native", "reconstructed"],
                    help="'reconstructed' marks a re-run reproducing trials already spent")
    ap.add_argument("--log-note", default="", help="text attached to every trial written")
    args = ap.parse_args(argv)

    with stage1_run("F04", provenance=args.provenance,
                    note=args.log_note) as recorder:
        cells, fills, sessions = run(args.products, args.seed)
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(render(cells, fills, sessions), encoding="utf-8")
        CELLS.write_text(json.dumps([asdict(c) for c in cells], indent=2, default=str),
                         encoding="utf-8")
        recorder.record(cells)
    print(f"\nwrote {REPORT}  ({recorder.written} trials logged, {args.provenance})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

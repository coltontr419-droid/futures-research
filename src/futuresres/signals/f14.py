"""F14 - timestamp_hash_control, Stage 1. CLAUDE_FUTURES.md §7.6.

    python -m futuresres.signals.f14

THIS IS THE NEGATIVE CONTROL. It must NOT separate. A clear result here is not a finding and
must never be treated as one: per the catalog, **clearing Stage 1 indicates a harness bug -
halt and run the §7 synthetic-noise test**.

THE CONDITION, fixed in writing at registration and reproduced here verbatim. At each
30-minute RTH slot open (09:30 through 15:30 ET), enter long if the low bit of SHA-256 of
the bar's ISO timestamp is 1, short otherwise, exit after hold. hold in {30, 60, 120}.
There are no other parameters and none may be added or swept: `param_cap` is 0.

WHY THIS PREMISE IS ADMISSIBLE WHERE F10's AND F11's WERE NOT. The direction is a
deterministic function of the CLOCK and never touches price. It is aperiodic, and because
each date hashes differently it cannot align with time-of-day. The claim is not that this
signal SHOULD have no edge - that would be a prediction about the market, which is what
sank F11 - but that it CANNOT have one by construction. A reader can recompute any single
direction from the timestamp alone and confirm no price entered it.

SCOPE, WHICH IS PART OF THE CLAIM. F14 fires ~13 times a session and reaches ~45,000 events,
so it speaks to the harness at F03-like counts. It says NOTHING about ~4,000-event samples,
and F01, F02, F04, F06 and F09 all live in that regime with no real-data control available
at any construction. See `control_scope` in the registry.

EVENT COUNT WILL EXCEED THE PRE-REGISTRATION ESTIMATE, and that is expected rather than a
discrepancy to explain away. `reports/control_candidates.md` measured 9.2 firings a session
on MNQ by requiring a TRADED bar at the exact slot minute. The pipeline reindexes each
session to a complete minute grid and forward-fills, as F03 and F04 do, so all 13 slot opens
exist and the condition fires at every one - which is what the registered condition says.
The 9.2 was a conservative lower bound on the same quantity. More events, not fewer, so
resolvability is unaffected.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
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
REPORT: Final[Path] = ROOT / "reports" / "f14_stage1.md"
CELLS: Final[Path] = ROOT / "reports" / "f14_cells.json"

WINDOW_START: Final[int] = 9 * 60 + 30       # 09:30 ET
WINDOW_MINUTES: Final[int] = 490             # through 17:40 ET, covering 15:30 + 120
SLOT_MINUTES: Final[int] = 30
N_SLOTS: Final[int] = 13                     # 09:30 .. 15:30 inclusive

HOLDS: Final[tuple[int, ...]] = (30, 60, 120)

SERIES: Final[dict[str, str]] = {"MNQ": "NQ_MNQ_spliced", "MGC": "MGC"}
COST_BPS: Final[dict[str, float]] = {"MNQ": 0.48, "MGC": 0.65}

#: reports/detectability.md - F14 resolves on every combination, which is the point of
#: having chosen this firing regime rather than a once-a-session one.
FLOOR_BPS: Final[dict[tuple[str, int], float]] = {
    ("MNQ", 30): 2.57, ("MNQ", 60): 2.57, ("MNQ", 120): 15.66,
    ("MGC", 30): 4.17, ("MGC", 60): 4.17, ("MGC", 120): 14.34,
}

ALPHA: Final[float] = 0.05


@dataclass(slots=True)
class Grid:
    sessions: np.ndarray
    logp: np.ndarray
    stamps: np.ndarray            # ISO timestamp per flat grid position
    fill_fraction: float

    @property
    def n_sessions(self) -> int:
        return self.sessions.size


def load(product: str) -> Grid:
    """Complete 09:30-17:40 ET minute grid, forward-filled within each session."""
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

    # The stamp for a grid position is its session date plus its minute-of-day. It is built
    # from the CALENDAR, never from the bar, so a forward-filled minute hashes the same as
    # a traded one - the direction must not depend on whether a trade happened.
    stamps = np.empty(filled.size, dtype=object)
    for i, day in enumerate(sessions):
        base = i * WINDOW_MINUTES
        for m in range(WINDOW_MINUTES):
            mod = WINDOW_START + m
            stamps[base + m] = f"{day}T{mod // 60:02d}:{mod % 60:02d}"
    return Grid(sessions, np.log(filled).ravel(), stamps,
                float(traded) / max(filled.size, 1))


def hash_bit(stamp: str) -> int:
    """Low bit of SHA-256 of the ISO timestamp. The entire signal."""
    return hashlib.sha256(stamp.encode("ascii")).digest()[0] & 1


def slot_indices(grid: Grid) -> np.ndarray:
    """Flat indices of every session's 13 RTH slot opens."""
    offsets = np.arange(N_SLOTS) * SLOT_MINUTES          # 0, 30, ... 360 -> 09:30..15:30
    base = np.arange(grid.n_sessions)[:, None] * WINDOW_MINUTES
    return (base + offsets[None, :]).ravel()


def build_direction(grid: Grid) -> np.ndarray:
    """+1/-1 at each slot open, from the timestamp hash. No price input anywhere."""
    direction = np.zeros(grid.logp.size)
    idx = slot_indices(grid)
    bits = np.fromiter((hash_bit(grid.stamps[i]) for i in idx), dtype=np.int8,
                       count=idx.size)
    direction[idx] = np.where(bits == 1, 1.0, -1.0)
    return direction


@dataclass(slots=True)
class CellResult:
    product: str
    hold: int
    events: int
    mean_bps: float
    sharpe: float
    p_value: float | None
    hit_rate: float | None
    separated: bool
    long_share: float
    reason: str


def evaluate(grid: Grid, product: str, hold: int,
             rng: np.random.Generator) -> CellResult:
    direction = build_direction(grid)
    idx = np.flatnonzero(direction)
    idx = idx[idx + hold < grid.logp.size]
    per_event = (direction[idx] * (grid.logp[idx + hold] - grid.logp[idx])
                 if idx.size else np.array([]))
    long_share = float(np.mean(direction[idx] > 0)) if idx.size else 0.0
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
        product, hold, int(idx.size),
        float(per_event.mean() * 1e4) if per_event.size else 0.0, sharpe,
        res.p_value if res else None, res.hit_rate if res else None,
        bool(res and res.separated), long_share, reason,
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
              f"{grid.fill_fraction:.2%} of 09:30-17:40 ET minutes traded")
        rng = np.random.default_rng(seed)
        for hold in HOLDS:
            r = evaluate(grid, product, hold, rng)
            cells.append(r)
            print(f"  hold={hold:<4} n={r.events:>6,}  long {r.long_share:.3f}  "
                  f"mean {r.mean_bps:>+6.2f} bps  p={r.p_value:.4f}"
                  + ("  *** SEPARATES ***" if r.separated else ""))
    return cells, fills, sessions


def render(cells: list[CellResult], fills: dict, sessions: dict) -> str:
    w: list[str] = []
    a = w.append
    survivors: dict[str, int] = {}
    for product in sorted({c.product for c in cells}):
        sub = [c for c in cells if c.product == product and c.p_value is not None]
        p = np.array([c.p_value for c in sub])
        survivors[product] = int((benjamini_hochberg(p)
                                  & np.array([c.separated for c in sub])).sum())
    clean = sum(survivors.values()) == 0

    a("# F14 - timestamp_hash_control, Stage 1")
    a("")
    a("Run by `python -m futuresres.signals.f14`. CLAUDE_FUTURES.md §7.6.")
    a("")
    if clean:
        a("## PASS - the control did not separate")
        a("")
        a("**0 BH survivors on either instrument.** The harness declines to promote a "
          "signal that cannot relate to future returns by construction, on real futures "
          "data with real gaps, real volatility clustering and real session boundaries.")
    else:
        a("## FAIL - HALT")
        a("")
        a("**The negative control cleared Benjamini-Hochberg. This is not a finding.** Per "
          "CLAUDE_FUTURES.md §7 the required response is to halt and run the synthetic-noise "
          "test; nothing downstream of the harness may be trusted until that is resolved.")
    a("")

    a("## The condition, as registered")
    a("")
    a("| | |")
    a("|---|---|")
    a("| signal | low bit of SHA-256 of the bar's ISO timestamp |")
    a("| fires | each 30-minute RTH slot open, 09:30-15:30 ET (13 a session) |")
    a("| holds | 30, 60, 120 minutes |")
    a("| free parameters | **none** (`param_cap: 0`) |")
    a("")
    a("The premise is that this signal **cannot** relate to future returns, not that it "
      "*should* not - the distinction that retired F11. The direction is a deterministic "
      "function of the clock, never of price, and any single value can be recomputed from "
      "the timestamp to confirm it.")
    a("")

    a("## Results")
    a("")
    a("| instrument | hold | events | long share | mean bps | net bps | Sharpe | p | floor bps |")
    a("|---|---|---|---|---|---|---|---|---|")
    for c in sorted(cells, key=lambda c: (c.product, c.hold)):
        cost = COST_BPS[c.product]
        floor = FLOOR_BPS.get((c.product, c.hold))
        a(f"| {c.product} | {c.hold}m | {c.events:,} | {c.long_share:.3f} | "
          f"{c.mean_bps:+.2f} | {c.mean_bps - cost:+.2f} | {c.sharpe:+.4f} | "
          f"{c.p_value:.4f} | " + (f"{floor:.2f}" if floor else "—") + " |")
    a("")

    a("## Multiplicity")
    a("")
    a("| instrument | cells | nominal separations | expected by chance | BH survivors |")
    a("|---|---|---|---|---|")
    for product in sorted({c.product for c in cells}):
        sub = [c for c in cells if c.product == product and c.p_value is not None]
        a(f"| {product} | {len(sub)} | {sum(c.separated for c in sub)} | "
          f"{ALPHA * len(sub):.2f} | **{survivors[product]}** |")
    allc = [c for c in cells if c.p_value is not None]
    a(f"| **both** | {len(allc)} | {sum(c.separated for c in allc)} | "
      f"{ALPHA * len(allc):.2f} | **{sum(survivors.values())}** |")
    a("")
    a("Six cells is a small grid, and deliberately so: a control with no free parameters "
      "has nothing to sweep. Expected-by-chance is correspondingly small "
      f"({ALPHA * len(allc):.2f} across both instruments), which means a single nominal "
      "separation would already be notable here in a way it would not be in a 117-cell "
      "hypothesis.")
    a("")

    a("## Aggregate")
    a("")
    a("| instrument | aggregate bps | net of cost | cost floor |")
    a("|---|---|---|---|")
    for product in sorted({c.product for c in cells}):
        sub = [c for c in cells if c.product == product]
        agg = float(np.mean([c.mean_bps for c in sub]))
        a(f"| {product} | {agg:+.2f} | **{agg - COST_BPS[product]:+.2f}** | "
          f"{COST_BPS[product]} |")
    a("")

    a("## Data")
    a("")
    a("| instrument | sessions | 09:30-17:40 ET minutes traded |")
    a("|---|---|---|")
    for product in sorted(fills):
        a(f"| {product} | {sessions[product]:,} | {fills[product]:.2%} |")
    a("")
    a("Event counts exceed the 45,513 and 38,494 estimated at registration, and that is "
      "expected. `reports/control_candidates.md` measured firings by requiring a **traded** "
      "bar at the exact slot minute, giving 9.2 a session on MNQ. The pipeline reindexes "
      "each session to a complete minute grid and forward-fills, exactly as F03 and F04 do, "
      "so all 13 slot opens exist and the condition fires at every one - which is what the "
      "registered condition says. The registration figure was a conservative lower bound on "
      "the same quantity; more events, not fewer, so resolvability is unaffected.")
    a("")
    a("The timestamp a position hashes is built from the **calendar**, not from the bar, so "
      "a forward-filled minute hashes identically to a traded one. Had the hash been taken "
      "from the bar's own recorded timestamp, a filled minute would have inherited the "
      "previous trade's stamp and the direction would have become a function of trading "
      "activity - which is a property of the market, and would have quietly made the "
      "control a hypothesis.")
    a("")

    a("## Scope of what this licenses")
    a("")
    a("**F03-like event counts only.** F14 reaches ~45,000-53,000 events. It demonstrates "
      "that the harness declines to promote a mechanism-free signal at that sample size on "
      "real data. It demonstrates **nothing** about ~4,000-event samples.")
    a("")
    a("**F01, F02, F04, F06 and F09 have no real-data control and cannot get one.** A "
      "once-a-session condition over sixteen years yields ~3,500 events against MNQ's "
      "19,722 - a property of the sample, not of any signal. A null from any of those five "
      "must say so rather than borrowing this result's assurance. The synthetic GARCH nulls "
      "of §7.2 are the only check that reaches that regime, and they test idealised noise "
      "rather than real microstructure.")
    a("")
    return "\n".join(w)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.signals.f14")
    ap.add_argument("--products", nargs="*", default=["MNQ", "MGC"])
    ap.add_argument("--seed", type=int, default=20260902)
    ap.add_argument("--provenance", default="native", choices=["native", "reconstructed"],
                    help="'reconstructed' marks a re-run reproducing trials already spent")
    ap.add_argument("--log-note", default="", help="text attached to every trial written")
    args = ap.parse_args(argv)

    with stage1_run("F14", provenance=args.provenance,
                    note=args.log_note or "negative control") as recorder:
        cells, fills, sessions = run(args.products, args.seed)
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(render(cells, fills, sessions), encoding="utf-8")
        CELLS.write_text(json.dumps([asdict(c) for c in cells], indent=2, default=str),
                         encoding="utf-8")
        recorder.record(cells)
    print(f"\nwrote {REPORT}  ({recorder.written} trials logged, {args.provenance})")

    survived = 0
    for product in {c.product for c in cells}:
        sub = [c for c in cells if c.product == product and c.p_value is not None]
        p = np.array([c.p_value for c in sub])
        survived += int((benjamini_hochberg(p)
                         & np.array([c.separated for c in sub])).sum())
    if survived:
        print(f"\n*** CONTROL CLEARED BH ON {survived} CELL(S) - HALT. "
              f"Run `python -m futuresres.integrity.futures_noise`. ***")
        return 1
    print("\ncontrol did not separate: 0 BH survivors")
    return 0


if __name__ == "__main__":
    sys.exit(main())

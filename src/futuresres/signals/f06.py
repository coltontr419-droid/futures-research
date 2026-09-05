"""F06 - cash_open_drive_continuation, Stage 1. CLAUDE_FUTURES.md §5, §6, §7.6.

    python -m futuresres.signals.f06

THE CONDITION. range = high/low over [09:30, 09:30 + W]. On a close beyond the range
boundary, enter that direction and exit at H hours or 15:55 ET. W in {5, 15, 30} min, confirm
in {close beyond, 2 closes beyond}, H in {1, 2, 3} h, vol_filter in {none, >median}.

vol_filter WAS SETTLED BEFORE THIS RUN (decisions.md §28): this session's realised volatility,
from its own RTH minute returns, against the MEDIAN REALISED VOLATILITY OVER THE TRAILING 20
SESSIONS, strictly prior. As registered it named neither quantity nor lookback, which left
the event count - and so whether F06's routes were open - undetermined.

READ THE SCOPE LIMIT IN THE REGISTRY BEFORE READING ANY NUMBER HERE. Both open routes are on
MGC, and MGC is where this mechanism is WEAKEST. The mechanism names 09:30 ET as the moment
overnight positioning meets CASH liquidity - that is the EQUITY cash open. Gold's own
liquidity event is the COMEX open at 08:20 ET. On MGC this therefore tests CROSS-ASSET
SPILLOVER from the equity open, not the registered claim, and **a positive result would not
support the mechanism as written**; it would require re-registration as its own hypothesis.

MNQ IS NOT RUN. It is closed on every route - 1,708 measured events against the 19,722 at
which a floor resolves. Spending 36 trials on an instrument that cannot carry a verdict would
raise SR* for the rest of the catalog and buy nothing. **Its absence below is a CLOSED ROUTE,
not a null.** MGC at 60 minutes is closed too (1,785 against 5,620) and its cells are marked
uninformative.

THE ROW IS 09:30 TO 15:55 ET, 386 minutes, because that is the condition's exit cap. A cell
fires only where the full hold fits before 15:55: a truncated hold is a different holding
period, and §2's 17:00 hard exit requires the same of a real position. That constraint bites
hardest at H=3h, where entry must occur by 12:55, and the excluded armings are counted.

NO REAL-DATA CONTROL EXISTS AT THIS EVENT REGIME. F14 validated the harness at ~48,000-52,000
events; F06's cells hold far fewer. Any null here carries the §7.2 synthetic GARCH assurance
and nothing from F14.
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
from futuresres.signals.logged_run import stage1_run
from futuresres.signals.stage1 import evaluate_signed_signal
from futuresres.stats.dsr import sharpe_ratio

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
CONTINUOUS: Final[Path] = ROOT / "data" / "continuous"
REPORT: Final[Path] = ROOT / "reports" / "f06_stage1.md"
CELLS: Final[Path] = ROOT / "reports" / "f06_cells.json"

RTH_START: Final[int] = 9 * 60 + 30
ROW_MINUTES: Final[int] = 386              # 09:30 through 15:55 inclusive
LOOKBACK: Final[int] = 20

WS: Final[tuple[int, ...]] = (5, 15, 30)
CONFIRMS: Final[tuple[int, ...]] = (1, 2)
HOLDS: Final[tuple[int, ...]] = (60, 120, 180)
VOL_FILTERS: Final[tuple[str, ...]] = ("none", ">median")

SERIES: Final[dict[str, str]] = {"MGC": "MGC"}
COST_BPS: Final[dict[str, float]] = {"MGC": 0.65}

#: reports/detectability.md. MGC 60m is below the swept range; 120m and 180m are open.
BLOCKED_HOLDS: Final[frozenset[int]] = frozenset({60})
FLOOR_BPS: Final[dict[int, float]] = {60: 4.17, 120: 14.34, 180: 14.34}

#: The smallest sample at which a floor resolved, BY PROXY HORIZON - not one number. A
#: 60-minute hold is compared against MGC's 60m cell (5,620); 120m and 180m map to the 180m
#: cell (2,862), the lowest threshold in the study. Using the 60m figure for every hold
#: would mark informative cells as blocked, which an earlier draft of this module did.
RESOLVING_BY_HOLD: Final[dict[int, int]] = {60: 5_620, 120: 2_862, 180: 2_862}

ALPHA: Final[float] = 0.05


@dataclass(slots=True)
class Grid:
    rows: np.ndarray
    logp: np.ndarray
    high: np.ndarray
    low: np.ndarray
    fill_fraction: float

    @property
    def n_rows(self) -> int:
        return self.rows.size


def load(product: str) -> Grid:
    """RTH rows of 09:30-15:55 ET, complete and forward-filled, with highs and lows."""
    bars = pl.read_parquet(CONTINUOUS / f"{SERIES[product]}.parquet")
    local = pl.col("ts_event").dt.convert_time_zone(str(ET))
    f = bars.with_columns(
        (local.dt.hour().cast(pl.Int32) * 60
         + local.dt.minute().cast(pl.Int32) - RTH_START).alias("m"),
        local.dt.date().alias("day"),
    ).filter((pl.col("m") >= 0) & (pl.col("m") < ROW_MINUTES))

    days = f.get_column("day").to_numpy()
    minutes = f.get_column("m").to_numpy().astype(np.int64)
    closes = f.get_column("close").to_numpy().astype(float)
    highs = f.get_column("high").to_numpy().astype(float)
    lows = f.get_column("low").to_numpy().astype(float)

    rows = np.unique(days)
    pos = np.searchsorted(rows, days) * ROW_MINUTES + minutes
    flat = np.full(rows.size * ROW_MINUTES, np.nan)
    hi = np.full_like(flat, np.nan)
    lo = np.full_like(flat, np.nan)
    flat[pos], hi[pos], lo[pos] = closes, highs, lows
    traded = int(np.isfinite(flat).sum())

    def ffill(a: np.ndarray) -> np.ndarray:
        g = a.reshape(rows.size, ROW_MINUTES)
        ok = np.isfinite(g)
        idx = np.where(ok, np.arange(ROW_MINUTES)[None, :], 0)
        np.maximum.accumulate(idx, axis=1, out=idx)
        out = np.take_along_axis(g, idx, axis=1)
        first = np.argmax(ok, axis=1)
        for i in np.flatnonzero(ok.any(axis=1) & ~np.isfinite(out[:, 0])):
            out[i, : first[i]] = g[i, first[i]]
        return out

    c, h, l = ffill(flat), ffill(hi), ffill(lo)
    keep = np.isfinite(c).all(axis=1) & np.isfinite(h).all(axis=1) \
        & np.isfinite(l).all(axis=1)
    c, h, l, rows = c[keep], h[keep], l[keep], rows[keep]
    return Grid(rows, np.log(c).ravel(), h, l, float(traded) / max(c.size, 1))


def rolling_pct_prior(v: np.ndarray, w: int, pct: float) -> np.ndarray:
    out = np.full(v.size, np.nan)
    if v.size <= w:
        return out
    win = np.lib.stride_tricks.sliding_window_view(v, w)[:-1]
    out[w:] = np.percentile(win, pct, axis=1)
    return out


def vol_pass(grid: Grid) -> np.ndarray:
    """Session realised vol above the trailing-20 median. decisions.md §28."""
    px = grid.logp.reshape(grid.n_rows, ROW_MINUTES)
    vol = np.diff(px, axis=1).std(axis=1, ddof=1)
    return vol > rolling_pct_prior(vol, LOOKBACK, 50)


def build_direction(grid: Grid, W: int, confirm: int, hold: int,
                    vol_filter: str) -> tuple[np.ndarray, int]:
    """First confirmed close beyond the opening range. (direction, dropped_no_room)."""
    px = grid.logp.reshape(grid.n_rows, ROW_MINUTES)
    rng_hi = np.log(grid.high[:, :W].max(axis=1))
    rng_lo = np.log(grid.low[:, :W].min(axis=1))
    ok_vol = vol_pass(grid) if vol_filter == ">median" \
        else np.ones(grid.n_rows, dtype=bool)

    direction = np.zeros(grid.logp.size)
    dropped = 0
    for i in range(grid.n_rows):
        if not ok_vol[i]:
            continue
        run_up = run_dn = 0
        for m in range(W, ROW_MINUTES):
            if px[i, m] > rng_hi[i]:
                run_up, run_dn = run_up + 1, 0
            elif px[i, m] < rng_lo[i]:
                run_dn, run_up = run_dn + 1, 0
            else:
                run_up = run_dn = 0
            if run_up >= confirm or run_dn >= confirm:
                if m + hold >= ROW_MINUTES:
                    dropped += 1
                    break
                direction[i * ROW_MINUTES + m] = 1.0 if run_up >= confirm else -1.0
                break
    return direction, dropped


@dataclass(slots=True)
class CellResult:
    product: str
    W: int
    confirm: int
    hold: int
    vol_filter: str
    events: int
    dropped: int
    mean_bps: float
    sharpe: float
    p_value: float | None
    separated: bool
    blocked: bool
    reason: str


def evaluate(grid: Grid, product: str, W: int, confirm: int, hold: int, vol_filter: str,
             rng: np.random.Generator) -> CellResult:
    direction, dropped = build_direction(grid, W, confirm, hold, vol_filter)
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
        product, W, confirm, hold, vol_filter, int(idx.size), dropped,
        float(per_event.mean() * 1e4) if per_event.size else 0.0, sharpe,
        res.p_value if res else None, bool(res and res.separated),
        hold in BLOCKED_HOLDS or idx.size < RESOLVING_BY_HOLD[hold], reason,
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
        fills[product], rows[product] = grid.fill_fraction, grid.n_rows
        print(f"\n=== {product} === {grid.n_rows:,} sessions, "
              f"{grid.fill_fraction:.2%} of 09:30-15:55 ET minutes traded", flush=True)
        rng = np.random.default_rng(seed)
        for W in WS:
            for confirm in CONFIRMS:
                for vf in VOL_FILTERS:
                    for hold in HOLDS:
                        r = evaluate(grid, product, W, confirm, hold, vf, rng)
                        cells.append(r)
                        flag = " [UNINFORMATIVE]" if r.blocked else ""
                        print(f"  W={W:<3} c={confirm} vol={vf:<8} H={hold:<4} "
                              f"n={r.events:>5,} (-{r.dropped:,})  "
                              f"mean {r.mean_bps:>+7.2f}  p={r.p_value:.4f}{flag}"
                              + ("  SEPARATES" if r.separated else ""), flush=True)
    return cells, fills, rows


def render(cells: list[CellResult], fills: dict, rows: dict) -> str:
    w: list[str] = []
    a = w.append
    a("# F06 - cash_open_drive_continuation, Stage 1")
    a("")
    a("Run by `python -m futuresres.signals.f06`. CLAUDE_FUTURES.md §5, §6, §7.6.")
    a("")

    a("## Read this before any number below")
    a("")
    a("**Both open routes are MGC, and MGC is where this mechanism is weakest.** The "
      "mechanism names 09:30 ET as the moment overnight positioning meets CASH liquidity - "
      "that is the EQUITY cash open. Gold's own liquidity event is the COMEX open at 08:20 "
      "ET. On MGC this condition therefore tests **cross-asset spillover** from the equity "
      "open, not the registered claim.")
    a("")
    a("**A positive result here would not support the mechanism as written.** It would say "
      "gold moves directionally after the equity cash open - a different proposition with a "
      "different counterparty - and promoting it would require re-registration as its own "
      "hypothesis with its own pre-committed grid and trial budget. Recorded in the registry "
      "before this run, not after seeing it.")
    a("")
    a("**MNQ - where the mechanism actually lives - was NOT RUN.** It is closed on every "
      "route at 1,708 measured events against the 19,722 at which a floor resolves. "
      "Spending 36 trials there would raise SR\\* for the rest of the catalog and buy "
      "nothing. **Its absence from this report is a closed route, not a null.**")
    a("")

    a("## What can carry a verdict")
    a("")
    a("| hold | cells | events | resolving threshold | status |")
    a("|---|---|---|---|---|")
    for hold in HOLDS:
        sub = [c for c in cells if c.hold == hold]
        n = max((c.events for c in sub), default=0)
        blocked = all(c.blocked for c in sub)
        a(f"| {hold}m | {len(sub)} | {n:,} | {RESOLVING_BY_HOLD[hold]:,} | "
          + ("**UNINFORMATIVE**" if blocked else "informative") + " |")
    a("")
    a("MGC at 60 minutes is below the swept range and its cells are excluded from the "
      "verdict. The 120m and 180m holds map to the 180-minute floor cell, whose threshold "
      "of 2,862 is the lowest in the study - these routes are open by the narrowest margin "
      "available anywhere in the catalog.")
    a("")

    inf = [c for c in cells if not c.blocked and c.p_value is not None]
    a("## Multiplicity")
    a("")
    a("| | |")
    a("|---|---|")
    a(f"| informative cells | {len(inf)} of {len(cells)} |")
    a(f"| **nominal separations** | **{sum(c.separated for c in inf)}** |")
    a(f"| expected by chance at alpha={ALPHA} | {ALPHA * len(inf):.2f} |")
    if inf:
        pv = np.array([c.p_value for c in inf])
        bh = benjamini_hochberg(pv) & np.array([c.separated for c in inf])
        a(f"| **BH survivors at FDR {ALPHA}** | **{int(bh.sum())}** |")
        a(f"| smallest p | {pv.min():.4f} |")
    a("")
    a("The cells overlap heavily - the three holds share entry minutes, and W and confirm "
      "select nested subsets of the same breakouts - so effective independent looks are "
      "fewer than the cell count and expected-by-chance is an overestimate.")
    a("")

    a("## Effect against the detection floor")
    a("")
    a("| hold | cells | events | aggregate bps | net | best cell | floor | best/floor |")
    a("|---|---|---|---|---|---|---|---|")
    cost = COST_BPS["MGC"]
    for hold in HOLDS:
        sub = [c for c in cells if c.hold == hold]
        if not sub:
            continue
        agg = float(np.mean([c.mean_bps for c in sub]))
        best = max(c.mean_bps for c in sub)
        floor = FLOOR_BPS[hold]
        tag = " (uninformative)" if all(c.blocked for c in sub) else ""
        a(f"| {hold}m{tag} | {len(sub)} | {max(c.events for c in sub):,} | {agg:+.2f} | "
          f"**{agg - cost:+.2f}** | {best:+.2f} | {floor:.2f} | {best / floor:.2f}x |")
    if inf:
        agg = float(np.mean([c.mean_bps for c in inf]))
        a(f"| **informative** | {len(inf)} | | **{agg:+.2f}** | **{agg - cost:+.2f}** | "
          f"{max(c.mean_bps for c in inf):+.2f} | | |")
    a("")

    a("## No real-data control exists at this event regime")
    a("")
    a("F14, the catalog's negative control, fires ~13 times a session and reaches "
      "~48,000-52,000 events. It established that the harness declines to promote a "
      "mechanism-free signal **at that sample size**. F06's cells hold ~3,900.")
    a("")
    a("**No control can be built at F06's regime on this data.** It fires once per session, "
      "and measured candidates at that regime resolved in only 2 of 12 combinations "
      "(`reports/control_candidates.md`) - both MGC at the longest hold, on the instrument "
      "carrying the coverage caveat. So this result carries the §7.2 synthetic GARCH "
      "assurance and **nothing from F14**.")
    a("")

    a("## Data")
    a("")
    a("| instrument | sessions | 09:30-15:55 ET minutes traded |")
    a("|---|---|---|")
    for product in sorted(fills):
        a(f"| {product} | {rows[product]:,} | {fills[product]:.2%} |")
    a("")
    a("Breakouts whose full hold would not fit before 15:55 ET are excluded rather than "
      "truncated - a shortened hold is a different holding period, and §2's 17:00 hard exit "
      "requires the same of a real position. At most "
      f"{max(c.dropped for c in cells):,} sessions were excluded that way, at H=3h where "
      "entry must occur by 12:55.")
    a("")

    a("## Every cell")
    a("")
    a("| W | confirm | vol_filter | hold | events | mean bps | Sharpe | p | |")
    a("|---|---|---|---|---|---|---|---|---|")
    for c in sorted(cells, key=lambda c: (c.W, c.confirm, c.vol_filter, c.hold)):
        a(f"| {c.W} | {c.confirm} | {c.vol_filter} | {c.hold}m | {c.events:,} | "
          f"{c.mean_bps:+.2f} | {c.sharpe:+.4f} | {c.p_value:.4f} | "
          + ("UNINFORMATIVE" if c.blocked else ("SEPARATES" if c.separated else "")) + " |")
    a("")
    a(f"**{len(cells)} trials**, MGC only. 3 W x 2 confirm x 2 vol_filter x 3 holds.")
    a("")
    return "\n".join(w)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.signals.f06")
    ap.add_argument("--products", nargs="*", default=["MGC"],
                    help="MNQ is closed on every route and is deliberately not run")
    ap.add_argument("--seed", type=int, default=20260902)
    ap.add_argument("--provenance", default="native", choices=["native", "reconstructed"])
    ap.add_argument("--log-note", default="", help="text attached to every trial written")
    args = ap.parse_args(argv)

    with stage1_run("F06", provenance=args.provenance, note=args.log_note) as recorder:
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

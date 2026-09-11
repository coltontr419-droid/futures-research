"""Firing rates, placebo matching and disjointness for the whole L-series, in one batch.

    python -m futuresres.reporting.level_rates

NO STAGE 1 IS RUN AND NO TRIAL IS SPENT. This computes three things the gate needs before
anything can be scheduled:

  1. FIRING RATE per Stage 1 cell, with every threshold applied - the §21 rule that a declared
     rate never gates, only a measured one.
  2. PLACEBO MATCHING, verified rather than asserted, because every L-series result reports
     (real - placebo) and that comparison is invalid if the placebos are not matched.
  3. DISJOINTNESS per hypothesis - do two cells of the same hypothesis fire on the same
     minute? Level cells usually do, because the same touch enters under several parameter
     settings. Per F07, the aggregate route is ASSUMED CLOSED until this says otherwise.

Runtime is dominated by the per-level Python scans in `definitions`; the whole batch is a few
minutes and it replaces a scheduling decision that would otherwise cost hundreds of trials.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Final

import numpy as np

from futuresres.levels import definitions as D
from futuresres.levels.placebo import (
    MatchReport,
    make_placebo,
    make_region_placebo,
    offset_unit,
    render_reports,
    verify,
)


def placebo_offset_for(day, kind: str) -> float:
    """The same deterministic offset the level placebos use, for curve placebos."""
    return offset_unit(day, kind, 0)

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
REPORTS: Final[Path] = ROOT / "reports"
RATES_JSON: Final[Path] = REPORTS / "level_rates.json"
RATES_MD: Final[Path] = REPORTS / "level_rates.md"
MATCH_MD: Final[Path] = REPORTS / "placebo_match.md"
DISJOINT_MD: Final[Path] = REPORTS / "disjointness.md"

#: reports/floor_cache.json - smallest sample at which a floor resolved, by proxy horizon.
SMALLEST_RESOLVING: Final[dict[tuple[str, int], int]] = {
    ("MNQ", 60): 19_722, ("MNQ", 180): 5_884,
    ("MGC", 60): 5_620, ("MGC", 180): 2_862,
}


def proxy(h: int) -> int:
    import math
    return min((60, 180), key=lambda m: abs(math.log(h / m)))


@dataclass(slots=True)
class CellRate:
    hypothesis: str
    product: str
    cell: str
    horizons: list[int]
    firings: int
    minutes_key: str = ""      # not serialised in full; see disjointness


@dataclass(slots=True)
class Disjointness:
    hypothesis: str
    product: str
    n_cells: int
    max_pairwise_overlap: float
    verdict: str
    note: str


#: Stride used to pack (row, minute) into one integer. ROW_MINUTES is 1,375, so 2,048
#: leaves the minute field room to spare and keeps the arithmetic a shift.
_MINUTE_STRIDE: Final[int] = 2048


def _fired_keys(rows: np.ndarray, minutes: np.ndarray,
                mask: np.ndarray) -> np.ndarray:
    """Firing minutes as a SORTED UNIQUE int64 ARRAY, not a set of tuples.

    THIS IS A MEMORY FIX AND IT IS LOAD-BEARING. Every cell's firing minutes are retained
    for the whole run so the disjointness pass can compare cells pairwise at the end. As a
    Python `set[tuple[int, int]]` that costs roughly 150 bytes per firing - about 130 MB for
    ONE L07 cell at 863,490 firings, and L07 has 18 cells per product. The run was OOM-killed
    at the L07 stage twice, at 1,030 MB and 1,086 MB.

    Packed into int64 the same cell is 6.9 MB, a ~20x reduction, and `np.intersect1d` gives
    the pairwise overlap the set intersection used to. Identical semantics: `np.unique`
    dedupes exactly as the set did, and both forms drop `m < 0`.
    """
    ok = np.asarray(mask, dtype=bool) & (np.asarray(minutes) >= 0)
    if not ok.any():
        return np.empty(0, dtype=np.int64)
    r = np.asarray(rows, dtype=np.int64)[ok]
    m = np.asarray(minutes, dtype=np.int64)[ok]
    return np.unique(r * _MINUTE_STRIDE + m)


def measure(product: str) -> tuple[list[CellRate], list[MatchReport], list[Disjointness],
                                   dict]:
    g = D.load(product, ROOT)
    atr = g.atr()
    rates: list[CellRate] = []
    matches: list[MatchReport] = []
    fires: dict[str, list[tuple[str, np.ndarray]]] = {}

    def add(hyp: str, cell: str, horizons: list[int], keys: np.ndarray) -> None:
        rates.append(CellRate(hyp, product, cell, horizons, int(keys.size)))
        fires.setdefault(hyp, []).append((cell, keys))

    def check_placebo(kind: str, levels: D.LevelSet, touched: np.ndarray,
                      tol: float) -> None:
        """Build the matched placebo for a level set and verify it. Never strict here -
        the failures are collected and reported, so one bad level type does not hide the
        rest. `match_report` is what fails loudly."""
        days = g.days[levels.row]
        # NOT daily ATR. The scale is the intraday range over each level's own validity
        # window - see D.window_scale. Daily ATR put placebos 3x-63x too far from price and
        # failed 53 of 55 level types; decisions.md 36.
        lvl_scale = D.window_scale(g, levels)
        ok = np.isfinite(levels.price) & np.isfinite(lvl_scale) & (lvl_scale > 0)
        if ok.sum() < 50:
            return
        # THE NULL IS AN ARBITRARY REGION AT A MATCHED DISTANCE, not the real level
        # displaced. Redefined 2026-09-09; decisions.md 37.
        pl_price = make_region_placebo(levels.price[ok], levels.ref_price[ok], days[ok],
                                       kind, lvl_scale[ok])
        pl_set = D.LevelSet(kind + "_placebo", pl_price, levels.row[ok],
                            levels.valid_from[ok], levels.ref_price[ok])
        pl_touch, _ = D.touches(g, pl_set, tol, product)
        matches.append(verify(
            kind, product, levels.price[ok], pl_price,
            np.abs(levels.price[ok] - levels.ref_price[ok]),
            np.abs(pl_price - pl_set.ref_price),
            touched[ok], pl_touch, strict=False,
        ))

    # ---------------------------------------------------------------- L01 / L10
    print(f"    {product} L01/L10 vwap ...", flush=True)
    rows_ix = np.arange(g.n)
    for anchor in ("RTH", "CME", "R24"):
        curve = D.vwap_curve(g, anchor)
        for d in (0.5, 1.0, 1.5):
            t, mins = D.curve_touches(g, curve, 2, product, d, atr, 15)
            add("L01", f"anchor={anchor} d={d}", [30, 60, 120],
                _fired_keys(rows_ix, mins, t))
        # the placebo is the CURVE shifted by the hash offset, so the comparison is
        # like-for-like: a moving reference against a moving reference
        lv = D.vwap_levels(g, anchor)
        tl, _ = D.touches(g, lv, 2, product)
        check_placebo(f"vwap_{anchor}", lv, tl, 2)
        # The placebo curve is live from its anchor to the close, so its scale is the
        # intraday range over that window - the same rule check_placebo applies. The
        # `require_away` argument below still uses DAILY atr, deliberately: which ATR L01's
        # "d ATR away" precondition means is an open specification question and changing it
        # would change L01's firing rate. decisions.md 36.
        # L10 is the placebo control, so its curve is built to the SAME definition: an
        # arbitrary region at a matched distance, not the VWAP curve displaced. The offset
        # per row is the matched region's own distance from the real curve at its anchor.
        curve_scale = D.window_scale(
            g, D.LevelSet(f"vwap_{anchor}_curve", curve[:, 0].copy(), rows_ix,
                          np.full(rows_ix.size, lv.valid_from[0] if lv.valid_from.size
                                  else 0, int), curve[:, 0].copy()))
        region = make_region_placebo(lv.price, lv.ref_price, g.days[lv.row],
                                     f"vwap_{anchor}", D.window_scale(g, lv))
        shift = np.zeros(rows_ix.size)
        row_of = {int(r): j for j, r in enumerate(lv.row)}
        for j, r in enumerate(rows_ix):
            k = row_of.get(int(r))
            if k is not None and np.isfinite(region[k]) and np.isfinite(lv.price[k]):
                shift[j] = region[k] - lv.price[k]
        pcurve = curve + shift[:, None]
        tp_, minp = D.curve_touches(g, pcurve, 2, product, 1.0, atr, 15)
        add("L10", f"placebo curve anchor={anchor}", [30, 60, 120],
            _fired_keys(rows_ix, minp, tp_))

    # ---------------------------------------------------------------- L02
    print(f"    {product} L02 opening range ...", flush=True)
    # THE SWEEP ARM IS WITHDRAWN AND ITS CELLS ARE GONE. `confirmed_break` fired on every
    # opening-range level at valid_from + (k-1): measured entry-minute sd 0.07-0.10 on MNQ,
    # 0% identical minutes between adjacent k, and 92-99% of high/low pairs firing at the
    # SAME (row, minute). k was an offset, not a selection. The ABSORPTION arm below uses
    # `sweep_reclaim`, is a genuine two-stage test, and discriminates properly. decisions.md 41.
    for W in (15, 30, 60):
        lv = D.opening_range(g, W)
        for m in (2, 4, 8):
            for k in (2, 3, 5):
                f, mins = D.sweep_reclaim(g, lv, m, k, product)
                add("L02", f"absorb W={W} m={m} k={k}", [60, 120, 180],
                    _fired_keys(lv.row, mins, f))
        t, _ = D.touches(g, lv, 2, product)
        check_placebo(f"or{W}", lv, t, 2)

    # ---------------------------------------------------------------- L03
    print(f"    {product} L03 prior day ...", flush=True)
    for kind in ("prior_rth", "prior_full"):
        lv = D.prior_day_levels(g, kind)
        for m in (2, 4, 8):
            for k in (2, 3, 5):
                f, mins = D.sweep_reclaim(g, lv, m, k, product)
                add("L03", f"{kind} m={m} k={k}", [60, 120, 180],
                    _fired_keys(lv.row, mins, f))
        t, _ = D.touches(g, lv, 2, product)
        check_placebo(kind, lv, t, 2)

    # ---------------------------------------------------------------- L04
    print(f"    {product} L04 session extremes ...", flush=True)
    for sess in ("Asia", "London", "US"):
        lv = D.session_extremes(g, sess)
        for m in (2, 4, 8):
            for k in (2, 3, 5):
                f, mins = D.sweep_reclaim(g, lv, m, k, product)
                add("L04", f"{sess} m={m} k={k}", [60, 120, 180],
                    _fired_keys(lv.row, mins, f))
        t, _ = D.touches(g, lv, 2, product)
        check_placebo(f"sess_{sess}", lv, t, 2)

    # L05 IS NOT MEASURED HERE ANY MORE. Its condition is `confirmed_break` on the
    # overnight range, which price sits inside at 09:30 by construction: measured entry-minute
    # sd 0.05, all 8,234 levels firing, 99.6% of high/low pairs colliding on (row, minute).
    # The 8,234 figure was a count of SESSIONS, not of breaks. L05 was already
    # blocked_insufficient_events so nothing downstream changes, but continuing to publish a
    # meaningless rate would be worse than publishing none. decisions.md 41.

    # ---------------------------------------------------------------- L06
    print(f"    {product} L06 session open ...", flush=True)
    for kind in ("RTH", "CME"):
        lv = D.session_open(g, kind)
        for d in (0.5, 1.0, 1.5):
            t, mins = D.touches(g, lv, 2, product, require_away=d, atr=atr,
                                away_minutes=30)
            add("L06", f"{kind} d={d}", [60, 120, 180], _fired_keys(lv.row, mins, t))
        t, _ = D.touches(g, lv, 2, product)
        check_placebo(f"open_{kind}", lv, t, 2)

    # ---------------------------------------------------------------- L07
    print(f"    {product} L07 fair value gaps ...", flush=True)
    for w in (2, 4, 8):
        for tf in (1, 5):
            lv = D.fvg_zones(g, w, tf, product)
            if lv.price.size == 0:
                continue
            for gbars in (10, 30, 60):
                shifted = D.LevelSet(lv.kind, lv.price, lv.row,
                                     np.minimum(lv.valid_from + gbars * tf,
                                                D.ROW_MINUTES - 1), lv.ref_price)
                t, mins = D.touches(g, shifted, 2, product)
                add("L07", f"w={w} tf={tf}m g={gbars}", [60, 120, 180],
                    _fired_keys(lv.row, mins, t))
            t, _ = D.touches(g, lv, 2, product)
            check_placebo(f"fvg_w{w}_{tf}m", lv, t, 2)

    # ---------------------------------------------------------------- L08
    print(f"    {product} L08 moving averages ...", flush=True)
    for period in (20, 50, 200):
        for tf in (5, 15):
            curve = D.ema_curve(g, period, tf)
            for d in (0.5, 1.0, 1.5):
                t, mins = D.curve_touches(g, curve, 2, product, d, atr, 30)
                add("L08", f"ema{period} {tf}m d={d}", [60, 120, 180],
                    _fired_keys(rows_ix, mins, t))
            lv = D.ema_levels(g, period, tf)
            tl, _ = D.touches(g, lv, 2, product)
            check_placebo(f"ema{period}_{tf}m", lv, tl, 2)

    # ---------------------------------------------------------------- L09
    print(f"    {product} L09 weekly/monthly ...", flush=True)
    for kind in ("week", "month"):
        lv = D.weekly_monthly(g, kind)
        if lv.price.size == 0:
            continue
        for m in (2, 4, 8):
            for k in (2, 3, 5):
                f, mins = D.sweep_reclaim(g, lv, m, k, product)
                add("L09", f"prior_{kind} m={m} k={k}", [60, 120, 180],
                    _fired_keys(lv.row, mins, f))
        t, _ = D.touches(g, lv, 2, product)
        check_placebo(f"prior_{kind}", lv, t, 2)

    # L11 WAS MEASURED HERE AND IS WITHDRAWN. Its condition fired unconditionally at the
    # first valid minute of every session rather than on a breakout, so the block is removed
    # rather than left to regenerate degenerate rows into these reports every run.
    # `D.bollinger_levels` is KEPT and still unit-tested - the band arithmetic is correct and
    # a corrected condition would use it - but no registered hypothesis consumes it.
    # decisions.md 40, hypotheses.yaml L11.

    # ---------------------------------------------------------------- disjointness
    disj: list[Disjointness] = []
    for hyp, cells in fires.items():
        worst = 0.0
        for i in range(len(cells)):
            for j in range(i + 1, len(cells)):
                a, b = cells[i][1], cells[j][1]
                if a.size == 0 or b.size == 0:
                    continue
                # Both are sorted and unique, so this is the same count the set
                # intersection produced.
                shared = np.intersect1d(a, b, assume_unique=True).size
                worst = max(worst, shared / min(a.size, b.size))
        if worst >= 0.5:
            verdict, note = "OVERLAPPING", (
                f"cells share up to {worst:.0%} of their firing minutes - the same touch "
                f"enters under multiple parameter settings, so pooling them would count one "
                f"observation many times. AGGREGATE ROUTE CLOSED.")
        elif worst >= 0.1:
            verdict, note = "PARTIAL", (
                f"cells share up to {worst:.0%} of firing minutes. Pooling would inflate the "
                f"sample by an amount this measurement cannot bound. AGGREGATE CLOSED absent "
                f"a per-pair correction.")
        else:
            verdict, note = "DISJOINT", (
                f"cells share at most {worst:.0%} of firing minutes, so an aggregate route "
                f"is genuinely available.")
        disj.append(Disjointness(hyp, product, len(cells), worst, verdict, note))

    meta = {"rows": g.n, "fill": g.fill_fraction}
    return rates, matches, disj, meta


def status_for(product: str, horizon: int, n: int) -> tuple[str, int]:
    need = SMALLEST_RESOLVING.get((product, proxy(horizon)), 0)
    return ("RESOLVABLE" if n >= need else "BELOW SWEPT RANGE"), need


def render_rates(rates: list[CellRate], meta: dict) -> str:
    w: list[str] = []
    a = w.append
    a("# L-series measured firing rates")
    a("")
    a("Generated by `python -m futuresres.reporting.level_rates`. "
      "LEVEL_HYPOTHESES.md; `reports/decisions.md` §21, §22.")
    a("")
    a("**No Stage 1 was run and no trial was spent.** These are counts of how often each "
      "condition triggers, per Stage 1 cell, with every threshold applied - the §22 rule that "
      "a declared rate never gates, only a measured one.")
    a("")

    a("## Summary, per hypothesis")
    a("")
    a("| hypothesis | product | cells | worst cell | best cell | needs (60m / 180m) | verdict |")
    a("|---|---|---|---|---|---|---|")
    for hyp in sorted({r.hypothesis for r in rates}):
        for product in sorted({r.product for r in rates if r.hypothesis == hyp}):
            sub = [r for r in rates if r.hypothesis == hyp and r.product == product]
            lo = min(r.firings for r in sub)
            hi = max(r.firings for r in sub)
            h = sub[0].horizons
            n60 = SMALLEST_RESOLVING.get((product, 60), 0)
            n180 = SMALLEST_RESOLVING.get((product, 180), 0)
            if lo >= n180:
                v = "**RESOLVABLE**" if lo >= n60 else "**RESOLVABLE at 120m+**"
            elif hi >= n180:
                v = "MIXED"
            else:
                v = "BELOW SWEPT RANGE"
            a(f"| {hyp} | {product} | {len(sub)} | {lo:,} | {hi:,} | "
              f"{n60:,} / {n180:,} | {v} |")
    a("")
    a("A cell clears at 120m or 180m against the 180-minute floor cell, whose resolving "
      "sample is the lowest in the study (5,884 MNQ, 2,862 MGC). Clearing there and not at "
      "60m is the common case and is reported as such rather than as a blanket pass.")
    a("")

    a("## Data")
    a("")
    a("| instrument | trading days | 18:00-16:55 ET minutes traded |")
    a("|---|---|---|")
    for prod, m in sorted(meta.items()):
        a(f"| {prod} | {m['rows']:,} | {m['fill']:.2%} |")
    a("")

    a("## Every cell")
    a("")
    a("| hypothesis | product | cell | firings | 60m | 180m |")
    a("|---|---|---|---|---|---|")
    for r in sorted(rates, key=lambda r: (r.hypothesis, r.product, r.cell)):
        s60, _ = status_for(r.product, 60, r.firings)
        s180, _ = status_for(r.product, 180, r.firings)
        a(f"| {r.hypothesis} | {r.product} | {r.cell} | {r.firings:,} | "
          f"{'ok' if s60 == 'RESOLVABLE' else 'below'} | "
          f"{'ok' if s180 == 'RESOLVABLE' else 'below'} |")
    a("")
    return "\n".join(w)


def render_disjointness(dis: list[Disjointness]) -> str:
    w: list[str] = []
    a = w.append
    a("# L-series disjointness - which aggregate routes exist")
    a("")
    a("Generated by `python -m futuresres.reporting.level_rates`.")
    a("")
    a("**Per F07, the aggregate route is ASSUMED CLOSED until measured.** Pooling a "
      "hypothesis's cells only adds observations if those cells fire at DIFFERENT times. "
      "Level cells usually do not: the same touch enters under several parameter settings, so "
      "pooling would count one observation many times. F07's twelve slots all predicted the "
      "same 15:30 target and its aggregate looked four times larger than it was.")
    a("")
    a("The measurement is the maximum pairwise overlap of firing minutes across a "
      "hypothesis's cells - the fraction of the smaller cell's firings that the larger one "
      "shares.")
    a("")
    a("| hypothesis | product | cells | max pairwise overlap | aggregate route |")
    a("|---|---|---|---|---|")
    for d in sorted(dis, key=lambda d: (d.hypothesis, d.product)):
        route = "**OPEN**" if d.verdict == "DISJOINT" else "**CLOSED**"
        a(f"| {d.hypothesis} | {d.product} | {d.n_cells} | "
          f"{d.max_pairwise_overlap:.0%} | {route} ({d.verdict}) |")
    a("")
    for d in sorted(dis, key=lambda d: (d.hypothesis, d.product)):
        a(f"- **{d.hypothesis} / {d.product}** - {d.note}")
    a("")
    return "\n".join(w)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.reporting.level_rates")
    ap.add_argument("--products", nargs="*", default=["MNQ", "MGC"])
    args = ap.parse_args(argv)

    all_rates: list[CellRate] = []
    all_match: list[MatchReport] = []
    all_disj: list[Disjointness] = []
    meta: dict = {}
    for product in args.products:
        print(f"  measuring {product} ...", flush=True)
        r, m, d, info = measure(product)
        all_rates += r
        all_match += m
        all_disj += d
        meta[product] = info

    RATES_JSON.write_text(json.dumps(
        {"rates": [asdict(r) for r in all_rates],
         "disjointness": [asdict(d) for d in all_disj],
         "match": [asdict(x) for x in all_match]}, indent=2, default=str),
        encoding="utf-8")
    RATES_MD.write_text(render_rates(all_rates, meta), encoding="utf-8")
    MATCH_MD.write_text(render_reports(all_match), encoding="utf-8")
    DISJOINT_MD.write_text(render_disjointness(all_disj), encoding="utf-8")

    bad = [x for x in all_match if not x.ok]
    print(f"\n{len(all_rates)} cells measured across "
          f"{len({r.hypothesis for r in all_rates})} hypotheses")
    print(f"placebo matching: {len(all_match) - len(bad)}/{len(all_match)} level types ok")
    for x in bad:
        print(f"  FAIL {x.product} {x.level_type}: {x.failures[0][:100]}")
    print(f"wrote {RATES_MD.name}, {MATCH_MD.name}, {DISJOINT_MD.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

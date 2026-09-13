"""N02 S7 - round-number cross continuation, against matched placebo regions.

    python -m futuresres.signals.n02 [--dry-run]

THE LEVEL POPULATION IS CHOSEN WITHOUT REFERENCE TO WHERE PRICE LATER GOES: the two nearest
50-point grid levels above and below the SESSION-OPEN close, four per session. A first draft
admitted a level only when price came within 0.5 points of it, which made real levels touched
100% BY DEFINITION and could not be matched by any placebo. decisions.md 49.

MGC IS NOT A ROBUSTNESS INSTRUMENT HERE. Its real touch rate is 11.5% - gold's session range
rarely spans two 50-point steps - so the S8 cross-market route is closed before it is tried
and S8 rests on the era split alone.
"""
from __future__ import annotations
import argparse, json
from dataclasses import asdict
from pathlib import Path
from typing import Final
import numpy as np

from futuresres.levels import definitions as D
from futuresres.levels.placebo import make_region_placebo
from futuresres.signals.logged_run import stage1_run
from futuresres.signals.sweep_stage1 import (
    COST_BPS, FLOOR_BPS, ALPHA, MIN_EVENTS, Cell, apply_bh, paired_stats, _signed_return_bps,
)

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
DATE_RANGE: Final[tuple[str, str]] = ("2010-06-06", "2026-08-27")
PRODUCT: Final[str] = "MNQ"
GRID: Final[float] = 50.0
N_EACH: Final[int] = 2
D_GRID: Final[tuple[float, ...]] = (2.0, 4.0, 8.0)
HOLDS: Final[tuple[int, ...]] = (180,)
HORIZON_SCAN: Final[int] = 60


def round_levels(g: D.Grid) -> D.LevelSet:
    """Two grid levels either side of the session open. No path dependence."""
    close = g.close
    px, row, val, ref = [], [], [], []
    for r in range(g.n):
        o = close[r, 0]
        if not np.isfinite(o):
            continue
        base = np.floor(o / GRID) * GRID
        for k in range(-N_EACH + 1, N_EACH + 1):
            lvl = base + k * GRID
            if lvl <= 0:
                continue
            px.append(lvl); row.append(r); val.append(0); ref.append(o)
    return D.LevelSet(f"round{int(GRID)}_open", np.array(px, float), np.array(row, int),
                      np.array(val, int), np.array(ref, float))


def crosses(g: D.Grid, lv: D.LevelSet, d: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """First minute price trades through a level by d points; direction of the break."""
    close = g.close; n_min = close.shape[1]
    fired = np.zeros(lv.price.size, bool)
    minute = np.full(lv.price.size, -1, int)
    direction = np.zeros(lv.price.size, int)
    for i, (pxl, r, v) in enumerate(zip(lv.price, lv.row, lv.valid_from)):
        path = close[r, v:min(v + n_min, n_min)]
        if path.size < 2 or not np.isfinite(pxl):
            continue
        start = path[0]
        side = 1.0 if start < pxl else -1.0        # approaching from below or above
        hit = np.flatnonzero(side * (path - pxl) >= d)
        if hit.size:
            fired[i] = True; minute[i] = v + int(hit[0]); direction[i] = int(side)
    return fired, minute, direction


def variance_check(g: D.Grid) -> list[dict]:
    """S5 gate, re-run on the CORRECTED population (decisions.md 49)."""
    lv = round_levels(g); out = []; prev = None
    print(f"  {PRODUCT} N02 S5 gate, corrected population: {lv.price.size:,} levels "
          f"({lv.price.size/g.n:.1f}/session)", flush=True)
    for d in D_GRID:
        f, m, dd = crosses(g, lv, d)
        fm = m[f]
        same = float("nan")
        if prev is not None:
            b = f & prev[0]
            same = float((m[b] == prev[1][b]).mean()) if b.any() else float("nan")
        prev = (f.copy(), m.copy())
        rec = {"d": d, "fired": int(f.sum()), "per_session": int(f.sum())/g.n,
               "minute_sd": float(fm.std()) if fm.size else float("nan"),
               "identical_vs_prev": same,
               "up_share": float((dd[f] > 0).mean()) if f.any() else float("nan")}
        out.append(rec)
        print(f"    d={d:>4}pt: fired {rec['fired']:>7,} ({rec['per_session']:.2f}/sess) "
              f"sd {rec['minute_sd']:.1f} up={rec['up_share']:.2f}"
              + (f" identical-vs-prev {same:.1%}" if same == same else ""), flush=True)
    return out


def run(g: D.Grid, seed: int) -> list[Cell]:
    rng = np.random.default_rng(seed)
    lv = round_levels(g)
    sc = D.window_scale(g, lv)
    ok = np.isfinite(lv.price) & np.isfinite(sc) & (sc > 0)
    price, row, valid, ref = lv.price[ok], lv.row[ok], lv.valid_from[ok], lv.ref_price[ok]
    plac_px = make_region_placebo(price, ref, g.days[row], lv.kind, sc[ok])
    real = D.LevelSet(lv.kind, price, row, valid, ref)
    plac = D.LevelSet(lv.kind, plac_px, row, valid, ref)
    cells: list[Cell] = []
    for d in D_GRID:
        fr, mr, dr = crosses(g, real, d)
        fp, mp, dp = crosses(g, plac, d)
        for h in HOLDS:
            rr = _signed_return_bps(g, row, mr, dr, h)      # enter IN the break direction
            pp = _signed_return_bps(g, row, mp, dp, h)
            a, b, diff, lo, hi, n, pv = paired_stats(rr, pp, row, rng)
            sep = bool(np.isfinite(lo) and np.isfinite(hi) and (lo > 0 or hi < 0) and pv < ALPHA)
            cost = COST_BPS[PRODUCT]
            cells.append(Cell(PRODUCT, "N02", lv.kind, int(d), 0, h, events=n,
                              real_bps=a, placebo_bps=b, diff_bps=diff, ci_low=lo, ci_high=hi,
                              p_value=pv, separated=sep, cost_bps=cost,
                              diff_over_cost=(abs(diff)/cost if np.isfinite(diff) else float("nan")),
                              detection_floor_bps=FLOOR_BPS[(PRODUCT, h)],
                              entry_minute_sd=float(mr[fr].std()) if fr.any() else float("nan"),
                              real_dir_up_share=float((dr[fr] > 0).mean()) if fr.any() else float("nan")))
            c = cells[-1]
            print(f"    {PRODUCT} N02 d={d} H={h}: n={c.events:,} diff={c.diff_bps:+.4f} bps "
                  f"p={c.p_value:.4f} x_cost={c.diff_over_cost:.1f}", flush=True)
    return cells


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.signals.n02")
    ap.add_argument("--seed", type=int, default=20260913)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    g = D.load(PRODUCT, ROOT)
    if args.dry_run:
        out = ROOT / "reports" / "variance_check_N02_MNQ.json"
        out.write_text(json.dumps(variance_check(g), indent=1), encoding="utf-8")
        print(f"  wrote {out}", flush=True); return 0
    with stage1_run("N02", provenance="native", date_range=DATE_RANGE,
                    note=("round-number cross continuation vs matched arbitrary regions; "
                          "corrected level population, decisions.md 49; H=180")) as log:
        cells = run(g, args.seed)
        apply_bh(cells)
        log.record([c for c in cells if not c.excluded],
                   param_keys=["level_type", "m", "k", "horizon"])
    path = ROOT / "reports" / "n02_cells.json"
    path.write_text(json.dumps([asdict(c) for c in cells], indent=1, default=float), encoding="utf-8")
    print(f"  wrote {path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

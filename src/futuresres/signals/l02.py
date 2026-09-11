"""L02 Stage 1 — opening-range ABSORPTION only, against matched placebo regions.

    python -m futuresres.signals.l02 [--dry-run]

ABSORPTION ONLY. L02 registered two variants on MUTUALLY EXCLUSIVE price paths, and the
SWEEP arm was WITHDRAWN 2026-09-11 as degenerate: `confirmed_break` fired on every
opening-range level at valid_from + (k-1), so k was an offset rather than a selection, and
the high and low of the same session fired at the same minute in 92-99% of cases. Because the
arms are mutually exclusive by registration, absorption stands alone coherently and its 27
cells at H=180 are unaffected. decisions.md 41.

A corrected sweep condition would be a NEW REGISTRATION competing on its own merits, not an
inherited slot.

THE MECHANISM IS ATTENUATED ON MGC AND THIS RUN IS MGC-ONLY. 09:30 ET is the EQUITY cash
open; gold's own liquidity event is the COMEX open at 08:20. The registry says so, and says a
positive result on MGC would not support the mechanism as written. MNQ is unavailable for a
different reason - its best cell sits at 5,178 against a 5,884 detection floor - so the only
resolvable route is the one where the mechanism is weakest. That is a real limit on what this
run can establish and it belongs in the write-up, not in a footnote.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Final

import numpy as np

from futuresres.levels import definitions as D
from futuresres.signals.logged_run import stage1_run
from futuresres.signals.sweep_stage1 import (
    HOLDS, K_GRID, M_GRID, apply_bh, evaluate,
)

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
DATE_RANGE: Final[tuple[str, str]] = ("2010-06-06", "2026-08-27")
PRODUCTS: Final[tuple[str, ...]] = ("MGC",)
W_GRID: Final[tuple[int, ...]] = (15, 30, 60)

SPECS: Final[list] = [
    (f"or{W}", (lambda W: (lambda g: D.opening_range(g, W)))(W)) for W in W_GRID
]


def variance_check(product: str, g: D.Grid) -> list[dict]:
    """The check that would have caught the withdrawn sweep arm before it was registered."""
    out: list[dict] = []
    print(f"  {product} L02 absorption firing-minute variance check", flush=True)
    for level_type, factory in SPECS:
        lv = factory(g)
        n_half = lv.price.size // 2
        prev = None
        for m in M_GRID:
            f, mins, d = D.sweep_reclaim_directed(g, lv, m, 3, product)
            fm = mins[f]
            if fm.size == 0:
                continue
            hf, lf = f[:n_half], f[n_half:]
            both = hf & lf
            collide = int((mins[:n_half][both] == mins[n_half:][both]).sum())
            same = float("nan")
            if prev is not None:
                pf, pm = prev
                b = f & pf
                same = float((mins[b] == pm[b]).mean()) if b.any() else float("nan")
            prev = (f.copy(), mins.copy())
            rec = {"hypothesis": "L02", "product": product, "level_type": level_type,
                   "m": m, "fired": int(f.sum()), "minute_sd": float(fm.std()),
                   "minute_min": int(fm.min()), "minute_max": int(fm.max()),
                   "hi_lo_collision": (collide / int(both.sum())) if both.any() else 0.0,
                   "identical_minutes_vs_prev_m": same,
                   "up_share": float((d[f] > 0).mean())}
            out.append(rec)
            print(f"    {level_type} m={m}: fired={rec['fired']:,} "
                  f"minute sd={rec['minute_sd']:.1f} "
                  f"[{rec['minute_min']}..{rec['minute_max']}] "
                  f"hi/lo collide={rec['hi_lo_collision']:.1%}", flush=True)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.signals.l02")
    ap.add_argument("--seed", type=int, default=20260911)
    ap.add_argument("--dry-run", action="store_true",
                    help="firing-minute variance check only; spends no trials")
    args = ap.parse_args(argv)

    for product in PRODUCTS:
        g = D.load(product, ROOT)
        if args.dry_run:
            checks = variance_check(product, g)
            out = ROOT / "reports" / f"variance_check_L02_{product}.json"
            out.write_text(json.dumps(checks, indent=1), encoding="utf-8")
            print(f"  wrote {out}", flush=True)
            del g
            continue

        rng = np.random.default_rng(args.seed)
        with stage1_run("L02", provenance="native", date_range=DATE_RANGE,
                        note=("opening-range ABSORPTION only (sweep arm withdrawn, "
                              "decisions.md 41) vs matched arbitrary regions; H=180 "
                              "pre-registered")) as log:
            cells = evaluate("L02", product, SPECS, g, rng)
            apply_bh(cells)
            log.record([c for c in cells if not c.excluded],
                       param_keys=["level_type", "m", "k", "horizon"])
        path = ROOT / "reports" / "l02_cells.json"
        path.write_text(json.dumps([asdict(c) for c in cells], indent=1, default=float),
                        encoding="utf-8")
        print(f"  wrote {path}", flush=True)
        del g
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

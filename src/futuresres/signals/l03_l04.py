"""L03 and L04 Stage 1 — sweep-and-reclaim at prior-day and session extremes.

    python -m futuresres.signals.l03_l04 [--dry-run] [--hypothesis L03|L04]

ONE RUNNER FOR TWO HYPOTHESES because they are the same condition on different level types:
price exceeds a level by >= m ticks then closes back inside within k bars, traded COUNTER to
the penetration. L03 uses prior-day extremes, L04 session extremes. Sharing the
implementation means the pairing, the bootstrap and the permutation are right or wrong in one
place. They remain SEPARATE HYPOTHESES with separate trials and separate BH corrections.

--dry-run RUNS THE FIRING-MINUTE VARIANCE CHECK AND SPENDS NO TRIALS. Use it before any real
run. A condition that fires on everything at a fixed minute looks healthy in every summary
this project prints; it is only visible in the entry-minute distribution. That defect reached
three registered hypotheses before anyone looked (decisions.md 41).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Final

import numpy as np

from futuresres.levels import definitions as D
from futuresres.signals.logged_run import stage1_run
from futuresres.signals.sweep_stage1 import (
    HOLDS, K_GRID, M_GRID, Cell, apply_bh, evaluate,
)

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
DATE_RANGE: Final[tuple[str, str]] = ("2010-06-06", "2026-08-27")

#: MGC ONLY. On MNQ the best cell of each sits below the 180m detection floor of 5,884
#: (L03 3,762 = 0.64x, L04 5,442 = 0.93x), so no MNQ cell can reach a verdict.
PRODUCTS: Final[tuple[str, ...]] = ("MGC",)

SPECS: Final[dict[str, list]] = {
    "L03": [("prior_rth", lambda g: D.prior_day_levels(g, "prior_rth")),
            ("prior_full", lambda g: D.prior_day_levels(g, "prior_full"))],
    # sess_US/MGC FAILS placebo matching (touch ratio 1.33) and must not run Stage 1
    # (decisions.md 37). It is passed through anyway so `evaluate` records it as an
    # EXCLUDED cell with its measured reason rather than dropping it silently.
    "L04": [("sess_Asia", lambda g: D.session_extremes(g, "Asia")),
            ("sess_London", lambda g: D.session_extremes(g, "London")),
            ("sess_US", lambda g: D.session_extremes(g, "US"))],
}


def variance_check(hypothesis: str, product: str, g: D.Grid) -> list[dict]:
    """Does each parameter SELECT events, or merely offset an entry that happens anyway?"""
    out: list[dict] = []
    print(f"  {product} {hypothesis} firing-minute variance check", flush=True)
    for level_type, factory in SPECS[hypothesis]:
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
            rec = {"hypothesis": hypothesis, "product": product, "level_type": level_type,
                   "m": m, "fired": int(f.sum()), "minute_sd": float(fm.std()),
                   "minute_min": int(fm.min()), "minute_max": int(fm.max()),
                   "hi_lo_collision": (collide / int(both.sum())) if both.any() else 0.0,
                   "identical_minutes_vs_prev_m": same,
                   "up_share": float((d[f] > 0).mean())}
            out.append(rec)
            print(f"    {level_type} m={m}: fired={rec['fired']:,} "
                  f"minute sd={rec['minute_sd']:.1f} "
                  f"[{rec['minute_min']}..{rec['minute_max']}] "
                  f"hi/lo collide={rec['hi_lo_collision']:.1%} "
                  f"identical vs prev m={same:.1%}" if same == same else
                  f"    {level_type} m={m}: fired={rec['fired']:,} "
                  f"minute sd={rec['minute_sd']:.1f} "
                  f"[{rec['minute_min']}..{rec['minute_max']}] "
                  f"hi/lo collide={rec['hi_lo_collision']:.1%}", flush=True)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.signals.l03_l04")
    ap.add_argument("--hypothesis", choices=["L03", "L04"], action="append")
    ap.add_argument("--seed", type=int, default=20260911)
    ap.add_argument("--dry-run", action="store_true",
                    help="firing-minute variance check only; spends no trials")
    args = ap.parse_args(argv)
    hyps = args.hypothesis or ["L03", "L04"]

    for product in PRODUCTS:
        g = D.load(product, ROOT)
        if args.dry_run:
            checks = [r for h in hyps for r in variance_check(h, product, g)]
            out = ROOT / "reports" / f"variance_check_{'_'.join(hyps)}_{product}.json"
            out.write_text(json.dumps(checks, indent=1), encoding="utf-8")
            print(f"  wrote {out}", flush=True)
            continue

        for h in hyps:
            rng = np.random.default_rng(args.seed)
            with stage1_run(h, provenance="native", date_range=DATE_RANGE,
                            note=("sweep-and-reclaim vs matched arbitrary regions "
                                  "(decisions.md 37); H=180 pre-registered; matched level "
                                  "types only")) as log:
                cells = evaluate(h, product, SPECS[h], g, rng)
                apply_bh(cells)
                log.record([c for c in cells if not c.excluded],
                           param_keys=["level_type", "m", "k", "horizon"])
            path = ROOT / "reports" / f"{h.lower()}_cells.json"
            path.write_text(json.dumps([asdict(c) for c in cells], indent=1, default=float),
                            encoding="utf-8")
            print(f"  wrote {path}", flush=True)
        del g
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

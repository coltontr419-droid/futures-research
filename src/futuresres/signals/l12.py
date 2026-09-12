"""L12 Stage 1 - L04's Asia-session result, tested out of sample on MNQ.

    python -m futuresres.signals.l12 [--dry-run]

WHAT THIS IS. L04 tested three session types on MGC. `sess_Asia` gave 5 of 18 nominal
separations and `sess_London` gave none, so Asia was **selected by its result**
(decisions.md 43). Selection by result is not repaired by re-testing the survivor on the same
data - 38 refused that for L07's mirror and 43 refused it here. It is repaired by testing the
selected claim on data that did not generate it.

**MNQ IS THAT DATA, AND MGC IS DELIBERATELY EXCLUDED.** The two-instrument Stage 4 requirement
cannot be met and must not be: MGC generated the claim, so an "out-of-sample" test including
it would not be one.

THE PREDICTION IS REGISTERED, not derived here: positive, +1.3 to +3.5 bps, and it CONFIRMS
only on a positive mean AND at least one BH survivor at FDR 0.05 - both, not either. A
positive point estimate that fails correction is what L04 already produced; reproducing it on
a second instrument without clearing the bar leaves the claim exactly where it was. See
hypotheses.yaml L12 `prediction`.

POWER IS SHORT OF THE TABULATED FLOOR AND THE REGISTRATION SAYS SO. 4,903-5,442 firings
against 5,884 at 180m. That floor sizes the pipeline's MINIMUM resolvable effect (15.66 bps),
not the +3.5 bps under test, and MGC separated on 2,715 paired events. A null here is
correspondingly weaker evidence than a null at full power.
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
from futuresres.signals.sweep_stage1 import M_GRID, apply_bh, evaluate

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
DATE_RANGE: Final[tuple[str, str]] = ("2010-06-06", "2026-08-27")
PRODUCT: Final[str] = "MNQ"
SPECS: Final[list] = [("sess_Asia", lambda g: D.session_extremes(g, "Asia"))]


def variance_check(g: D.Grid) -> list[dict]:
    """The same check run before L02/L03/L04, on this runner's own output."""
    out: list[dict] = []
    print(f"  {PRODUCT} L12 firing-minute variance check", flush=True)
    lv = D.session_extremes(g, "Asia")
    n_half = lv.price.size // 2
    prev = None
    for m in M_GRID:
        f, mins, d = D.sweep_reclaim_directed(g, lv, m, 3, PRODUCT)
        fm = mins[f]
        if fm.size == 0:
            continue
        both = f[:n_half] & f[n_half:]
        collide = int((mins[:n_half][both] == mins[n_half:][both]).sum())
        same = float("nan")
        if prev is not None:
            pf, pm = prev
            b = f & pf
            same = float((mins[b] == pm[b]).mean()) if b.any() else float("nan")
        prev = (f.copy(), mins.copy())
        rec = {"hypothesis": "L12", "product": PRODUCT, "level_type": "sess_Asia", "m": m,
               "fired": int(f.sum()), "minute_sd": float(fm.std()),
               "minute_min": int(fm.min()), "minute_max": int(fm.max()),
               "hi_lo_collision": (collide / int(both.sum())) if both.any() else 0.0,
               "identical_minutes_vs_prev_m": same,
               "up_share": float((d[f] > 0).mean())}
        out.append(rec)
        print(f"    sess_Asia m={m}: fired={rec['fired']:,} minute sd={rec['minute_sd']:.1f} "
              f"[{rec['minute_min']}..{rec['minute_max']}] "
              f"hi/lo collide={rec['hi_lo_collision']:.1%}", flush=True)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.signals.l12")
    ap.add_argument("--seed", type=int, default=20260911)
    ap.add_argument("--dry-run", action="store_true",
                    help="firing-minute variance check only; spends no trials")
    args = ap.parse_args(argv)

    g = D.load(PRODUCT, ROOT)
    if args.dry_run:
        out = ROOT / "reports" / "variance_check_L12_MNQ.json"
        out.write_text(json.dumps(variance_check(g), indent=1), encoding="utf-8")
        print(f"  wrote {out}", flush=True)
        return 0

    rng = np.random.default_rng(args.seed)
    with stage1_run("L12", provenance="native", date_range=DATE_RANGE,
                    note=("OUT-OF-SAMPLE test of L04's sess_Asia result, MNQ; prediction "
                          "pre-registered in hypotheses.yaml L12; H=180")) as log:
        cells = evaluate("L12", PRODUCT, SPECS, g, rng)
        apply_bh(cells)
        log.record([c for c in cells if not c.excluded],
                   param_keys=["level_type", "m", "k", "horizon"])
    path = ROOT / "reports" / "l12_cells.json"
    path.write_text(json.dumps([asdict(c) for c in cells], indent=1, default=float),
                    encoding="utf-8")
    print(f"  wrote {path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""L07 market-state comparison: what the market was doing when each entry fired.

    python -m futuresres.signals.l07_state

THIS IS A MEASUREMENT, NOT A TEST. It searches nothing, computes no candidate, and cannot
promote anything, so it spends no trial and logs to `measurements.jsonl` on the same
reasoning that keeps firing rates out of N. N stays at 684.

WHY IT EXISTS, AND IT IS NOT A ROBUSTNESS CHECK. `decisions.md` 37 records that the
redefined null - an arbitrary region at a matched distance - is a WEAKER control than the
displaced level it replaced, because it no longer holds constant HOW PRICE ARRIVED. It
equalises where the region sits and how often price reaches it, and nothing else.

**A fair-value gap forms, by definition, immediately after a fast directional move.** So real
entries may sit downstream of volatility spikes while their matched placebos do not. If they
do, that alone would produce a real-minus-placebo difference that GROWS WITH GAP WIDTH -
because a wider gap means a faster move - without any difference in reaction at the zone. That
is precisely the competing explanation 37 says this design cannot separate, and the L07 result
shows exactly that monotone widening in w.

So this measurement is the one that decides how the L07 result may be written up. It is
reported whether or not it shows a difference.

THREE STATE VARIABLES, chosen before looking:
  realized volatility over the preceding 30 and 60 minutes   - the direct test of the above
  time of day                                                - gaps cluster at the open
  distance from session open                                 - trend context

SUBSAMPLED, AND THAT IS SAFE HERE. Zones are capped per configuration with a fixed seed.
These are distributional medians, not a significance test; tens of thousands of entries pin a
median far tighter than any difference worth acting on, and the full population would cost an
hour to say the same thing.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

import numpy as np

from futuresres.levels import definitions as D
from futuresres.levels.placebo import make_region_placebo
from futuresres.signals.l07 import GS, PRODUCTS, TFS, WS, _first_entry, matched_types

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
REPORT: Final[Path] = ROOT / "reports" / "l07_market_state.md"
JSON_OUT: Final[Path] = ROOT / "reports" / "l07_market_state.json"
MEASUREMENTS: Final[Path] = ROOT / "measurements.jsonl"

CAP: Final[int] = 40_000
SEED: Final[int] = 20260910


@dataclass(slots=True)
class StateRow:
    product: str
    w: int
    tf: int
    g: int
    n_real: int
    n_placebo: int
    rv30_real: float
    rv30_placebo: float
    rv30_ratio: float
    rv60_real: float
    rv60_placebo: float
    rv60_ratio: float
    minute_real: float
    minute_placebo: float
    minute_diff: float
    from_open_real: float
    from_open_placebo: float
    from_open_ratio: float


def _realized_vol_bps(g: D.Grid, row: np.ndarray, entry: np.ndarray,
                      window: int) -> np.ndarray:
    """Root sum of squared 1m log returns over the `window` minutes BEFORE entry, in bps.

    Strictly prior: the entry minute itself is excluded, so the number describes what the
    market had already done when the entry fired rather than what it did at it.
    """
    out = np.full(row.size, np.nan)
    for i in range(row.size):
        e = int(entry[i])
        if e <= 1:
            continue
        lo = max(e - window, 0)
        seg = g.close[row[i], lo:e]
        if seg.size < 3 or not np.isfinite(seg).all() or (seg <= 0).any():
            continue
        r = np.diff(np.log(seg))
        out[i] = float(np.sqrt(np.sum(r * r)) * 1e4)
    return out


def _from_open_bps(g: D.Grid, row: np.ndarray, entry: np.ndarray) -> np.ndarray:
    """|entry price - the session's 09:30 ET open| in bps of that open."""
    out = np.full(row.size, np.nan)
    for i in range(row.size):
        e = int(entry[i])
        if e < 0:
            continue
        op = g.close[row[i], D.RTH_OPEN]
        px = g.close[row[i], e]
        if op > 0 and px > 0:
            out[i] = abs(np.log(px / op)) * 1e4
    return out


def _med(x: np.ndarray) -> float:
    f = x[np.isfinite(x)]
    return float(np.median(f)) if f.size else float("nan")


def run(product: str) -> list[StateRow]:
    rng = np.random.default_rng(SEED)
    mt = matched_types()
    g = D.load(product, ROOT)
    rows: list[StateRow] = []

    for tf in TFS:
        for w in WS:
            lt = f"fvg_w{w}_{tf}m"
            rec = mt.get((lt, product))
            if rec is None or rec.get("failures"):
                print(f"    {product} {lt}: EXCLUDED, placebo unmatched", flush=True)
                continue

            zones, half, created = D.fvg_zones_directed(g, w, tf, product)
            scale = D.window_scale(g, zones)
            good = np.flatnonzero(np.isfinite(zones.price) & np.isfinite(half)
                                  & np.isfinite(scale) & (scale > 0))
            if good.size < 100:
                continue
            if good.size > CAP:
                good = np.sort(rng.choice(good, CAP, replace=False))

            z_price, z_row = zones.price[good], zones.row[good]
            z_valid, z_half = zones.valid_from[good], half[good]
            z_ref, z_scale = zones.ref_price[good], scale[good]
            placebo = make_region_placebo(z_price, z_ref, g.days[z_row], lt, z_scale)

            for gb in GS:
                earliest = np.minimum(z_valid + gb * tf, D.ROW_MINUTES - 1)
                e_real = _first_entry(g, z_price, z_half, z_row, earliest)
                e_plac = _first_entry(g, placebo, z_half, z_row, earliest)
                fr, fp = e_real >= 0, e_plac >= 0

                def state(mask: np.ndarray, ent: np.ndarray) -> tuple:
                    r30 = _realized_vol_bps(g, z_row[mask], ent[mask], 30)
                    r60 = _realized_vol_bps(g, z_row[mask], ent[mask], 60)
                    fo = _from_open_bps(g, z_row[mask], ent[mask])
                    return _med(r30), _med(r60), float(np.median(ent[mask])), _med(fo)

                a30, a60, amin, aopen = state(fr, e_real)
                b30, b60, bmin, bopen = state(fp, e_plac)
                rows.append(StateRow(
                    product, w, tf, gb, int(fr.sum()), int(fp.sum()),
                    a30, b30, a30 / b30 if b30 else float("nan"),
                    a60, b60, a60 / b60 if b60 else float("nan"),
                    amin, bmin, amin - bmin,
                    aopen, bopen, aopen / bopen if bopen else float("nan"),
                ))
                print(f"    {product} {lt} g={gb}: rv30 real {a30:.1f} vs placebo {b30:.1f} "
                      f"({rows[-1].rv30_ratio:.2f}x)", flush=True)
    return rows


def _clock(minute_of_row: float) -> str:
    """Minute-of-row back to an ET clock time. Row starts at 18:00 ET."""
    total = (D.ROW_START_MOD + int(round(minute_of_row))) % 1440
    return f"{total // 60:02d}:{total % 60:02d}"


def render(rows: list[StateRow]) -> str:
    w: list[str] = []
    a = w.append
    a("# L07 market-state comparison — real entries against placebo entries")
    a("")
    a("**A measurement, not a test.** It searches nothing and spends no trial; N stays at "
      "684. It exists to decide how the L07 Stage 1 result may be written up.")
    a("")
    a("`decisions.md` §37 records that the redefined null is a **weaker** control than the "
      "one it replaced: it equalises *where* a region sits and *how often* price reaches it, "
      "and nothing else. It does **not** hold constant how price arrived.")
    a("")
    a("**A fair-value gap forms, by definition, immediately after a fast directional move.** "
      "If real entries sit downstream of volatility spikes and their matched placebos do "
      "not, that alone produces a real-minus-placebo difference **growing with gap width** — "
      "a wider gap means a faster move — with no difference in reaction at the zone. L07's "
      "result shows exactly that monotone widening in `w`, so this is the competing "
      "explanation that has to be measured rather than argued.")
    a("")

    for product in PRODUCTS:
        sub = [r for r in rows if r.product == product]
        if not sub:
            continue
        rv30 = [r.rv30_ratio for r in sub if np.isfinite(r.rv30_ratio)]
        rv60 = [r.rv60_ratio for r in sub if np.isfinite(r.rv60_ratio)]
        fo = [r.from_open_ratio for r in sub if np.isfinite(r.from_open_ratio)]
        md = [r.minute_diff for r in sub if np.isfinite(r.minute_diff)]
        a(f"## {product}")
        a("")
        a("| state variable | real / placebo, median across cells | range |")
        a("|---|---|---|")
        a(f"| realized vol, prior 30 min | **{np.median(rv30):.2f}×** | "
          f"{min(rv30):.2f}× – {max(rv30):.2f}× |")
        a(f"| realized vol, prior 60 min | **{np.median(rv60):.2f}×** | "
          f"{min(rv60):.2f}× – {max(rv60):.2f}× |")
        a(f"| distance from session open | **{np.median(fo):.2f}×** | "
          f"{min(fo):.2f}× – {max(fo):.2f}× |")
        a(f"| entry time, real minus placebo | **{np.median(md):+.0f} min** | "
          f"{min(md):+.0f} – {max(md):+.0f} min |")
        a("")
        a("| w | tf | g | n real | n plac | rv30 real | rv30 plac | ratio | rv60 ratio | "
          "entry real | entry plac | from-open ratio |")
        a("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for r in sorted(sub, key=lambda r: (r.tf, r.w, r.g)):
            a(f"| {r.w} | {r.tf}m | {r.g} | {r.n_real:,} | {r.n_placebo:,} | "
              f"{r.rv30_real:.1f} | {r.rv30_placebo:.1f} | **{r.rv30_ratio:.2f}×** | "
              f"{r.rv60_ratio:.2f}× | {_clock(r.minute_real)} | {_clock(r.minute_placebo)} | "
              f"{r.from_open_ratio:.2f}× |")
        a("")
    return "\n".join(w) + "\n"


def log_measurement(rows: list[StateRow]) -> str:
    from futuresres.stats.trials import Trial, TrialLog

    log = TrialLog(MEASUREMENTS)
    rv = [r.rv30_ratio for r in rows if np.isfinite(r.rv30_ratio)]
    t = Trial(
        trial_id=log.next_id("m"),
        hypothesis_id="L07",
        params={"kind": "market_state", "cells": len(rows), "cap": CAP, "seed": SEED,
                "rv30_ratio_median": float(np.median(rv)) if rv else None},
        symbol="MGC/MNQ",
        date_range=("2010-06-06", "2026-08-27"),
        status="completed",
        note=("kind=measurement; NOT a trial and NOT counted in N - a descriptive "
              "comparison of market state at real versus placebo entries, run to decide how "
              "the L07 Stage 1 result may be written up. Searches nothing and cannot "
              "produce a candidate. decisions.md 37."),
    )
    log.append(t)
    return t.trial_id


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.signals.l07_state")
    ap.add_argument("--product", choices=PRODUCTS, action="append")
    args = ap.parse_args(argv)
    products = tuple(args.product) if args.product else PRODUCTS

    rows: list[StateRow] = []
    for product in products:
        print(f"  {product} ...", flush=True)
        rows.extend(run(product))

    JSON_OUT.write_text(json.dumps([asdict(r) for r in rows], indent=2, default=float),
                        encoding="utf-8")
    REPORT.write_text(render(rows), encoding="utf-8")
    mid = log_measurement(rows)
    print(f"\nwrote {REPORT.name}, {JSON_OUT.name}; logged {mid} (no trial spent)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

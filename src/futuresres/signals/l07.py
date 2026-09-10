"""L07 Stage 1 — fair-value-gap fill, real zones against matched placebo regions.

    python -m futuresres.signals.l07

THE STATISTIC IS (REAL - PLACEBO), NEVER (REAL - 0). LEVEL_HYPOTHESES.md is explicit: price
reacts at arbitrary levels, so a raw fill statistic is not evidence that a gap matters. L07's
own registry entry doubts its counterparty in writing and predicts the raw number will look
impressive - 70-90% - and be equally impressive for placebo zones. Only the difference is
evidence.

THE PLACEBO IS THE NULL AS REDEFINED 2026-09-09 (decisions.md 37): an arbitrary REGION at a
matched distance, carrying the same half-width and the same traded direction as the real zone
it is paired with. Region against region, not point against point.

MATCHED TYPES ONLY, AND EXCLUSIONS ARE EXPLICIT. Every level type is checked against
reports/level_rates.json before it is used. An unmatched type is recorded as an excluded cell
with its measured ratios, never dropped by omission - a type that vanishes from a report is
indistinguishable from one nobody thought of.

WHY THE ECONOMICS DECIDES THIS AND NOT THE P-VALUE. L07 fires 535,428 times on MNQ and
655,490 on MGC against detection floors of 5,884 and 2,862. At that event count a separation
is close to assured for any effect that is not exactly zero, so a significant result carries
almost no information on its own. The number that decides L07 is the size of the difference in
basis points against the measured cost floor.

THE DIRECTION IS THE REGISTERED ONE AND IT IS WORTH STATING. "Counter to the move that created
the gap": a bullish imbalance is created by an up-move, so the trade is SHORT on entry into
the zone. That is consistent with the registered mechanism, which claims price returns to FILL
the zone rather than reverse at it - the trade rides the fill rather than fading it. The
opposite reading, zone-as-support, is a different hypothesis and is not what is registered.
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
from futuresres.signals.logged_run import stage1_run
from futuresres.signals.stage1 import calibrated_alpha

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
RATES: Final[Path] = ROOT / "reports" / "level_rates.json"
REPORT: Final[Path] = ROOT / "reports" / "l07_stage1.md"
CELLS_JSON: Final[Path] = ROOT / "reports" / "l07_cells.json"

WS: Final[tuple[int, ...]] = (2, 4, 8)
GS: Final[tuple[int, ...]] = (10, 30, 60)
TFS: Final[tuple[int, ...]] = (1, 5)
HOLDS: Final[tuple[int, ...]] = (60, 120, 180)
PRODUCTS: Final[tuple[str, ...]] = ("MGC", "MNQ")

COST_BPS: Final[dict[str, float]] = {"MNQ": 0.48, "MGC": 0.65}
#: reports/calibration.md. The smallest effect the pipeline can resolve at each horizon.
FLOOR_BPS: Final[dict[tuple[str, int], float]] = {
    ("MNQ", 60): 2.57, ("MNQ", 120): 15.66, ("MNQ", 180): 15.66,
    ("MGC", 60): 4.17, ("MGC", 120): 14.34, ("MGC", 180): 14.34,
}

ALPHA: Final[float] = 0.05
N_BOOT: Final[int] = 2000
N_PERM: Final[int] = 2000
DATE_RANGE: Final[tuple[str, str]] = ("2010-06-06", "2026-08-27")


@dataclass(slots=True)
class Cell:
    product: str
    w: int
    g: int
    tf: int
    horizon: int
    level_type: str
    excluded: bool = False
    reason: str = ""
    events: int = 0
    real_bps: float = float("nan")
    placebo_bps: float = float("nan")
    diff_bps: float = float("nan")
    ci_low: float = float("nan")
    ci_high: float = float("nan")
    p_value: float = float("nan")
    separated: bool = False
    bh_survivor: bool = False
    cost_bps: float = float("nan")
    diff_over_cost: float = float("nan")
    detection_floor_bps: float = float("nan")
    sharpe: float | None = None


def matched_types(path: Path = RATES) -> dict[tuple[str, str], dict]:
    """Every level type's matching verdict, keyed (level_type, product)."""
    m = json.loads(path.read_text(encoding="utf-8"))["match"]
    return {(x["level_type"], x["product"]): x for x in m}


def benjamini_hochberg(p: np.ndarray, alpha: float = ALPHA) -> np.ndarray:
    """Standard step-up. Returns a boolean mask of survivors."""
    p = np.asarray(p, float)
    n = p.size
    if n == 0:
        return np.zeros(0, bool)
    order = np.argsort(p)
    thresh = alpha * (np.arange(1, n + 1) / n)
    passed = p[order] <= thresh
    keep = np.zeros(n, bool)
    if passed.any():
        cutoff = np.flatnonzero(passed).max()
        keep[order[: cutoff + 1]] = True
    return keep


def _first_entry(g: D.Grid, centre: np.ndarray, half: np.ndarray, row: np.ndarray,
                 earliest: np.ndarray) -> np.ndarray:
    """First minute-of-row at or after `earliest` whose close sits inside [c-h, c+h].

    -1 where the region is never entered. One pass per region; the `g` parameter only moves
    `earliest`, so all three g values share this scan by being called with different
    `earliest` arrays rather than by rescanning the grid.
    """
    out = np.full(centre.size, -1, np.int64)
    close = g.close
    for i in range(centre.size):
        c, h, r, e = centre[i], half[i], row[i], earliest[i]
        if not (np.isfinite(c) and np.isfinite(h)) or e >= D.ROW_MINUTES - 1:
            continue
        path = close[r, e:]
        hit = np.flatnonzero(np.abs(path - c) <= h)
        if hit.size:
            out[i] = e + hit[0]
    return out


def _signed_return_bps(g: D.Grid, row: np.ndarray, entry: np.ndarray,
                       traded_dir: np.ndarray, horizon: int) -> np.ndarray:
    """Signed log return from the entry close to min(entry + horizon, 15:55 ET), in bps."""
    out = np.full(row.size, np.nan)
    exit_cap = D.RTH_EXIT
    for i in range(row.size):
        e = entry[i]
        if e < 0:
            continue
        x = min(e + horizon, exit_cap, D.ROW_MINUTES - 1)
        if x <= e:
            continue
        p0, p1 = g.close[row[i], e], g.close[row[i], x]
        if p0 > 0 and p1 > 0:
            out[i] = traded_dir[i] * np.log(p1 / p0) * 1e4
    return out


def _paired_stats(
    real: np.ndarray, plac: np.ndarray, rows: np.ndarray, rng: np.random.Generator
) -> tuple[float, float, float, float, float, int, float]:
    """Paired real-minus-placebo difference with a session bootstrap and an exact-style
    paired permutation.

    THE BOOTSTRAP RESAMPLES SESSIONS, NOT EVENTS. Zones cluster heavily inside a session -
    one trending morning produces dozens - so resampling events would treat a session's
    worth of correlated observations as independent and report an interval far too narrow.

    THE PERMUTATION SWAPS REAL AND PLACEBO WITHIN A PAIR. Under the null that the zone
    carries no information, which member of a pair is the real one is exchangeable, so
    flipping the label at random is the right randomisation. It needs no distributional
    assumption and it is paired, which removes the session-level common movement that
    dominates both series.
    """
    ok = np.isfinite(real) & np.isfinite(plac)
    r, p_, s = real[ok], plac[ok], rows[ok]
    n = r.size
    if n < 100:
        return (float("nan"),) * 5 + (n, float("nan"))

    d = r - p_
    obs = float(d.mean())

    sessions = np.unique(s)
    idx_by_session = {int(v): np.flatnonzero(s == v) for v in sessions}
    keys = list(idx_by_session)
    boot = np.empty(N_BOOT)
    for b in range(N_BOOT):
        pick = rng.integers(0, len(keys), len(keys))
        take = np.concatenate([idx_by_session[keys[k]] for k in pick])
        boot[b] = d[take].mean()
    eff_alpha = calibrated_alpha(max(len(keys), 2))
    lo, hi = np.percentile(boot, [100 * eff_alpha / 2, 100 * (1 - eff_alpha / 2)])

    null = np.empty(N_PERM)
    for k in range(N_PERM):
        flip = rng.integers(0, 2, n) * 2 - 1
        null[k] = float((d * flip).mean())
    pval = float(np.mean(np.abs(null) >= abs(obs)))

    return float(r.mean()), float(p_.mean()), obs, float(lo), float(hi), n, pval


def run(product: str, seed: int = 20260909) -> list[Cell]:
    rng = np.random.default_rng(seed)
    mt = matched_types()
    g = D.load(product, ROOT)
    cells: list[Cell] = []

    for tf in TFS:
        for w in WS:
            lt = f"fvg_w{w}_{tf}m"
            rec = mt.get((lt, product))
            ok = rec is not None and not rec.get("failures")
            if not ok:
                why = ("no matching record" if rec is None
                       else "; ".join(rec["failures"])[:200])
                for gb in GS:
                    for h in HOLDS:
                        cells.append(Cell(product, w, gb, tf, h, lt, excluded=True,
                                          reason=f"EXCLUDED, placebo unmatched: {why}"))
                print(f"    {product} {lt}: EXCLUDED - {why}", flush=True)
                continue

            zones, half, created = D.fvg_zones_directed(g, w, tf, product)
            scale = D.window_scale(g, zones)
            good = (np.isfinite(zones.price) & np.isfinite(half) & np.isfinite(scale)
                    & (scale > 0))
            if good.sum() < 100:
                continue
            z_price = zones.price[good]
            z_row, z_valid = zones.row[good], zones.valid_from[good]
            z_half, z_dir = half[good], created[good]
            z_ref, z_scale = zones.ref_price[good], scale[good]
            days = g.days[z_row]

            placebo = make_region_placebo(z_price, z_ref, days, lt, z_scale)
            # The traded direction is COUNTER to the move that created the gap, and the
            # placebo inherits it so the pair differs only in WHERE the region sits.
            traded = -z_dir

            for gb in GS:
                earliest = np.minimum(z_valid + gb * tf, D.ROW_MINUTES - 1)
                e_real = _first_entry(g, z_price, z_half, z_row, earliest)
                e_plac = _first_entry(g, placebo, z_half, z_row, earliest)
                for h in HOLDS:
                    rr = _signed_return_bps(g, z_row, e_real, traded, h)
                    pp = _signed_return_bps(g, z_row, e_plac, traded, h)
                    rmean, pmean, diff, lo, hi, n, pval = _paired_stats(rr, pp, z_row, rng)
                    sep = bool(np.isfinite(lo) and np.isfinite(hi)
                               and (lo > 0 or hi < 0) and pval < ALPHA)
                    cost = COST_BPS[product]
                    cells.append(Cell(
                        product, w, gb, tf, h, lt, events=n,
                        real_bps=rmean, placebo_bps=pmean, diff_bps=diff,
                        ci_low=lo, ci_high=hi, p_value=pval, separated=sep,
                        cost_bps=cost,
                        diff_over_cost=(abs(diff) / cost if np.isfinite(diff) else float("nan")),
                        detection_floor_bps=FLOOR_BPS[(product, h)],
                    ))
                print(f"    {product} {lt} g={gb}: {len(GS) and ''}"
                      f"n={cells[-1].events:,} diff={cells[-1].diff_bps:+.4f} bps",
                      flush=True)
    return cells


def apply_bh(cells: list[Cell]) -> None:
    """BH WITHIN THE HYPOTHESIS, across every test actually performed.

    Excluded cells are not tests and are left out of the correction - including them would
    inflate the denominator with things that were never looked at, which makes the
    correction weaker rather than more honest. The count of tests is reported alongside so
    the denominator stays visible.
    """
    live = [c for c in cells if not c.excluded and np.isfinite(c.p_value)]
    if not live:
        return
    keep = benjamini_hochberg(np.array([c.p_value for c in live]))
    for c, k in zip(live, keep):
        c.bh_survivor = bool(k) and c.separated


def render(cells: list[Cell]) -> str:
    w: list[str] = []
    a = w.append
    live = [c for c in cells if not c.excluded]
    excl = [c for c in cells if c.excluded]

    a("# L07 Stage 1 - fair-value-gap fill, against matched placebo regions")
    a("")
    a("Every figure is **(real zone) minus (placebo region)**. A raw fill statistic is not "
      "evidence that a gap matters, because price reacts at arbitrary levels; only the "
      "difference is. The placebo is the null as redefined in `decisions.md` 37 - an "
      "arbitrary region at a matched distance, carrying the **same half-width and the same "
      "traded direction** as the real zone it is paired with.")
    a("")
    a("## The number that decides this is not the p-value")
    a("")
    a("L07 fires hundreds of thousands of times against detection floors in the thousands. "
      "**At that event count a separation is close to assured for any effect that is not "
      "exactly zero**, so significance carries almost no information here. The deciding "
      "number is the size of the difference in basis points against the measured cost "
      "floor: MNQ **0.48 bps**, MGC **0.65 bps**, both round trip.")
    a("")

    for product in PRODUCTS:
        sub = [c for c in live if c.product == product]
        if not sub:
            continue
        n_tests = len(sub)
        n_sep = sum(c.separated for c in sub)
        n_bh = sum(c.bh_survivor for c in sub)
        best = max(sub, key=lambda c: abs(c.diff_bps) if np.isfinite(c.diff_bps) else -1.0)
        a("## " + product)
        a("")
        a("| | |")
        a("|---|---|")
        a("| tests performed | {} |".format(n_tests))
        a("| nominal separations | **{}** |".format(n_sep))
        a("| expected by chance at alpha=0.05 | {:.1f} |".format(n_tests * ALPHA))
        a("| BH survivors at FDR 0.05 | **{}** |".format(n_bh))
        a("| largest absolute difference | **{:+.4f} bps** (w={}, g={}, tf={}m, H={}) |"
          .format(best.diff_bps, best.w, best.g, best.tf, best.horizon))
        a("| cost floor | {:.2f} bps |".format(COST_BPS[product]))
        a("| largest difference as a fraction of cost | **{:.3f}x** |"
          .format(abs(best.diff_bps) / COST_BPS[product]))
        a("")
        over = [c for c in sub if np.isfinite(c.diff_bps)
                and abs(c.diff_bps) > COST_BPS[product]]
        if over:
            a("**{} of {} cells exceed the cost floor.**".format(len(over), n_tests))
        else:
            a("**Not one of the {} cells produces a difference larger than the cost "
              "floor.**".format(n_tests))
        a("")
        a("| w | g | tf | H | events | real bps | placebo bps | **diff bps** | CI | p | "
          "sep | BH | diff/cost |")
        a("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for c in sorted(sub, key=lambda c: (c.tf, c.w, c.g, c.horizon)):
            ci = ("[{:+.3f}, {:+.3f}]".format(c.ci_low, c.ci_high)
                  if np.isfinite(c.ci_low) else "-")
            a("| {} | {} | {}m | {} | {:,} | {:+.3f} | {:+.3f} | **{:+.4f}** | {} | "
              "{:.4f} | {} | {} | {:.3f}x |".format(
                  c.w, c.g, c.tf, c.horizon, c.events, c.real_bps, c.placebo_bps,
                  c.diff_bps, ci, c.p_value,
                  "yes" if c.separated else "no",
                  "yes" if c.bh_survivor else "no", c.diff_over_cost))
        a("")

    a("## Level types excluded, stated rather than omitted")
    a("")
    if excl:
        seen: dict[tuple[str, str], str] = {}
        for c in excl:
            seen.setdefault((c.level_type, c.product), c.reason)
        a("| level type | product | why |")
        a("|---|---|---|")
        for (lt, p), why in sorted(seen.items()):
            a("| `{}` | {} | {} |".format(lt, p, why))
        a("")
        a("**{} cells were not run.** They are listed because a type that simply vanishes "
          "from a report is indistinguishable from one nobody thought of.".format(len(excl)))
    else:
        a("**None, and that is a measured statement rather than an empty section.** All six "
          "fair-value-gap level types match their placebo on both instruments - 12 of 12 "
          "type-product pairs in `reports/placebo_match.md` - so every registered cell was "
          "run. Each type was checked against the matching report before use; none was "
          "dropped by omission.")
    a("")
    a("## What the design does, and what it costs")
    a("")
    a("1. **Direction is the registered one.** \"Counter to the move that created the "
      "gap\": a bullish imbalance is created by an up-move, so the trade is SHORT on entry "
      "into the zone. That matches the registered mechanism, which claims price returns to "
      "*fill* the zone rather than reverse at it. The zone-as-support reading is a "
      "different hypothesis and is not what is registered.")
    a("2. **The placebo inherits its pair's half-width and traded direction**, so the two "
      "differ only in *where the region sits*.")
    a("3. **The bootstrap resamples sessions, not events.** Zones cluster heavily inside a "
      "session, so resampling events would treat correlated observations as independent "
      "and report an interval far too narrow.")
    a("4. **The permutation swaps real and placebo within a pair.** Under the null that the "
      "zone carries no information, which member of a pair is real is exchangeable.")
    a("5. **The control is weaker than it looks**, per 37: a matched-distance arbitrary "
      "region does not hold constant *how price arrived*. A surviving difference could be "
      "price arriving at real zones differently rather than reacting at them differently, "
      "and this design cannot separate those.")
    return "\n".join(w) + "\n"


def _logged_trials(hypothesis_id: str) -> int:
    """How many trials this hypothesis has already spent, read from the chained log."""
    from futuresres.signals.logged_run import TRIAL_LOG
    from futuresres.stats.trials import TrialLog

    return sum(1 for t in TrialLog(TRIAL_LOG).read_all()
               if t.hypothesis_id == hypothesis_id)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.signals.l07")
    ap.add_argument("--product", choices=PRODUCTS, action="append")
    ap.add_argument("--seed", type=int, default=20260909)
    ap.add_argument("--reuse-trials", action="store_true",
                    help="recompute a run whose trials are already logged; refuses if "
                         "they are not on file")
    args = ap.parse_args(argv)
    products = tuple(args.product) if args.product else PRODUCTS

    cells: list[Cell] = []
    if args.reuse_trials:
        # THE TRIALS FOR THIS RUN ARE ALREADY SPENT AND LOGGED. The first execution
        # completed both instruments, recorded all 108 trials, and then died writing the
        # output file - `Cell` uses slots, so it has no `__dict__`. Re-running the
        # computation to recover the report is NOT a second look at the data: the run is
        # deterministic in `--seed`, so it reproduces the same numbers exactly. Logging
        # them again would double-count N for one look and inflate SR* on nothing.
        #
        # The flag REFUSES to run unless the trials it is standing in for already exist,
        # so it cannot be used to run unlogged work.
        n_have = _logged_trials("L07")
        want = len(products) * len(WS) * len(GS) * len(TFS) * len(HOLDS)
        if n_have < want:
            raise SystemExit(
                f"--reuse-trials refused: only {n_have} L07 trials on file, {want} needed "
                f"for this grid. Run without the flag so the trials are spent and logged."
            )
        print(f"  reusing {n_have} already-logged L07 trials; N is unchanged", flush=True)
        for product in products:
            print("  {} ...".format(product), flush=True)
            cells.extend(run(product, args.seed))
        apply_bh(cells)
    else:
        with stage1_run("L07", provenance="native", date_range=DATE_RANGE,
                        note=("real-minus-placebo against matched arbitrary regions "
                              "(decisions.md 37); matched level types only")) as log:
            for product in products:
                print("  {} ...".format(product), flush=True)
                cells.extend(run(product, args.seed))
            apply_bh(cells)
            log.record([c for c in cells if not c.excluded],
                       param_keys=["w", "g", "tf", "horizon", "level_type"])

    CELLS_JSON.write_text(json.dumps([asdict(c) for c in cells], indent=2, default=float),
                          encoding="utf-8")
    REPORT.write_text(render(cells), encoding="utf-8")
    live = [c for c in cells if not c.excluded]
    print("\n{} tests, {} nominal separations, {} BH survivors".format(
        len(live), sum(c.separated for c in live), sum(c.bh_survivor for c in live)))
    print("wrote {}, {}".format(REPORT.name, CELLS_JSON.name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

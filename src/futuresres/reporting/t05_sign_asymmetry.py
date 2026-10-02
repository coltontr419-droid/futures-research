"""T05 — sign asymmetry. T_SERIES_CANDIDATES.md Class C. A RE-ANALYSIS OF FIRINGS ALREADY
ON FILE: no trial is spent; one summary record per entry goes to `measurements.jsonl`.

    python -m futuresres.reporting.t05_sign_asymmetry --entry L07 --product MNQ
    python -m futuresres.reporting.t05_sign_asymmetry --entry L07 --product MGC
    python -m futuresres.reporting.t05_sign_asymmetry --entry P03
    python -m futuresres.reporting.t05_sign_asymmetry --entry R01-merge
    python -m futuresres.reporting.t05_sign_asymmetry --log     # append measurement records

One (entry, product) per process: `D.load` builds the full price grid (~626 MB by CHECKPOINT's
own measurement) on a machine with ~1 GB available.

REPRODUCE FIRST, THEN SPLIT. A split is only a split of the registered result if the pooled
numbers it recombines to ARE the registered result. So each entry recomputes its pooled figure
with the registered code path and refuses to continue unless it matches the file on record:

  L07   every one of the product's 54 cells against `reports/l07_cells.json` — events exactly,
        real/placebo/diff means to 1e-9. Same practice as decisions.md S38 decision 2, which
        refused to accept reused trials until 36 cells reproduced to four decimals.
  P03   n, real, control and diff against `reports/p03_stage1.json`.
  R01   done in `r-series-research/scripts/t05_sign_split.py` against `r01_checks.json`,
        merged here by reading its JSON.

WHAT "SIGN OF THE CONDITIONING MOVE" MEANS, PER ENTRY.

  L07   `created` (z_dir) in `l07.run()`: whether the gap was made by an up-move or a down-move.
        The registered trade is -z_dir, and the placebo inherits its pair's direction, so the
        split keeps every real/placebo pair intact - it partitions PAIRS, not legs.
  P03   the sign of the firing bar's own return before `outcomes()` fades it. The control
        leg takes its own direction by the registered rule (S55: direction is a property of the
        event), so pairs are partitioned by the REAL bar's sign.
  R01   the sign of `direction` (ratio cheap -> long, rich -> short).

THE GAP TEST USES SESSIONS AS THE UNIT. Events inside a session are correlated (decisions.md
S45; DEFF up to 65.6 measured), so an event-level label permutation would overstate the
evidence by the same factor the programme has already corrected three times. The first draft
of this module did exactly that, and it is replaced here, not patched. The test resamples
sessions with replacement (multinomial weights over per-session sums, so it is vectorised and
cheap) and recomputes each side's paired-difference mean and their gap inside each resample.
Two-sided p is the doubled bootstrap tail at zero; CIs use the programme's calibrated alpha.

POWER IS REPORTED, NOT ASSUMED. Each side's bootstrap SE is reported against the pooled SE;
for a balanced split the ratio is ~sqrt(2).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Final

import numpy as np

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
RESULT_JSON: Final[Path] = ROOT / "reports" / "t05_sign_asymmetry.json"
REPORT_MD: Final[Path] = ROOT / "reports" / "t05_sign_asymmetry.md"
L07_CELLS: Final[Path] = ROOT / "reports" / "l07_cells.json"
P03_STAGE1: Final[Path] = ROOT / "reports" / "p03_stage1.json"
R01_EXTERNAL: Final[Path] = ROOT.parent / "r-series-research" / "reports" / "t05_sign_split.json"

N_BOOT: Final[int] = 2000      # matches l07.N_BOOT and state_control.N_BOOT
TOL: Final[float] = 1e-9


def session_bootstrap_split(diff: np.ndarray, up: np.ndarray, session: np.ndarray,
                            rng: np.random.Generator, alpha: float) -> dict:
    """Per-side paired-difference means, their gap, and session-clustered uncertainty."""
    _, sid = np.unique(session, return_inverse=True)
    s = int(sid.max()) + 1
    su = np.bincount(sid[up], weights=diff[up], minlength=s)
    nu = np.bincount(sid[up], minlength=s).astype(float)
    sd = np.bincount(sid[~up], weights=diff[~up], minlength=s)
    nd = np.bincount(sid[~up], minlength=s).astype(float)
    sp = su + sd
    npool = nu + nd

    mu, md = float(su.sum() / nu.sum()), float(sd.sum() / nd.sum())
    mp = float(sp.sum() / npool.sum())

    bu, bd, bp = np.empty(N_BOOT), np.empty(N_BOOT), np.empty(N_BOOT)
    for b in range(N_BOOT):
        w = rng.multinomial(s, np.full(s, 1.0 / s)).astype(float)
        bu[b] = (w @ su) / max(w @ nu, 1.0)
        bd[b] = (w @ sd) / max(w @ nd, 1.0)
        bp[b] = (w @ sp) / max(w @ npool, 1.0)
    gap = bu - bd
    q = [100 * alpha / 2, 100 * (1 - alpha / 2)]
    p_gap = float(min(1.0, 2 * min(np.mean(gap <= 0), np.mean(gap >= 0))))
    return {
        "n_up": int(nu.sum()), "n_down": int(nd.sum()), "sessions": s,
        "mean_up": mu, "mean_down": md, "mean_pooled": mp,
        "ci_up": [float(v) for v in np.percentile(bu, q)],
        "ci_down": [float(v) for v in np.percentile(bd, q)],
        "gap": mu - md, "ci_gap": [float(v) for v in np.percentile(gap, q)],
        "p_gap": p_gap,
        "se_pooled": float(bp.std(ddof=1)),
        "se_up": float(bu.std(ddof=1)), "se_down": float(bd.std(ddof=1)),
    }


def inject_and_detect(diff: np.ndarray, up: np.ndarray, session: np.ndarray, delta: float,
                      rng: np.random.Generator, alpha: float) -> dict:
    """Outcome injection for the asymmetry null (STAGES.md, adopted S60).

    A null counts only from a pipeline shown to recover an injected effect OF THE SIZE SOUGHT,
    AT THE RUN'S OWN NOISE AND n. So the injection is into the real paired differences - real
    noise, real n, real session clustering - by adding `delta` to the up side only, and the
    identical test is re-run. Recovery is checked two ways: the gap must move by exactly
    delta (plumbing), and the test must call it (power). The analytic power from the same
    bootstrap's SE is reported beside the single injected run.
    """
    from scipy.stats import norm
    base = session_bootstrap_split(diff, up, session, rng, alpha)
    d2 = diff.copy()
    d2[up] += delta
    inj = session_bootstrap_split(d2, up, session, rng, alpha)
    se_gap = (inj["ci_gap"][1] - inj["ci_gap"][0]) / (2 * norm.ppf(1 - alpha / 2))
    detected = bool(inj["p_gap"] < 0.05 and (inj["ci_gap"][0] > 0 or inj["ci_gap"][1] < 0))
    return {
        "delta": delta, "observed_gap": base["gap"], "injected_gap": inj["gap"],
        "shift_recovered": inj["gap"] - base["gap"], "plumbing_ok": abs(
            (inj["gap"] - base["gap"]) - delta) < 1e-9,
        "p_gap_injected": inj["p_gap"], "detected": detected, "se_gap": se_gap,
        "analytic_power": float(norm.cdf(abs(delta) / se_gap - norm.ppf(0.975))),
    }


# ─────────────────────────────────────────────────────────────────── L07 ──

def load_grid_lowmem(product: str):
    """The same `Grid` as `definitions.load`, built in year chunks.

    WHY THIS EXISTS. `definitions.load` peaks at ~626 MB (CHECKPOINT) and was OOM-killed on
    2026-10-02 with ~1.0 GB free, alone, before a single L07 cell could be reproduced. The
    peak is the frame and its derived time columns, not the grids (4 x ~45 MB). This builds
    the row-date index in one lazy pass, preallocates the four flat grids, scatters each
    year's bars straight into them, then applies `load`'s fill logic verbatim.

    It is NOT trusted on the strength of that argument. `run_l07` refuses to report anything
    unless all 54 cells reproduce `l07_cells.json` to 1e-9, and a grid differing in any way
    L07 uses would fail that.
    """
    import polars as pl
    from futuresres.levels import definitions as D

    path = ROOT / "data" / "continuous" / f"{D.SERIES[product]}.parquet"
    local = pl.col("ts_event").dt.convert_time_zone(str(D.ET))
    mod = local.dt.hour().cast(pl.Int32) * 60 + local.dt.minute().cast(pl.Int32)

    def framed(lf: pl.LazyFrame) -> pl.LazyFrame:
        return (lf.with_columns(mod.alias("mod"), local.dt.date().alias("d"))
                  .with_columns(((pl.col("mod") - D.ROW_START_MOD) % 1440).alias("m"))
                  .filter(pl.col("m") < D.ROW_MINUTES)
                  .with_columns(pl.when(pl.col("mod") >= D.ROW_START_MOD)
                                  .then(pl.col("d") + pl.duration(days=1))
                                  .otherwise(pl.col("d")).alias("row")))

    days = (framed(pl.scan_parquet(path).select("ts_event")).select("row").unique()
            .sort("row").collect(engine="streaming").get_column("row").to_numpy())
    size = days.size * D.ROW_MINUTES
    flats = {c: np.full(size, np.nan) for c in ("close", "high", "low", "volume")}

    years = (pl.scan_parquet(path).select(pl.col("ts_event").dt.year().unique())
             .collect().to_series().sort().to_list())
    for y in years:
        chunk = (framed(pl.scan_parquet(path)
                        .select("ts_event", "high", "low", "close", "volume")
                        .filter(pl.col("ts_event").dt.year() == y))
                 .select("row", "m", "close", "high", "low", "volume")
                 .collect(engine="streaming"))
        pos = (np.searchsorted(days, chunk.get_column("row").to_numpy()) * D.ROW_MINUTES
               + chunk.get_column("m").to_numpy().astype(np.int64))
        for c in flats:
            flats[c][pos] = chunk.get_column(c).to_numpy().astype(float)
        del chunk, pos

    traded = {"n": 0}

    def grid_of(col: str) -> np.ndarray:            # verbatim from definitions.load
        flat = flats.pop(col)
        traded["n"] = max(traded["n"], int(np.isfinite(flat).sum()))
        g = flat.reshape(days.size, D.ROW_MINUTES)
        ok = np.isfinite(g)
        idx = np.where(ok, np.arange(D.ROW_MINUTES, dtype=np.int32)[None, :], np.int32(0))
        np.maximum.accumulate(idx, axis=1, out=idx)
        out = np.take_along_axis(g, idx, axis=1)
        del idx
        first = np.argmax(ok, axis=1)
        for i in np.flatnonzero(ok.any(axis=1) & ~np.isfinite(out[:, 0])):
            out[i, : first[i]] = g[i, first[i]]
        return out

    close = grid_of("close")
    n_traded = traded["n"]
    high, low = grid_of("high"), grid_of("low")
    vol = np.nan_to_num(grid_of("volume"))
    keep = np.isfinite(close).all(axis=1) & np.isfinite(high).all(axis=1) \
        & np.isfinite(low).all(axis=1)
    return D.Grid(days[keep], close[keep], high[keep], low[keep], vol[keep],
                  float(n_traded) / max(close.size, 1))


def fvg_zones_chunked(g, w: int, tf: int, product: str, n_chunks: int = 6):
    """`definitions.fvg_zones_directed`, fed the grid in row chunks.

    The builder loops row by row and appends six Python floats per zone, so on MGC's w=2/1m
    type (1.17M zones) its transient is ~390 MB over the resident grid - measured, and enough
    to be OOM-killed. Rows are independent in it (each row's gaps use only that row), so
    calling it on row slices (views, not copies) and concatenating in row order yields the
    same zones in the same order. Row indices are offset back to full-grid rows, because
    `window_scale` reaches back over prior sessions and must see the whole grid.
    """
    from futuresres.levels import definitions as D

    edges = np.linspace(0, g.n, n_chunks + 1).astype(int)
    parts, halves, dirs = [], [], []
    for a, b in zip(edges[:-1], edges[1:]):
        sub = D.Grid(g.days[a:b], g.close[a:b], g.high[a:b], g.low[a:b], g.volume[a:b],
                     g.fill_fraction)
        z, h, d = D.fvg_zones_directed(sub, w, tf, product)
        parts.append((z.price, z.row + a, z.valid_from, z.ref_price))
        halves.append(h)
        dirs.append(d)
        del sub, z
    zones = D.LevelSet(f"fvg_w{w}_{tf}m",
                       np.concatenate([p[0] for p in parts]),
                       np.concatenate([p[1] for p in parts]).astype(int),
                       np.concatenate([p[2] for p in parts]).astype(int),
                       np.concatenate([p[3] for p in parts]))
    return zones, np.concatenate(halves), np.concatenate(dirs)


def _l07_level_type(g, product: str, tf: int, w: int, registered: dict, mt: dict,
                    rng: np.random.Generator) -> list[dict]:
    """All (g, h) cells of one level type. A function so its ~1M-element arrays are freed on
    return: holding one type's arrays while building the next type's zones was OOM-killed."""
    import gc
    from futuresres.levels import definitions as D
    from futuresres.levels.placebo import make_region_placebo
    from futuresres.signals.l07 import COST_BPS, GS, HOLDS, _first_entry, _signed_return_bps
    from futuresres.signals.stage1 import calibrated_alpha

    lt = f"fvg_w{w}_{tf}m"
    rec = mt.get((lt, product))
    if rec is None or rec.get("failures"):
        return []
    zones, half, created = fvg_zones_chunked(g, w, tf, product)
    scale = D.window_scale(g, zones)
    good = (np.isfinite(zones.price) & np.isfinite(half) & np.isfinite(scale) & (scale > 0))
    z_price, z_row, z_valid = zones.price[good], zones.row[good], zones.valid_from[good]
    z_half, z_dir = half[good], created[good]
    z_ref, z_scale = zones.ref_price[good], scale[good]
    del zones, half, created, scale
    gc.collect()
    placebo = make_region_placebo(z_price, z_ref, g.days[z_row], lt, z_scale)
    traded = -z_dir
    cost = COST_BPS[product]
    cells: list[dict] = []
    for gb in GS:
        earliest = np.minimum(z_valid + gb * tf, D.ROW_MINUTES - 1)
        e_real = _first_entry(g, z_price, z_half, z_row, earliest)
        e_plac = _first_entry(g, placebo, z_half, z_row, earliest)
        for h in HOLDS:
            rr = _signed_return_bps(g, z_row, e_real, traded, h)
            pp = _signed_return_bps(g, z_row, e_plac, traded, h)
            ok = np.isfinite(rr) & np.isfinite(pp)
            r_, p_, rows, up = rr[ok], pp[ok], z_row[ok], z_dir[ok] > 0
            diff = r_ - p_
            reg = registered[(w, gb, tf, h)]
            if (int(ok.sum()) != reg["events"]
                    or abs(float(r_.mean()) - reg["real_bps"]) > TOL
                    or abs(float(p_.mean()) - reg["placebo_bps"]) > TOL
                    or abs(float(diff.mean()) - reg["diff_bps"]) > TOL):
                raise SystemExit(
                    f"L07 {product} w={w} tf={tf} g={gb} h={h} does not reproduce "
                    f"l07_cells.json (events {int(ok.sum())} vs {reg['events']}, diff "
                    f"{float(diff.mean()):.9f} vs {reg['diff_bps']:.9f}). Refusing to split "
                    f"numbers that are not the registered ones.")
            bs = session_bootstrap_split(diff, up, rows, rng,
                                         calibrated_alpha(len(np.unique(rows))))
            cells.append({
                "w": w, "tf": tf, "g": gb, "h": h, "events": int(ok.sum()),
                "pooled_diff": float(diff.mean()),
                "real_up": float(r_[up].mean()), "placebo_up": float(p_[up].mean()),
                "real_down": float(r_[~up].mean()), "placebo_down": float(p_[~up].mean()),
                "cost_bps": cost, **bs,
            })
            del rr, pp, ok, r_, p_, rows, up, diff
        print(f"  {product} {lt} g={gb}: reproduced, split "
              f"{cells[-1]['mean_up']:+.3f} / {cells[-1]['mean_down']:+.3f} (h={h})", flush=True)
        del e_real, e_plac, earliest
    return cells


def run_l07(product: str) -> dict:
    """All 54 cells, one level type at a time, checkpointed after each type so a kill on this
    machine resumes instead of restarting. Checkpointed cells were reproduced before they were
    written, so resuming does not weaken the reproduction guarantee."""
    from futuresres.signals.l07 import TFS, WS, matched_types

    ckpt = ROOT / "reports" / f"t05_l07_{product}.ckpt.json"
    done: dict[str, list] = json.loads(ckpt.read_text()) if ckpt.exists() else {}
    registered = {
        (c["w"], c["g"], c["tf"], c["horizon"]): c
        for c in json.loads(L07_CELLS.read_text())
        if c["product"] == product and not c["excluded"]
    }
    mt = matched_types()
    g = load_grid_lowmem(product)
    for tf in TFS:
        for w in WS:
            key = f"w{w}_tf{tf}"
            if key in done:
                print(f"  {product} fvg_w{w}_{tf}m: from checkpoint", flush=True)
                continue
            # one seed per level type, so a resumed run draws exactly what an unbroken one would
            rng = np.random.default_rng([20261002, w, tf])
            done[key] = _l07_level_type(g, product, tf, w, registered, mt, rng)
            ckpt.write_text(json.dumps(done))
    cells = [c for k in sorted(done) for c in done[k]]
    if len(cells) != len(registered):
        raise SystemExit(f"{len(cells)} cells reproduced against {len(registered)} on file")
    ckpt.unlink()
    return {"entry": "L07", "product": product, "reproduced_cells": len(cells),
            "cells": cells}


# ─────────────────────────────────────────────────────────────────── P03 ──

def run_p03() -> dict:
    from futuresres.reporting.state_control_feasibility import build_state, load_bars
    from futuresres.signals.p03 import outcomes
    from futuresres.signals.stage1 import calibrated_alpha
    from futuresres.signals.state_control import (
        UNMATCHED, make_matched_control, verify_control,
    )

    reg = json.loads(P03_STAGE1.read_text())["result"]
    df = load_bars()
    w = build_state(df)
    w["close"] = df["close"].to_numpy()
    w["slot"] = df["slot"].to_numpy().astype(int)
    state = w["state"] & (w["vol_q"] >= 0)
    sid = w["session"]
    real_idx = np.flatnonzero(state)
    draw = make_matched_control(state, sid, w["tod"], w["vol_q"], condition_name="P03",
                                year=w["year"], session_exclusion="bar")
    rep = verify_control("P03", "NQ", real_idx, draw, w["tod"], w["vol_q"], w["year"],
                         strict=False)
    if not rep.ok:
        raise SystemExit("P03's control no longer verifies; refusing to split")

    paired = draw.index != UNMATCHED
    r_idx, c_idx = real_idx[paired], draw.index[paired]
    real_out, ctrl_out = outcomes(w, r_idx), outcomes(w, c_idx)
    both = np.isfinite(real_out) & np.isfinite(ctrl_out)
    real_out, ctrl_out, r_idx = real_out[both], ctrl_out[both], r_idx[both]
    sess = sid[r_idx]
    diff = real_out - ctrl_out

    if (diff.size != reg["n"] or abs(float(real_out.mean()) - reg["real_bps"]) > TOL
            or abs(float(ctrl_out.mean()) - reg["control_bps"]) > TOL
            or abs(float(diff.mean()) - reg["diff_bps"]) > TOL):
        raise SystemExit(
            f"P03 does not reproduce p03_stage1.json (n {diff.size} vs {reg['n']}, diff "
            f"{float(diff.mean()):.9f} vs {reg['diff_bps']:.9f}). Refusing to split.")

    close = w["close"]
    up = (np.log(close[r_idx] / close[r_idx - 1]) * 1e4) > 0
    alpha = calibrated_alpha(len(np.unique(sess)))
    bs = session_bootstrap_split(diff, up, sess, np.random.default_rng(20261002), alpha)
    # size sought: one side carries an effect at the pre-registered threshold on average,
    # the other none -> gap = 2 x 0.625 (the draft's "real effect averaged with a null")
    inj = inject_and_detect(diff, up, sess, 2 * reg["preregistered_threshold_bps"],
                            np.random.default_rng(20261003), alpha)
    return {"entry": "P03", "threshold_bps": reg["preregistered_threshold_bps"],
            "cost_bps": reg["cost_bps"], "pooled_diff": float(diff.mean()),
            "real_up": float(real_out[up].mean()), "ctrl_up": float(ctrl_out[up].mean()),
            "real_down": float(real_out[~up].mean()), "ctrl_down": float(ctrl_out[~up].mean()),
            "injection": inj, **bs}


def run_l07_inject(product: str) -> dict:
    """Injection on L07's SMALLEST-n cell (w=8, tf=5m, g=60), the least powered of the 54, at
    h=60. If the asymmetry test recovers the sought gap there, every larger cell has more
    power. Size sought: 2 x |pooled diff| - one side carrying the whole effect, one none."""
    from futuresres.levels import definitions as D
    from futuresres.levels.placebo import make_region_placebo
    from futuresres.signals.l07 import _first_entry, _signed_return_bps
    from futuresres.signals.stage1 import calibrated_alpha

    reg = next(c for c in json.loads(L07_CELLS.read_text())
               if c["product"] == product and (c["w"], c["tf"], c["g"], c["horizon"]) == (8, 5, 60, 60))
    g = load_grid_lowmem(product)
    zones, half, created = fvg_zones_chunked(g, 8, 5, product)
    scale = D.window_scale(g, zones)
    good = (np.isfinite(zones.price) & np.isfinite(half) & np.isfinite(scale) & (scale > 0))
    zp, zr, zv, zh, zd = (zones.price[good], zones.row[good], zones.valid_from[good],
                          half[good], created[good])
    plac = make_region_placebo(zp, zones.ref_price[good], g.days[zr], "fvg_w8_5m", scale[good])
    earliest = np.minimum(zv + 60 * 5, D.ROW_MINUTES - 1)
    rr = _signed_return_bps(g, zr, _first_entry(g, zp, zh, zr, earliest), -zd, 60)
    pp = _signed_return_bps(g, zr, _first_entry(g, plac, zh, zr, earliest), -zd, 60)
    ok = np.isfinite(rr) & np.isfinite(pp)
    diff = rr[ok] - pp[ok]
    if int(ok.sum()) != reg["events"] or abs(float(diff.mean()) - reg["diff_bps"]) > TOL:
        raise SystemExit("injection cell does not reproduce l07_cells.json")
    rows, up = zr[ok], zd[ok] > 0
    inj = inject_and_detect(diff, up, rows, 2 * abs(reg["diff_bps"]),
                            np.random.default_rng(20261004),
                            calibrated_alpha(len(np.unique(rows))))
    return {"product": product, "cell": "w8 tf5 g60 h60", "events": int(ok.sum()), **inj}


# ──────────────────────────────────────────────────────────────── report ──

def l07_summary(r: dict) -> dict:
    cells = r["cells"]
    up_neg = sum(c["mean_up"] < 0 for c in cells)
    dn_neg = sum(c["mean_down"] < 0 for c in cells)
    sig = [c for c in cells if c["p_gap"] < 0.05]
    # BH across the 54 gap tests, p floored at 1/N_BOOT (the bootstrap's resolution)
    pv = np.sort(np.array([max(c["p_gap"], 1.0 / N_BOOT) for c in cells]))
    m = pv.size
    hit = np.flatnonzero(pv <= 0.05 * np.arange(1, m + 1) / m)
    bh = int(hit.max() + 1) if hit.size else 0
    return {
        "gap_bh_survivors": bh,
        "gap_positive": int(sum(c["gap"] > 0 for c in cells)),
        "gap_median": float(np.median([c["gap"] for c in cells])),
        "pooled_abs_median": float(np.median([abs(c["pooled_diff"]) for c in cells])),
        "cells": len(cells), "up_negative": up_neg, "down_negative": dn_neg,
        "gap_nominal_p05": len(sig),
        "gap_range": [min(c["gap"] for c in cells), max(c["gap"] for c in cells)],
        "up_range": [min(c["mean_up"] for c in cells), max(c["mean_up"] for c in cells)],
        "down_range": [min(c["mean_down"] for c in cells), max(c["mean_down"] for c in cells)],
        "se_ratio_median": float(np.median([c["se_up"] / c["se_pooled"] for c in cells])),
        "smaller_side_over_cost_min": min(
            min(abs(c["mean_up"]), abs(c["mean_down"])) / c["cost_bps"] for c in cells),
    }


def render(res: dict) -> str:
    w: list[str] = []
    a = w.append
    a("# T05 — sign asymmetry")
    a("")
    a("Generated by `python -m futuresres.reporting.t05_sign_asymmetry`. A re-analysis of "
      "firings already on file: **no trial spent**. Every split below is of numbers that were "
      "first reproduced against the registered record, exactly (module docstring). Gap tests "
      "resample **sessions**, not events (decisions.md §45).")
    a("")
    for key in ("L07_MNQ", "L07_MGC"):
        r = res.get(key)
        if not r:
            continue
        s = l07_summary(r)
        a(f"## L07 — {r['product']}: {s['cells']} cells reproduced from `l07_cells.json`")
        a("")
        a(f"- Up-created gaps (traded short): real − placebo negative in **{s['up_negative']} of "
          f"{s['cells']}** cells, range {s['up_range'][0]:+.3f} to {s['up_range'][1]:+.3f} bps.")
        a(f"- Down-created gaps (traded long): negative in **{s['down_negative']} of "
          f"{s['cells']}**, range {s['down_range'][0]:+.3f} to {s['down_range'][1]:+.3f} bps.")
        a(f"- Gap (up − down): {s['gap_range'][0]:+.3f} to {s['gap_range'][1]:+.3f} bps; "
          f"nominally significant at 0.05 in {s['gap_nominal_p05']} of {s['cells']} cells "
          f"(session bootstrap; {0.05 * s['cells']:.1f} expected by chance); **{s['gap_bh_survivors']} "
          f"survive BH** within the 54. Up − down is positive in {s['gap_positive']} of "
          f"{s['cells']} cells, i.e. down-created gaps (traded long) are the more negative side; "
          f"median gap {s['gap_median']:+.3f} bps against a median pooled effect of "
          f"{s['pooled_abs_median']:.3f} bps.")
        a(f"- Power: median per-side SE is {s['se_ratio_median']:.2f}× the pooled SE.")
        a(f"- The weaker side is still at least {s['smaller_side_over_cost_min']:.2f}× the "
          f"cost floor in every cell.")
        a("")
        a("| w | tf | g | h | events | up: real−plac | down: real−plac | gap | gap CI | p |")
        a("|---|---|---|---|---|---|---|---|---|---|")
        for c in r["cells"]:
            if c["h"] != 180:
                continue
            a(f"| {c['w']} | {c['tf']}m | {c['g']} | {c['h']} | {c['events']:,} | "
              f"{c['mean_up']:+.3f} | {c['mean_down']:+.3f} | {c['gap']:+.3f} | "
              f"[{c['ci_gap'][0]:+.3f}, {c['ci_gap'][1]:+.3f}] | {c['p_gap']:.3f} |")
        a("")
        a("H = 180 rows shown; all 54 cells are in `t05_sign_asymmetry.json`.")
        a("")
    p = res.get("P03")
    if p:
        a("## P03 — reproduced from `p03_stage1.json`")
        a("")
        a("| split | n | real | control | real − control | CI | clears +0.625? |")
        a("|---|---|---|---|---|---|---|")
        a(f"| pooled | {p['n_up'] + p['n_down']:,} | — | — | {p['pooled_diff']:+.4f} | — | "
          f"{p['pooled_diff'] > p['threshold_bps']} |")
        a(f"| up-move bar (faded short) | {p['n_up']:,} | {p['real_up']:+.4f} | "
          f"{p['ctrl_up']:+.4f} | {p['mean_up']:+.4f} | [{p['ci_up'][0]:+.3f}, "
          f"{p['ci_up'][1]:+.3f}] | {p['mean_up'] > p['threshold_bps']} |")
        a(f"| down-move bar (faded long) | {p['n_down']:,} | {p['real_down']:+.4f} | "
          f"{p['ctrl_down']:+.4f} | {p['mean_down']:+.4f} | [{p['ci_down'][0]:+.3f}, "
          f"{p['ci_down'][1]:+.3f}] | {p['mean_down'] > p['threshold_bps']} |")
        a("")
        a(f"Gap {p['gap']:+.4f} bps, CI [{p['ci_gap'][0]:+.3f}, {p['ci_gap'][1]:+.3f}], "
          f"session-bootstrap p = {p['p_gap']:.3f}. Per-side SE {p['se_up']:.3f} / "
          f"{p['se_down']:.3f} against pooled {p['se_pooled']:.3f}. Real leg net of cost: "
          f"up {p['real_up'] - p['cost_bps']:+.3f}, down {p['real_down'] - p['cost_bps']:+.3f}.")
        a("")
    a("## Can this test see the asymmetry it is looking for? (STAGES.md, adopted §60)")
    a("")
    a("Every 'no asymmetry' above is a null, so it counts only if the pipeline recovers an "
      "injected asymmetry **of the size sought, at the run's own noise and n**. Size sought: "
      "the draft's own scenario — one side carrying the whole effect, the other none — which at "
      "a fixed pooled value is a gap of 2 × |pooled| (2 × the +0.625 threshold for P03). The "
      "injection adds that gap to one side's *real* paired differences and re-runs the "
      "identical test.")
    a("")
    a("| entry | cell | δ injected (bps) | gap moved by | p after injection | detected | analytic power |")
    a("|---|---|---|---|---|---|---|")
    for prod, i in res.get("injection_L07", {}).items():
        a(f"| L07 {prod} | {i['cell']} (smallest n, {i['events']:,}) | {i['delta']:.3f} | "
          f"{i['shift_recovered']:.3f} | {i['p_gap_injected']:.3g} | {i['detected']} | "
          f"{i['analytic_power']:.3f} |")
    if p and "injection" in p:
        i = p["injection"]
        a(f"| P03 | registered cell | {i['delta']:.3f} | {i['shift_recovered']:.3f} | "
          f"{i['p_gap_injected']:.3g} | {i['detected']} | {i['analytic_power']:.3f} |")
    r1i = res.get("R01")
    if r1i:
        for c in r1i["cells"]:
            i = c.get("injection")
            if i:
                a(f"| R01 | W={c['W']} k={c['k']} | {i['delta_bps']:.3f} | "
                  f"{i['shift_recovered_bps']:.3f} | {i['p_injected']:.3g} | {i['detected']} | "
                  f"{i['analytic_power']:.3f} |")
    a("")
    r1 = res.get("R01")
    if r1:
        a("## R01 — reproduced from `r01_checks.json` (r-series-research)")
        a("")
        a("Non-overlapping per-trade statistic, the one behind the headline +0.452 bps. "
          "Welch t on the gap; non-overlapping entries are the independence assumption the "
          "registered t already used.")
        a("")
        a("| W | k | pooled | long | short | gap | p |")
        a("|---|---|---|---|---|---|---|")
        for c in r1["cells"]:
            a(f"| {c['W']} | {c['k']} | {c['pooled']['bps']:+.3f} (t {c['pooled']['t']:.2f}) | "
              f"{c['long']['bps']:+.3f} (n {c['long']['n']:,}) | {c['short']['bps']:+.3f} "
              f"(n {c['short']['n']:,}) | {c['gap_bps']:+.3f} | {c['gap_p']:.3f} |")
        a("")
    return "\n".join(w)


def log_measurements(res: dict) -> None:
    from futuresres.stats.trials import Trial, TrialLog
    log = TrialLog(ROOT / "measurements.jsonl")
    for key in ("L07_MNQ", "L07_MGC"):
        if key in res:
            s = l07_summary(res[key])
            rec = log.append(Trial(
                trial_id=log.next_id("m"), hypothesis_id="L07", symbol=res[key]["product"],
                date_range=("2010-06-06", "2026-08-27"), status="completed",
                params={"kind": "t05_sign_split", **{k: v for k, v in s.items()},
                        "injection": res.get("injection_L07", {}).get(res[key]["product"])},
                note=("kind=measurement; NOT a trial and NOT counted in N. T-series T05: all "
                      "54 L07 cells reproduced from l07_cells.json, then split by the sign of "
                      "the gap-creating move; gap tested by session bootstrap. decisions.md 65."),
            ))
            print(f"logged {rec['trial_id']} ({key})")
    if "P03" in res:
        p = res["P03"]
        rec = log.append(Trial(
            trial_id=log.next_id("m"), hypothesis_id="P03", symbol="NQ/MNQ",
            date_range=("2010-06-07", "2026-08-27"), status="completed",
            params={"kind": "t05_sign_split", "mean_up": p["mean_up"],
                    "mean_down": p["mean_down"], "gap": p["gap"], "p_gap": p["p_gap"],
                    "injection": p.get("injection")},
            note=("kind=measurement; NOT a trial and NOT counted in N. T-series T05: P03 "
                  "reproduced from p03_stage1.json, split by the firing bar's own sign; "
                  "session bootstrap. decisions.md 65."),
        ))
        print(f"logged {rec['trial_id']} (P03)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.reporting.t05_sign_asymmetry")
    ap.add_argument("--entry", choices=["L07", "L07-inject", "P03", "R01-merge"])
    ap.add_argument("--product", choices=["MNQ", "MGC"])
    ap.add_argument("--log", action="store_true")
    args = ap.parse_args(argv)

    res: dict = {}
    if RESULT_JSON.exists():
        res = json.loads(RESULT_JSON.read_text(encoding="utf-8"))
    if args.entry == "L07":
        if not args.product:
            ap.error("--product is required for --entry L07")
        res[f"L07_{args.product}"] = run_l07(args.product)
    elif args.entry == "L07-inject":
        if not args.product:
            ap.error("--product is required")
        res.setdefault("injection_L07", {})[args.product] = run_l07_inject(args.product)
    elif args.entry == "P03":
        res["P03"] = run_p03()
    elif args.entry == "R01-merge":
        res["R01"] = json.loads(R01_EXTERNAL.read_text(encoding="utf-8"))
    RESULT_JSON.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    REPORT_MD.write_text(render(res), encoding="utf-8")
    print(f"wrote {RESULT_JSON.name} and {REPORT_MD.name}")
    if args.log:
        log_measurements(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())

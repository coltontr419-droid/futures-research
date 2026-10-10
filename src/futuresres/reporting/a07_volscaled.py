"""A07 - A03's solved staking with contracts scaled to recent volatility instead of a fixed 2 MNQ.
A COMPUTATION; zero edge (drift removed); no trial. decisions.md 105. Also: the same policy at FIXED sizes
1-8 MNQ, which turned out to be the finding (4 MNQ beats A03's 2 on both histories, both methods).

    python -m futuresres.reporting.a07_volscaled --era post && python -m futuresres.reporting.a07_volscaled --era pre
    python -m futuresres.reporting.a07_volscaled --log          # merge and record

A05 found the fixed-size bracket behaves differently by regime: in calm years most brackets end at the close
with neither level hit, so the account crawls. Rule fixed before the run: contracts on session t =
clip(round(2 * sigma_ref / sigma_hat_t), 1, 15), sigma_hat_t the std of the 1-MNQ 09:30-16:00 P&L over the
20 sessions BEFORE t (real order), sigma_ref its std over the whole replay (a level normalisation only:
average size stays near A03's 2; with drift removed there is no outcome to fit). The first 20 sessions trade 2.
Levels 0.75x-2x. Same test as A03: back-to-back $80 attempts, 84 trading days,
real 2021-2026 sessions in order from every start date; repeated on 2015-2020 (A05's set, an
independent history) and by a 21-session block bootstrap (a02_real mode 'block') on each.

Per-session size enters through the paths: each 1-contract path is scaled by n and shifted down by the
extra n-1 round trips, so a02_real.sequential's fixed one-contract cost arithmetic still nets a take to +W,
a stop to -L and a close to (gross - n x $2.32) exactly.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.a01_game as g
import futuresres.reporting.a02_real as a2
import futuresres.reporting.z_firms as zf

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "a07_volscaled.json"
RT = np.float32(2.32)
LOOKBACK, BASE, NMAX = 20, 2, 15


def contracts(c_gross_close: np.ndarray, level: float = 1.0) -> np.ndarray:
    S = len(c_gross_close)
    ref = float(c_gross_close.std())
    n = np.full(S, BASE, dtype=np.int64)
    for t in range(LOOKBACK, S):
        sh = float(c_gross_close[t - LOOKBACK:t].std())
        n[t] = int(np.clip(round(BASE * level * ref / sh), 1, NMAX))
    return n


def scaled_paths(h1, l1, c1, n):
    nn = n.astype(np.float32)[:, None]
    extra = (RT * (nn - 1)).astype(np.float32)
    return (h1 * nn - extra).astype(np.float32), ((l1 + RT) * nn - RT * nn).astype(np.float32), \
           ((c1 + RT) * nn - RT * nn).astype(np.float32)


def _era_paths(era: str):
    """1-MNQ paths in zf's format (cost inside l and c): 'post' = A03's 2021-2026 set; 'pre' = A05's 2015-2020 set.
    Cached under data/cache (gitignored, regenerable): the minute-series load is the memory peak on this machine."""
    cache = ROOT / "data" / "cache" / f"a07_{era}.npz"
    if cache.exists():
        z = np.load(cache)
        return z["h"], z["l"], z["c"]
    import polars as pl
    import futuresres.reporting.y03_sessions as s3
    cache.parent.mkdir(parents=True, exist_ok=True)
    spec = s3.PRODUCTS["MNQ"]; full = ROOT / "data" / "continuous" / f"{spec['series']}.parquet"
    # stream this era's rows to a subset file: the loader then never holds 2010-2026 at once. Each era's own
    # loader removes drift within the era (as before); $ paths are rescaled to TODAY's contract value, which
    # the full-series loader used (its notional is the series' last close).
    era_rows = (pl.col("session") >= pl.date(2021, 1, 1)) if era == "post" else (pl.col("session") < pl.date(2021, 1, 1))
    sub = cache.parent / f"a07_{era}_series.parquet"
    pl.scan_parquet(full).filter(era_rows).sink_parquet(sub)
    last_full = float(pl.scan_parquet(full).select(pl.col("close").sort_by("ts_event").last()).collect().item())
    last_sub = float(pl.scan_parquet(sub).select(pl.col("close").sort_by("ts_event").last()).collect().item())
    scale = np.float32(last_full / last_sub)
    saved = spec["series"]; spec["series"] = f"../cache/a07_{era}_series"
    try:
        if era == "post":
            h1, l1, c1 = zf.strategy_paths(("MNQ_RTH_0",))["MNQ_RTH_0"]      # cost inside l, c
            h1, l1, c1 = h1 * scale, (l1 + RT) * scale - RT, (c1 + RT) * scale - RT
        else:
            import futuresres.reporting.a05_empirical as a5
            h, l, c = a5.train_paths()            # 2 MNQ, no cost, drift removed within the era
            h1, l1, c1 = h / 2 * scale, l / 2 * scale - RT, c / 2 * scale - RT
            del h, l, c
    finally:
        spec["series"] = saved
        sub.unlink(missing_ok=True)
    h1, l1, c1 = (x.astype(np.float32) for x in (h1, l1, c1))
    np.savez(cache, h=h1, l=l1, c=c1)
    return h1, l1, c1


def _row(r: dict) -> dict:
    return {k: r[k] for k in ("p_any_payout", "mean_net", "p_net_positive", "mean_attempts", "mean_fees")}


def run(era: str) -> dict:
    """Vol-scaled vs fixed size on one history (one per process: the 2.7 GB machine), by in-order replay and by
    21-day block bootstrap. 'pre' uses the 2021-26 one-contract sd as its $ target, read from the 'post' output."""
    warnings.filterwarnings("ignore")
    import gc as _gc
    _era_paths(era); _gc.collect()                # load (or cache) before the solver allocates
    with contextlib.redirect_stdout(io.StringIO()), np.errstate(all="ignore"):
        g.solve_all(21, keep_policy_at=21); g.solve_funded(21, "dollars", keep_policy_at=21)
    out = {}
    ref = None if era == "post" else json.loads(_era_out("post").read_text())["post"]["one_contract_daily_sd"]
    for era in (era,):
        h1, l1, c1 = _era_paths(era)
        S = len(c1); gc = (c1[:, -1] + RT).astype(np.float64)
        ref = ref if ref is not None else float(gc.std())            # one $ target for both histories (2021-26 level)
        e = out[era] = {"sessions": int(S), "one_contract_daily_sd": float(gc.std()), "fixed": {}, "vol_scaled": {}}
        for k in (1, 2, 3, 4, 5, 6, 8):
            a2._PATHS["p"] = scaled_paths(h1, l1, c1, np.full(S, k))
            e["fixed"][k] = {"replay": _row(a2.sequential(1, "replay")),
                             "block": [_row(a2.sequential(1, "block", traders=6000, seed=s)) for s in (11, 12)]}
            print(era, "fixed", k, json.dumps(e["fixed"][k]["replay"]), flush=True)
        for level in (0.75, 1.0, 1.25, 1.5, 1.75, 2.0):
            n = np.full(S, BASE, dtype=np.int64)
            for t in range(LOOKBACK, S):
                n[t] = int(np.clip(round(BASE * level * ref / gc[t - LOOKBACK:t].std()), 1, NMAX))
            a2._PATHS["p"] = scaled_paths(h1, l1, c1, n)
            e["vol_scaled"][level] = {"contracts_mean": float(n.mean()), "replay": _row(a2.sequential(1, "replay"))}
            print(era, "vol", level, json.dumps(e["vol_scaled"][level]), flush=True)
        a2._PATHS.clear(); del h1, l1, c1
    return out


def _era_out(era: str) -> Path:
    return ROOT / "reports" / f"a07_volscaled_{era}.json"


def main(argv=None) -> int:
    """--era post, then --era pre (separate processes), then --log merges both into OUT and records it."""
    ap = argparse.ArgumentParser(); ap.add_argument("--era", choices=("post", "pre")); ap.add_argument("--log", action="store_true")
    a = ap.parse_args(argv)
    if a.era:
        _era_out(a.era).write_text(json.dumps(run(a.era), indent=1, default=float) + "\n")
        return 0
    r = {**json.loads(_era_out("post").read_text()), **json.loads(_era_out("pre").read_text())}
    OUT.write_text(json.dumps(r, indent=1, default=float) + "\n")
    for e in ("post", "pre"):
        _era_out(e).unlink()
    if a.log:
        from futuresres.stats.trials import Trial, TrialLog
        log = TrialLog(ROOT / "measurements.jsonl")
        rec = log.append(Trial(trial_id=log.next_id("m"), hypothesis_id="A-series", symbol="MNQ",
                               date_range=("2015-11-20", "2026-08-27"), status="completed",
                               params={"kind": "vol_scaled_staking", **r},
                               note="kind=computation; NOT a trial. Supersedes m00153 (logged the first, vol-only run's file by mistake). A07: A03 with volatility-scaled and fixed 1-8 contracts, two histories, replay and block bootstrap. decisions.md 105."))
        print("logged", rec["trial_id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())

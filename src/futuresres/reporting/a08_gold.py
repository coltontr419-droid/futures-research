"""A08 - the A01 solved staking policy on MGC (gold), London 03:00-11:30 ET long - the gold cell fixed in Y03
(decisions.md 83) - at fixed sizes, as A07 did for MNQ. A COMPUTATION; zero edge (drift removed); no trial.
decisions.md 106.

    python -m futuresres.reporting.a08_gold --era post && python -m futuresres.reporting.a08_gold --era pre
    python -m futuresres.reporting.a08_gold --log          # merge, correlation with MNQ, record

Same tests as A07: 84 trading days of back-to-back $80 attempts, real sessions in order from every start date
and by 21-session block bootstrap; 2021-26 and 2011-20 histories, drift removed within each, $ at today's
contract value. One era per process, the minute series streamed to a subset (the 2.7 GB machine).

Per-session size and MGC's $3.32 round trip enter through the paths: a02_real.sequential charges $2.32 for one
contract, so each path is scaled by n and shifted by (n x 3.32 - 2.32) on the high and n x 3.32 on the low and
close (cost-inclusive in zf's format) - a take still nets +W, a stop -L, a close gross - n x $3.32, exactly.
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

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "a08_gold.json"
PRODUCT, WINDOW = "MGC", "london_0300_1130"
RT, RT_ENGINE = np.float32(3.32), np.float32(2.32)
SIZES = (2, 4, 6, 8, 10, 12, 15)


def era_paths(era: str, product: str = PRODUCT, window: str = WINDOW):
    """GROSS 1-contract $ paths (no cost) and session dates for one era, drift removed within the era, at
    today's contract value. Cached under data/cache (gitignored)."""
    cache = ROOT / "data" / "cache" / f"a08_{product}_{window}_{era}.npz"
    if cache.exists():
        z = np.load(cache)
        return z["h"], z["l"], z["c"], z["d"]
    import polars as pl
    import futuresres.reporting.y01_structure_ev as y
    import futuresres.reporting.y03_sessions as s3
    cache.parent.mkdir(parents=True, exist_ok=True)
    spec = s3.PRODUCTS[product]
    full = ROOT / "data" / "continuous" / f"{spec['series']}.parquet"
    rows = (pl.col("session") >= pl.date(2021, 1, 1)) if era == "post" else (pl.col("session") < pl.date(2021, 1, 1))
    sub = cache.parent / f"a08_{product}_{era}_series.parquet"
    pl.scan_parquet(full).filter(rows).sink_parquet(sub)
    try:
        y.SERIES = sub; y.MULT = spec["mult"]; y.WINDOWS.update(s3.WINDOWS)
        d, H, L, C, _ = y.load_sessions()
        h, l, c, _ = y.window_paths(H, L, C, window, None)
        del H, L, C
        today = float(pl.scan_parquet(full).select(pl.col("close").sort_by("ts_event").last()).collect().item()) * spec["mult"]
        h, l, c = (np.asarray(x * today, np.float32) for x in (h, l, c))
    finally:
        sub.unlink(missing_ok=True)
    np.savez(cache, h=h, l=l, c=c, d=d)
    return h, l, c, d


def engine_paths(h, l, c, n: int):
    """n contracts at RT each, in a02_real.sequential's one-contract, $2.32, cost-inclusive format."""
    tot = RT * n
    return (h * n - (tot - RT_ENGINE)).astype(np.float32), (l * n - tot).astype(np.float32), (c * n - tot).astype(np.float32)


def _row(r: dict) -> dict:
    return {k: r[k] for k in ("p_any_payout", "mean_net", "p_net_positive", "mean_attempts", "mean_fees")}


def run(era: str) -> dict:
    warnings.filterwarnings("ignore")
    h, l, c, d = era_paths(era)
    with contextlib.redirect_stdout(io.StringIO()), np.errstate(all="ignore"):
        g.solve_all(21, keep_policy_at=21); g.solve_funded(21, "dollars", keep_policy_at=21)
    e = {"sessions": int(len(c)), "first": str(d[0]), "last": str(d[-1]),
         "one_contract_daily_sd": float(c[:, -1].std()), "fixed": {}}
    for n in SIZES:
        a2._PATHS["p"] = engine_paths(h, l, c, n)
        e["fixed"][n] = {"replay": _row(a2.sequential(1, "replay")),
                         "block": [_row(a2.sequential(1, "block", traders=6000, seed=s)) for s in (11, 12)]}
        print(era, n, json.dumps(e["fixed"][n]["replay"]), flush=True)
    a2._PATHS.clear()
    return {era: e}


def correlation() -> dict:
    """Daily close P&L correlation, MGC London vs MNQ 09:30-16:00 (both drift removed), on shared dates."""
    out = {}
    for era in ("post", "pre"):
        _, _, cg, dg = era_paths(era)
        _, _, cn, dn = era_paths(era, "MNQ", "rth_0930_1600")
        common, ig, in_ = np.intersect1d(dg, dn, return_indices=True)
        out[era] = {"days": int(len(common)), "corr": float(np.corrcoef(cg[ig, -1], cn[in_, -1])[0, 1])}
    return out


def _out(era: str) -> Path:
    return ROOT / "reports" / f"a08_gold_{era}.json"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--era", choices=("post", "pre")); ap.add_argument("--log", action="store_true")
    a = ap.parse_args(argv)
    if a.era:
        _out(a.era).write_text(json.dumps(run(a.era), indent=1, default=float) + "\n")
        return 0
    r = {**json.loads(_out("post").read_text()), **json.loads(_out("pre").read_text())}
    r["corr_with_mnq_rth"] = correlation()
    OUT.write_text(json.dumps(r, indent=1, default=float) + "\n")
    for e in ("post", "pre"):
        _out(e).unlink()
    print(json.dumps(r["corr_with_mnq_rth"]))
    if a.log:
        from futuresres.stats.trials import Trial, TrialLog
        log = TrialLog(ROOT / "measurements.jsonl")
        rec = log.append(Trial(trial_id=log.next_id("m"), hypothesis_id="A-series", symbol="MGC",
                               date_range=(r["pre"]["first"], r["post"]["last"]), status="completed",
                               params={"kind": "staking_size_gold", **r},
                               note="kind=computation; NOT a trial. A08: A01 policy on MGC London long, fixed sizes, two histories. decisions.md 106."))
        print("logged", rec["trial_id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())

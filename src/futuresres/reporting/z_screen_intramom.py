"""Route-2 size screen: market intraday momentum (Baltussen, Da, Lammers & Martens, JFE 2021) on MNQ and MGC,
measured ONLY inside the paper's own sample (to 2020-04-30), so no post-publication data is read. A COMPUTATION;
no trial. decisions.md 103.

    python -m futuresres.reporting.z_screen_intramom [--log]

The paper's rule (its eq. 12): hold the last half hour LONG if the return from the previous close to 30 minutes
before today's close (r_ROD) is positive, else SHORT. Closes as the paper's Table 1 hours: NQ 16:00 ET, gold
13:30 ET. Prices are closes of the 1-minute bars ending at 15:30/16:00 (13:00/13:30); days whose r_ROD spans a
contract roll are dropped (the continuous series is unadjusted). Size bar for route 2: several bps per held day.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "z_screen_intramom.json"
SAMPLE_END = np.datetime64("2020-05-01")          # the paper's sample ends May 2020; nothing at or after is read
MARKETS = {"MNQ": ("NQ_MNQ_spliced", "15:30", "16:00", 2.32, 2.0),
           "MGC": ("MGC", "13:00", "13:30", 3.32, 10.0)}


def _hm(s: str) -> int:
    h, m = map(int, s.split(":"))
    return h * 60 + m


def screen(series: str, lh_start: str, close_t: str, rt: float, mult: float) -> dict:
    a, b = _hm(lh_start) - 1, _hm(close_t) - 1        # bar starting one minute earlier closes at the time
    et = pl.col("ts_event").dt.convert_time_zone("America/New_York")
    df = (pl.scan_parquet(ROOT / "data" / "continuous" / f"{series}.parquet").with_columns(et.alias("et"))
            .with_columns((pl.col("et").dt.hour().cast(pl.Int32) * 60 + pl.col("et").dt.minute().cast(pl.Int32)).alias("m"),
                          pl.col("et").dt.date().alias("d"))
            .filter(pl.col("m").is_in([a, b]) & (pl.col("d") < pl.lit(str(SAMPLE_END)).str.to_date()))
            .select("d", "m", "close", "contract").collect())
    p = df.pivot(on="m", index="d", values="close").join(df.filter(pl.col("m") == a).select("d", "contract"), on="d")
    p = p.drop_nulls().sort("d")
    d = p["d"].to_numpy().astype("datetime64[D]"); P1 = p[str(a)].to_numpy(); P2 = p[str(b)].to_numpy(); k = p["contract"].to_numpy()
    assert d.max() < SAMPLE_END
    rod = P1[1:] / P2[:-1] - 1; lh = P2[1:] / P1[1:] - 1; same = k[1:] == k[:-1]
    g = np.sign(rod[same]) * lh[same]
    usd = g * P2[1:][same] * mult - rt
    n = int(same.sum())
    return {"window": [str(d[1:][same][0]), str(d[1:][same][-1])], "days": n,
            "corr_rod_lh": float(np.corrcoef(rod[same], lh[same])[0, 1]),
            "timing_gross_bps_per_day": float(g.mean() * 1e4), "t_gross": float(g.mean() / g.std() * math.sqrt(n)),
            "sd_last_half_hour_bps": float(lh[same].std() * 1e4), "sharpe_gross": float(g.mean() / g.std() * math.sqrt(252)),
            "net_usd_per_day_1_contract": float(usd.mean()), "sharpe_net_1_contract": float(usd.mean() / usd.std() * math.sqrt(252)),
            "hit_rate": float((g > 0).mean())}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--log", action="store_true")
    a = ap.parse_args(argv)
    r = {k: screen(*v) for k, v in MARKETS.items()}
    OUT.write_text(json.dumps(r, indent=1) + "\n")
    print(json.dumps(r, indent=1))
    if a.log:
        from futuresres.stats.trials import Trial, TrialLog
        log = TrialLog(ROOT / "measurements.jsonl")
        rec = log.append(Trial(trial_id=log.next_id("m"), hypothesis_id="Z-screen", symbol="MNQ+MGC",
                               date_range=(min(v["window"][0] for v in r.values()), max(v["window"][1] for v in r.values())),
                               status="completed", params={"kind": "route2_size_screen_in_paper_sample", **r},
                               note="kind=computation; NOT a trial. Intraday momentum size screen, paper's sample only. decisions.md 103."))
        print("logged", rec["trial_id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())

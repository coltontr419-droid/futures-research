"""Price a top-of-book quote pull (Databento GLBX.MDP3, mbp-1) for auditing the cost floor.

IT AUDITS THE SMALLER TERM (decisions.md 71). The cost floor is ~80% commission and ~20% spread,
and the spread term already assumes the one-tick minimum a futures book can quote, so quote data can
only confirm or RAISE it. Whether the convergence result (0.48 > 0.452) inverts turns on all-in
commission (flip point ~$1.69 per MNQ round trip against $1.82 assumed) - a fee-schedule check - or
on passive fills, which quote data cannot measure. Run this before a strategy's economics turn on the
spread, not as the audit that could invert the result.

QUOTES ONLY - this module downloads no market data and spends nothing. It calls Databento's free
metadata endpoints (`get_record_count`, `get_cost`, `get_dataset_range`), which return what a pull
WOULD contain and cost.

    python -m futuresres.reporting.cost_floor_quote --sample-only   # pre-register the sample
    python -m futuresres.reporting.cost_floor_quote                 # quote (needs an API key)

API KEY. Read from the environment variable DATABENTO_API_KEY, or from `.env` (gitignored). It is
sent only to hist.databento.com as HTTP Basic auth (the key as username, empty password - the
official client's scheme) and is never printed, logged or written to any report. The `.env` on this
machine holds FTP batch-delivery credentials, which this API does not accept.

THE THREE WINDOWS, per instrument:
  full      MNQ from its first session (2019-05-06; MNQ did not trade earlier), MGC from 2010-06-06
            (the start of the ohlcv-1m pull, whose ~$40 cost is the scale reference), to the end of
            the dataset.
  recent    the last two years to the end of the dataset.
  sample    30 non-consecutive full CME sessions per instrument (18:00 ET to 17:00 ET, so each
            covers the whole trading day), stratified 10 per era and balanced across weekdays,
            drawn ONCE with a fixed seed from sessions on disk and written to
            `reports/spread_sample_sessions.json` BEFORE any quote or quote data exists - so the
            sample cannot be chosen after seeing anything.

SYMBOLOGY. The spread a strategy pays is the front month's, so the primary quote uses Databento's
volume-rolled continuous front contract (`MNQ.v.0`, `MGC.v.0`, stype_in="continuous"). The ohlcv
pull used `parent` symbology (every expiry and calendar spread); parent is quoted beside it for the
full and recent windows only, so the difference is visible.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Final
from zoneinfo import ZoneInfo

import numpy as np
import polars as pl

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
SAMPLE_JSON: Final[Path] = ROOT / "reports" / "spread_sample_sessions.json"
OUT_JSON: Final[Path] = ROOT / "reports" / "cost_floor_quote.json"
OUT_MD: Final[Path] = ROOT / "reports" / "cost_floor_quote.md"
BASE: Final[str] = "https://hist.databento.com/v0/metadata"
DATASET: Final[str] = "GLBX.MDP3"
SCHEMA: Final[str] = "mbp-1"
ET: Final = ZoneInfo("America/New_York")
SEED: Final[int] = 20261003

INSTRUMENTS: Final[dict[str, dict]] = {
    "MNQ": {"continuous": "MNQ.v.0", "parent": "MNQ.FUT", "full_start": date(2019, 5, 6),
            "series": "MNQ", "eras": [(2019, 2020), (2021, 2023), (2024, 2026)]},
    "MGC": {"continuous": "MGC.v.0", "parent": "MGC.FUT", "full_start": date(2010, 6, 6),
            "series": "MGC", "eras": [(2010, 2015), (2016, 2020), (2021, 2026)]},
}


# ── the pre-registered sample ─────────────────────────────────────────────────────────

def draw_sample() -> dict[str, list[str]]:
    """10 sessions per era, two per weekday, no two on adjacent calendar days. Drawn from the
    sessions the continuous series contains (so every one is a real trading day), with a fixed seed.
    Reads session DATES only - no prices."""
    rng = np.random.default_rng(SEED)
    out: dict[str, list[str]] = {}
    for inst, cfg in INSTRUMENTS.items():
        sessions = (pl.scan_parquet(ROOT / "data" / "continuous" / f"{cfg['series']}.parquet")
                    .select("session").unique().collect()["session"].sort().to_list())
        picked: list[date] = []
        for lo, hi in cfg["eras"]:
            pool = [s for s in sessions if lo <= s.year <= hi]
            for wd in range(5):                         # Monday..Friday, two each
                cand = [s for s in pool if s.weekday() == wd]
                rng.shuffle(cand)
                n = 0
                for s in cand:
                    if all(abs((s - p).days) > 1 for p in picked):
                        picked.append(s)
                        n += 1
                        if n == 2:
                            break
        out[inst] = sorted(d.isoformat() for d in picked)
    return out


def session_window(d: date) -> tuple[str, str]:
    """A CME trading day D runs from 18:00 ET on D-1 to 17:00 ET on D, in UTC ISO."""
    start = datetime.combine(d - timedelta(days=1), time(18, 0), ET).astimezone(ZoneInfo("UTC"))
    end = datetime.combine(d, time(17, 0), ET).astimezone(ZoneInfo("UTC"))
    return start.strftime("%Y-%m-%dT%H:%M:%SZ"), end.strftime("%Y-%m-%dT%H:%M:%SZ")


# ── the API, free metadata endpoints only ─────────────────────────────────────────────

def api_key() -> str | None:
    key = os.environ.get("DATABENTO_API_KEY")
    env = ROOT / ".env"
    if not key and env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("DATABENTO_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"')
    return key or None


def call(key: str, endpoint: str, params: dict, method: str = "POST"):
    auth = base64.b64encode(f"{key}:".encode()).decode()
    data = urllib.parse.urlencode(params).encode()
    url = f"{BASE}.{endpoint}"
    if method == "GET":
        req = urllib.request.Request(f"{url}?{data.decode()}", method="GET")
    else:
        req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Basic {auth}")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def quote(key: str, symbols: str, stype: str, start: str, end: str) -> dict:
    p = {"dataset": DATASET, "symbols": symbols, "schema": SCHEMA, "stype_in": stype,
         "start": start, "end": end}
    return {"records": int(call(key, "get_record_count", p)),
            "cost_usd": float(call(key, "get_cost", p))}


def run(key: str, sample: dict[str, list[str]]) -> dict:
    rng = call(key, "get_dataset_range", {"dataset": DATASET}, method="GET")
    ds_end = rng.get("end") or rng.get("end_date")
    end_dt = datetime.fromisoformat(str(ds_end).replace("Z", "+00:00"))
    end = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    two_back = (end_dt - timedelta(days=730)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = {"dataset_end": end, "schema": SCHEMA, "instruments": {}}
    for inst, cfg in INSTRUMENTS.items():
        full_start = session_window(cfg["full_start"])[0]
        r = {
            "full_continuous": quote(key, cfg["continuous"], "continuous", full_start, end),
            "full_parent": quote(key, cfg["parent"], "parent", full_start, end),
            "recent_continuous": quote(key, cfg["continuous"], "continuous", two_back, end),
            "recent_parent": quote(key, cfg["parent"], "parent", two_back, end),
        }
        per = []
        for d in sample[inst]:
            s, e = session_window(date.fromisoformat(d))
            q = quote(key, cfg["continuous"], "continuous", s, e)
            per.append({"session": d, **q})
        r["sample_continuous"] = {
            "sessions": len(per), "records": sum(x["records"] for x in per),
            "cost_usd": sum(x["cost_usd"] for x in per), "per_session": per,
        }
        out["instruments"][inst] = r
    return out


def render(q: dict) -> str:
    w: list[str] = []
    a = w.append
    a("# mbp-1 quote for auditing the cost floor")
    a("")
    a(f"Databento {DATASET}, schema `{SCHEMA}`, priced by the free metadata endpoints — nothing "
      f"downloaded, nothing spent. Dataset end {q['dataset_end']}. Scale reference: the ohlcv-1m "
      f"pull for the same instruments cost about $40.")
    a("")
    a("| instrument | window | symbology | records | cost (USD) | × the $40 reference |")
    a("|---|---|---|---|---|---|")
    labels = [("full_continuous", "full range", "front month (v.0)"),
              ("full_parent", "full range", "parent (all expiries + spreads)"),
              ("recent_continuous", "last two years", "front month (v.0)"),
              ("recent_parent", "last two years", "parent"),
              ("sample_continuous", "30 sessions", "front month (v.0)")]
    for inst, r in q["instruments"].items():
        for key, win, sym in labels:
            x = r[key]
            a(f"| {inst} | {win} | {sym} | {x['records']:,} | ${x['cost_usd']:,.2f} | "
              f"{x['cost_usd'] / 40:.1f}× |")
    a("")
    return "\n".join(w)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.reporting.cost_floor_quote")
    ap.add_argument("--sample-only", action="store_true")
    args = ap.parse_args(argv)
    if SAMPLE_JSON.exists():
        sample = json.loads(SAMPLE_JSON.read_text())["sessions"]
    else:
        sample = draw_sample()
        SAMPLE_JSON.write_text(json.dumps({
            "drawn": "2026-10-03", "seed": SEED,
            "rule": "per instrument: 3 eras x 10 sessions, 2 per weekday, none on adjacent days, "
                    "from sessions in the continuous series; drawn before any quote or quote data",
            "sessions": sample}, indent=1) + "\n")
        print(f"pre-registered {sum(len(v) for v in sample.values())} sessions -> {SAMPLE_JSON.name}")
    if args.sample_only:
        return 0
    key = api_key()
    if not key:
        print("No DATABENTO_API_KEY in the environment or .env. Quote not run; the sample stands.")
        return 2
    q = run(key, sample)
    OUT_JSON.write_text(json.dumps(q, indent=1) + "\n")
    OUT_MD.write_text(render(q))
    print(f"wrote {OUT_JSON.name}, {OUT_MD.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

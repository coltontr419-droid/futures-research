"""A122 forward test (decisions.md 1095): the Fast Track trade and account rules replayed minute by minute on real NQ prices after the backtest.

Every run pulls Yahoo's 1-minute NQ=F bars (the same price as MNQ; Yahoo keeps ~30 days of 1-minute history, so a missed day is caught up
within a month), stores them under data/forward/ (gitignored), and replays every complete RTH session from FIRST onward with the same
minute engine as the history (a122_fast_track_minute.simulate, worst order inside a bar). Real dollars: no drift removed, MNQ $2 a point,
long (the user's side). Writes reports/a122_forward.json and reports/a122_forward.md.

    python -m futuresres.reporting.a122_forward
"""

from __future__ import annotations

import datetime as dt
import json
import time
import zoneinfo
from pathlib import Path

import numpy as np
import pandas as pd

from futuresres.reporting.a122_fast_track_minute import TERMS, simulate

ROOT = Path(__file__).resolve().parents[3]
STORE = ROOT / "data" / "forward" / "nq_1m.parquet"
NY = zoneinfo.ZoneInfo("America/New_York")
FIRST = dt.date(2026, 9, 30)          # first day Yahoo still had at the start; the A23 history ends 2026-08-27
URL = "https://query1.finance.yahoo.com/v8/finance/chart/NQ=F"


def fetch() -> pd.DataFrame:
    from curl_cffi import requests
    now = int(time.time()); rows = []
    for back in (29, 22, 15, 8, 1):
        p1 = now - back * 86400; p2 = min(now, p1 + 7 * 86400 + 3600)
        r = requests.get(URL, params={"interval": "1m", "period1": p1, "period2": p2}, impersonate="chrome", timeout=30)
        res = (r.json().get("chart") or {}).get("result") if r.status_code == 200 else None
        if not res or not res[0].get("timestamp"):
            continue
        q = res[0]["indicators"]["quote"][0]
        rows.append(pd.DataFrame({"ts": res[0]["timestamp"], "open": q["open"], "high": q["high"], "low": q["low"], "close": q["close"]}))
        time.sleep(1.5)
    return pd.concat(rows).dropna() if rows else pd.DataFrame(columns=["ts", "open", "high", "low", "close"])


def update() -> pd.DataFrame:
    new = fetch()
    old = pd.read_parquet(STORE) if STORE.exists() else new.iloc[:0]
    df = pd.concat([old, new]).drop_duplicates("ts", keep="last").sort_values("ts").reset_index(drop=True)
    STORE.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(STORE)
    return df


def sessions(df: pd.DataFrame):
    """Complete RTH sessions (09:30-15:59 bars present through 15:55) as 1-contract $ paths relative to the 09:30 open."""
    t = pd.to_datetime(df["ts"], unit="s", utc=True).dt.tz_convert(NY)
    df = df.assign(day=t.dt.date, hm=t.dt.hour * 100 + t.dt.minute)
    rth = df[(df.hm >= 930) & (df.hm < 1600) & (df.day >= FIRST)]
    today = dt.datetime.now(NY)
    H, Lo, C, D = [], [], [], []
    for day, g in rth.groupby("day"):
        if g.hm.iloc[0] != 930 or (day == today.date() and today.hour * 100 + today.minute < 1605):
            continue
        if g.hm.iloc[-1] < 1555 and day.weekday() < 5 and len(g) < 200:   # partial day in the store (not a holiday half-session)
            continue
        e = float(g.open.iloc[0])
        H.append(((g.high.values - e) * 2.0).astype(np.float32)); Lo.append(((g.low.values - e) * 2.0).astype(np.float32))
        C.append(((g.close.values - e) * 2.0).astype(np.float32)); D.append(day)
    return H, Lo, C, D


def main() -> int:
    df = update()
    H, Lo, C, D = sessions(df)
    r = simulate(H, Lo, C, D, TERMS, exact=True, side=1)
    out = {"updated": dt.datetime.now(NY).isoformat(timespec="minutes"), "first": str(FIRST), "last": str(D[-1]) if D else None, **r,
           "history_reference": "A122 history, long, minute replay: +$3,872 (2010-20) / +$3,876 (2021-26) per 84 sessions; 3.4-3.7 accounts per payout"}
    (ROOT / "reports" / "a122_forward.json").write_text(json.dumps(out, indent=1) + "\n")
    lines = [f"# Fast Track forward test (A122) — updated {out['updated']} ET", "",
             f"Sessions {r['sessions']} ({out['first']} → {out['last']}), long, 3 MNQ, take 108.25 / stop 333.25 pts, minute replay.", "",
             f"Accounts bought {r['bought']}, payouts {r['payouts']}, paid after split ${r['paid']:,.0f}, fees ${r['fees']:,.0f}, "
             f"**net ${r['net']:+,.0f}** (${r['net_per_84']:+,.0f} per 84 sessions); open account balance ${r['open_balance']:+,.0f}.", "",
             f"Reference: {out['history_reference']}.", "", "| Date | Event | $ | Account balance (P&L) |", "|---|---|---|---|"]
    fm = lambda v: "" if v is None else f"{v:+,.0f}"
    lines += [f"| {d} | {e} | {fm(a)} | {fm(b)} |" for d, e, a, b in r["log"]]
    (ROOT / "reports" / "a122_forward.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:5]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

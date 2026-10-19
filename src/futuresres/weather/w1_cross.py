"""W1: when the temperature passes a Kalshi daily-high bracket's top, that bracket is dead (the day's high only rises). How fast does
Kalshi's price collapse after the first 5-minute ASOS reading above it? IEM 5-minute archive + Kalshi trades, settled since the cutoff.

    python -m futuresres.weather.w1_cross
"""

from __future__ import annotations

import bisect
import csv
import datetime as dt
import io
import json
import os
import statistics as st
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "kalshi_lip"))
os.environ.setdefault("KALSHI_RATE", "4")
from kalshi_api import Client  # noqa: E402

from futuresres.mention.m0_download import trades  # noqa: E402
from futuresres.mention.m1_prize import T, fee  # noqa: E402

CITY = {"KXHIGHCHI": "MDW", "KXHIGHMIA": "MIA", "KXHIGHAUS": "AUS", "KXHIGHLAX": "LAX", "KXHIGHDEN": "DEN", "KXHIGHPHIL": "PHL"}
LST = {"KXHIGHCHI": -6, "KXHIGHMIA": -5, "KXHIGHAUS": -6, "KXHIGHLAX": -8, "KXHIGHDEN": -7, "KXHIGHPHIL": -5}   # NWS climate day = local STANDARD time


def climate_day(series: str, event_ticker: str) -> tuple[dt.datetime, dt.datetime]:
    d = dt.datetime.strptime(event_ticker.split("-")[1], "%y%b%d").replace(tzinfo=dt.timezone(dt.timedelta(hours=LST[series])))
    return d.astimezone(dt.timezone.utc), (d + dt.timedelta(days=1)).astimezone(dt.timezone.utc)
OUT = ROOT / "data" / "weather" / "w1"
START = dt.date(2026, 8, 20)
MARGIN = float(os.environ.get("W1_MARGIN", "1"))


def obs(st_: str) -> tuple[list, list]:
    f = OUT / f"{st_}_5min.csv"
    if not f.exists():
        u = (f"https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station={st_}&data=tmpf&tz=Etc/UTC&format=onlycomma&latlon=no&missing=M"
             f"&report_type=1&report_type=3&report_type=4&year1={START.year}&month1={START.month}&day1={START.day}&year2=2026&month2=10&day2=19")
        f.write_text(urllib.request.urlopen(u, timeout=300).read().decode()); time.sleep(3)
    rows = sorted((dt.datetime.fromisoformat(r["valid"]).replace(tzinfo=dt.timezone.utc), float(r["tmpf"]))
                  for r in csv.DictReader(io.StringIO(f.read_text())) if r["tmpf"] not in ("M", ""))
    return [t for t, _ in rows], [x for _, x in rows]


def main() -> int:
    c = Client(); OUT.mkdir(parents=True, exist_ok=True); res = []
    for s, stn in CITY.items():
        ts, tf = obs(stn); ms, cur = [], None
        for _ in range(10):
            d = c.req("GET", f"/markets?series_ticker={s}&status=settled&limit=1000" + (f"&cursor={cur}" if cur else ""))
            ms += d.get("markets", []); cur = d.get("cursor")
            if not cur or not d.get("markets"):
                break
        for m in ms:
            if m.get("result") != "no" or m.get("cap_strike") is None:
                continue
            try:
                final = float(m.get("expiration_value"))
            except (TypeError, ValueError):
                continue
            cap = float(m["cap_strike"])            # bracket/threshold top: the market is dead once a reading exceeds it
            if final <= cap + 0.5 or m["strike_type"] not in ("between", "less"):
                continue
            day0, day1 = climate_day(s, m["event_ticker"])
            i = next((k for k in range(bisect.bisect_left(ts, day0), bisect.bisect_left(ts, day1)) if tf[k] >= cap + MARGIN), None)
            if i is None:
                continue
            cross = ts[i]
            f = OUT / f"{m['ticker']}.json"
            if not f.exists():
                f.write_text(json.dumps(trades(c, m["ticker"])))
            tr = sorted(json.loads(f.read_text()), key=lambda x: x["created_time"])
            before = [x for x in tr if T(x["created_time"]) < cross]
            if not before or float(before[-1]["yes_price_dollars"]) < 0.15:
                continue                             # already priced as dead before the crossing
            # takers selling YES (buying NO) at no <= 0.85 from the crossing on: the prize; first such sweep time
            sells = [x for x in tr if T(x["created_time"]) >= cross - dt.timedelta(minutes=30) and x["taker_side"] == "no"
                     and float(x["no_price_dollars"]) <= 0.85]
            after = [x for x in tr if T(x["created_time"]) >= cross]
            dead = next((x for x in after if float(x["yes_price_dollars"]) <= 0.05), None)
            prize = sum(float(x["count_fp"]) * (1 - float(x["no_price_dollars"]) - fee(float(x["no_price_dollars"]))) for x in sells
                        if T(x["created_time"]) >= cross)
            pre = sum(float(x["count_fp"]) for x in sells if T(x["created_time"]) < cross)
            res.append({"ticker": m["ticker"], "cross": cross.isoformat(), "last_yes_before": float(before[-1]["yes_price_dollars"]),
                        "minutes_to_dead": (T(dead["created_time"]) - cross).total_seconds() / 60 if dead else None,
                        "prize_after_cross": prize, "no_bought_in_30min_before": pre})
        print(s, "done", len([r for r in res if r["ticker"].startswith(s)]), flush=True)
    (ROOT / "reports" / "w1_cross.json").write_text(json.dumps(res, indent=1) + "\n")
    md = [r["minutes_to_dead"] for r in res if r["minutes_to_dead"] is not None]
    print(f"crossings with the bracket still >= 15c before: {len(res)}; prize after the 5-min reading (NO bought <= 85c): ${sum(r['prize_after_cross'] for r in res):,.0f}")
    if md:
        md.sort(); print(f"minutes from the reading to YES <= 5c: median {st.median(md):.1f}, p10 {md[len(md)//10]:.1f}, p90 {md[9*len(md)//10]:.1f}")
    print(f"contracts of NO bought at <= 85c in the 30 min BEFORE the reading: {sum(r['no_bought_in_30min_before'] for r in res):,.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

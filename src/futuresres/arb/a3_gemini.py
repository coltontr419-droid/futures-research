"""A3: Gemini Predictions x Kalshi game-winner markets (NFL, NBA, MLB, NHL): buy team A YES on one venue + team B YES on the other
for < $1 after taker fees? Top of book, one snapshot. Gemini: public API (no key); fee assumed equal to Kalshi's (conservative).

    python -m futuresres.arb.a3_gemini
"""

from __future__ import annotations

import datetime as dt
import json
import math
import re
import sys
import urllib.request

KAL = "https://api.elections.kalshi.com/trade-api/v2"
GEM = "https://api.gemini.com/v1/prediction-markets/events?status=active&limit=200"
SER = {"NFL": "KXNFLGAME", "NBA": "KXNBAGAME", "MLB": "KXMLBGAME", "NHL": "KXNHLGAME"}


def get(u):
    return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "research"}), timeout=60).read())


def fee(p):
    return math.ceil(7 * p * (1 - p)) / 100


def main() -> int:
    gem, off = [], 0
    for _ in range(20):
        d = get(GEM + f"&offset={off}"); rows = d if isinstance(d, list) else d.get("data", [])
        gem += rows; off += len(rows)
        if len(rows) < 200:
            break
    kal = {}
    for lg, s in SER.items():
        d = get(f"{KAL}/markets?series_ticker={s}&status=open&limit=1000")
        for m in d.get("markets", []):
            kal[m["ticker"]] = m
    found = checked = 0
    for e in gem:
        m = re.match(r"(NFL|NBA|MLB|NHL)-(\d{10})-([A-Z]+)-([A-Z]+)-M$", e.get("ticker", ""))
        if not m:
            continue
        lg, ts, a, h = m.groups(); t = dt.datetime.strptime(ts, "%y%m%d%H%M").replace(tzinfo=dt.timezone.utc)
        g = {c.get("label"): c.get("prices") or {} for c in e.get("contracts", [])}
        for local_day in {(t - dt.timedelta(hours=5)).date(), t.date()}:
            ev = f"{SER[lg]}-{local_day:%y%b%d}{a}{h}".upper()
            km = {k.rsplit("-", 1)[1]: v for k, v in kal.items() if k.startswith(ev + "-")}
            if len(km) < 2:
                continue
            checked += 1
            teams = list(km)
            gl = list(g.items())
            for team_k in teams:
                other_k = [x for x in teams if x != team_k][0]
                ka = float(km[team_k].get("yes_ask_dollars") or 1)
                other_name = (km[other_k].get("yes_sub_title") or "").lower()
                # the Gemini contract for the OTHER team (labels are team/city names, e.g. "San Francisco")
                for lab, pr in gl:
                    if not lab or not (lab.lower() in other_name or other_name in lab.lower()):
                        continue
                    ga = float(pr.get("bestAsk") or 1)
                    cost = ka + ga + fee(ka) + fee(ga)
                    if cost < 0.995:
                        found += 1; print(f"  {ev} Kalshi {team_k} ask {ka} + Gemini '{lab}' ask {ga} = {cost:.3f}")
            break
    print(f"games matched {checked}; candidate pairs under $1 after fees: {found}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

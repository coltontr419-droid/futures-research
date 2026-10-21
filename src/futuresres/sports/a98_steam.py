"""A98 (decisions.md 794): does Kalshi's game-line book lag Pinnacle's moneyline moves? Records only, no orders.

    python -m futuresres.sports.a98_steam record     # service futres-a98, ~20 s cadence
    python -m futuresres.sports.a98_steam            # readout
"""

from __future__ import annotations

import collections
import datetime as dt
import difflib
import json
import statistics as st
import sys
import time
from pathlib import Path

from futuresres.kalshi.k1_longshot import fee
from futuresres.sports import a96_prophetx as a

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "sports" / "a98"
KB = "https://api.elections.kalshi.com/trade-api/v2"
LEAGUES = {"NBA": (4, "KXNBAGAME"), "NHL": (19, "KXNHLGAME"), "NFL": (15, "KXNFLGAME"), "NCAAF": (15, "KXNCAAFGAME")}
UTC = dt.timezone.utc


def pin() -> list:
    """[(league, start ET date, {team: no-vig p})] for games starting within 24 h, pre-match."""
    out, now = [], dt.datetime.now(UTC)
    for sid in {v[0] for v in LEAGUES.values()}:
        mu = a.get(f"{a.PIN}/sports/{sid}/matchups?withSpecials=false", a.PIN_H) or []
        mk = a.get(f"{a.PIN}/sports/{sid}/markets/straight", a.PIN_H) or []
        ml = {m["matchupId"]: m for m in mk if m.get("type") == "moneyline" and m.get("period") == 0}
        for m in mu:
            if m.get("parentId") or m["id"] not in ml or len(m.get("participants", [])) != 2 or m.get("isLive"):
                continue
            lg = m["league"]["name"]; lg = "NCAAF" if "NCAA" in lg and sid == 15 else lg
            st_ = dt.datetime.fromisoformat(m["startTime"].replace("Z", "+00:00"))
            if lg not in LEAGUES or not dt.timedelta(0) < st_ - now < dt.timedelta(hours=24):
                continue
            pr = {p["designation"]: 1 / a.dec(float(p["price"])) for p in ml[m["id"]]["prices"]}
            if set(pr) != {"home", "away"}:
                continue
            s = sum(pr.values())
            out.append((lg, st_.astimezone(dt.timezone(dt.timedelta(hours=-4))).strftime("%y%b%d").upper(),
                        {a.norm(p["name"]): round(pr[p["alignment"]] / s, 4) for p in m["participants"]}))
    return out


def kalshi() -> dict:
    """(league, YYMONDD) -> [ {city: (bid, ask, ticker)} per event ]."""
    out = collections.defaultdict(list)
    for lg, (_, ser) in LEAGUES.items():
        d = a.get(f"{KB}/markets?series_ticker={ser}&status=open&limit=1000") or {}
        ev = collections.defaultdict(dict)
        for m in d.get("markets", []):
            ev[m["event_ticker"]][a.norm(m.get("yes_sub_title") or "")] = (float(m.get("yes_bid_dollars") or 0), float(m.get("yes_ask_dollars") or 1), m["ticker"])
        for e, mk in ev.items():
            out[(lg, e.split("-")[1][:7])].append(mk)
    return out


def match(teams: dict, events: list):
    """Both Pinnacle teams start with distinct Kalshi cities of one event -> {team: (bid, ask, ticker)}."""
    for mk in events:
        got = {}
        for t in teams:
            c = [c for c in mk if c and (t.startswith(c) or c in t)]
            if len(c) == 1:
                got[t] = mk[c[0]]
        if len(got) == 2 and got[list(teams)[0]][2] != got[list(teams)[1]][2]:
            return got
    return None


def record() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    while True:
        t0 = time.time()
        try:
            P = pin(); K = kalshi(); now = dt.datetime.now(UTC).isoformat(timespec="seconds"); rows = []
            for lg, day, teams in P:
                got = match(teams, K.get((lg, day), []))
                for t, (b, ak, tk) in (got or {}).items():
                    rows.append({"t": now, "lg": lg, "team": t, "p": teams[t], "bid": b, "ask": ak, "tk": tk})
            with open(OUT / f"{dt.datetime.now(UTC):%Y%m%d}.jsonl", "a") as f:
                for r in rows:
                    f.write(json.dumps(r) + "\n")
        except Exception as e:
            print("poll error", e, flush=True)
        time.sleep(max(5.0, 20 - (time.time() - t0)))


def readout() -> dict:
    rows = [json.loads(l) for p in sorted(OUT.glob("*.jsonl")) for l in open(p)]
    by = collections.defaultdict(list)
    for r in rows:
        by[(r["lg"], r["team"])].append(r)
    opp = collections.defaultdict(list)
    for k, v in by.items():
        v.sort(key=lambda r: r["t"])
        for i in range(1, len(v)):
            d = v[i]["p"] - v[i - 1]["p"]
            if abs(d) < 0.02:
                continue
            t0 = dt.datetime.fromisoformat(v[i]["t"]); new = v[i]["p"]
            for lag in (0, 20, 40, 60, 120):
                r = next((x for x in v[i:] if (dt.datetime.fromisoformat(x["t"]) - t0).total_seconds() >= lag), None)
                if r:
                    e = (new - r["ask"] - fee(r["ask"])) if d > 0 else (r["bid"] - new - fee(r["bid"]))
                    opp[lag].append(e)
    if not opp:
        print(f"rows {len(rows)}; no Pinnacle moves >= 2 pts yet"); return {}
    n = len(opp[0])
    print(f"moves {n} (rows {len(rows)})")
    for lag, v in sorted(opp.items()):
        print(f"  +{lag:3d}s: median opportunity {st.median(v)*100:+.2f}c, >= 1c on {sum(x >= 0.01 for x in v)/len(v):.0%} (n {len(v)})")
    return {"moves": n}


if __name__ == "__main__":
    record() if sys.argv[1:2] == ["record"] else readout()

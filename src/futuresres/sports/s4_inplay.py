"""S4: Kalshi NFL game-winner markets after big plays — how much stale-price volume remains X seconds after the snap?
ESPN play-by-play `wallclock` (the snap) for scoring plays and turnovers; Kalshi public trades of the home team's winner market.
The reaction's settled level = VWAP of trades 50-70 s after the snap. Descriptive (no trial): the prize available to a bot with
X-second latency, for X in 3, 6, 10, 15, 20, 30.

    python -m futuresres.sports.s4_inplay [YYYYMMDD ...]
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import math
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "kalshi_lip"))
os.environ.setdefault("KALSHI_RATE", "4")
from kalshi_api import Client  # noqa: E402

from futuresres.mention.m0_download import trades  # noqa: E402

OUT = ROOT / "data" / "sports" / "inplay"
LAGS = (3, 6, 10, 15, 20, 30)
ESPN = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"


def T(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def fee(p):
    return math.ceil(7 * p * (1 - p)) / 100


def get(u):
    return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "research"}), timeout=30).read())


def key_plays(summary) -> list[tuple[dt.datetime, str]]:
    out = []
    for d in summary.get("drives", {}).get("previous", []):
        for p in d.get("plays", []):
            ty = p.get("type", {}).get("text", ""); w = p.get("wallclock")
            if w and (p.get("scoringPlay") or "Interception" in ty or "Fumble Recovery (Opponent)" in ty or "Blocked" in ty or "Safety" in ty):
                out.append((T(w), f"{ty}: {p.get('text', '')[:60]}"))
    return sorted(out)


def kalshi_ticker(c: Client, summary) -> str | None:
    comp = summary["header"]["competitions"][0]; d = T(comp["date"]).astimezone(dt.timezone(dt.timedelta(hours=-5)))
    teams = {x["homeAway"]: x["team"]["abbreviation"] for x in comp["competitors"]}
    fix = {"WSH": "WAS", "LAR": "LA"}
    a, h = fix.get(teams["away"], teams["away"]), fix.get(teams["home"], teams["home"])
    ev = f"KXNFLGAME-{d:%y%b%d}{a}{h}".upper()
    try:
        ms = c.req("GET", f"/markets?event_ticker={ev}&limit=10").get("markets", [])
    except Exception:
        return None
    return next((m["ticker"] for m in ms if m["ticker"].endswith("-" + h)), None)


def main(argv) -> int:
    c = Client(); OUT.mkdir(parents=True, exist_ok=True); days = argv or ["20261018"]
    tot = collections.defaultdict(float); vol = collections.defaultdict(float); n_plays = 0; moves = []
    for day in days:
        sb = get(f"{ESPN}/scoreboard?dates={day}")
        for e in sb["events"]:
            if e["status"]["type"]["description"] != "Final":
                continue
            f = OUT / f"{e['id']}.json"
            if not f.exists():
                s = get(f"{ESPN}/summary?event={e['id']}"); tk = kalshi_ticker(c, s)
                if not tk:
                    print("no Kalshi market for", e["shortName"]); continue
                for k in range(6):
                    try:
                        tr = trades(c, tk); break
                    except RuntimeError:
                        time.sleep(8 * (k + 1))
                f.write_text(json.dumps({"game": e["shortName"], "ticker": tk, "plays": [(t.isoformat(), x) for t, x in key_plays(s)],
                                         "trades": sorted(tr, key=lambda x: x["created_time"])}))
            g = json.loads(f.read_text()); tr = [(T(x["created_time"]), float(x["yes_price_dollars"]), float(x["count_fp"]), x["taker_side"]) for x in g["trades"]]
            ts_ = [x[0] for x in tr]
            import bisect
            for w, label in g["plays"]:
                t0 = T(w); i0 = bisect.bisect_left(ts_, t0)
                if i0 == 0:
                    continue
                before = tr[i0 - 1][1]
                settle = [(p, q) for t, p, q, _ in tr[bisect.bisect_left(ts_, t0 + dt.timedelta(seconds=50)):bisect.bisect_left(ts_, t0 + dt.timedelta(seconds=70))]]
                if not settle:
                    continue
                after = sum(p * q for p, q in settle) / sum(q for _, q in settle); mv = after - before
                if abs(mv) < 0.03:
                    continue
                n_plays += 1; moves.append(round(mv, 3))
                for X in LAGS:
                    for t, p, q, side in tr[bisect.bisect_left(ts_, t0 + dt.timedelta(seconds=X)):bisect.bisect_left(ts_, t0 + dt.timedelta(seconds=45))]:
                        if mv > 0 and side == "yes" and p < after - 0.01:
                            tot[X] += q * (after - p - fee(p)); vol[X] += q
                        elif mv < 0 and side == "no" and p > after + 0.01:
                            tot[X] += q * (p - after - fee(1 - p)); vol[X] += q
            print(f"{g['game']:12} {g['ticker']:32} plays {len(g['plays'])} trades {len(tr)}", flush=True)
    print(f"\nkey plays with a >= 3c move: {n_plays}; median |move| {sorted(abs(m) for m in moves)[len(moves)//2] if moves else 0:.3f}")
    for X in LAGS:
        print(f"  latency {X:2d}s after the snap: stale-side taker volume {vol[X]:10,.0f} contracts, prize ${tot[X]:9,.0f} (to the 50-70 s level, after fee)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

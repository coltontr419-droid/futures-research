"""A96 (decisions.md 782): ProphetX offers vs Pinnacle — forward paper bets scored on closing-line value. Records only, no orders.

    python -m futuresres.sports.a96_prophetx record      # every 10 min, forever (service futres-a96)
    python -m futuresres.sports.a96_prophetx             # paper bets + closing-line EV so far
"""

from __future__ import annotations

import collections
import datetime as dt
import difflib
import json
import re
import statistics as st
import sys
import time
import unicodedata
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "sports" / "a96"
PX = "https://www.prophetx.co/trade/public/api"
PIN = "https://guest.api.arcadia.pinnacle.com/0.1"
PIN_H = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.pinnacle.com/", "Origin": "https://www.pinnacle.com",
         "X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R"}          # the key pinnacle.com's own pages send
SPORTS = {"Tennis": 33, "American Football": 15, "Ice Hockey": 19, "Basketball": 4, "MMA": 22, "Esports": 12, "Baseball": 3}
FEE = 0.02                                                       # ProphetX: 2% of net winnings
UTC = dt.timezone.utc


def get(url: str, headers: dict | None = None):
    for k in range(4):
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"}), timeout=30).read())
        except Exception:
            time.sleep(1 + k)
    return None


def norm(n: str) -> str:
    return " ".join(re.sub(r"[^a-z ]", "", unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode().lower()).split())


def dec(a: float) -> float:
    return 1 + a / 100 if a > 0 else 1 + 100 / -a


def pinnacle() -> dict:
    """(sport, team) -> {p, opp, start, id}: proportional no-vig moneyline, pre-match only."""
    out = {}
    for sp, sid in SPORTS.items():
        mu = get(f"{PIN}/sports/{sid}/matchups?withSpecials=false", PIN_H) or []
        mk = get(f"{PIN}/sports/{sid}/markets/straight", PIN_H) or []
        ml = {m["matchupId"]: m for m in mk if m.get("type") == "moneyline" and m.get("period") == 0}
        for m in mu:
            if m.get("parentId") or m["id"] not in ml or len(m.get("participants", [])) != 2 or m.get("isLive"):
                continue
            pr = {p["designation"]: 1 / dec(float(p["price"])) for p in ml[m["id"]]["prices"]}
            if set(pr) != {"home", "away"}:
                continue
            s = sum(pr.values()); nm = {p["alignment"]: norm(p["name"]) for p in m["participants"]}
            for a, b in (("home", "away"), ("away", "home")):
                out[(sp, nm[a])] = {"p": pr[a] / s, "opp": nm[b], "start": m["startTime"], "id": m["id"]}
        time.sleep(0.5)
    return out


def snapshot() -> list[dict]:
    pins = pinnacle(); keys = collections.defaultdict(list)
    for sp, nm in pins:
        keys[sp].append(nm)
    evs, nxt = [], None
    for _ in range(80):
        d = get(f"{PX}/v1/events" + (f"?next={nxt}" if nxt else "")) or {}
        evs += d.get("data") or []; nxt = d.get("next")
        if not nxt or not d.get("data"):
            break
    now = dt.datetime.now(UTC); rows = []
    for e in evs:
        sp = e["sport"]["name"]
        if sp not in SPORTS or e.get("status") != "not_started":
            continue
        start = dt.datetime.fromisoformat(e["scheduled"].replace("Z", "+00:00"))
        if not dt.timedelta(0) < start - now < dt.timedelta(days=7):
            continue
        comp = {c["id"]: norm(c["name"]) for c in e.get("competitors", [])}
        ms = ((get(f"{PX}/v2/events/{e['id']}/markets") or {}).get("data") or {}).get("markets") or []
        time.sleep(0.4)
        m = next((x for x in ms if x.get("type") == "moneyline"), None)
        if not m or len(comp) != 2:
            continue
        for side in m.get("selections") or []:
            if not side:
                continue
            best = max(side, key=lambda s: dec(s["odds"])); me = comp.get(best.get("competitorId"), "")
            other = next((v for k, v in comp.items() if k != best.get("competitorId")), "")
            hit = me if (sp, me) in pins else (difflib.get_close_matches(me, keys[sp], 1, 0.85) or [None])[0]
            if not hit or not difflib.get_close_matches(other, [pins[(sp, hit)]["opp"]], 1, 0.8):
                continue
            pz = pins[(sp, hit)]; D = dec(best["odds"])
            rows.append({"t": now.isoformat(timespec="seconds"), "sport": sp, "px_event": e["id"], "start": e["scheduled"], "side": me,
                         "odds": best["odds"], "risk_avail": float(best.get("value") or 0), "pin_id": pz["id"], "pin_p": round(pz["p"], 4),
                         "ev": round(pz["p"] * (D - 1) * (1 - FEE) - (1 - pz["p"]), 4)})
    return rows


def record() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    while True:
        t0 = time.time()
        try:
            rows = snapshot()
            with open(OUT / f"{dt.datetime.now(UTC):%Y%m%d}.jsonl", "a") as f:
                for r in rows:
                    f.write(json.dumps(r) + "\n")
            print(f"{dt.datetime.now(UTC):%H:%MZ} sides {len(rows)}, EV >= 2%: {sum(r['ev'] >= 0.02 for r in rows)}", flush=True)
        except Exception as e:                                   # keep recording through a bad sweep
            print("sweep error", e, flush=True)
        time.sleep(max(60.0, 600 - (time.time() - t0)))


def analyse() -> dict:
    rows = [json.loads(l) for p in sorted(OUT.glob("*.jsonl")) for l in open(p)]
    last = {}                                                    # closing: last snapshot before the start, per (event, side)
    for r in rows:
        if r["t"] < r["start"]:
            last[(r["px_event"], r["side"])] = r
    bets, seen = [], {}
    for r in sorted(rows, key=lambda r: r["t"]):
        k = (r["px_event"], r["side"]); t = dt.datetime.fromisoformat(r["t"])
        if r["ev"] < 0.02 or r["risk_avail"] < 25 or r["t"] >= r["start"]:
            continue
        if k in seen and (t - seen[k]).total_seconds() < 6 * 3600:
            continue
        seen[k] = t; c = last.get(k)
        if not c or c["t"] == r["t"] or dt.datetime.fromisoformat(r["start"].replace("Z", "+00:00")) > dt.datetime.now(UTC):
            continue                                             # not closed yet
        D = dec(r["odds"]); p = c["pin_p"]
        bets.append({"sport": r["sport"], "size": min(r["risk_avail"], 100.0), "ev_entry": r["ev"], "clv_ev": p * (D - 1) * (1 - FEE) - (1 - p),
                     "t": r["t"], "side": r["side"]})
    if len(bets) < 3:
        print(f"closed paper bets so far: {len(bets)}"); return {"bets": len(bets)}
    x = [b["clv_ev"] for b in bets]; m = st.mean(x); t = m / (st.stdev(x) / len(x) ** 0.5)
    by = collections.defaultdict(list)
    for b in bets:
        by[b["sport"]].append(b["clv_ev"])
    weeks = max(1.0, (dt.datetime.fromisoformat(bets[-1]["t"]) - dt.datetime.fromisoformat(bets[0]["t"])).total_seconds() / 604800)
    wk = sum(b["size"] * b["clv_ev"] for b in bets) / weeks
    print(f"paper bets {len(bets)}; mean entry EV {st.mean(b['ev_entry'] for b in bets)*100:+.2f}%, closing-line EV {m*100:+.2f}% (t {t:+.2f}); "
          f"EV $/week {wk:,.0f} | " + ", ".join(f"{k} {len(v)}:{st.mean(v)*100:+.2f}%" for k, v in by.items()))
    res = {"bets": len(bets), "clv_ev": m, "t": t, "usd_week": wk, "by_sport": {k: {"n": len(v), "mean": st.mean(v)} for k, v in by.items()}}
    (ROOT / "reports" / "a96_prophetx.json").write_text(json.dumps(res, indent=1) + "\n")
    return res


if __name__ == "__main__":
    record() if sys.argv[1:2] == ["record"] else analyse()

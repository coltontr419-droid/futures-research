"""A96 (decisions.md 782): ProphetX offers vs Pinnacle — forward paper bets scored on closing-line value. Records only, no orders.

    python -m futuresres.sports.a96_prophetx record      # every 20 min, forever (service futres-a96)
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
import urllib.error
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
        except urllib.error.HTTPError as e:
            time.sleep(60 if e.code in (403, 429) else 1 + k)          # ProphetX's CDN rate-limits bursts with 403
        except Exception:
            time.sleep(1 + k)
    return None


def norm(n: str) -> str:
    return " ".join(re.sub(r"[^a-z ]", "", unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode().lower()).split())


def dec(a: float) -> float:
    return 1 + a / 100 if a > 0 else 1 + 100 / -a


def pinnacle() -> dict:
    """(sport, team) -> {p, opp, start, id, spread: (points, p), total: (points, p_over)}: proportional no-vig, pre-match, main lines."""
    out = {}
    for sp, sid in SPORTS.items():
        mu = get(f"{PIN}/sports/{sid}/matchups?withSpecials=false", PIN_H) or []
        mk = get(f"{PIN}/sports/{sid}/markets/straight", PIN_H) or []
        ml = {m["matchupId"]: m for m in mk if m.get("type") == "moneyline" and m.get("period") == 0}
        sp_ = {m["matchupId"]: m for m in mk if m.get("type") == "spread" and m.get("period") == 0 and not m.get("isAlternate")}
        to_ = {m["matchupId"]: m for m in mk if m.get("type") == "total" and m.get("period") == 0 and not m.get("isAlternate")}
        for m in mu:
            if m.get("parentId") or m["id"] not in ml or len(m.get("participants", [])) != 2 or m.get("isLive"):
                continue
            pr = {p["designation"]: 1 / dec(float(p["price"])) for p in ml[m["id"]]["prices"]}
            if set(pr) != {"home", "away"}:
                continue
            s = sum(pr.values()); nm = {p["alignment"]: norm(p["name"]) for p in m["participants"]}
            def novig(mm, keys):
                q = {x["designation"]: (1 / dec(float(x["price"])), x.get("points")) for x in mm["prices"]}
                if set(q) != set(keys):
                    return None
                t = sum(v[0] for v in q.values()); return {k: (v[1], v[0] / t) for k, v in q.items()}
            spr = novig(sp_[m["id"]], ("home", "away")) if m["id"] in sp_ else None
            tot = novig(to_[m["id"]], ("over", "under")) if m["id"] in to_ else None
            for a, b in (("home", "away"), ("away", "home")):
                out[(sp, nm[a])] = {"p": pr[a] / s, "opp": nm[b], "start": m["startTime"], "id": m["id"],
                                    "spread": spr[a] if spr else None, "total": tot}
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
        if not dt.timedelta(0) < start - now < dt.timedelta(days=4):
            continue
        comp = {c["id"]: norm(c["name"]) for c in e.get("competitors", [])}
        ms = ((get(f"{PX}/v2/events/{e['id']}/markets") or {}).get("data") or {}).get("markets") or []
        time.sleep(1.5)
        if len(comp) != 2:
            continue
        names = list(comp.values()); pz = None
        for me in names:
            hit = me if (sp, me) in pins else (difflib.get_close_matches(me, keys[sp], 1, 0.9) or [None])[0] if len(me) >= 8 else None
            other = next(v for v in names if v != me)                # short names (esports tags) must match exactly
            if hit and difflib.get_close_matches(other, [pins[(sp, hit)]["opp"]], 1, 0.8):
                pz = {me: pins[(sp, hit)], other: pins[(sp, pins[(sp, hit)]["opp"])]} if (sp, pins[(sp, hit)]["opp"]) in pins else None
                break
        if not pz:
            continue
        base = {"t": now.isoformat(timespec="seconds"), "sport": sp, "px_event": e["id"], "start": e["scheduled"]}
        for x in ms:
            st_ = x.get("subType")
            if st_ not in ("moneyline", "spread", "total") or (sp == "Tennis" and st_ != "moneyline"):
                continue                                         # ProphetX tennis handicaps/totals are in sets, Pinnacle's in games
            sides = x.get("selections") or [sd for ln in x.get("marketLines") or [] for sd in ln.get("selections") or []]
            for side in sides:                                  # spreads / totals keep their offers under marketLines
                for o in side or []:
                    who = comp.get(o.get("competitorId"), ""); nm_ = (o.get("name") or "").lower(); line = o.get("line")
                    if st_ == "moneyline" and who in pz:
                        p = pz[who]["p"]; key = who
                    elif st_ == "spread" and who in pz and pz[who]["spread"] and pz[who]["spread"][0] is not None and float(line) == float(pz[who]["spread"][0]):
                        p = pz[who]["spread"][1]; key = f"{who} {line:+g}"
                    elif st_ == "total" and pz[names[0]]["total"] and nm_[:4] in ("over", "unde"):
                        ou = "over" if nm_.startswith("over") else "under"; pt, pp = pz[names[0]]["total"][ou]
                        if pt is None or float(line) != float(pt):
                            continue
                        p = pp; key = f"{ou} {line:g}"
                    else:
                        continue
                    D = dec(o["odds"])
                    rows.append({**base, "market": st_, "side": key, "odds": o["odds"], "risk_avail": float(o.get("value") or 0),
                                 "pin_id": pz[names[0]]["id"], "pin_p": round(p, 4), "ev": round(p * (D - 1) * (1 - FEE) - (1 - p), 4)})
    best = {}                                                    # keep the best-priced offer per (event, market, side)
    for r in rows:
        k = (r["px_event"], r["market"], r["side"])
        if k not in best or dec(r["odds"]) > dec(best[k]["odds"]):
            best[k] = r
    return list(best.values())


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
        time.sleep(max(120.0, 1200 - (time.time() - t0)))


def analyse() -> dict:
    rows = [json.loads(l) for p in sorted(OUT.glob("*.jsonl")) for l in open(p)]
    last = {}                                                    # closing: last snapshot before the start, per (event, side)
    for r in rows:
        if r["t"] < r["start"]:
            last[(r["px_event"], r.get("market", "moneyline"), r["side"])] = r
    bets, seen = [], {}
    for r in sorted(rows, key=lambda r: r["t"]):
        k = (r["px_event"], r.get("market", "moneyline"), r["side"]); t = dt.datetime.fromisoformat(r["t"])
        if r["ev"] < 0.02 or r["risk_avail"] < 25 or r["t"] >= r["start"]:
            continue
        if k in seen and (t - seen[k]).total_seconds() < 6 * 3600:
            continue
        seen[k] = t; c = last.get(k)
        if not c or c["t"] == r["t"] or dt.datetime.fromisoformat(r["start"].replace("Z", "+00:00")) > dt.datetime.now(UTC):
            continue                                             # not closed yet
        D = dec(r["odds"]); p = c["pin_p"]
        bets.append({"sport": r["sport"], "market": r.get("market", "moneyline"), "size": min(r["risk_avail"], 100.0), "ev_entry": r["ev"], "clv_ev": p * (D - 1) * (1 - FEE) - (1 - p),
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

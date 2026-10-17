"""S-series family 3 - NFL point spreads in published situational spots (decisions.md 686).

    python -m futuresres.sports.s3_nfl_spots             (discovery 1999-2014)
    python -m futuresres.sports.s3_nfl_spots --validate  (once, sealed 2015-2025, carried cells only)
"""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

from futuresres.sports.s2_nfl_weather import GAMES, LOSS, WIN, _f, _t

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "s3_discovery.json"
DISC, VAL = range(1999, 2015), range(2015, 2026)


def rows(seasons):
    for r in csv.DictReader(open(GAMES)):
        se = int(r["season"]); sp = _f(r["spread_line"]); res = _f(r["result"]); tl = _f(r["total_line"]); tot = _f(r["total"])
        if se not in seasons or sp is None or res is None:
            continue
        gt = r["gametime"] or ""
        yield {"season": se, "week": (se, int(r["week"])), "sp": sp, "res": res, "tl": tl, "tot": tot, "hr": _f(r["home_rest"]),
               "ar": _f(r["away_rest"]), "div": r["div_game"] == "1", "wd": r["weekday"], "hour": int(gt[:2]) if gt[:2].isdigit() else None}


def side_ret(g, side):
    """side 'home' / 'away' against the spread; 'under' against the total; None on a push or a missing line."""
    if side == "under":
        if g["tl"] is None or g["tot"] is None or g["tot"] == g["tl"]:
            return None
        return WIN if g["tot"] < g["tl"] else LOSS
    m = g["res"] - g["sp"]
    if m == 0:
        return None
    return WIN if (m > 0) == (side == "home") else LOSS


def bet(g, test):
    if test == "home underdogs":
        return "home" if g["sp"] < 0 else None
    if test == "rest edge >= 3 days":
        if g["hr"] is None or g["ar"] is None:
            return None
        return "home" if g["hr"] - g["ar"] >= 3 else ("away" if g["ar"] - g["hr"] >= 3 else None)
    if test == "Thursday home":
        return "home" if g["wd"] == "Thursday" else None
    if test == "divisional underdogs":
        return None if not g["div"] or g["sp"] == 0 else ("home" if g["sp"] < 0 else "away")
    if test == "10+ point underdogs":
        return "home" if g["sp"] <= -10 else ("away" if g["sp"] >= 10 else None)
    if test == "prime-time under":
        return "under" if g["hour"] is not None and g["hour"] >= 19 else None
    raise KeyError(test)


TESTS = ("home underdogs", "rest edge >= 3 days", "Thursday home", "divisional underdogs", "10+ point underdogs", "prime-time under")


def cell(seasons, test):
    weeks, seas = {}, {}
    for g in rows(seasons):
        sd = bet(g, test)
        if sd:
            r = side_ret(g, sd)
            if r is not None:
                weeks.setdefault(g["week"], []).append(r); seas.setdefault(g["season"], []).append(r)
    allb = [x for v in weeks.values() for x in v]; x = np.array([np.mean(v) for v in weeks.values()])
    return {"test": test, "bets": len(allb), "weeks": len(weeks), "win_rate": float(np.mean([v > 0 for v in allb])), "return_per_bet": float(np.mean(allb)),
            "t": _t(x), "t_season": _t([np.sum(v) for v in seas.values()]), "weekly": x, "by_season": {s: (len(v), float(np.mean(v))) for s, v in sorted(seas.items())}}


def scan():
    res = []
    for test in TESTS:
        r = cell(DISC, test); r.pop("weekly"); r["carried"] = bool(r["weeks"] > 30 and r["t"] > 1.96 and r["return_per_bet"] > 0 and r["t_season"] > 1.96)
        res.append(r)
        print(f"  {test:22}: bets {r['bets']:4} win {r['win_rate']:.1%} return/bet {r['return_per_bet']:+.2%} t {r['t']:+.2f} (season {r['t_season']:+.2f}){'  CARRIED' if r['carried'] else ''}", flush=True)
    OUT.write_text(json.dumps({"discovery": [1999, 2014], "tests": len(res), "all": res, "carried": [r for r in res if r["carried"]]}, indent=1, default=str) + "\n")
    print(f"{sum(r['carried'] for r in res)} carried of {len(res)}", flush=True)


def validate(tests) -> list[dict]:
    rng = np.random.default_rng(686); out = []
    for test in tests:
        r = cell(VAL, test); x = r.pop("weekly"); n = len(x); m = float(x.mean())
        null = np.array([(x * rng.choice((-1.0, 1.0), n)).mean() for _ in range(2000)]); pct = float((null < m).mean() * 100)
        post0 = m * 0.05 ** 2 / (0.05 ** 2 + x.var(ddof=1) / n)
        r.update(placebo_pct=pct, posterior_zero_prior=post0,
                 decision="CONFIRM" if (r["t"] > 1.645 and pct >= 95 and m > 0 and post0 > 0) else ("WATCHLIST" if m > 0 else "REJECT"))
        out.append(r); print(f"  sealed {test}: bets {r['bets']} win {r['win_rate']:.1%} return/bet {r['return_per_bet']:+.2%} t {r['t']:+.2f} -> {r['decision']}", flush=True)
    (ROOT / "reports" / "s3_validation.json").write_text(json.dumps({"seasons": [2015, 2025], "cells": out}, indent=1, default=str) + "\n")
    return out


if __name__ == "__main__":
    if "--validate" in sys.argv:
        validate([r["test"] for r in json.loads(OUT.read_text())["carried"]])
    else:
        scan()

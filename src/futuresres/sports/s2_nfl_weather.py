"""S-series family 2 - NFL totals and game-day weather (decisions.md 680).

    python -m futuresres.sports.s2_nfl_weather             (discovery: seasons 1999-2014)
    python -m futuresres.sports.s2_nfl_weather --validate  (once, sealed 2015-2025, the carried cells only)
"""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
GAMES = ROOT / "data" / "sports" / "nfl" / "games.csv"
OUT = ROOT / "reports" / "s2_discovery.json"
DISC = range(1999, 2015)
VAL = range(2015, 2026)
WIN, LOSS = 100 / 110, -1.0


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


TESTS = {
    "under, wind >= 10": lambda g: g["out"] and g["wind"] is not None and g["wind"] >= 10,
    "under, wind >= 15": lambda g: g["out"] and g["wind"] is not None and g["wind"] >= 15,
    "under, wind >= 20": lambda g: g["out"] and g["wind"] is not None and g["wind"] >= 20,
    "under, temp <= 25": lambda g: g["out"] and g["temp"] is not None and g["temp"] <= 25,
    "under, temp <= 35": lambda g: g["out"] and g["temp"] is not None and g["temp"] <= 35,
    "over, dome": lambda g: not g["out"],
}


def games(seasons):
    for r in csv.DictReader(open(GAMES)):
        se = int(r["season"]); tl = _f(r["total_line"]); hs, as_ = _f(r["home_score"]), _f(r["away_score"])
        if se not in seasons or tl is None or hs is None or as_ is None:
            continue
        roof = r["roof"]
        yield {"season": se, "week": (se, int(r["week"])), "total": hs + as_, "line": tl, "out": roof in ("outdoors", "open"),
               "wind": _f(r["wind"]), "temp": _f(r["temp"])}


def ret(g, side):
    d = g["total"] - g["line"]
    if d == 0:
        return None
    win = d < 0 if side == "under" else d > 0
    return WIN if win else LOSS


def _t(x) -> float:
    x = np.asarray(x, float)
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 and x.std() > 0 else float("nan")


def cell(seasons, name):
    f = TESTS[name]; side = name.split(",")[0]; weeks = {}; seas = {}
    for g in games(seasons):
        if f(g):
            r = ret(g, side)
            if r is not None:
                weeks.setdefault(g["week"], []).append(r); seas.setdefault(g["season"], []).append(r)
    allb = [r for v in weeks.values() for r in v]; x = np.array([np.mean(v) for v in weeks.values()])
    return {"test": name, "bets": len(allb), "weeks": len(weeks), "win_rate": float(np.mean([r > 0 for r in allb])) if allb else float("nan"),
            "return_per_bet": float(np.mean(allb)) if allb else float("nan"), "t": _t(x), "t_season": _t([np.sum(v) for v in seas.values()])}


def scan():
    res = []
    for name in TESTS:
        r = cell(DISC, name); r["carried"] = bool(r["weeks"] > 30 and r["t"] > 1.96 and r["return_per_bet"] > 0 and r["t_season"] > 1.96); res.append(r)
        print(f"  {name:18}: bets {r['bets']:4} weeks {r['weeks']:3} win {r['win_rate']:.1%} return/bet {r['return_per_bet']:+.2%} t {r['t']:+.2f} "
              f"(by season {r['t_season']:+.2f}){'  CARRIED' if r['carried'] else ''}", flush=True)
    OUT.write_text(json.dumps({"discovery": [DISC.start, DISC.stop - 1], "tests": len(res), "all": res, "carried": [r for r in res if r["carried"]]}, indent=1) + "\n")
    print(f"{sum(r['carried'] for r in res)} carried of {len(res)}", flush=True)


if __name__ == "__main__":
    if "--validate" in sys.argv:
        raise SystemExit("validation runs once, after the discovery result is recorded (decisions.md 680)")
    scan()


TESTS_2B = {
    "under, wind >= 15": TESTS["under, wind >= 15"],
    "over, temp <= 35": lambda g: g["out"] and g["temp"] is not None and g["temp"] <= 35,
    "over, temp <= 25": lambda g: g["out"] and g["temp"] is not None and g["temp"] <= 25,
}


def validate_2b() -> list[dict]:
    """Once, sealed seasons 2015-2025 (decisions.md 682)."""
    rng = np.random.default_rng(682); out = []
    for name, f in TESTS_2B.items():
        side = name.split(",")[0]; weeks = {}; seas = {}
        for g in games(VAL):
            if f(g):
                r = ret(g, side)
                if r is not None:
                    weeks.setdefault(g["week"], []).append(r); seas.setdefault(g["season"], []).append(r)
        x = np.array([np.mean(v) for v in weeks.values()]); allb = [r for v in weeks.values() for r in v]; n = len(x)
        m = float(x.mean()); t = _t(x)
        null = np.array([(x * rng.choice((-1.0, 1.0), n)).mean() for _ in range(2000)]); pct = float((null < m).mean() * 100)
        se2 = x.var(ddof=1) / n; post0 = m * 0.05 ** 2 / (0.05 ** 2 + se2)
        dec = "CONFIRM" if (t > 1.645 and pct >= 95 and m > 0 and post0 > 0) else ("WATCHLIST" if m > 0 else "REJECT")
        r = {"test": name, "bets": len(allb), "weeks": n, "win_rate": float(np.mean([v > 0 for v in allb])), "return_per_bet": float(np.mean(allb)),
             "mean_weekly": m, "t": t, "placebo_pct": pct, "posterior_zero_prior": post0, "decision": dec,
             "by_season": {s: (len(v), round(float(np.mean(v)), 4)) for s, v in sorted(seas.items())}}
        out.append(r)
        print(f"  {name:18}: bets {r['bets']:4} weeks {n:3} win {r['win_rate']:.1%} return/bet {r['return_per_bet']:+.2%} t {t:+.2f} placebo {pct:.0f}% -> {dec}", flush=True)
        print("      " + " ".join(f"{s}:{a[1]:+.0%}/{a[0]}" for s, a in r["by_season"].items()), flush=True)
    (ROOT / "reports" / "s2b_validation.json").write_text(json.dumps({"seasons": [VAL.start, VAL.stop - 1], "cells": out}, indent=1) + "\n")
    return out

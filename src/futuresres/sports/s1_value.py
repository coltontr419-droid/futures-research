"""S-series family 1 - soccer value betting at Bet365 against Pinnacle's de-margined price (decisions.md 676).

    python -m futuresres.sports.s1_value             (discovery: seasons 2012/13 -> 2018/19)
    python -m futuresres.sports.s1_value --validate  (once, sealed 2019/20 -> today, the carried cells only)
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
FD = ROOT / "data" / "sports" / "fd"
OUT = ROOT / "reports" / "s1_discovery.json"
DISC = ("1213", "1314", "1415", "1516", "1617", "1718", "1819")
THETAS = (0.02, 0.04, 0.06)
OUTCOMES = ("H", "D", "A", "any")


def _f(x):
    try:
        v = float(x); return v if v > 1.0 else None
    except (TypeError, ValueError):
        return None


def _date(s: str):
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def matches(seasons=None):
    """(season, league, date, result, b365 (H, D, A), pinnacle pre (H, D, A), pinnacle close (H, D, A) or None)."""
    for f in sorted(FD.glob("*.csv")):
        lg, se = f.stem.split("_")
        if seasons is not None and se not in seasons:
            continue
        raw = f.read_bytes()
        try:
            txt = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            txt = raw.decode("latin-1")
        for r in csv.DictReader(io.StringIO(txt)):
            d = _date(r.get("Date") or ""); res = r.get("FTR")
            b = tuple(_f(r.get(f"B365{k}")) for k in "HDA"); p = tuple(_f(r.get(f"PS{k}")) for k in "HDA")
            pc = tuple(_f(r.get(f"PSC{k}")) for k in "HDA")
            if d is None or res not in ("H", "D", "A") or None in b or None in p:
                continue
            yield se, lg, d, res, b, p, (pc if None not in pc else None)


def bets(seasons):
    """(date, outcome, theta index, return, clv or None) for every bet the rule places."""
    for se, lg, d, res, b, p, pc in matches(seasons):
        inv = [1 / x for x in p]; fair = [x / sum(inv) for x in inv]
        fc = None
        if pc:
            ic = [1 / x for x in pc]; fc = [x / sum(ic) for x in ic]
        for i, k in enumerate("HDA"):
            v = b[i] * fair[i] - 1
            for j, th in enumerate(THETAS):
                if v > th:
                    ret = b[i] - 1 if res == k else -1.0
                    yield d, k, j, ret, (b[i] * fc[i] - 1 if fc else None)


def _t(x) -> float:
    x = np.asarray(x, float)
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 and x.std() > 0 else float("nan")


def stats(days: dict) -> dict:
    ds = sorted(days); x = np.array([np.mean(days[d]) for d in ds]); months = {}
    for d, v in zip(ds, x):
        months.setdefault((d.year, d.month), []).append(v)
    allb = [r for v in days.values() for r in v]
    return {"dates": len(ds), "bets": len(allb), "mean_return_per_bet": float(np.mean(allb)) if allb else float("nan"),
            "mean_daily": float(x.mean()) if len(x) else float("nan"), "t": _t(x), "t_monthly": _t([np.sum(v) for v in months.values()])}


def cells_of(seasons):
    cells = {}
    for d, k, j, ret, clv in bets(seasons):
        for o in (k, "any"):
            cells.setdefault((o, j), {}).setdefault(d, []).append(ret)
    return cells


def scan() -> dict:
    C = cells_of(DISC); res = []
    for o in OUTCOMES:
        for j, th in enumerate(THETAS):
            r = {"outcome": o, "theta": th, **(stats(C[(o, j)]) if (o, j) in C else {"dates": 0})}
            r["carried"] = bool(r["dates"] > 30 and r["t"] > 1.96 and r["mean_daily"] > 0 and r["t_monthly"] > 1.96); res.append(r)
            print(f"  {o:3} theta {th:.0%}: dates {r['dates']:4} bets {r.get('bets', 0):6} return/bet {r.get('mean_return_per_bet', float('nan')):+.2%} "
                  f"t {r.get('t', float('nan')):+5.2f} (monthly {r.get('t_monthly', float('nan')):+5.2f}){'  CARRIED' if r['carried'] else ''}", flush=True)
    carried = sorted([r for r in res if r["carried"]], key=lambda r: -r["t"])[:5]
    OUT.write_text(json.dumps({"discovery": DISC, "tests": len(res), "all": res, "carried": carried}, indent=1) + "\n")
    print(f"{len(carried)} carried of {len(res)}", flush=True)
    return res


if __name__ == "__main__":
    if "--validate" in sys.argv:
        raise SystemExit("validation runs once, after the discovery result is recorded (decisions.md 676)")
    scan()

"""A49 - forward test of the watchlist (decisions.md 133, 582). No trial.

The near misses of families 141-166 that were positive in both sealed years (2025, 2026) with placebo >= 90th, re-evaluated on data
AFTER the sealed window (from 2026-09-01) with each family's own rows() - the exact signal definitions. Targets the research caches no
longer extend (MNQ, MGC London, NKD Tokyo, DAX, MNQ night: owned / HistData files ending 2026-08) are rebuilt from Yahoo 5-minute bars
(~60 days kept by Yahoo: run at least every six weeks; results accumulate in data/cache/forward/targets.json). D708 (owned CME volume) is
left out - its data does not update.

    python -m futuresres.reporting.a49_watchlist [--no-refresh]
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import importlib
import json
import math
import sys
import time
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

import futuresres.reporting.a22_more_markets as a22
import futuresres.reporting.d111_screen as d111

ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / "data" / "cache" / "forward"
TG = CACHE / "targets.json"
OUT = ROOT / "reports" / "a49_watchlist.json"
FWD_START = dt.date(2026, 9, 1)
ET = ZoneInfo("America/New_York")
#: hypothesis -> (module, first id of its family, field naming the predictor)
RULES = {h: m for m, hs in {
    ("d141_mnqwin", 396, "predictor"): ("D400", "D408", "D410", "D411", "D415"),
    ("d142_threeday", 419, "predictor"): ("D424", "D443", "D452"),
    ("d143_composite", 456, "predictor"): ("D466",),
    ("d144_moremkts", 468, "predictor"): ("D489", "D507"),
    ("d146_newseries", 533, "predictor"): ("D536", "D545", "D549", "D553", "D569", "D584"),
    ("d153_asia", 648, "predictor"): ("D652",),
    ("d156_asiafx", 657, "predictor"): ("D659",),
    ("d161_remaining", 684, "predictor"): ("D686",),
    ("d165_ratios", 713, "spread"): ("D714",)}.items() for h in hs}
#: Yahoo 5-minute windows: name -> (symbol, tz, start hh:mm, end hh:mm, starts the previous evening)
WIN = {"MNQ": ("NQ=F", "America/New_York", (9, 30), (16, 0), False), "MGC": ("GC=F", "America/New_York", (3, 0), (11, 30), False),
       "NKD": ("NKD=F", "Asia/Tokyo", (9, 0), (15, 0), False), "DAX": ("^GDAXI", "Europe/Berlin", (9, 0), (17, 30), False),
       "mnq_night": ("NQ=F", "America/New_York", (18, 0), (9, 30), True)}
SYMS = (d111.OC + d111.CC + ("COPX", "EWT", "EWY", "OIH", "XHB", "INDA", "^KS11", "CNY=X", "XLI", "YM=F"))


def _bars5(sym: str) -> list:
    u = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym.replace('^', '%5E').replace('=', '%3D')}?interval=5m&range=60d"
    d = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read())["chart"]["result"][0]
    q = d["indicators"]["quote"][0]
    return [(dt.datetime.fromtimestamp(t, dt.timezone.utc), o, c) for t, o, c in zip(d["timestamp"], q["open"], q["close"]) if o and c]


def window_returns() -> dict:
    """name -> {date: bps}, from Yahoo 5-minute bars; dated as the research targets (NKD: Tokyo date; mnq_night: the morning's date)."""
    out = {}; cache5 = {}
    for name, (sym, tz, (sh, sm), (eh, em), prev) in WIN.items():
        b = cache5.get(sym) or cache5.setdefault(sym, _bars5(sym)); Z = ZoneInfo(tz); r = {}
        days = sorted({t.astimezone(Z).date() for t, _, _ in b})
        for d in days:
            if d.weekday() >= 5:
                continue
            e0 = dt.datetime.combine(d - dt.timedelta(days=(3 if d.weekday() == 0 else 1)) if prev else d, dt.time(sh, sm), Z)
            e1 = dt.datetime.combine(d, dt.time(eh, em), Z)
            if dt.datetime.now(dt.timezone.utc) < e1 + dt.timedelta(minutes=10):
                continue
            w = [(t, o, c) for t, o, c in b if e0 <= t < e1]
            if len(w) < 0.6 * (e1 - e0).total_seconds() / 300 or w[0][0] > e0 + dt.timedelta(minutes=15):
                continue
            r[d.isoformat()] = (w[-1][2] / w[0][1] - 1) * 1e4
        out[name] = r
    return out


def refresh() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    for s in SYMS:
        try:
            a22.fetch(s, "1d")
        except Exception as e:
            print(f"  fetch {s}: {type(e).__name__}", flush=True)
        time.sleep(0.3)
    for f in d111.FRED:
        urllib.request.urlretrieve(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={f}", ROOT / "data" / "cache" / f"fred_{f}.csv")
    old = json.loads(TG.read_text()) if TG.exists() else {}
    new = window_returns()
    for k, v in new.items():
        old.setdefault(k, {}).update(v)
    TG.write_text(json.dumps(old, indent=0))


def patch_targets() -> dict:
    """Extend the stale research targets with the Yahoo window returns from FWD_START (earlier dates are left as they were)."""
    T = {k: {dt.date.fromisoformat(d): v for d, v in x.items()} for k, x in json.loads(TG.read_text()).items()}
    for tg in ("MNQ", "MGC", "NKD", "DAX"):
        base = d111.target(tg)
        base.update({d: v for d, v in T[tg].items() if d >= FWD_START})
    import futuresres.reporting.d141_mnqwin as d141
    d141.target("mnq_night").update({d: v for d, v in T["mnq_night"].items() if d >= FWD_START})
    return T


def overlap_check(T: dict) -> dict:
    """The Yahoo windows against the research targets where both exist (before FWD_START): correlation and sign agreement."""
    import futuresres.reporting.d141_mnqwin as d141
    out = {}
    for tg in ("MNQ", "MGC", "NKD", "DAX", "mnq_night"):
        H = d141.target(tg) if tg == "mnq_night" else d111.target(tg)
        ds = [d for d in T[tg] if d < FWD_START and d in H]
        if len(ds) >= 5:
            a = np.array([T[tg][d] for d in ds]); b = np.array([H[d] for d in ds])
            out[tg] = {"days": len(ds), "corr": float(np.corrcoef(a, b)[0, 1]), "sign_agree": float((np.sign(a) == np.sign(b)).mean())}
    return out


def run(do_refresh: bool = True) -> dict:
    if do_refresh:
        refresh()
    T = patch_targets(); ov = overlap_check(T)
    hi = dt.date.today() - dt.timedelta(days=1); res = {}
    for hid, (mod, first, pname) in sorted(RULES.items()):
        m = importlib.import_module(f"futuresres.reporting.{mod}")
        c = json.loads((ROOT / "reports" / f"{mod.split('_')[0]}_discovery.json").read_text())["carried"][int(hid[1:]) - first]
        cost = m.TARGETS[c["target"]] if hasattr(m, "TARGETS") and c["target"] in m.TARGETS else 0.5
        D, S, Y, _ = m.rows(c[pname], c["h"], c["target"], c["form"], FWD_START, hi, med=c["median_abs"])
        sg = 1.0 if c["dir"] == "follow" else -1.0; net = sg * S * Y - cost if len(Y) else np.array([])
        sealed = json.loads((ROOT / "reports" / f"{hid.lower()}_trial.json").read_text())
        res[hid] = {"cell": sealed["cell"], "sealed_net": sealed["net_bps"], "n": int(len(net)), "net": float(net.mean()) if len(net) else None,
                    "t": float(net.mean() / (net.std(ddof=1) / math.sqrt(len(net)))) if len(net) > 2 and net.std() > 0 else None,
                    "sum": float(net.sum()) if len(net) else 0.0}
    OUT.write_text(json.dumps({"forward_from": str(FWD_START), "through": str(hi), "overlap_check": ov, "rules": res}, indent=1) + "\n")
    print(f"Watchlist forward test, {FWD_START} -> {hi}")
    print("Yahoo windows vs research targets (overlap): " + ", ".join(f"{k} corr {v['corr']:.2f} sign {v['sign_agree']:.0%} ({v['days']}d)" for k, v in ov.items()))
    for hid, x in res.items():
        print(f"  {hid} {x['cell'][:52]:52} sealed {x['sealed_net']:+6.2f} | forward n {x['n']:3} "
              + (f"net {x['net']:+7.2f} t {x['t']:+5.2f}" if x["net"] is not None and x["t"] is not None else "-"), flush=True)
    pos = sum(1 for x in res.values() if x["net"] and x["net"] > 0)
    print(f"{pos} of {len(res)} positive so far (about half expected by chance).")
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--no-refresh", action="store_true")
    run(not ap.parse_args(argv).no_refresh)
    return 0


if __name__ == "__main__":
    sys.exit(main())

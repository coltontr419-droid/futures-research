"""M-family 2 (decisions.md 747): buy NO on still-unsaid mention words tau minutes into the speech.

    python -m futuresres.mention.m6_decay            # discovery only (events before 2026-06-01)
    python -m futuresres.mention.m6_decay validate   # the sealed window, once
"""

from __future__ import annotations

import bisect
import datetime as dt
import glob
import json
import math
import sys
from pathlib import Path

import numpy as np

from futuresres.kalshi.k1_longshot import PRIOR_SD
from futuresres.mention.m1_prize import T, jump

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "data" / "kalshi" / "mention_trades"
SEAL = dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc)
END = dt.datetime(2026, 10, 19, 23, 59, tzinfo=dt.timezone.utc)
TAUS = (15, 30, 45)


def fee(p: float) -> float:
    return math.ceil(7 * p * (1 - p)) / 100


def events():
    for f in sorted(glob.glob(str(SRC / "KXTRUMPMENTION-*.no.json"))):
        ev = Path(f).name[:-len(".no.json")]; yf = SRC / f"{ev}.json"
        if not yf.exists():
            continue
        said = json.loads(yf.read_text())["markets"]; unsaid = json.loads(Path(f).read_text())["markets"]
        js = [j for j in (jump(m["trades"]) for m in said) if j]
        if not js:
            continue
        start = min(T(j["t"]) for j in js)
        mk = [(m, True) for m in said] + [(m, False) for m in unsaid]
        yield ev, start, mk


def run(validate: bool) -> dict:
    per = {tau: {} for tau in TAUS}; cap = {tau: 0.0 for tau in TAUS}; hits = {tau: [] for tau in TAUS}
    for ev, start, mk in events():
        if (validate and not SEAL <= start <= END) or (not validate and start >= SEAL):
            continue
        for tau in TAUS:
            t = start + dt.timedelta(minutes=tau)
            for m, said in mk:
                tr = sorted(m["trades"], key=lambda x: x["created_time"]); ts = [T(x["created_time"]) for x in tr]
                i = bisect.bisect_left(ts, t)
                if i == 0 or any(float(x["yes_price_dollars"]) >= 0.90 for x in tr[:i]):
                    continue                                       # no price yet, or already jumped
                p = float(tr[i - 1]["yes_price_dollars"])
                if not 0.10 <= p <= 0.60:
                    continue
                q = 1 - p + 0.01
                per[tau].setdefault(ev, []).append((0.0 if said else 1.0) - q - fee(q)); hits[tau].append(not said)
                cap[tau] += sum(float(x["count_fp"]) for x in tr[i:bisect.bisect_left(ts, t + dt.timedelta(minutes=10))])
    res = {}
    for tau in TAUS:
        x = np.array([np.mean(v) for v in per[tau].values()]); n = len(x)
        m = float(x.mean()) if n else float("nan"); t_ = float(m / (x.std(ddof=1) / np.sqrt(n))) if n > 2 else float("nan")
        r = {"tau_min": tau, "events": n, "markets": int(sum(len(v) for v in per[tau].values())), "mean_net": m, "t": t_,
             "no_rate": float(np.mean(hits[tau])) if hits[tau] else None, "next_10min_volume": cap[tau]}
        if validate:
            rng = np.random.default_rng(747)
            pct = float((np.array([(x * rng.choice((-1.0, 1.0), n)).mean() for _ in range(2000)]) < m).mean() * 100)
            post0 = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / n)
            r.update(placebo_pct=pct, posterior_zero_prior=post0,
                     decision="CONFIRM" if (t_ > 1.645 and pct >= 95 and m > 0 and post0 > 0) else ("WATCHLIST" if m > 0 else "REJECT"))
        else:
            r["carried"] = bool(t_ > 1.96 and m > 0)
        res[f"tau{tau}"] = r
        print(f"tau {tau:2d} min: events {n}, markets {r['markets']}, mean net {m*100:+.2f}c, t {t_:+.2f}, NO rate {r['no_rate']}, "
              f"next-10-min volume {cap[tau]:,.0f}" + (f" -> {r.get('decision')}" if validate else ("  CARRIED" if r["carried"] else "")), flush=True)
    (ROOT / "reports" / ("m6_validation.json" if validate else "m6_discovery.json")).write_text(json.dumps(res, indent=1) + "\n")
    return res


if __name__ == "__main__":
    run(sys.argv[1:2] == ["validate"])

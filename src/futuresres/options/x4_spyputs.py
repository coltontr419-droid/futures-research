"""X-family 4 (decisions.md 974): monthly SPY put credit spread (-0.30 / -0.15 delta), ~30 days, closed 3 days before expiry.

    python -m futuresres.options.x4_spyputs fetch
    python -m futuresres.options.x4_spyputs [validate]
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

from futuresres.options import smile
from futuresres.options.x1_straddle import COMM, PRIOR_SD, sql
from futuresres.options.x3_cheapvol import form_dates, snaps

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "options" / "x4"
SEAL = "2024-01"


def chain(d: str, ex: str | None = None, lo: float = 0.0, hi: float = 1.0) -> list | None:
    d0 = dt.date.fromisoformat(d)
    w = (f"expiration='{ex}'" if ex else
         f"expiration BETWEEN '{(d0 + dt.timedelta(days=20)).isoformat()}' AND '{(d0 + dt.timedelta(days=45)).isoformat()}'")
    rows = sql(f"SELECT expiration, strike, bid, ask, delta FROM option_chain WHERE date='{d}' AND act_symbol='SPY' AND call_put='Put' "
               f"AND {w} AND ABS(delta) BETWEEN {lo} AND {hi}")
    return None if rows is None else [[r["expiration"], float(r["strike"]), float(r["bid"] or 0), float(r["ask"] or 0), float(r["delta"] or 0)] for r in rows]


def fetch() -> None:
    OUT.mkdir(parents=True, exist_ok=True); f = OUT / "trades.jsonl"; S = snaps()
    done = {json.loads(l)["date"] for l in open(f)} if f.exists() else set()
    with open(f, "a") as fo:
        for d in form_dates():
            if d in done:
                continue
            q = chain(d, lo=0.08, hi=0.45)
            if not q:
                print("  no chain", d); continue
            d0 = dt.date.fromisoformat(d)
            ex = min({r[0] for r in q}, key=lambda e: abs((dt.date.fromisoformat(e) - d0).days - 30))
            P = [r for r in q if r[0] == ex]
            s_, l_ = min(P, key=lambda r: abs(r[4] + 0.30)), min(P, key=lambda r: abs(r[4] + 0.15))
            y, qy = None, None                                   # §975: last snapshot <= expiry - 3 on which the expiry is listed
            for t in sorted((t for t in S if d < t <= (dt.date.fromisoformat(ex) - dt.timedelta(days=3)).isoformat()), reverse=True)[:6]:
                r = chain(t, ex)
                if r:
                    y, qy = t, r; break
            fo.write(json.dumps({"date": d, "ex": ex, "short": s_, "long": l_, "y": y, "qy": qy}) + "\n"); fo.flush()


def spy_close() -> dict:
    r = json.loads((ROOT / "data" / "stocks" / "y_SPY.json").read_text())["chart"]["result"][0]
    return {dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat(): c for t, c in zip(r["timestamp"], r["indicators"]["quote"][0]["close"]) if c}


def evaluate(validate: bool) -> None:
    C = spy_close(); res, skip, nq = [], 0, [0]
    for l in open(OUT / "trades.jsonl"):
        x = json.loads(l)
        if (x["date"][:7] >= SEAL) != validate:
            continue
        sh, lg = x["short"], x["long"]
        if sh[1] <= lg[1] or not x["y"] or x["qy"] is None or sh[2] <= 0:
            skip += 1; continue
        credit = sh[2] - lg[3]; risk = sh[1] - lg[1] - credit + 2 * COMM
        S = C.get(x["y"])
        rows = [(r[1], "P", r[2], r[3], r[4]) for r in x["qy"]]
        def px(k, side):                                         # §976: listed quote, else the IV-smile value, else intrinsic
            v = smile.leg(rows, k, "P", side, x["y"], x["ex"], F=S)
            if v is not None:
                return v
            if not S:
                return float("nan")
            nq[0] += 1; iv = max(k - S, 0.0)
            return iv + (0.01 * S if side == "ask" else 0.0)
        pnl = credit - px(sh[1], "ask") + px(lg[1], "bid") - 4 * COMM
        res.append(pnl / risk if np.isfinite(pnl) else -1.0)
    x = np.array(res); m, t = float(x.mean()), float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
    s = f"X4 {'sealed' if validate else 'discovery'}: months {len(x)} (skipped {skip}), return on risk {m*100:+.2f}%/month, t {t:+.2f}, win {np.mean(x > 0)*100:.0f}%, worst {x.min()*100:+.0f}%, legs at intrinsic {nq[0]}"
    if validate:
        rng = np.random.default_rng(974); pct = float((np.array([(x * rng.choice((-1.0, 1.0), len(x))).mean() for _ in range(4000)]) < m).mean() * 100)
        post = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / len(x))
        s += f", placebo {pct:.0f}th, posterior {post*100:+.2f}% -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 and post > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
    else:
        s += "  CARRIED" if m > 0 and t > 1.96 else "  not carried"
    print(s)


if __name__ == "__main__":
    a = sys.argv[1:2]
    fetch() if a == ["fetch"] else evaluate(a == ["validate"])

"""L-family 18 (decisions.md 990): closed-end fund discount reversion — buy the 10 lowest discount z-scores monthly.

    python -m futuresres.stocks.l18_cef fetch      # candidate list, Yahoo NAV check, price + NAV histories (cached)
    python -m futuresres.stocks.l18_cef [validate]
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "stocks" / "l18"
COST, PRIOR_SD, SEAL, K = 0.004, 0.02, "2022-01", 10
NAME = re.compile(r"fund|trust|income|municipal|opportunit|strategic", re.I)


def yahoo(sym: str) -> dict | None:
    f = OUT / f"{sym}.json"
    if f.exists():
        r = json.loads(f.read_text())
        return r or None
    for k in range(3):
        try:
            r = json.loads(urllib.request.urlopen(urllib.request.Request(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&period1=1325376000&period2=1792800000",
                headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read())["chart"]["result"][0]
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                r = {}; break
            time.sleep(2 + 2 * k); r = None
        except Exception:
            time.sleep(2 + 2 * k); r = None
    time.sleep(0.4)
    if r is None:
        return None
    f.write_text(json.dumps(r)); return r or None


def fetch() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = json.loads((ROOT / "data" / "stocks" / "screener.json").read_text())["data"]["rows"]
    cand = sorted({r["symbol"].strip() for r in rows if NAME.search(r.get("name") or "") and re.fullmatch(r"[A-Z]{2,5}", r["symbol"].strip())})
    print("candidates", len(cand), flush=True); funds = []
    for s in cand:
        n = yahoo(f"X{s}X")
        if n and n.get("meta", {}).get("instrumentType") == "MUTUALFUND" and yahoo(s):
            funds.append(s)
    (OUT / "funds.json").write_text(json.dumps(funds)); print("CEFs with NAV", len(funds))


def series(r: dict, key: str) -> dict:
    try:
        q = r["indicators"]["adjclose"][0]["adjclose"] if key == "adj" else r["indicators"]["quote"][0]["close"]
    except (KeyError, IndexError):
        return {}
    return {dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat(): x for t, x in zip(r["timestamp"], q) if x}


def main(validate: bool) -> None:
    funds = json.loads((OUT / "funds.json").read_text()); P, A, N = {}, {}, {}
    for s in funds:
        p, n = yahoo(s), yahoo(f"X{s}X")
        P[s], A[s], N[s] = series(p, "close"), series(p, "adj"), series(n, "close")
    days = sorted({d for s in funds for d in A[s]})
    me = [days[i] for i in range(len(days) - 1) if days[i][:7] != days[i + 1][:7]]
    res = []
    for d0, d1 in zip(me[:-1], me[1:]):
        if not ("2013-06" <= d1[:7] <= "2026-09") or (d1[:7] >= SEAL) != validate:
            continue
        i0 = days.index(d0); win = days[max(0, i0 - 251):i0 + 1]; z, fwd = {}, {}
        for s in funds:
            if d0 not in A[s] or d1 not in A[s]:
                continue
            D = [P[s][d] / N[s][d] - 1 for d in win if d in P[s] and d in N[s] and N[s][d] > 0]
            if len(D) < 200 or d0 not in N[s] or d0 not in P[s]:
                continue
            sd = float(np.std(D, ddof=1))
            if sd <= 0:
                continue
            z[s] = (D[-1] - float(np.mean(D))) / sd; fwd[s] = A[s][d1] / A[s][d0] - 1
        if len(z) < 50:
            continue
        top = sorted(z, key=z.get)[:K]
        res.append(float(np.mean([fwd[s] for s in top])) - COST - float(np.mean(list(fwd.values()))))
    x = np.array(res); m, t = float(x.mean()), float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
    line = f"L18 {'sealed' if validate else 'discovery'}: funds {len(funds)}, months {len(x)}, excess {m*100:+.2f}%/month, t {t:+.2f}"
    if validate:
        rng = np.random.default_rng(990); pct = float((np.array([(x * rng.choice((-1.0, 1.0), len(x))).mean() for _ in range(4000)]) < m).mean() * 100)
        post = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / len(x))
        line += f", placebo {pct:.0f}th -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 and post > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
    else:
        line += "  CARRIED" if m > 0 and t > 1.96 else "  not carried"
    print(line)


if __name__ == "__main__":
    a = sys.argv[1:2]
    fetch() if a == ["fetch"] else main(a == ["validate"])

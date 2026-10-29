"""S-family 4 (decisions.md §1117): FINRA consolidated off-exchange short-volume ratio (top-500 liquid names, dollar-weighted) as a next-session sign for MNQ.

    python -m futuresres.stocks.s4_shortvol fetch
    python -m futuresres.stocks.s4_shortvol [validate]
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path

import numpy as np
from curl_cffi import requests

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "stocks" / "s4"
URL = "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{}.txt"
SEAL, COST = "2023-01", 0.25 / 20000 * 2


def fetch() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / "rows.json"
    got = json.loads(f.read_text()) if f.exists() else {}
    z = np.load(ROOT / "data" / "stocks" / "long" / "pack.npz"); cal = [str(c) for c in z["cal"]]; syms = list(z["syms"])
    A = z["A"].astype(np.float64); DV = np.nan_to_num(A * z["V"].astype(np.float64))
    ix = {s: k for k, s in enumerate(syms)}
    for i, d in enumerate(cal):
        if d < "2018-08-01" or d in got or i < 60:
            continue
        top = set(np.argsort(DV[:, i - 60:i].mean(axis=1))[::-1][:500])
        r = requests.get(URL.format(d.replace("-", "")), timeout=60)
        if r.status_code != 200:
            continue
        sv = tv = 0.0
        for line in r.text.splitlines()[1:]:
            p = line.split("|")
            k = ix.get(p[1]) if len(p) >= 5 else None
            if k is None or k not in top or not np.isfinite(A[k, i]):
                continue
            sv += float(p[2]) * A[k, i]; tv += float(p[4]) * A[k, i]
        if tv > 0:
            got[d] = sv / tv
        if len(got) % 50 == 0:
            f.write_text(json.dumps(got)); print(d, len(got), flush=True)
        time.sleep(0.2)
    f.write_text(json.dumps(dict(sorted(got.items())))); print("done", len(got))


def main(validate: bool) -> None:
    D = json.loads((OUT / "rows.json").read_text())
    q = json.loads((ROOT / "data" / "stocks" / "y_QQQ.json").read_text())["chart"]["result"][0]
    qd = {dt.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d"): c for t, c in zip(q["timestamp"], q["indicators"]["adjclose"][0]["adjclose"]) if c}
    days = [k for k in sorted(qd) if k in D]; v = np.array([D[k] for k in days])
    x, r, sd, prev = [], [], [], None
    for i in range(60, len(days) - 1):
        d0, d1 = days[i], days[i + 1]
        if (d0[:7] >= SEAL) != validate or d0 < "2018-11":
            continue
        side = 1.0 if v[i] - v[i - 60:i].mean() > 0 else -1.0; ret = qd[d1] / qd[d0] - 1
        x.append((side - 1.0) * ret - (COST if prev is not None and side != prev else 0.0)); r.append(ret); sd.append(side); prev = side
    x = np.array(x); m, t = x.mean(), x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    line = f"S4 {'sealed' if validate else 'discovery'}: sessions {len(x)}, long share {np.mean(np.array(sd) > 0):.0%}, mean x {m*1e4:+.2f} bp/session, t {t:+.2f}"
    if validate:
        rng = np.random.default_rng(1117); sig = np.array(sd) < 0; R = np.array(r); sh = []
        for _ in range(2000):
            s2 = np.roll(sig, rng.integers(1, len(x))); sh.append((np.where(s2, -2.0, 0.0) * R).mean())
        pct = float((np.array(sh) < m).mean() * 100)
        line += f", placebo {pct:.0f}th -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
    print(line)


if __name__ == "__main__":
    if sys.argv[1:] == ["fetch"]:
        fetch()
    else:
        main(sys.argv[1:] == ["validate"])

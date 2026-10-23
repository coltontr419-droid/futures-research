"""U-family 1 (decisions.md 905): Upbit listing notices -> Coinbase 1-minute move a minute later.

    python -m futuresres.xarb.u1_upbit fetch
    python -m futuresres.xarb.u1_upbit              # discovery (notices before 2026-01-01)
    python -m futuresres.xarb.u1_upbit validate     # sealed (from 2026-01-01), once
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

import numpy as np

from futuresres.xarb.x1_snapshot import get
from futuresres.xarb.x3_listings import CB, candles

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "xarb" / "u1"
LISTING = re.compile(r"신규 거래지원 안내|KRW 마켓 디지털 자산 추가")
COST, PRIOR_SD, SEAL = 0.012, 0.02, "2026-01-01"
LAGS, HOLDS = (1, 2, 5), (15, 60, 240)


def notices() -> list[dict]:
    f = OUT / "notices.json"
    if f.exists():
        return json.loads(f.read_text())
    out = []
    for page in range(1, 200):
        for k in range(6):
            try:
                d = get(f"https://api-manager.upbit.com/api/v1/announcements?os=web&page={page}&per_page=20&category=trade"); break
            except Exception:
                time.sleep(10 * (k + 1))
        else:
            break
        n = d["data"]["notices"]
        if not n:
            break
        out += n; time.sleep(1.5)
        if n[-1]["listed_at"] < "2025-01-01":
            break
    f.write_text(json.dumps(out)); return out


def fetch() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cb = {p["base_currency"]: p["id"] for p in get(f"{CB}/products") if p["quote_currency"] == "USD"}
    N = [n for n in notices() if LISTING.search(n["title"]) and n["listed_at"] >= "2025-01-01"]
    seen, rows = set(), []
    for n in sorted(N, key=lambda x: x["listed_at"]):
        m = re.search(r"\(([A-Z0-9]{2,12})\)", n["title"])
        if not m or m.group(1) in seen:
            continue
        tok = m.group(1); seen.add(tok)
        if tok not in cb:
            rows.append({"tok": tok, "t": n["listed_at"], "title": n["title"], "cb": None}); continue
        t0 = dt.datetime.fromisoformat(n["listed_at"]).astimezone(dt.timezone.utc).replace(second=0, microsecond=0)
        c = candles(cb[tok], t0 - dt.timedelta(minutes=2), 60, 250)
        rows.append({"tok": tok, "t": n["listed_at"], "title": n["title"], "cb": cb[tok], "t0": t0.isoformat(), "candles": c})
        time.sleep(0.4)
    (OUT / "events.json").write_text(json.dumps(rows))
    print("listing notices", len(N), "tokens", len(rows), "on Coinbase", sum(r["cb"] is not None for r in rows))


def ret(r: dict, lag: int, hold: int) -> float | None:
    if not r.get("candles"):
        return None
    t0 = dt.datetime.fromisoformat(r["t0"]).timestamp()
    by = {int(c[0]): c[4] for c in r["candles"]}                      # candle start -> close
    def close_at(minute):                                              # close of the candle starting `minute` after the notice minute
        for k in range(0, 5):                                          # tolerate a few empty minutes
            v = by.get(int(t0 + (minute + k) * 60))
            if v:
                return v
        return None
    a, b = close_at(lag), close_at(hold)
    return (b / a - 1 - COST) if a and b else None


def run(validate: bool) -> None:
    R = [r for r in json.loads((OUT / "events.json").read_text()) if r.get("candles") and (r["t"] >= SEAL) == validate]
    print(f"U1 {'sealed' if validate else 'discovery'}: events on Coinbase {len(R)}")
    for lag in LAGS:
        for hold in HOLDS:
            x = np.array([v for v in (ret(r, lag, hold) for r in R) if v is not None])
            if len(x) < 3:
                continue
            m, t = float(x.mean()), float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
            tag = "  <- primary" if (lag, hold) == (1, 60) else ""
            line = f"  entry +{lag}m, exit +{hold}m: n {len(x)}, mean {m*100:+.2f}%, median {np.median(x)*100:+.2f}%, t {t:+.2f}{tag}"
            if validate and (lag, hold) == (1, 60):
                rng = np.random.default_rng(905)
                pct = float((np.array([(x * rng.choice((-1.0, 1.0), len(x))).mean() for _ in range(4000)]) < m).mean() * 100)
                post = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / len(x))
                line += f", placebo {pct:.0f}th, posterior {post*100:+.2f}% -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 and post > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
            elif not validate and (lag, hold) == (1, 60):
                line += "  CARRIED" if (m > 0 and t > 1.96) else "  not carried"
            print(line)


if __name__ == "__main__":
    a = sys.argv[1:2]
    fetch() if a == ["fetch"] else run(a == ["validate"])

"""AI-family 1 (decisions.md 1011): blind Claude reads of post-cutoff earnings releases; next-open long on score >= +1.

    python -m futuresres.stocks.ai1_reads events    # EDGAR submissions -> after-hours Item 2.02 8-Ks for pack symbols; sample 300
    python -m futuresres.stocks.ai1_reads texts     # EX-99.1 text for the sample -> data/ai1/texts/
    python -m futuresres.stocks.ai1_reads score     # (after scores.json is written and hashed) prices and the verdict
"""

from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import random
import re
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "ai1"
UA = {"User-Agent": "futures-research-screen research-bot/1.0 (contact via repo)"}
PRIOR_SD, COST = 0.02, 0.001


def get(u: str, raw: bool = False):
    for k in range(4):
        try:
            time.sleep(0.12)
            b = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60).read()
            return b.decode("utf-8", "ignore") if raw else json.loads(b)
        except Exception:
            time.sleep(1 + 2 * k)
    return None


def events() -> None:
    syms = set(np.load(ROOT / "data" / "stocks" / "long" / "pack.npz")["syms"].tolist())
    tk = get("https://www.sec.gov/files/company_tickers.json"); cik = {v["ticker"]: v["cik_str"] for v in tk.values() if v["ticker"] in syms}
    ev = []
    for i, (s, c) in enumerate(sorted(cik.items())):
        r = get(f"https://data.sec.gov/submissions/CIK{c:010d}.json")
        if not r:
            continue
        f = r["filings"]["recent"]
        for form, acc, items, at, doc in zip(f["form"], f["accessionNumber"], f["items"], f["acceptanceDateTime"], f["primaryDocument"]):
            if form != "8-K" or "2.02" not in items:
                continue
            t = dt.datetime.fromisoformat(at.replace("Z", "+00:00")) - dt.timedelta(hours=4)   # UTC -> ET (EDT through 11-01)
            if not ("2026-07-01" <= t.date().isoformat() <= "2026-10-16"):
                continue
            hm = t.hour * 60 + t.minute
            if 570 <= hm < 960:
                continue                                         # accepted during regular hours: excluded
            ev.append({"sym": s, "cik": c, "acc": acc, "accepted_et": t.isoformat(), "after_close": hm >= 960})
    random.Random(1011).shuffle(ev); json.dump(ev, open(OUT / "events_all.json", "w")); json.dump(ev[:300], open(OUT / "sample.json", "w"))
    print("after-hours Item 2.02 events", len(ev), "sample", min(300, len(ev)))


def text_of(htm: str) -> str:
    t = re.sub(r"(?is)<(script|style).*?</\1>", " ", htm); t = re.sub(r"(?s)<[^>]+>", " ", t); t = html.unescape(t)
    return re.sub(r"\s+", " ", t).strip()


def texts() -> None:
    (OUT / "texts").mkdir(exist_ok=True)
    for e in json.load(open(OUT / "sample.json")):
        f = OUT / "texts" / f"{e['acc']}.txt"
        if f.exists():
            continue
        a = e["acc"].replace("-", ""); idx = get(f"https://www.sec.gov/Archives/edgar/data/{e['cik']}/{a}/index.json")
        if not idx:
            continue
        docs = [d["name"] for d in idx["directory"]["item"]]
        ex = next((d for d in docs if re.search(r"ex[-_]?99[-_.]?0?1|ex991|exhibit991|ex99\.htm", d, re.I)), None) or \
             next((d for d in docs if re.search(r"99", d) and d.lower().endswith((".htm", ".html", ".txt"))), None)
        if not ex:                                               # fallback: the largest .htm that is not the 8-K itself or an index/XBRL file
            items = [d for d in idx["directory"]["item"] if d["name"].lower().endswith((".htm", ".html")) and "index" not in d["name"].lower()
                     and not re.search(r"8-?k|form8", d["name"], re.I) and not d["name"].lower().startswith("r")]
            ex = max(items, key=lambda d: int(d.get("size") or 0))["name"] if items else None
        if not ex:
            continue
        h = get(f"https://www.sec.gov/Archives/edgar/data/{e['cik']}/{a}/{ex}", raw=True)
        if h:
            f.write_text(text_of(h)[:12000])
    print("texts", len(list((OUT / "texts").glob("*.txt"))))


def score() -> None:
    S = json.load(open(OUT / "scores.json")); hfile = OUT / "scores.sha256"
    h = hashlib.sha256(open(OUT / "scores.json", "rb").read()).hexdigest()
    assert hfile.exists() and hfile.read_text().strip() == h, "scores.json changed after hashing (or never hashed)"
    z = np.load(ROOT / "data" / "stocks" / "long" / "pack.npz"); cal = list(z["cal"]); sx = {s: i for i, s in enumerate(z["syms"])}
    O, A = z["O"].astype(np.float64), z["A"].astype(np.float64)
    y = json.loads((ROOT / "data" / "stocks" / "y_SPY.json").read_text())["chart"]["result"][0]; q = y["indicators"]["quote"][0]
    spy = {dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat(): (o, c) for t, o, c in zip(y["timestamp"], q["open"], q["close"]) if o and c}
    import bisect
    rows = []
    for e in json.load(open(OUT / "sample.json")):
        if e["acc"] not in S:
            continue
        d = e["accepted_et"][:10]; i = bisect.bisect_right(cal, d) if e["after_close"] else bisect.bisect_left(cal, d)
        j = sx[e["sym"]]
        if i >= len(cal) or not (np.isfinite(O[j, i]) and np.isfinite(A[j, i])) or O[j, i] <= 0:
            continue
        # adjusted open/close of the same session: the open->close return is unaffected by the adjustment factor
        if cal[i] not in spy:
            continue
        r = A[j, i] / O[j, i] - 1; m = spy[cal[i]][1] / spy[cal[i]][0] - 1
        rows.append((S[e["acc"]], r - m - COST, cal[i]))
    sc = np.array([r[0] for r in rows]); x = np.array([r[1] for r in rows])
    from scipy.stats import spearmanr
    rho = spearmanr(sc, x + COST).correlation
    L = x[sc >= 1]; m_, t = float(L.mean()), float(L.mean() / (L.std(ddof=1) / np.sqrt(len(L))))
    rng = np.random.default_rng(1011); pct = float((np.array([(L * rng.choice((-1.0, 1.0), len(L))).mean() for _ in range(4000)]) < m_).mean() * 100)
    post = m_ * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + L.var(ddof=1) / len(L))
    print(f"AI1: scored {len(x)}, longs {len(L)}, mean excess {m_*100:+.2f}%/trade, t {t:+.2f}, placebo {pct:.0f}th, posterior {post*100:+.2f}% -> "
          + ("CONFIRM" if t > 1.645 and pct >= 95 and m_ > 0 and post > 0 else ("WATCHLIST" if m_ > 0 else "REJECT")) + f"; Spearman(all) {rho:+.3f}")
    for k in (-2, -1, 0, 1, 2):
        v = x[sc == k]
        if len(v):
            print(f"  score {k:+d}: n {len(v):3}, mean {v.mean()*100:+.2f}%")


if __name__ == "__main__":
    {"events": events, "texts": texts, "score": score}[sys.argv[1]]()

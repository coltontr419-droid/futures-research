"""E-family 1 (decisions.md 752): the earnings press release for each Kalshi earnings-mention event — EDGAR acceptance time (to the
second) and the release text (8-K item 2.02 / 6-K exhibit 99.x), filed within the 36 h before the market's close.

    python -m futuresres.earnings.e1_edgar
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EV = ROOT / "data" / "kalshi" / "earnings"
OUT = ROOT / "data" / "edgar"
UA = {"User-Agent": "futures-research earnings-screen research@example.org"}


def get(url: str, cache: bool = True) -> str:
    f = OUT / "http" / re.sub(r"[^A-Za-z0-9._-]", "_", url)[-180:]
    if cache and f.exists():
        return f.read_text()
    time.sleep(0.15)
    t = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read().decode("utf-8", "replace")
    f.parent.mkdir(parents=True, exist_ok=True); f.write_text(t)
    return t


def text(raw: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style).*?</\1>", " ", raw))))


def ticker_of(series: str) -> str:
    return re.sub(r"^KX(EARNINGSMENTION|EARNIGNSMENTION|MENTIONEARN)", "", series)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    tick = {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in json.loads(get("https://www.sec.gov/files/company_tickers.json")).values()}
    res = {}; miss = []
    for f in sorted(EV.glob("*.json")):
        e = json.loads(f.read_text()); tk = ticker_of(e["series"]).upper()
        closes = sorted(m["close"] for m in e["markets"] if m.get("close"))
        if not closes:
            continue
        close = dt.datetime.fromisoformat(closes[0].replace("Z", "+00:00"))
        cik = tick.get(tk) or tick.get(tk.replace(".", "-"))
        if not cik:
            miss.append((e["event"], tk, "no CIK")); continue
        sub = json.loads(get(f"https://data.sec.gov/submissions/CIK{cik}.json"))
        r = sub["filings"]["recent"]; best = None
        for form, acc, adsh, items, prim in zip(r["form"], r["acceptanceDateTime"], r["accessionNumber"], r.get("items", [""] * len(r["form"])), r["primaryDocument"]):
            if form not in ("8-K", "6-K"):
                continue
            t = dt.datetime.fromisoformat(acc.replace("Z", "+00:00"))
            if not close - dt.timedelta(hours=36) <= t <= close:
                continue
            if form == "8-K" and "2.02" not in (items or ""):
                continue
            if best is None or t > best[0]:
                best = (t, adsh, prim, form)
        if not best:
            miss.append((e["event"], tk, "no filing in window")); continue
        t, adsh, prim, form = best
        base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{adsh.replace('-', '')}/"
        idx = json.loads(get(base + "index.json"))["directory"]["item"]
        docs = [i["name"] for i in idx if re.search(r"(ex|exh|exhibit)[-_]?99", i["name"], re.I) and i["name"].lower().endswith((".htm", ".html", ".txt"))]
        if not docs and form == "6-K":
            docs = [prim]
        if not docs:
            miss.append((e["event"], tk, "no exhibit 99")); continue
        body = " ".join(text(get(base + d)) for d in docs[:3])
        res[e["event"]] = {"ticker": tk, "accepted": t.isoformat(), "close": close.isoformat(), "form": form, "adsh": adsh, "docs": docs[:3],
                           "chars": len(body)}
        (OUT / f"{e['event']}.txt").write_text(body)
    (OUT / "releases.json").write_text(json.dumps({"matched": res, "missing": miss}, indent=1))
    print(f"events matched to a release {len(res)}; unmatched {len(miss)}")
    for x in miss[:15]:
        print("   ", x)
    return 0


if __name__ == "__main__":
    sys.exit(main())

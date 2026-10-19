"""T-family 1 (decisions.md 731): odd-lot tender offers from EDGAR, 2024-01 -> 2026-10. A measurement of the stream.

    python -m futuresres.tender.t1_oddlot
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
CACHE = ROOT / "data" / "tender"
UA = {"User-Agent": "futures-research tender-screen research@example.org"}
START, END = "2024-01-01", "2026-10-18"


def get(url: str, cache: bool = True) -> str:
    f = CACHE / "http" / re.sub(r"[^A-Za-z0-9._-]", "_", url)[-180:]
    if cache and f.exists():
        return f.read_text()
    time.sleep(0.15)
    t = urllib.request.urlopen(urllib.request.Request(url, headers=UA if "sec.gov" in url else {"User-Agent": "Mozilla/5.0"}), timeout=60).read().decode("utf-8", "replace")
    f.parent.mkdir(parents=True, exist_ok=True); f.write_text(t)
    return t


def text(raw: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw)))


def candidates() -> dict:
    """{cik: (ticker, name)} for listed issuers with an 'odd lot' SC TO-I document."""
    out = {}
    for frm in range(0, 1000, 100):
        d = json.loads(get(f"https://efts.sec.gov/LATEST/search-index?q=%22odd%20lot%22&forms=SC%20TO-I&dateRange=custom&startdt={START}&enddt={END}&from={frm}"))
        for x in d["hits"]["hits"]:
            s = x["_source"]; m = re.search(r"\(([A-Z][A-Z0-9.\-]*)[,)]", s["display_names"][0])
            if m and "CIK" not in m.group(1):
                out[s["ciks"][0]] = (m.group(1), s["display_names"][0].split("  (")[0])
        if len(d["hits"]["hits"]) < 100:
            return out
    return out


def filings(cik: str) -> list[tuple[str, str, str]]:
    d = json.loads(get(f"https://data.sec.gov/submissions/CIK{cik}.json"))
    r = d["filings"]["recent"]
    return [(f, dd, a) for f, dd, a in zip(r["form"], r["filingDate"], r["accessionNumber"]) if f in ("SC TO-I", "SC TO-I/A") and START <= dd <= END]


def docs(cik: str, adsh: str) -> str:
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{adsh.replace('-', '')}/"
    idx = json.loads(get(base + "index.json"))["directory"]["item"]
    hs = [i["name"] for i in idx if i["name"].lower().endswith((".htm", ".html", ".txt")) and "index" not in i["name"].lower()]
    return " ".join(text(get(base + h)) for h in hs[:8])


MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"


def terms(t: str) -> dict:
    o = {"type": "buyback"}
    if re.search(r"net asset value", t, re.I) and re.search(r"\d{2}(?:\.\d+)?% of (?:the )?(?:Fund'?s? )?(?:net asset value|NAV)", t, re.I):
        o["type"] = "nav"
    elif re.search(r"exchange offer", t, re.I):
        o["type"] = "exchange"
    m = re.search(r"not (?:greater|more) than \$([\d,.]+) (?:nor|and not|or) less than \$([\d,.]+)", t, re.I) or \
        re.search(r"not less than \$([\d,.]+) (?:nor|and not|or) (?:greater|more) than \$([\d,.]+)", t, re.I)
    if m:
        a, b = sorted(float(x.replace(",", "")) for x in m.groups()); o.update(kind="dutch", lo=a, hi=b)
    else:
        m = re.search(r"(?:purchase price|price) of (?:US)?\$([\d,]+\.\d+|[\d,]+) per (?:share|common share)", t, re.I)
        if m:
            o.update(kind="fixed", price=float(m.group(1).replace(",", "")))
    m = re.search(rf"EXPIRE[S]? AT [^.]{{0,80}}?(?:ON )?(?:\w+DAY, )?((?:{MONTHS}) \d{{1,2}}, \d{{4}})", t, re.I)
    if m:
        o["expiry"] = dt.datetime.strptime(m.group(1).title(), "%B %d, %Y").date().isoformat()
    o["odd_lot_excluded"] = bool(re.search(r"odd lot[^.]{0,160}(?:same proration|subject to proration|will be subject to the same)", t, re.I)
                                 or re.search(r"no(?:t| preferential) (?:provide for )?preferential treatment", t, re.I))
    o["odd_lot_priority"] = bool(re.search(r"odd lot", t, re.I)) and not o["odd_lot_excluded"]
    return o


def final_price(t: str):
    for pat in (r"(?:accepted for (?:purchase|payment)|purchased?|repurchased?|take up and pay for)[^.]{0,160}?(?:at|for) (?:a (?:final )?(?:purchase )?price of )?(?:US)?\$([\d,]+\.\d+) per (?:share|common share)",
                r"final (?:purchase )?price of (?:US)?\$([\d,]+\.\d+)", r"purchase price (?:was|of|is) (?:US)?\$([\d,]+\.\d+) per"):
        ms = re.findall(pat, t, re.I)
        if ms and re.search(r"final|expired", t, re.I):
            return float(ms[-1].replace(",", ""))
    return None


def closes(tick: str) -> dict:
    y = tick.replace(".", "-")
    d = json.loads(get(f"https://query1.finance.yahoo.com/v8/finance/chart/{y}?period1=1700000000&period2=1792500000&interval=1d"))["chart"]["result"]
    if not d:
        return {}
    r = d[0]; ts = r.get("timestamp") or []; c = r["indicators"]["quote"][0]["close"]
    return {dt.datetime.utcfromtimestamp(a).date(): b for a, b in zip(ts, c) if b is not None}


def next_close(cl: dict, day: dt.date):
    ks = sorted(k for k in cl if k > day)
    return (ks[0], cl[ks[0]]) if ks else (None, None)


def main() -> int:
    C = candidates(); rows = []
    print("listed issuers", len(C), flush=True)
    for cik, (tick, name) in sorted(C.items(), key=lambda kv: kv[1][0]):
        fs = sorted(filings(cik), key=lambda x: x[1])
        origs = [f for f in fs if f[0] == "SC TO-I"]
        try:
            cl = closes(tick)
        except Exception as e:
            cl = {}
        for k, (_, day, adsh) in enumerate(origs):
            nxt = origs[k + 1][1] if k + 1 < len(origs) else "9999"
            try:
                o = terms(docs(cik, adsh))
            except Exception as e:
                print("  fail", tick, day, e); continue
            amends = [f for f in fs if f[0] == "SC TO-I/A" and day < f[1] < nxt]
            fp = None
            for _, aday, aadsh in reversed(amends):
                try:
                    fp = final_price(docs(cik, aadsh))
                except Exception:
                    fp = None
                if fp:
                    break
            d0 = dt.date.fromisoformat(day); bday, buy = next_close(cl, d0)
            r = dict(ticker=tick, name=name[:40], filed=day, **o, final=fp, buy_day=str(bday) if bday else None, buy=buy, amendments=len(amends))
            if buy and fp and r["odd_lot_priority"]:
                r["pnl_99"] = round(99 * (fp - buy) - 2, 2)
            rows.append(r)
            print(f"{tick:6} {day} {o.get('type'):8} {o.get('kind','?'):5} price {o.get('price', (o.get('lo'), o.get('hi')))} exp {o.get('expiry')} "
                  f"oddlot {o['odd_lot_priority']} final {fp} buy {buy if buy is None else round(buy,2)} pnl {r.get('pnl_99')}", flush=True)
    (ROOT / "reports" / "t1_oddlot.json").write_text(json.dumps(rows, indent=1, default=str) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

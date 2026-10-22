"""V-family 1 (decisions.md 840): reverse-split round-up arbitrage — measured from EDGAR filings and Yahoo daily prices.

    python -m futuresres.stocks.v1_revsplit hits       # EDGAR full-text hits (cached)
    python -m futuresres.stocks.v1_revsplit docs       # fetch + classify each company's documents (cached)
    python -m futuresres.stocks.v1_revsplit prices     # Yahoo splits/prices per ticker (cached)
    python -m futuresres.stocks.v1_revsplit            # readout
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import re
import statistics as st
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DIR = ROOT / "data" / "stocks" / "v1"
SEC_UA = {"User-Agent": "futures-research-screen research-bot/1.0"}
WEB_UA = {"User-Agent": "Mozilla/5.0"}
START, END = "2025-10-01", "2026-10-21"


def fetch(u: str, ua: dict, tries: int = 4) -> bytes:
    for k in range(tries):
        try:
            time.sleep(0.25)
            return urllib.request.urlopen(urllib.request.Request(u, headers=ua), timeout=60).read()
        except Exception:
            time.sleep(2 ** k)
    raise RuntimeError(u)


def hits() -> list[dict]:
    f = DIR / "hits.json"
    if f.exists():
        return json.loads(f.read_text())
    DIR.mkdir(parents=True, exist_ok=True); out = {}
    for phrase in ('"rounded up"', '"round up"', '"round-up"'):
        q = urllib.parse.quote(f'"reverse stock split" {phrase}'); frm = 0
        while True:
            d = json.loads(fetch(f"https://efts.sec.gov/LATEST/search-index?q={q}&forms=8-K,6-K&dateRange=custom&startdt={START}&enddt={END}&from={frm}", SEC_UA))
            hs = d["hits"]["hits"]
            for h in hs:
                s = h["_source"]; out[h["_id"]] = {"id": h["_id"], "cik": s["ciks"][0], "name": s["display_names"][0], "date": s["file_date"], "adsh": s["adsh"]}
            frm += len(hs)
            if not hs or frm >= d["hits"]["total"]["value"] or frm >= 10_000:
                break
        print(phrase, "hits so far", len(out), flush=True)
    f.write_text(json.dumps(list(out.values()))); return list(out.values())


def classify(text: str) -> str:
    t = re.sub(r"\s+", " ", text.lower())
    if re.search(r"round[- ]lot", t) and "100 shares" in t:
        return "roundlot"
    if "participant level" in t or "participant-level" in t:
        return "participant"
    if re.search(r"(rounded|round) up", t):
        return "holder"
    return "other"


def docs() -> dict:
    f = DIR / "docs.json"; D = json.loads(f.read_text()) if f.exists() else {}
    H = hits()
    for i, h in enumerate(H):
        if h["id"] in D:
            continue
        adsh, fn = h["id"].split(":"); u = f"https://www.sec.gov/Archives/edgar/data/{int(h['cik'])}/{adsh.replace('-', '')}/{fn}"
        try:
            txt = re.sub(r"<[^>]+>", " ", fetch(u, SEC_UA).decode("utf-8", "replace"))
            D[h["id"]] = {**h, "cls": classify(txt), "ratio_txt": (re.findall(r"(?:1|one)[- ]for[- ](\w+)", txt.lower()) or [None])[0]}
        except Exception as e:
            D[h["id"]] = {**h, "cls": "error", "err": repr(e)[:80]}
        if i % 50 == 0:
            f.write_text(json.dumps(D)); print(f"  docs {i}/{len(H)}", flush=True)
    f.write_text(json.dumps(D)); return D


def ticker(name: str) -> str | None:
    m = re.search(r"\(([A-Z0-9.\-]+)(?:,|\))", name)
    return m.group(1) if m else None


def prices() -> dict:
    f = DIR / "prices.json"; P = json.loads(f.read_text()) if f.exists() else {}
    tick = sorted({ticker(d["name"]) for d in docs().values() if d.get("cls") in ("holder", "roundlot", "participant") and ticker(d["name"])})
    for i, t in enumerate(tick):
        if t in P:
            continue
        try:
            d = json.loads(fetch(f"https://query1.finance.yahoo.com/v8/finance/chart/{t}?interval=1d&period1=1735689600&period2=1792800000&events=split", WEB_UA))
            r = d["chart"]["result"][0]
            P[t] = {"ts": r["timestamp"], "close": r["indicators"]["quote"][0]["close"], "splits": list((r.get("events") or {}).get("splits", {}).values())}
        except Exception as e:
            P[t] = {"err": repr(e)[:80]}
        if i % 25 == 0:
            f.write_text(json.dumps(P)); print(f"  prices {i}/{len(tick)}", flush=True)
    f.write_text(json.dumps(P)); return P


def events() -> list[dict]:
    """One row per (ticker, reverse split in the window): class from that company's filings within 120 days before the split."""
    D = docs(); P = prices(); byt = collections.defaultdict(list)
    for d in D.values():
        t = ticker(d["name"])
        if t:
            byt[t].append(d)
    out = []
    for t, ds in byt.items():
        p = P.get(t) or {}
        if "ts" not in p:
            continue
        days = [dt.datetime.fromtimestamp(x, dt.timezone.utc).date() for x in p["ts"]]
        for sp in p["splits"]:
            num, den = float(sp["numerator"]), float(sp["denominator"])
            if den <= num:
                continue                                                          # forward split
            eff = dt.datetime.fromtimestamp(sp["date"], dt.timezone.utc).date()
            if not START <= eff.isoformat() <= END:
                continue
            rel = [d for d in ds if 0 <= (eff - dt.date.fromisoformat(d["date"])).days <= 120 or 0 <= (dt.date.fromisoformat(d["date"]) - eff).days <= 5]
            cls = {d["cls"] for d in rel}
            c = "participant" if "participant" in cls else ("roundlot" if "roundlot" in cls else ("holder" if "holder" in cls else "unmatched"))
            # Yahoo is not consistent about split adjustment: infer it from the jump across THIS split; skip if another split is near
            if any(s_ is not sp and abs((dt.datetime.fromtimestamp(s_["date"], dt.timezone.utc).date() - eff).days) <= 60 for s_ in p["splits"]):
                out.append({"ticker": t, "eff": eff.isoformat(), "ratio": den / num, "cls": c, "skip": "other split within 60 days"}); continue
            pre = max((i for i, d in enumerate(days) if d < eff), default=None); post = [i for i, d in enumerate(days) if d >= eff]
            if pre is None or len(post) < 11 or None in (p["close"][pre], p["close"][post[0]], p["close"][post[10]]):
                continue
            N = den / num; cp, c0, c10 = p["close"][pre], p["close"][post[0]], p["close"][post[10]]; r = c0 / cp
            if 1 / 3 <= r <= 3:                                                   # adjusted series: also undo every LATER split's scaling
                k = 1.0
                for s_ in p["splits"]:
                    if dt.datetime.fromtimestamp(s_["date"], dt.timezone.utc).date() > eff:
                        k *= float(s_["denominator"]) / float(s_["numerator"])
                pre_raw = cp / N / k; c0, c10 = c0 / k, c10 / k
            elif N / 3 <= r <= 3 * N:
                pre_raw = cp                                                      # raw series
            else:
                out.append({"ticker": t, "eff": eff.isoformat(), "ratio": N, "cls": c, "skip": "ambiguous jump"}); continue
            out.append({"ticker": t, "eff": eff.isoformat(), "ratio": N, "cls": c, "pre_raw": pre_raw, "post0": c0, "post10_raw": c10})
    return out


def readout() -> None:
    E = events(); print("reverse splits in window with a classified filing:", collections.Counter(e["cls"] for e in E), "| skipped:", collections.Counter(e.get("skip") for e in E if e.get("skip")))
    rows = []
    for e in E:
        if e.get("skip"):
            continue
        sh = {"holder": 1, "roundlot": 100}.get(e["cls"], 0)
        e["profit"] = sh * e["post10_raw"] - e["pre_raw"] if sh else 0.0; rows.append(e)
    for half, lo, hi in (("10-2025 → 03-2026", "2025-10-01", "2026-03-31"), ("04-2026 → 10-2026", "2026-04-01", "2026-10-21")):
        q = [e for e in rows if lo <= e["eff"] <= hi and e["cls"] in ("holder", "roundlot")]; months = 6.0 if half.startswith("10") else 6.7
        tot = sum(e["profit"] for e in q)
        print(f"{half}: qualifying {len(q)} ({sum(e['cls'] == 'roundlot' for e in q)} round-lot), per account ${tot:,.0f} = ${tot / months:,.0f}/month "
              f"→ 10 accounts ${10 * tot / months:,.0f}, 20 accounts ${20 * tot / months:,.0f}/month; median per event ${st.median([e['profit'] for e in q]) if q else 0:,.2f}")
    for e in sorted(rows, key=lambda e: -e["profit"])[:25]:
        print(f"  {e['ticker']:6} {e['eff']} 1-for-{e['ratio']:.0f} {e['cls']:11} pre ${e['pre_raw']:.3f} post+10 ${e['post10_raw']:.2f} profit ${e['profit']:,.2f}")
    (ROOT / "reports" / "v1_revsplit.json").write_text(json.dumps(rows, indent=0, default=str))


if __name__ == "__main__":
    a = sys.argv[1:2]
    {"hits": hits, "docs": docs, "prices": prices}.get(a[0] if a else "", readout)()

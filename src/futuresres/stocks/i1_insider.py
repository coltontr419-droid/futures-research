"""I-family 1 (decisions.md 913): open-market insider purchases (Form 4, code P, officers/directors) -> drift over 5 / 20 sessions.

    python -m futuresres.stocks.i1_insider            # discovery (filings 2025-06-02 -> 2025-12-31)
    python -m futuresres.stocks.i1_insider validate   # sealed (2026), once
"""

from __future__ import annotations

import collections
import csv
import datetime as dt
import io
import json
import sys
import zipfile
from pathlib import Path

import numpy as np

from futuresres.stocks.e2_pead import H2, OUT as E2OUT


def bars() -> dict:
    """symbol -> (dates, open, close, volume) from H2's cached Yahoo daily bars; '__SPY' from E2's cache."""
    B = {}
    for l in open(H2):
        x = json.loads(l)
        if x.get("err") or not x.get("t"):
            continue
        B[x["sym"]] = ([dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat() for t in x["t"]], x["o"], x["c"], x["v"])
    s = json.loads((E2OUT / "spy.json").read_text())["chart"]["result"][0]; q = s["indicators"]["quote"][0]
    B["__SPY"] = ([dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat() for t in s["timestamp"]], q["open"], q["close"], q["volume"])
    return B

ROOT = Path(__file__).resolve().parents[3]
DIR = ROOT / "data" / "stocks" / "i1"
COST, PRIOR_SD, SEAL, START = 0.003, 0.02, "2026-01-01", "2025-06-02"
PRIMARY_B = "--b" in sys.argv          # decisions.md 914: I-family 1b primary (≥ $500k, 20 sessions)


def rows(z: zipfile.ZipFile, name: str):
    with z.open(name) as f:
        yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"), delimiter="\t")


def events() -> list[dict]:
    buys = collections.defaultdict(float); sym_date = {}
    for zp in sorted(DIR.glob("*.zip")):
        z = zipfile.ZipFile(zp)
        sub = {r["ACCESSION_NUMBER"]: r for r in rows(z, "SUBMISSION.tsv") if r["DOCUMENT_TYPE"] in ("4", "4/A")}
        insider = {r["ACCESSION_NUMBER"] for r in rows(z, "REPORTINGOWNER.tsv")
                   if any(k in (r["RPTOWNER_RELATIONSHIP"] or "") for k in ("Director", "Officer"))}
        for r in rows(z, "NONDERIV_TRANS.tsv"):
            a = r["ACCESSION_NUMBER"]
            if r["TRANS_CODE"] != "P" or a not in sub or a not in insider:
                continue
            try:
                v = float(r["TRANS_SHARES"] or 0) * float(r["TRANS_PRICEPERSHARE"] or 0)
            except ValueError:
                continue
            s = sub[a]; sym = (s["ISSUERTRADINGSYMBOL"] or "").strip().upper()
            try:
                fd = dt.datetime.strptime(s["FILING_DATE"], "%d-%b-%Y").date().isoformat()
            except ValueError:
                continue
            if sym and sym != "NONE":
                buys[(sym, fd)] += v
    out, last = [], {}
    for (sym, fd), v in sorted(buys.items(), key=lambda x: x[0][1]):
        if v < 100_000 or fd < START:
            continue
        if sym in last and (dt.date.fromisoformat(fd) - dt.date.fromisoformat(last[sym])).days < 30:
            continue
        last[sym] = fd; out.append({"sym": sym, "date": fd, "usd": v})
    return out


def run(validate: bool) -> None:
    B = bars(); sd, so, sc, _ = B["__SPY"]; si = {d: i for i, d in enumerate(sd)}; res = collections.defaultdict(list)
    E = [e for e in events() if (e["date"] >= SEAL) == validate]
    for e in E:
        b = B.get(e["sym"])
        if not b:
            continue
        ds, o, c, vol = b
        i0 = next((i for i, d in enumerate(ds) if d > e["date"]), None)       # first session after the filing date
        if i0 is None or i0 < 21:
            continue
        dv = [c[j] * vol[j] for j in range(i0 - 20, i0) if c[j] and vol[j]]
        if not dv or c[i0 - 1] is None or c[i0 - 1] < 1.0 or float(np.median(dv)) < 500_000:
            continue
        for h in (5, 20):
            x = i0 + h - 1
            if x >= len(ds) or not o[i0] or not c[x]:
                continue
            raw = c[x] / o[i0] - 1 - COST; a, zz = si.get(ds[i0]), si.get(ds[x])
            if a is None or zz is None:
                continue
            adj = raw - (sc[zz] / so[a] - 1)
            for tag, ok in (("≥$100k", True), ("≥$500k", e["usd"] >= 500_000)):
                if ok:
                    res[(tag, h)].append((e["date"], raw, adj))
    print(f"I1 {'sealed' if validate else 'discovery'}: events {len(E)}")
    for (tag, h), v in sorted(res.items()):
        by = collections.defaultdict(list)
        for d, raw, adj in v:
            by[d].append(adj)
        a = np.array([x[2] for x in v]); rw = np.array([x[1] for x in v]); dm = np.array([np.mean(x) for x in by.values()])
        if len(dm) < 3:
            continue
        t = float(dm.mean() / (dm.std(ddof=1) / np.sqrt(len(dm)))); m = float(a.mean())
        line = f"  {tag} hold {h:2}d: n {len(a):4} raw {rw.mean()*100:+.2f}% adj {m*100:+.2f}% (median {np.median(a)*100:+.2f}%) t {t:+.2f}"
        if (tag, h) == (("≥$500k", 20) if PRIMARY_B else ("≥$100k", 5)):
            if validate:
                rng = np.random.default_rng(914 if PRIMARY_B else 913); pct = float((np.array([(a * rng.choice((-1.0, 1.0), len(a))).mean() for _ in range(4000)]) < m).mean() * 100)
                post = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + a.var(ddof=1) / len(a))
                line += f" placebo {pct:.0f}th -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 and post > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
            else:
                line += "  CARRIED" if (m > 0 and t > 1.96 and rw.mean() > 0) else "  not carried"
        print(line)


if __name__ == "__main__":
    run(sys.argv[1:2] == ["validate"])

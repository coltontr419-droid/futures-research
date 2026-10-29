"""S-family 5 (decisions.md §1118): aggregate insider buy share (officers/directors, open-market P vs S, by filing date) as a weekly sign for MNQ.

    python -m futuresres.stocks.s5_insideragg fetch      # SEC quarterly zips -> daily counts in data/stocks/s5/counts.json (zips deleted after use)
    python -m futuresres.stocks.s5_insideragg [validate]
"""

from __future__ import annotations

import collections
import csv
import datetime as dt
import io
import json
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
from curl_cffi import requests

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "stocks" / "s5"
URL = "https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{}_form345.zip"
UA = {"User-Agent": "futures-research noreply@example.invalid"}
SEAL, COST = "2023-01", 0.25 / 20000 * 2


def rows(z: zipfile.ZipFile, name: str):
    with z.open(name) as f:
        yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"), delimiter="\t")


def fetch() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cf = OUT / "counts.json"
    C = json.loads(cf.read_text()) if cf.exists() else {"done": [], "P": {}, "S": {}}
    today = dt.date.today()
    for y in range(2006, today.year + 1):
        for qn in range(1, 5):
            q = f"{y}q{qn}"
            if q in C["done"] or dt.date(y, 3 * qn - 2, 1) > today:
                continue
            zp = OUT / f"{q}.zip"
            r = requests.get(URL.format(q), headers=UA, timeout=300)
            if r.status_code != 200:
                print(q, r.status_code, flush=True); continue
            zp.write_bytes(r.content); del r
            z = zipfile.ZipFile(zp)
            sub = {}
            for s in rows(z, "SUBMISSION.tsv"):
                if s["DOCUMENT_TYPE"] in ("4", "4/A"):
                    try:
                        sub[s["ACCESSION_NUMBER"]] = dt.datetime.strptime(s["FILING_DATE"], "%d-%b-%Y").date().isoformat()
                    except ValueError:
                        pass
            ins = {r["ACCESSION_NUMBER"] for r in rows(z, "REPORTINGOWNER.tsv")
                   if any(k in (r["RPTOWNER_RELATIONSHIP"] or "") for k in ("Director", "Officer"))}
            seen = set()
            for r in rows(z, "NONDERIV_TRANS.tsv"):
                a, c = r["ACCESSION_NUMBER"], r["TRANS_CODE"]
                if c not in ("P", "S") or a not in sub or a not in ins or (a, c) in seen:
                    continue
                seen.add((a, c)); C[c][sub[a]] = C[c].get(sub[a], 0) + 1
            z.close(); zp.unlink(); C["done"].append(q)
            cf.write_text(json.dumps(C)); print(q, len(seen), flush=True)
            time.sleep(1)


def main(validate: bool) -> None:
    C = json.loads((OUT / "counts.json").read_text())
    q = json.loads((ROOT / "data" / "stocks" / "y_QQQ.json").read_text())["chart"]["result"][0]
    qd = {dt.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d"): c for t, c in zip(q["timestamp"], q["indicators"]["adjclose"][0]["adjclose"]) if c}
    days = sorted(qd)
    P = np.array([C["P"].get(d, 0) for d in days], float); S = np.array([C["S"].get(d, 0) for d in days], float)
    fri = [i for i in range(20, len(days) - 1) if dt.date.fromisoformat(days[i]).weekday() == 4 or
           dt.date.fromisoformat(days[i + 1]).isocalendar()[1] != dt.date.fromisoformat(days[i]).isocalendar()[1]]
    b = {i: P[i - 19:i + 1].sum() / max(P[i - 19:i + 1].sum() + S[i - 19:i + 1].sum(), 1) for i in fri}
    x, r, sd, prev = [], [], [], None
    for k in range(52, len(fri) - 1):
        i, j = fri[k], fri[k + 1]; d0 = days[i]
        if (d0[:7] >= SEAL) != validate or d0 < "2007-06":
            continue
        zz = b[i] - np.mean([b[fri[m]] for m in range(k - 52, k)])
        side = 1.0 if zz > 0 else -1.0; ret = qd[days[j]] / qd[d0] - 1
        x.append((side - 1.0) * ret - (COST if prev is not None and side != prev else 0.0)); r.append(ret); sd.append(side); prev = side
    x = np.array(x); m, t = x.mean(), x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    line = f"S5 {'sealed' if validate else 'discovery'}: weeks {len(x)}, long share {np.mean(np.array(sd) > 0):.0%}, mean x {m*100:+.3f}%/week, t {t:+.2f}"
    if validate:
        rng = np.random.default_rng(1118); sig = np.array(sd) < 0; R = np.array(r); sh = []
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

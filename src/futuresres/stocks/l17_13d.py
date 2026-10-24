"""L-family 17 (decisions.md 985): buy the open after an original Schedule 13D, hold 20 sessions — activists (a) and all filers (b).

    python -m futuresres.stocks.l17_13d fetch     # EDGAR full-text search, weekly windows (cached)
    python -m futuresres.stocks.l17_13d [validate]
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "stocks" / "l17"
UA = {"User-Agent": "futures-research-screen research-bot/1.0"}
COST, PRIOR_SD, SEAL, HOLD = 0.003, 0.02, "2023-01", 20
ACTIVISTS = ["elliott", "starboard", "icahn", "trian", "third point", "valueact", "jana", "pershing square", "engaged capital",
             "land & buildings", "ancora", "legion partners", "corvex", "sachem head", "mantle ridge", "politan", "irenic", "engine capital",
             "barington", "blackwells", "cevian", "impactive", "inclusive capital", "glenview", "voss capital", "driver management",
             "anson funds", "sarissa", "d. e. shaw", "carronade", "oasis management", "saba capital", "bulldog", "marcato", "lone star value",
             "harbert discovery", "kanen", "22nw", "ortelius", "stilwell", "macellum", "land and buildings"]


def get(u: str):
    for k in range(5):
        try:
            time.sleep(0.15)
            r = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60).read())
            if "hits" in r:
                return r
        except Exception:
            pass
        time.sleep(2 ** k)
    return None


def fetch() -> None:
    OUT.mkdir(parents=True, exist_ok=True); f = OUT / "filings.jsonl"
    done = {json.loads(l)["week"] for l in open(f)} if f.exists() else set()
    d = dt.date(2015, 1, 26)
    with open(f, "a") as fo:
        while d <= dt.date(2026, 10, 1):
            a, b = d.isoformat(), (d + dt.timedelta(days=6)).isoformat(); d += dt.timedelta(days=7)
            if a in done:
                continue
            rows, frm, ok = [], 0, True
            while True:
                r = get(f"https://efts.sec.gov/LATEST/search-index?forms=SC%2013D,SCHEDULE%2013D&dateRange=custom&startdt={a}&enddt={b}&from={frm}")
                if r is None:
                    ok = False; break
                hs = r["hits"]["hits"]
                rows += [{"form": h["_source"]["form"], "date": h["_source"]["file_date"], "names": h["_source"]["display_names"]} for h in hs]
                frm += len(hs)
                if not hs or frm >= r["hits"]["total"]["value"] or frm >= 9900:
                    break
            if ok:
                fo.write(json.dumps({"week": a, "rows": rows}) + "\n"); fo.flush()


def events() -> list[dict]:
    ev, last = [], {}
    rows = [r for l in open(OUT / "filings.jsonl") for r in json.loads(l)["rows"] if r["form"] in ("SC 13D", "SCHEDULE 13D")]
    for r in sorted(rows, key=lambda r: r["date"]):
        subj = next((n for n in r["names"] if re.search(r"\(([A-Z][A-Z0-9.\-]{0,6})(?:,|\))", n)), None)
        if subj is None:
            continue
        tk = re.search(r"\(([A-Z][A-Z0-9.\-]{0,6})(?:,|\))", subj).group(1)
        filers = " ".join(n.lower() for n in r["names"] if n is not subj)
        if tk in last and (dt.date.fromisoformat(r["date"]) - dt.date.fromisoformat(last[tk])).days < 365:
            continue
        last[tk] = r["date"]
        ev.append({"tk": tk, "date": r["date"], "act": any(a in filers for a in ACTIVISTS), "filers": filers[:120]})
    return ev


def main(validate: bool) -> None:
    z = np.load(ROOT / "data" / "stocks" / "long" / "pack.npz"); cal = list(z["cal"]); sx = {s: i for i, s in enumerate(z["syms"])}
    A = z["A"].astype(np.float64); O = z["O"].astype(np.float64); res = {"a": collections.defaultdict(list), "b": collections.defaultdict(list)}
    import bisect
    for e in events():
        j = sx.get(e["tk"]); i = bisect.bisect_right(cal, e["date"])          # first session after the filing date
        if j is None or i + HOLD >= len(cal) or (cal[i][:7] >= SEAL) != validate or cal[i] < "2015-02":
            continue
        o, c = O[j, i], A[j, i + HOLD]
        if not (np.isfinite(o) and np.isfinite(c)) or o <= 0:
            continue
        with np.errstate(all="ignore"):
            u = float(np.nanmean(A[:, i + HOLD] / O[:, i] - 1))
        x = c / o - 1 - COST - u; m = cal[i][:7]
        res["b"][m].append(x)
        if e["act"]:
            res["a"][m].append(x)
    print(f"L17 {'sealed' if validate else 'discovery'}")
    for k, name in (("a", "L17a activists"), ("b", "L17b all filers")):
        x = np.array([np.mean(v) for _, v in sorted(res[k].items())]); n = sum(map(len, res[k].values()))
        if len(x) < 6:
            print(f"  {name}: months {len(x)}"); continue
        m, t = float(x.mean()), float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
        s = f"  {name}: events {n}, months {len(x)}, excess {m*100:+.2f}%/event-month, t {t:+.2f}"
        if validate:
            rng = np.random.default_rng(985 + (k == "b")); pct = float((np.array([(x * rng.choice((-1.0, 1.0), len(x))).mean() for _ in range(4000)]) < m).mean() * 100)
            post = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / len(x))
            s += f", placebo {pct:.0f}th -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 and post > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
        else:
            s += "  CARRIED" if m > 0 and t > 1.96 else "  not carried"
        print(s)


if __name__ == "__main__":
    a = sys.argv[1:2]
    fetch() if a == ["fetch"] else main(a == ["validate"])

"""H-family 7 (decisions.md 916): S&P 400 / 600 additions — buy after the announcement, sell at the close before the effective date.

    python -m futuresres.stocks.h7_additions [validate]
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import re
import sys
import time
import urllib.parse
import urllib.request

import numpy as np

UA = {"User-Agent": "Mozilla/5.0"}
COST, PRIOR_SD, SEAL = 0.002, 0.02, "2025-01-01"
PAGES = {"S&P 400": "List_of_S%26P_400_companies", "S&P 600": "List_of_S%26P_600_companies"}


def get(u: str) -> bytes:
    for k in range(4):
        try:
            time.sleep(0.4)
            return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60).read()
        except Exception:
            time.sleep(2 ** k)
    raise RuntimeError(u)


def additions() -> list[dict]:
    out = []
    for idx, page in PAGES.items():
        w = json.loads(get(f"https://en.wikipedia.org/w/api.php?action=parse&page={page}&prop=wikitext&format=json"))["parse"]["wikitext"]["*"]
        named = dict(re.findall(r'<ref name="([^"]+)">\{\{cite web[^}]*?\|date=([A-Za-z]+ \d{1,2}, \d{4})', w))
        s = w[re.search(r"announced changes", w).start():]
        for row in s.split("\n|-")[1:]:
            cells = [c.strip() for c in re.split(r"\|\||\n\|", row) if c.strip()]
            if len(cells) < 4:
                continue
            try:
                eff = dt.datetime.strptime(re.sub(r"\[\[|\]\]", "", cells[0]).strip("| "), "%B %d, %Y").date()
            except ValueError:
                continue
            sym = re.sub(r"[\[\]{}|]", "", cells[1]).strip().split(" ")[0] if len(cells) > 1 else ""
            m = re.search(r"\|date=([A-Za-z]+ \d{1,2}, \d{4})", row) or None
            ann = m.group(1) if m else None
            if not ann:
                n = re.search(r'<ref name="([^"]+)"\s*/>', row)
                ann = named.get(n.group(1)) if n else None
            if not ann or not sym or re.search(r"spun|spin", row, re.I):
                continue
            try:
                a = dt.datetime.strptime(ann, "%B %d, %Y").date()
            except ValueError:
                continue
            if dt.date(2023, 1, 1) <= eff <= dt.date(2026, 10, 20) and a <= eff:
                out.append({"index": idx, "sym": sym.replace(".", "-"), "ann": a.isoformat(), "eff": eff.isoformat()})
    return out


def run(validate: bool) -> None:
    A = [a for a in additions() if (a["ann"] >= SEAL) == validate]; rows = []
    for a in A:
        p1 = int(dt.datetime.fromisoformat(a["ann"]).replace(tzinfo=dt.timezone.utc).timestamp()) - 5 * 86400
        p2 = int(dt.datetime.fromisoformat(a["eff"]).replace(tzinfo=dt.timezone.utc).timestamp()) + 5 * 86400
        try:
            r = json.loads(get(f"https://query1.finance.yahoo.com/v8/finance/chart/{a['sym']}?interval=1d&period1={p1}&period2={p2}"))["chart"]["result"][0]
        except Exception:
            continue
        d = [dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat() for t in r["timestamp"]]; q = r["indicators"]["quote"][0]
        i0 = next((i for i, x in enumerate(d) if x > a["ann"]), None); i1 = max((i for i, x in enumerate(d) if x < a["eff"]), default=None)
        if i0 is None or i1 is None or i1 < i0 or not q["open"][i0] or not q["close"][i1]:
            continue
        rows.append((a["ann"], q["close"][i1] / q["open"][i0] - 1 - COST, a))
    by = collections.defaultdict(list)
    for d, r, _ in rows:
        by[d].append(r)
    x = np.array([r for _, r, _ in rows]); dm = np.array([np.mean(v) for v in by.values()])
    print(f"H7 {'sealed' if validate else 'discovery'}: additions {len(A)}, priced {len(x)}, announcement days {len(dm)}")
    if len(dm) < 3:
        return
    m, t = float(x.mean()), float(dm.mean() / (dm.std(ddof=1) / np.sqrt(len(dm))))
    line = f"  buy after announcement -> sell before effective: mean {m*100:+.2f}%, median {np.median(x)*100:+.2f}%, t {t:+.2f}"
    if validate:
        rng = np.random.default_rng(916); pct = float((np.array([(x * rng.choice((-1.0, 1.0), len(x))).mean() for _ in range(4000)]) < m).mean() * 100)
        post = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / len(x))
        line += f", placebo {pct:.0f}th -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 and post > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
    else:
        line += "  CARRIED" if m > 0 and t > 1.96 else "  not carried"
    print(line)
    for idx in PAGES:
        v = [r for _, r, a in rows if a["index"] == idx]
        if v:
            print(f"    {idx}: n {len(v)}, mean {np.mean(v)*100:+.2f}%")


if __name__ == "__main__":
    run(sys.argv[1:2] == ["validate"])

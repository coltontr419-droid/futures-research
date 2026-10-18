"""F0 screen (no prices): ForecastEx's daily high (Weather Underground table, inferred from settlements) against Kalshi's (NWS climate report).

    python -m futuresres.forecastex.f0_settle
"""

from __future__ import annotations

import collections
import csv
import datetime as dt
import glob
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CITY = {"UHLAX": "KXHIGHLAX", "UHMDW": "KXHIGHCHI", "UHAUS": "KXHIGHAUS", "UHMIA": "KXHIGHMIA", "UHPHL": "KXHIGHPHIL"}


def fx_settlements() -> dict:
    """{(product, date): {strike: 1/0}} from each contract's row on its expiry date."""
    out = collections.defaultdict(dict)
    for f in glob.glob(str(ROOT / "data/forecastex/prices/*.csv")):
        for r in csv.DictReader(open(f)):
            p, ds, k = r["event_contract"].split("_")
            if p not in CITY or r["subtype"] != "YES" or r["date"] != r["expiration_date"][:10]:
                continue
            s = float(r["settlement_price"] or "nan")
            if s in (0.0, 1.0):
                out[(p, dt.datetime.strptime(ds, "%m%d%y").date())][float(k)] = int(s)
    return out


def kalshi_high(series: str, d: dt.date):
    f = ROOT / "data/kalshi" / series / f"{series}-{d.strftime('%y%b%d').upper()}.json"
    if not f.exists():
        return None
    for m in json.load(open(f))["markets"]:
        try:
            return float(m.get("expiration_value"))
        except (TypeError, ValueError):
            continue
    return None


def main() -> int:
    st = fx_settlements(); rows = collections.defaultdict(list)
    for (p, d), ks in sorted(st.items()):
        yes = [k for k, v in ks.items() if v == 1]; no = [k for k, v in ks.items() if v == 0]
        if not yes or not no or max(yes) >= min(no):
            continue
        lo, hi = max(yes), min(no)                         # WU high in (lo, hi] if YES means "exceeds"
        nws = kalshi_high(CITY[p], d)
        if nws is None:
            continue
        rows[p].append((d, lo, hi, nws))
    for p, xs in rows.items():
        below = sum(n > hi for _, lo, hi, n in xs); above = sum(n <= lo for _, lo, hi, n in xs); inside = len(xs) - below - above
        gaps = collections.Counter(int(n - hi) if n > hi else (int(n - lo) - 1 if n <= lo else 0) for _, lo, hi, n in xs)
        print(f"{p} vs {CITY[p]}: {len(xs)} days | NWS above WU bracket {below} ({below/len(xs):.0%}) | consistent {inside} | NWS below {above}"
              f" | NWS-minus-WU (deg F, 0 = consistent): {dict(sorted(gaps.items()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

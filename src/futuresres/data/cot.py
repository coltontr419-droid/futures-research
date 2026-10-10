"""CFTC Commitments of Traders, legacy futures-only report (free; data/cot/deacot{YEAR}.zip from
https://www.cftc.gov/files/dea/history/, gitignored). decisions.md 117.

Positions are as of Tuesday and published the following Friday after 15:30 ET. Columns used: open interest (All),
commercial long and short (All). Codes: gold 088691 (COMEX), crude oil WTI 067651 (NYMEX).
"""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
COT_DIR = ROOT / "data" / "cot"
CODES = {"GC": "088691", "CL": "067651"}


def commercial_flow(root: str, years=range(2010, 2027)):
    """(tuesdays, Q): Q_t = (commercial net long_t - net long_{t-1}) / open interest_{t-1} (Kang, Rouwenhorst & Tang 2020)."""
    code = CODES[root]
    rows = set()
    for y in years:
        f = COT_DIR / f"deacot{y}.zip"
        if not f.exists():
            continue
        z = zipfile.ZipFile(f)
        rd = csv.reader(io.TextIOWrapper(z.open(z.namelist()[0]), encoding="latin-1"))
        next(rd)
        for x in rd:
            if x[3].strip() == code:
                rows.add((np.datetime64(x[2].strip()), float(x[7]), float(x[11]) - float(x[12])))
    rows = sorted(rows)
    d = np.array([r[0] for r in rows]); oi = np.array([r[1] for r in rows]); net = np.array([r[2] for r in rows])
    q = np.r_[np.nan, np.diff(net) / oi[:-1]]
    return d, q


def next_week_direction(tuesdays, q, sessions):
    """+1/-1 for each session dated in the week after a report's Friday release (Tuesday+6 .. Tuesday+10 days):
    the sign of that report's Q (Q = 0 -> +1); nan if no report covers it."""
    out = np.full(len(sessions), np.nan)
    for i, t in enumerate(sessions):
        k = np.searchsorted(tuesdays, t - np.timedelta64(6, "D"), side="right") - 1
        if k >= 1 and t - tuesdays[k] <= np.timedelta64(10, "D") and np.isfinite(q[k]):
            out[i] = 1.0 if q[k] >= 0 else -1.0
    return out

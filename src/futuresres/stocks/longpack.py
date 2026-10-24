"""Pack the long daily history into float32 matrices (decisions.md 942-943) — streamed, low memory.

    python -m futuresres.stocks.longpack      -> data/stocks/long/pack.npz (cal, syms, A adj close, O adj open, V dollar volume)
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
LONG = ROOT / "data" / "stocks" / "long"


def main() -> None:
    cal, syms = set(), []
    for l in open(LONG / "daily.jsonl"):                     # pass 1: calendar + symbols (timestamps only)
        x = json.loads(l); syms.append(x["sym"]); cal.update(x["t"])
    days = sorted({dt.datetime.fromtimestamp(t, dt.timezone.utc).date() for t in cal}); di = {d: i for i, d in enumerate(days)}
    A = np.full((len(syms), len(days)), np.nan, np.float32); O = A.copy(); V = A.copy()
    for j, l in enumerate(open(LONG / "daily.jsonl")):     # pass 2: fill
        x = json.loads(l)
        for t, o, c, a, v in zip(x["t"], x["o"], x["c"], x["a"], x["v"]):
            if a and c and o:
                i = di[dt.datetime.fromtimestamp(t, dt.timezone.utc).date()]; f = a / c
                A[j, i] = a; O[j, i] = o * f; V[j, i] = (v or 0) * c
    np.savez_compressed(LONG / "pack.npz", cal=np.array([d.isoformat() for d in days]), syms=np.array(syms), A=A, O=O, V=V)
    print("packed", A.shape)


if __name__ == "__main__":
    main()

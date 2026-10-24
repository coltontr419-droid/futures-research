"""K-calendar 7 (decisions.md 1004): mid-month (15th) Treasury coupon reinvestment in TLT and IEF.

    python -m futuresres.stocks.k_coupon [validate]
"""

from __future__ import annotations

import sys

from futuresres.stocks.k_flows import COST, ser, verdict


def main(validate: bool) -> None:
    sel = lambda d: (d[:7] >= "2016-01") == validate
    print(f"K7 {'sealed' if validate else 'discovery'}")
    for k, s in enumerate(("TLT", "IEF")):
        d, a = ser(s); drift = lambda n: (a[-1] / a[0]) ** (n / len(a)) - 1; out = []
        months = sorted({x[:7] for x in d})
        for m in months:
            mid = m + "-15"
            after = next((i for i, x in enumerate(d) if x >= mid), None)          # first session on/after the 15th
            if after is None or d[after][:7] != m:
                continue
            exit_ = after if d[after] == mid else after
            entry = exit_ - 3 if d[after] == mid else after - 3                    # >= 2 sessions before the 15th
            if entry < 0 or not sel(d[exit_]) or d[exit_] > "2026-10-31":
                continue
            out.append(a[exit_] / a[entry] - 1 - COST - drift(exit_ - entry))
        verdict(f"K7 {s} coupon", out, validate, 10040 + k)


if __name__ == "__main__":
    main(sys.argv[1:2] == ["validate"])

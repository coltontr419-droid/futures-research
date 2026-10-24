"""K-calendar 8 (decisions.md 1018): month-end extension in EDV, ZROZ, MBB, TIP, MUB, HYG, EMB (K5's rule).

    python -m futuresres.stocks.k_bondme [validate]
"""

from __future__ import annotations

import sys

from futuresres.stocks.k_flows import ser, verdict

SYMS = {"EDV": 0.0002, "ZROZ": 0.0002, "MBB": 0.0002, "TIP": 0.0002, "MUB": 0.0002, "HYG": 0.0005, "EMB": 0.0005}


def main(validate: bool) -> None:
    print(f"K8 {'sealed' if validate else 'discovery'}")
    for k, (s, cost) in enumerate(SYMS.items()):
        d, a = ser(s); drift = lambda n: (a[-1] / a[0]) ** (n / len(a)) - 1
        x = [a[i] / a[i - 4] - 1 - cost - drift(4) for i in range(5, len(d) - 1)
             if d[i][:7] != d[i + 1][:7] and ((d[i][:7] >= "2016-01") == validate) and d[i] <= "2026-09-30"]
        verdict(f"K8 {s}", x, validate, 10180 + k)


if __name__ == "__main__":
    main(sys.argv[1:2] == ["validate"])

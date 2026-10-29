"""A139: the Fast Track 100K MNQ day slot with the D68 side on ZN-shock days (follow the previous session's 10-year-note shock), else long. No trial (overlay of a
confirmed rule, §209-210). Minute engine a123 (worst order in a bar), take $800 / stop $4,000, 7 MNQ, drift removed, per 84 sessions.

    PYTHONPATH=src python scripts/a139_d68_overlay.py
"""
import datetime as dt

import numpy as np

import futuresres.reporting.a08_gold as a8
import futuresres.reporting.d10_universe as d10
import futuresres.reporting.d24_shock as d24
import futuresres.reporting.a123_fast_track_policy as p
from futuresres.reporting.a122_fast_track_minute import TERMS
from futuresres.reporting.a124_fast_track_sizes import SIZES

S = d10.series(); sh = d24.shocks(S, "ZN")
import futuresres.reporting.d3_relay as d3  # noqa: E402  (prev_weekday, as d24)
T = dict(TERMS, **SIZES["100K"])
for era in ("pre", "post"):
    h, l, c, d = a8.era_paths(era, "MNQ", "rth_0930_1600")
    side = np.ones(len(c))
    for i, day in enumerate(d):
        day = day if isinstance(day, dt.date) else dt.date.fromisoformat(str(day)[:10])
        q = sh.get(d3.prev_weekday(day))
        if q is not None and q[1]:
            side[i] = np.sign(q[0])   # ZN up = yields down; D68 "follow": ES moves with the ZN shock
    H = [h[i] if side[i] > 0 else -l[i] for i in range(len(c))]; L = [l[i] if side[i] > 0 else -h[i] for i in range(len(c))]
    C = [c[i] if side[i] > 0 else -c[i] for i in range(len(c))]
    base = p.simulate(h, l, c, 800.0, 4000.0, 0, None, T); ov = p.simulate(H, L, C, 800.0, 4000.0, 0, None, T)
    print(f"{era}: sessions {len(c)}, shock days {(side != 1).sum() + 0} short / {int(sum(1 for i in range(len(c)) if side[i] > 0 and sh.get(d3.prev_weekday(d[i] if isinstance(d[i], dt.date) else dt.date.fromisoformat(str(d[i])[:10])), (0, False))[1]))} long-on-shock;"
          f" always long {base[0]:+,.0f} ({base[1]:.2f}/payout), D68 overlay {ov[0]:+,.0f} ({ov[1]:.2f}/payout) per 84")

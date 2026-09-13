"""Q-series S2 magnitude filter: a predicted bps range for every candidate, against the cost floor
and against the BH bar at its expected n. ESTIMATES, NOT MEASUREMENTS. NO TRIALS.

What is measured and what is not, kept apart on purpose:

    MEASURED (reports/q_series_s1.json)   window SDs, session and event counts by era, the
                                          typical size of the Q02 conditioner
    MEASURED (reports/p03_stage1.json)    P03's reversal fraction, the only data-derived prior
    ESTIMATED                             every predicted bps range, with its provenance

THE SE IS COMPUTED FOR THE STATISTIC EACH CANDIDATE TESTS, not adjusted from an anchor. §57
recorded what happens otherwise. Four of the five predictable candidates are comparisons -
firing nights against non-firing nights, event days against the rest - and take a
difference-of-two-means SE, sd * sqrt(1/n1 + 1/n2). Q02 is a signed fade on every session and
takes a single-mean SE. No sqrt(2) factor appears anywhere.

THE POST-2021 BAR DECIDES. Q10 makes the era split a standing requirement and says a candidate
that works only pre-2021 is dead, so the verdict column is read at post-2021 n. The full-sample
bar is shown beside it because the NQ lineage mostly enlarges the era Q10 discounts.

DESIGN EFFECT: bracketed at 1.14-2.19, the two measured families closest to one event per
session (§45). The candidates' own DEFF depends on the outcome and is not measured here.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Final

from scipy.stats import norm

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
S1: Final[Path] = ROOT / "reports" / "q_series_s1.json"
P03: Final[Path] = ROOT / "reports" / "p03_stage1.json"
OUT: Final[Path] = ROOT / "reports" / "q_series_s2.json"

COST_BPS: Final[float] = 0.48          # MNQ round trip, CLAUDE_FUTURES.md; spread is an ESTIMATE
DEFF: Final[tuple[float, float]] = (1.14, 2.19)
FOMC_PER_YEAR: Final[int] = 8          # scheduled meetings; no calendar is on disk


def z(k: int) -> float:
    return float(norm.ppf(1 - (0.05 / k) / 2))


def diff_bar(sd: float, n1: float, n2: float, k: int, deff: float) -> float:
    return z(k) * sd * math.sqrt(deff / n1 + deff / n2)


def mean_bar(sd: float, n: float, k: int, deff: float) -> float:
    return z(k) * sd * math.sqrt(deff / n)


def verdict(lo: float, hi: float, bar_lo: float, bar_hi: float) -> tuple[str, str]:
    cost = ("above cost" if lo > COST_BPS else
            "below cost" if hi < COST_BPS else "at cost at the low end")
    bar = ("CLEARS" if lo > bar_hi else "BELOW" if hi < bar_lo else "STRADDLES")
    return cost, bar


def main() -> int:
    s1 = json.loads(S1.read_text())
    p03 = json.loads(P03.read_text())
    sd = s1["window_sd"]
    rows = []

    # ---- Q01 --------------------------------------------------------------------------------
    c = s1["q01_counts"]
    s = sd["Q01 01:45-03:15"]
    rows.append({
        "id": "Q01", "stat": "firing nights - other nights (difference)", "k": 1,
        "predicted_post": (0.0, 3.0), "predicted_pre": (1.0, 4.0),
        "provenance": ("3.6%/yr for the 02:00-03:00 window over 1998-2019 and ~0 since 2021, both as "
                       "CITED in F13 and the Q draft, not verified here; the size of the post-selloff "
                       "amplification is stated in neither and is ESTIMATED at up to ~2x. F02's "
                       "post-2021 +3.27 bps is deliberately NOT used: it is a prior look at this data."),
        "sd_post": s["sd_post"], "sd_full": s["sd"],
        "n_post": (c["fires_post"], c["nonfires_post"]),
        "n_full": (c["fires_pre"] + c["fires_post"], c["nonfires_pre"] + c["nonfires_post"]),
        "kind": "diff", "cost_note": "overnight spread UNMEASURED, likely above the RTH estimate",
    })

    # ---- Q02: two compliant windows ------------------------------------------------------------
    frac = p03["result"]["diff_bps"] / 9.18
    move = s1["median_abs_last30_bps"]["post_2021"]
    for label, win in (("Q02 16:00-16:59", "Q02 16:00-16:59"), ("Q02 16:00-16:14", "Q02 16:00-16:14")):
        s = sd[win]
        rows.append({
            "id": label, "stat": "signed fade, every session (single mean)", "k": 1,
            "predicted_post": (0.0, 0.068 * move), "predicted_pre": (0.0, 0.068 * move),
            "provenance": (f"P03's MEASURED reversal fraction ({frac:.2%} of excess at 15 min, a "
                           f"different condition on this series) up to P03's own 6.8% bar, times the "
                           f"MEASURED median last-30m move of {move:.1f} bps. Central estimate "
                           f"{frac * move:.2f} bps."),
            "sd_post": s["sd_post"], "sd_full": s["sd"],
            "n_post": (s["n_post"],), "n_full": (s["n"],), "kind": "mean",
            "cost_note": ("16:00-16:59 is continuous only from mid-2021 (16:15-16:30 halt before)"
                          if "59" in label else "the only window consistent across all eras"),
        })

    # ---- Q03, the 17:00-compliant truncation -----------------------------------------------------
    s = sd["Q03 09:30-14:00"]
    yrs_post = s["n_post"] / 252
    yrs_full = s["n"] / 252
    ev_post, ev_full = FOMC_PER_YEAR * yrs_post, FOMC_PER_YEAR * yrs_full
    rows.append({
        "id": "Q03", "stat": "FOMC-day 09:30-14:00 - other days (difference)", "k": 1,
        "predicted_post": (0.0, 25.0), "predicted_pre": (5.0, 30.0),
        "provenance": ("49 bps over the 24h before announcements (Lucca & Moench 2015 as CITED in "
                       "F12, not verified); the share falling inside 09:30-14:00 is documented "
                       "nowhere on disk and is ESTIMATED at up to ~half; post-2015 disappearance is "
                       "reported by one line of work, as recorded in F12. SD is the UNCONDITIONAL "
                       "window SD, which understates FOMC days and therefore the bar."),
        "sd_post": s["sd_post"], "sd_full": s["sd"],
        "n_post": (ev_post, s["n_post"] - ev_post), "n_full": (ev_full, s["n"] - ev_full),
        "kind": "diff", "cost_note": "no FOMC calendar on disk; counts are 8 x years",
    })

    # ---- Q05 ---------------------------------------------------------------------------------------
    m = s1["q05_months"]
    s = sd["Q05 18:00 to 16:00"]
    tom_post, tom_pre = 7 * m["post"], 7 * m["pre"]
    rows.append({
        "id": "Q05", "stat": "turn-of-month sessions - other sessions (difference)", "k": 1,
        "predicted_post": (0.0, 10.0), "predicted_pre": (2.0, 10.0),
        "provenance": ("RECALLED, not verified: turn-of-month days carry most of the equity premium "
                       "(McConnell & Xu 2008). With an assumed ~8%/yr premium spread over 84 TOM "
                       "sessions a year that is <=~10 bps a session. Neither Q document gives a bps "
                       "figure. The N/M split must be pre-registered or k rises."),
        "sd_post": s["sd_post"], "sd_full": s["sd"],
        "n_post": (tom_post, m["sessions_post"] - tom_post),
        "n_full": (tom_post + tom_pre, m["sessions_post"] + m["sessions_pre"] - tom_post - tom_pre),
        "kind": "diff", "cost_note": "session hold 18:00-16:00 includes the overnight spread",
    })

    # ---- Q06, pre-registered Monday - and as written ------------------------------------------------
    q6 = s1["q06_mondays"]
    s = sd["Q06 overnight to 09:30"]
    for label, k in (("Q06 Monday only", 1), ("Q06 as written (10 cells)", 10)):
        rows.append({
            "id": label, "stat": "Monday overnight - other overnights (difference)", "k": k,
            "predicted_post": (0.0, 3.0), "predicted_pre": (0.0, 3.0),
            "provenance": ("RECALLED, not verified: the weekend effect (French 1980) reversed or faded "
                           "after the 1990s. No bps figure in either document; ESTIMATED small."),
            "sd_post": q6["sd_post"], "sd_full": s["sd"],
            "n_post": (q6["mon_post"], q6["other_post"]),
            "n_full": (q6["mon_pre"] + q6["mon_post"], q6["other_pre"] + q6["other_post"]),
            "kind": "diff", "cost_note": "overnight spread UNMEASURED",
        })

    print("=" * 118)
    print("Q-SERIES S2 - ESTIMATED magnitudes vs cost floor (0.48 bps) and BH bar; POST-2021 DECIDES")
    print("=" * 118)
    print(f"{'candidate':<26} {'pred post':>10} {'n post (events/rest)':>22} {'sd':>6} "
          f"{'bar post':>12} {'bar full':>12}  {'vs cost':<22} {'vs bar (post)':<10}")
    out = []
    for r in rows:
        bars = {}
        for era in ("post", "full"):
            n, sdv = r[f"n_{era}"], r[f"sd_{era}"]
            lo_b = (diff_bar(sdv, *n, r["k"], DEFF[0]) if r["kind"] == "diff"
                    else mean_bar(sdv, n[0], r["k"], DEFF[0]))
            hi_b = (diff_bar(sdv, *n, r["k"], DEFF[1]) if r["kind"] == "diff"
                    else mean_bar(sdv, n[0], r["k"], DEFF[1]))
            bars[era] = (lo_b, hi_b)
        lo, hi = r["predicted_post"]
        cost_v, bar_v = verdict(lo, hi, *bars["post"])
        n_txt = " / ".join(f"{int(round(x)):,}" for x in r["n_post"])
        print(f"{r['id']:<26} {lo:>4.1f}-{hi:<5.1f} {n_txt:>22} {r['sd_post']:>6.1f} "
              f"{bars['post'][0]:>5.2f}-{bars['post'][1]:<6.2f} {bars['full'][0]:>5.2f}-{bars['full'][1]:<6.2f}"
              f"  {cost_v:<22} {bar_v:<10}")
        out.append({**r, "bar_post": bars["post"], "bar_full": bars["full"],
                    "vs_cost": cost_v, "vs_bar_post": bar_v})

    not_predictable = {
        "Q04": "no direction - 'the pre-event book is thin' names a condition, not a trade; and F12 already records releases at ~200 observations, 'do not register them individually'",
        "Q07": "no direction - forced roll flow is largely calendar-spread flow with no stated sign on the outright; ~65 rolls over 2010-2026, ~22 post-2021; spread files still unparsed",
        "Q08": "not a signal - a sizing rule, contingent on a surviving edge",
        "Q09": "not a signal - a computation, completed at S1 (q09_drawdown.py)",
        "Q10": "not a signal - a standing S8 gate",
        "Q11": "not a signal - an exclusion, contingent on a live primary (the P02/P10 case)",
        "Q12": "not a signal - a measurement, contingent on three survivors",
    }
    print("\nCANNOT BE PREDICTED IN BPS")
    for k, v in not_predictable.items():
        print(f"  {k}: {v}")

    OUT.write_text(json.dumps({"rows": out, "not_predictable": not_predictable,
                               "cost_bps": COST_BPS, "deff_bracket": DEFF},
                              indent=1, default=float) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

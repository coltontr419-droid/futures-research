"""T-series S2 filter: a predicted magnitude for T02-T07 against the within-entry BH bar at
expected n AND the prevailing SR*, in the same units. NOTHING IS REGISTERED; no trial spent.

    python -m futuresres.reporting.t_series_s2

Method inherited unchanged from decisions.md S54, S59 and S63 (`s_series_s2.py`), so the
T-series is filtered no more leniently than the P-, Q- and S-series were:

    bar       = z(1 - 0.05/(2k)) * anchor(H) / sqrt(units)       BH rank-1, within the entry
    anchor(H) = 64.7 * sqrt(H/180) bps                            L12's paired bootstrap (S57)
    SR*->bps  = SR*(N the entry would face) * per-event sd(H)     S63's conversion
    units     = post-2021 sessions * min(firings/session, slots(H)) / DEFF

SR* IN BPS, TWO WAYS. S63 converted with anchor(H), the sd of a PAIRED real-minus-control
difference. A per-trade Sharpe is mean over the OUTRIGHT per-trade sd, which is smaller:
`reports/kurtosis.md` measures MNQ at 21.4 bps (30m) and 30.4 (60m). Both conversions are
reported; the second is the lenient one, and every verdict below is stated under it.

FIRINGS. Measured where `t02_t04_scale_collinearity.json` measures them (T02, T04); by
construction for T03 (percentile thresholds fire on a fixed share of windows); none for T06.
Each trade holds H, so a session carries at most slots(H) non-overlapping entries:
RTH entries to the 15:55 exit give 385/H (base case); allowing entries from the 18:00 open
gives 1,315/H (generous case, shown so a reader can see it does not change a verdict).
DEFF 5.8 is the low end of the only measurement the programme has for an intrabar object
(L07 at 15m, `peak_bps_l07.json`) - the generous choice, as in S63.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Final

import numpy as np
from scipy.stats import norm

from futuresres.reporting.s_series_s2 import expected_max_sharpe, trial_state

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
PRECHECK: Final[Path] = ROOT / "reports" / "t02_t04_scale_collinearity.json"
OUT_JSON: Final[Path] = ROOT / "reports" / "t_series_s2.json"
OUT_MD: Final[Path] = ROOT / "reports" / "t_series_s2.md"

ANCHOR_180: Final[float] = 64.7
OUTRIGHT_SD: Final[dict[int, float]] = {30: 21.4, 60: 30.4, 120: 30.4 * math.sqrt(2)}
POST_2021_SESSIONS: Final[int] = 1390
DEFF: Final[float] = 5.8
RTH_MINUTES_TO_EXIT: Final[int] = 385          # 09:30 -> 15:55
FULL_MINUTES_TO_EXIT: Final[int] = 1315        # 18:00 -> 15:55
HORIZONS: Final[tuple[int, ...]] = (30, 60, 120)
K_CELLS: Final[int] = 54                       # 3 x 3 x 3 grid x 2 instruments

#: (id, label, prior low, prior high, prior basis, the draft's own range, firings source)
ENTRIES: Final = [
    ("T02", "jump vs diffusion, fade diffusive moves", 0.0, 0.5,
     "MEASURED analogues of the same counterparty claim (liquidity consumption reverts): "
     "P03 real-minus-control +0.079 bps (S58), L12 +0.306, R01 +0.452 - the largest effect "
     "the programme has measured. The draft's 2-5 bps cites R01's +0.452 as its anchor, which "
     "supports ~0.5, not 2-5; the draft's range is reported beside it, not used.",
     (2.0, 5.0), "T02"),
    ("T03", "realised skewness, fade the tail", 0.0, 1.0,
     "No measured analogue in seven series. The cited result is weekly and cross-sectional "
     "in equities; the draft itself says neither property transfers. Bounded by the "
     "programme's typical measured range, zero included (S59: decay is the stated prior).",
     (1.0, 3.0), "T03"),
    ("T04", "path efficiency, fade one-sided runs", 0.0, 0.5,
     "Same counterparty story as T02 by the draft's own account, so the same measured "
     "analogues. The draft states no magnitude at all.",
     None, "T04"),
]
NOT_PREDICTABLE: Final = [
    ("T06", "duration since last large move",
     "Its own mechanism forecasts MAGNITUDE, not direction (draft: 'the win rate must come "
     "back near 50%'), so a signed bps prediction is undefined. And it is not new: 'arm after "
     "quiet, trade the first k-sigma breach in its direction' is F05 (volatility compression "
     "-> first close beyond k*sigma), the one F-series hypothesis tested at adequate power "
     "(45 cells, 11,000-18,600 events) and retired on a null. The draft calls it distinct "
     "from 'L-series volatility compression'; that entry is F05, not an L entry."),
    ("T07", "variance-ratio regime",
     "A conditioner with no surviving primary to condition, the Q08 disposition. No trade "
     "rule, so no magnitude, and nothing for it to do."),
]


def anchor(h: int) -> float:
    return ANCHOR_180 * math.sqrt(h / 180.0)


def z_bh(k: int) -> float:
    return float(norm.ppf(1.0 - (0.05 / k) / 2.0))


def firings_per_rth_session(entry: str, pre: dict) -> dict[str, float]:
    """Windows firing per RTH session (390 one-minute windows), per instrument.

    T02/T04 at W=60, middle thresholds (j_low 0.2, e_high 0.65), from the measured share of
    windows. T03 by construction: p20/p80 thresholds fire on 40% of windows.
    """
    out = {}
    for prod, r in pre.items():
        f = r["by_window"]["60"]["fire"]["0.2/0.65"]
        if entry == "T02":
            out[prod] = 390 * f["p_t02"]
        elif entry == "T04":
            out[prod] = 390 * f["p_t04"]
        elif entry == "T03":
            out[prod] = 390 * 0.40
    return out


def main() -> int:
    pre = json.loads(PRECHECK.read_text())
    n0, var = trial_state()
    sr0 = expected_max_sharpe(n0, var)
    zk = z_bh(K_CELLS)

    rows, n = [], n0
    for eid, label, lo, hi, basis, draft, src in ENTRIES:
        fps = firings_per_rth_session(src, pre)
        fire_min = min(fps.values())
        n += K_CELLS
        srs = expected_max_sharpe(n, var)
        per_h = {}
        for h in HORIZONS:
            for case, minutes in (("rth", RTH_MINUTES_TO_EXIT), ("full", FULL_MINUTES_TO_EXIT)):
                slots = minutes / h
                per_session = min(fire_min * (minutes / 390), slots)
                units = POST_2021_SESSIONS * per_session / DEFF
                per_h[f"{h}_{case}"] = {
                    "units": units, "bar": zk * anchor(h) / math.sqrt(units),
                }
            per_h[f"{h}_srstar_anchor"] = srs * anchor(h)
            per_h[f"{h}_srstar_outright"] = srs * OUTRIGHT_SD[h]
        best_h = min(HORIZONS, key=lambda h: per_h[f"{h}_full"]["bar"])
        bar_best = per_h[f"{best_h}_full"]["bar"]
        sr_lenient = min(per_h[f"{h}_srstar_outright"] for h in HORIZONS)
        binding = "SR*" if sr_lenient > bar_best else "BH bar"
        rows.append({
            "id": eid, "label": label, "prior": [lo, hi], "prior_basis": basis,
            "draft_range": draft, "firings_per_rth_session": fps,
            "N_after": n, "SR_star_after": srs, "by_horizon": per_h,
            "lowest_bar_any_case": bar_best, "lowest_bar_horizon": best_h,
            "lowest_srstar_bps_lenient": sr_lenient,
            "prior_top_clears_bar": hi >= bar_best,
            "prior_top_clears_srstar": hi >= sr_lenient,
            "draft_top_clears_bar": (draft[1] >= bar_best) if draft else None,
            "draft_top_clears_srstar": (draft[1] >= sr_lenient) if draft else None,
            "binding": binding,
        })

    out = {"N_at_pickup": n0, "SR_star_at_pickup": sr0, "trial_sharpe_variance": var,
           "k_cells": K_CELLS, "z_bh": zk, "deff": DEFF,
           "post_2021_sessions": POST_2021_SESSIONS, "entries": rows,
           "not_predictable": [{"id": a, "label": b, "why": c} for a, b, c in NOT_PREDICTABLE]}
    OUT_JSON.write_text(json.dumps(out, indent=1) + "\n")
    OUT_MD.write_text(render(out))
    print(f"N {n0} SR* {sr0:.4f}; wrote {OUT_JSON.name}, {OUT_MD.name}")
    for r in rows:
        print(f"{r['id']}: prior {r['prior']}, lowest bar {r['lowest_bar_any_case']:.2f} "
              f"(H={r['lowest_bar_horizon']}), SR*bps lenient {r['lowest_srstar_bps_lenient']:.2f}, "
              f"binding {r['binding']}")
    return 0


def render(o: dict) -> str:
    w: list[str] = []
    a = w.append
    a("# T-series S2 filter — magnitude against the BH bar and the prevailing SR\\*")
    a("")
    a(f"Generated by `python -m futuresres.reporting.t_series_s2`. **Nothing registered, no "
      f"trial spent.** N = {o['N_at_pickup']}, SR\\* = {o['SR_star_at_pickup']:.4f} at pickup "
      f"(reproduced from `trials.jsonl`). k = {o['k_cells']} cells per entry, BH rank-1 "
      f"z = {o['z_bh']:.4f}, post-2021 decisive ({o['post_2021_sessions']:,} sessions), "
      f"DEFF {o['deff']}. Method in the module docstring.")
    a("")
    a("| entry | prior (bps) | draft's range | lowest BH bar, any H, generous n | SR\\* as bps (lenient) | N after | binds | prior top clears |")
    a("|---|---|---|---|---|---|---|---|")
    for r in o["entries"]:
        d = f"{r['draft_range'][0]}–{r['draft_range'][1]}" if r["draft_range"] else "none stated"
        clears = ("bar ✓" if r["prior_top_clears_bar"] else "bar ✗") + " · " + \
                 ("SR\\* ✓" if r["prior_top_clears_srstar"] else "SR\\* ✗")
        a(f"| **{r['id']}** {r['label']} | {r['prior'][0]}–{r['prior'][1]} | {d} | "
          f"{r['lowest_bar_any_case']:.2f} (H={r['lowest_bar_horizon']}) | "
          f"{r['lowest_srstar_bps_lenient']:.2f} | {r['N_after']} | {r['binding']} | {clears} |")
    for r in o["not_predictable"]:
        a(f"| **{r['id']}** {r['label']} | cannot predict | — | — | — | — | — | — |")
    a("")
    a("## Per horizon")
    a("")
    a("| entry | H | units (RTH / full) | BH bar (RTH / full) | SR\\* bps, paired-sd / outright-sd |")
    a("|---|---|---|---|---|")
    for r in o["entries"]:
        for h in HORIZONS:
            b = r["by_horizon"]
            a(f"| {r['id']} | {h} | {b[f'{h}_rth']['units']:,.0f} / {b[f'{h}_full']['units']:,.0f} | "
              f"{b[f'{h}_rth']['bar']:.2f} / {b[f'{h}_full']['bar']:.2f} | "
              f"{b[f'{h}_srstar_anchor']:.2f} / {b[f'{h}_srstar_outright']:.2f} |")
    a("")
    a("## Prior basis")
    a("")
    for r in o["entries"]:
        a(f"- **{r['id']}** — {r['prior_basis']}")
    for r in o["not_predictable"]:
        a(f"- **{r['id']}** — {r['why']}")
    a("")
    return "\n".join(w)


if __name__ == "__main__":
    raise SystemExit(main())

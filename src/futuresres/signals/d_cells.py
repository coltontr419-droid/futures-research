"""D03-D11 - the cells the corrected-clock discovery re-scan carried (decisions.md 142-143), each validated ONCE on the
sealed 2018-01 -> 2026-09 window. Data-derived; one trial per cell. hypotheses.yaml D03-D11.

    python -m futuresres.signals.d_cells --inject D05
    python -m futuresres.signals.d_cells --run D05         # THE TRIAL (refuses without a recovered injection)

Fixed before any validation data was read (decisions.md 143):
  DIRECTION  the sign of the discovery mean (2010-17); the statistic is the net return of that trade per event, in the
             pair's own terms (USD/CHF falling = short USD/CHF).
  COST       the scan's: FX 0.8 bp, DAX / Nikkei 1.0, silver 1.5.
  PRIOR      Normal(discovery |mean| / 2 - cost, max(1.0, cost)) bps net - §132's mean; the SD rule reproduces D01 (1.5)
             and D02 (1.0).
  PLACEBO    the same trade in the instrument's other cells of its family and day-set: family 1, the other UTC hours (on the
             same weekday for an hour-by-weekday cell); family 2, the instrument's other family-2 windows on the same day-set.
  TIERS      CONFIRM - net t > 1.645, placebo >= 95th pct, posterior > 0; WATCHLIST - else net mean > 0; REJECT (§133).
  INJECTION  the prior's mean planted in demeaned noise from the placebo cells (family 1) or from the same window on all
             weekdays (family 2); recovered within tolerance, and the strict t's power reported.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
VAL = (dt.date(2018, 1, 1), dt.date(2026, 9, 30))
VAL_DT = (dt.datetime(2018, 1, 1, tzinfo=dt.timezone.utc), dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc))
#: id -> cell. fam 1: pair, hour (UTC), weekday (1 = Mon .. 5 = Fri, None = all); fam 2: pair, window label prefix,
#: before?, day-set. `disc` = (discovery mean bps, t, n); `side` = +1 long the pair / -1 short.
CELLS = {
    "D03": dict(fam=1, pair="usdchf", fut="6S", cost=0.8, hour=20, wd=5, disc=(-2.876, -6.07, 403),
                title="USD/CHF falls in the last New York hour on Fridays (20:00-21:00 UTC)"),
    "D04": dict(fam=1, pair="xagusd", fut="SI", cost=1.5, hour=10, wd=None, disc=(-3.143, -4.22, 1949),
                title="silver falls 10:00-11:00 UTC"),
    "D05": dict(fam=2, pair="gbpusd", fut="6B", cost=0.8, win="WM/R 16:00 London fix", before=True, dayset="month-end",
                disc=(5.633, 2.84, 96), title="GBP rises into the London 4 pm fix at month-end"),
    "D06": dict(fam=2, pair="grxeur", fut="FDXM", cost=1.0, win="Xetra open 09:00", before=False, dayset="month-end",
                disc=(-8.712, -2.64, 79), title="DAX falls in the first half hour of Xetra at month-end"),
    "D07": dict(fam=2, pair="jpxjpy", fut="NKD", cost=1.0, win="Tokyo morning close 11:30", before=True, dayset="all weekdays",
                disc=(-2.352, -2.60, 1153), title="Nikkei falls into the Tokyo morning close"),
    "D08": dict(fam=2, pair="audusd", fut="6A", cost=0.8, win="WM/R 16:00 London fix", before=False, dayset="month-end",
                disc=(-3.451, -2.41, 96), title="AUD falls after the London 4 pm fix at month-end"),
    "D09": dict(fam=2, pair="usdchf", fut="6S", cost=0.8, win="WM/R 16:00 London fix", before=False, dayset="month-end",
                disc=(3.182, 2.34, 96), title="USD/CHF rises after the London 4 pm fix at month-end"),
    "D10": dict(fam=2, pair="audusd", fut="6A", cost=0.8, win="WM/R 16:00 London fix", before=True, dayset="month-end",
                disc=(4.233, 2.04, 96), title="AUD rises into the London 4 pm fix at month-end"),
    "D11": dict(fam=2, pair="grxeur", fut="FDXM", cost=1.0, win="Xetra close auction 17:30", before=False, dayset="month-end",
                disc=(4.255, 1.97, 78), title="DAX rises after the Xetra closing auction at month-end"),
}
FIRST_TEST_NUMBER = 15          # running count of Z and D market-tests: D01 was the 13th, D02 the 14th


def prior(hid: str) -> tuple[float, float]:
    c = CELLS[hid]
    return abs(c["disc"][0]) / 2 - c["cost"], max(1.0, c["cost"])


def side(hid: str) -> float:
    return 1.0 if CELLS[hid]["disc"][0] > 0 else -1.0


def _paths(hid: str) -> tuple[Path, Path, Path]:
    s = hid.lower()
    return ROOT / "reports" / f"{s}_injection.json", ROOT / "reports" / f"{s}_trial.json", ROOT / "reports" / f"{s}_trial.md"


def _t(x) -> float:
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x))))


# ------------------------------------------------------------------ data
def _fam1(c: dict):
    """(days, the cell's gross returns, {other cell: returns}) on the validation window, signed by the trade."""
    import polars as pl
    from futuresres.reporting.d_discovery import hourly_returns
    r = hourly_returns(c["pair"], start=VAL_DT[0], end=VAL_DT[1])
    assert r["start"].min() >= VAL_DT[0], "validation read discovery data"
    if c["wd"] is not None:
        r = r.filter(pl.col("wd") == c["wd"])
    cell = r.filter(pl.col("hour") == c["hour"])
    days = [s.date() for s in cell["start"].to_list()]
    others = {f"{h:02d} UTC": r.filter(pl.col("hour") == h)["bps"].to_numpy() for h in range(24)
              if h != c["hour"] and r.filter(pl.col("hour") == h).height >= 30}
    return days, cell["bps"].to_numpy(), others


def _fam2_series(pair: str, label: str, before: bool, dayset: str):
    import futuresres.reporting.d2_discovery as d2
    from futuresres.data.fx_fix import quarter_marks
    win = [w for w in d2.windows() if w["pair"] == pair and w["label"].startswith(label) and w["before"] == before][0]
    days, r = d2.returns(win, quarter_marks(pair), *VAL)
    assert not days or min(days) >= VAL[0], "validation read discovery data"
    if dayset == "month-end":
        me = d2._last_weekdays(*VAL)
        m = np.array([d in me for d in days]); days = [d for d, k in zip(days, m) if k]; r = r[m]
    return days, r


def _fam2(c: dict):
    import futuresres.reporting.d2_discovery as d2
    days, r = _fam2_series(c["pair"], c["win"], c["before"], c["dayset"])
    others = {}
    for w in d2.windows():
        if w["pair"] != c["pair"] or (w["label"].startswith(c["win"]) and w["before"] == c["before"]):
            continue
        _, x = _fam2_series(c["pair"], w["label"].rsplit(" ", 1)[0], w["before"], c["dayset"])
        if len(x) >= 30:
            others[w["label"]] = x
    return days, r, others


def data(hid: str):
    c = CELLS[hid]
    return _fam1(c) if c["fam"] == 1 else _fam2(c)


# ------------------------------------------------------------------ injection and trial
def injection(hid: str, reps: int = 2000) -> int:
    from futuresres.signals.z_strict import T_CRIT
    c = CELLS[hid]; mu, _ = prior(hid); inj_path = _paths(hid)[0]
    days, r, others = data(hid)
    if c["fam"] == 1:
        noise = np.concatenate([x - x.mean() for x in others.values()])
    else:
        _, allr = _fam2_series(c["pair"], c["win"], c["before"], "all weekdays")
        noise = allr - allr.mean()
    n = len(r); rng = np.random.default_rng(143 + int(hid[1:]))
    est = np.empty(reps); passes = 0
    for k in range(reps):
        x = rng.choice(noise, size=n, replace=True) + mu
        est[k] = x.mean(); passes += _t(x) > T_CRIT
    sd = float(est.std(ddof=1))
    res = {"hypothesis": hid, "n_events": n, "sought_net_bps": mu, "mean_estimate": float(est.mean()), "sd_estimate_bps": sd,
           "power_strict_t": passes / reps, "recovered": bool(abs(est.mean() - mu) <= 3 * sd / math.sqrt(reps) + 0.1)}
    inj_path.write_text(json.dumps(res, indent=1) + "\n"); print(json.dumps(res, indent=1))
    return 0 if res["recovered"] else 1


def run_trial(hid: str) -> int:
    from futuresres.signals.z_strict import T_CRIT
    c = CELLS[hid]; inj_path, out_path, md_path = _paths(hid)
    inj = json.loads(inj_path.read_text()) if inj_path.exists() else None
    if not (inj and inj["recovered"]):
        raise SystemExit("refusing to run: outcome injection missing or failed")
    days, r, others = data(hid)
    s = side(hid); cost = c["cost"]
    gross = s * r; net = gross - cost; t = _t(net)
    other_net = {k: float((s * x - cost).mean()) for k, x in others.items()}
    pct = float((np.array(list(other_net.values())) < net.mean()).mean() * 100) if other_net else float("nan")
    mu0, sd0 = prior(hid)
    p0, p1 = 1 / sd0 ** 2, 1 / (net.std(ddof=1) ** 2 / len(net))
    post = (mu0 * p0 + net.mean() * p1) / (p0 + p1); post0 = net.mean() * p1 / (p0 + p1)
    yrs = np.array([d.year for d in days])
    eras = {lab: {"events": int(m.sum()), "net_bps": float(net[m].mean()), "t": _t(net[m]) if m.sum() > 2 else float("nan")}
            for lab, m in (("2018-21", yrs <= 2021), ("2022-26", yrs >= 2022))}
    c1, c2, c3 = t > T_CRIT, pct >= 95.0, post > 0
    tier = "CONFIRM" if (c1 and c2 and c3) else ("WATCHLIST" if net.mean() > 0 else "REJECT")
    number = FIRST_TEST_NUMBER + list(CELLS).index(hid)
    out = {"hypothesis": hid, "cell": c["title"], "side": "long" if s > 0 else "short", "pair": c["pair"], "future": c["fut"],
           "window": [str(days[0]), str(days[-1])], "events": int(len(net)), "gross_bps": float(gross.mean()),
           "net_bps": float(net.mean()), "sd_bps": float(gross.std(ddof=1)), "t_net": t, "win_rate_net": float((net > 0).mean()),
           "placebo_pct": pct, "placebo_cells_net": other_net, "prior": [mu0, sd0],
           "posterior_bps": {"registered_prior": post, "zero_prior": post0}, "eras": eras,
           "discovery": {"mean_bps": c["disc"][0], "t": c["disc"][1], "n": c["disc"][2]},
           "conditions": {"t_gt_1.645": bool(c1), "placebo_ge_95": bool(c2), "posterior_gt_0": bool(c3)},
           "z_d_market_test_number": number, "decision": tier, "injection": inj}
    out_path.write_text(json.dumps(out, indent=1, default=float) + "\n")
    rows = ["| period | events | net bps | t |", "|---|---|---|---|"] + [f"| {k} | {e['events']} | {e['net_bps']:+.2f} | {e['t']:+.2f} |" for k, e in eras.items()]
    md_path.write_text("\n".join([
        f"# {hid} — {c['title']}: the validation trial", "",
        f"**Decision: {tier}.** {len(net)} events, {out['window'][0]} → {out['window'][1]} (sealed until registration).", "",
        f"- {out['side'].title()} {c['pair'].upper()} ({c['fut']}): gross **{out['gross_bps']:+.2f} bps** (SD {out['sd_bps']:.1f}); net of "
        f"{cost} bp **{out['net_bps']:+.2f}**, t **{t:+.2f}** (needs > 1.645): {c1}; net win rate {out['win_rate_net']:.0%}.",
        f"- Placebo: the same trade in {len(other_net)} other cells — real at the **{pct:.0f}th** pct (needs ≥ 95): {c2}.",
        f"- Posterior net mean {post:+.2f} bps (prior Normal({mu0:+.2f}, {sd0:.1f}); zero prior {post0:+.2f}): {c3}.",
        f"- Discovery (2010–17): {c['disc'][0]:+.2f} bps, t {c['disc'][1]:+.2f}, n {c['disc'][2]}. Z and D market-test number {number}.", "",
        *rows, "",
        f"Outcome injection: {inj['sought_net_bps']:.2f} bp planted, recovered {inj['mean_estimate']:.2f} (SD {inj['sd_estimate_bps']:.2f}); "
        f"power of the strict t {inj['power_strict_t']:.0%}.", ""]))
    from futuresres.stats.trials import Trial, TrialLog
    log = TrialLog(ROOT / "trials.jsonl")
    rec = log.append(Trial(trial_id=log.next_id("t"), hypothesis_id=hid, symbol=c["fut"], date_range=(out["window"][0], out["window"][1]),
                           status="completed", sharpe=float(net.mean() / net.std(ddof=1)),
                           params={"statistic": f"net mean per event, {out['side']} {c['pair']}: {c['title']}; sealed 2018-2026; strict rule + tiers",
                                   "net_bps": out["net_bps"], "t_net": t, "placebo_pct": pct, "decision": tier},
                           note="provenance=native; source=data-derived (D-series re-scan on the corrected clock, decisions.md 142-143); validated once on sealed data."))
    print(md_path.read_text()); print("logged", rec["trial_id"])
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="futuresres.signals.d_cells")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--inject", action="store_true"); g.add_argument("--run", action="store_true")
    ap.add_argument("hid", choices=tuple(CELLS))
    a = ap.parse_args(argv)
    return injection(a.hid) if a.inject else run_trial(a.hid)


if __name__ == "__main__":
    sys.exit(main())

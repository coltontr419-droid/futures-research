"""A15 - a third account: the A01 staking on crude (MCL), full session, from the daily bars already owned (one
candle per session, the OHLC path rule); then all three accounts together. A COMPUTATION; zero edge (drift
removed); no trial. decisions.md 116.

    python -m futuresres.reporting.a15_crude [--log]

Minute and hourly crude data were too expensive (decisions.md 115). The owned GLBX ohlcv-1d file has roll-correct
CL returns with the held contract's high and low against the previous close (data/daily_bars.py). One bar per
session: entry at the previous close, the high and low as the day's extremes, a bar touching both levels resolved
by the OHLC rule (the extreme nearer the entry first). Checked on MNQ and MGC full sessions against 1-minute paths
(scratch, decisions.md 116): mean net within ~+-30%, P(payout) within ~5 points. Window: the whole session (the
user confirmed the 18:00->16:55 hold; UTC-day bars track the session at 0.97, decisions.md 74). Sizes 5-30 MCL
($100 a point per CL, so 1 MCL = $100 x price change / 10), $3.32 a round trip each. Histories 2016-20 and 2021-26.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.a01_game as g
import futuresres.reporting.a02_real as a2
import futuresres.reporting.a08_gold as a8
import futuresres.reporting.a12_joint as j

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "a15_crude.json"
RT_MCL = np.float32(3.32)
SIZES = (5, 10, 15, 20, 25, 30)
ERAS = {"pre": ("2016-01-01", "2020-12-31"), "post": ("2021-01-01", "2026-12-31")}


def mcl_paths(era: str):
    """GROSS one-MCL $ 'paths' of a single bar per session (h, l, c with T = 1), drift removed within the era, at
    today's price; and the session dates."""
    from futuresres.data.daily_bars import load_market
    mk = load_market("CL")
    lo, hi = ERAS[era]
    m = (mk.dates >= np.datetime64(lo)) & (mk.dates <= np.datetime64(hi)) & ~mk.crossover & (mk.ret != 0)
    notional = float(mk.front_close[np.isfinite(mk.front_close)][-1]) * 1000.0 / 10.0     # one MCL
    r, rl, rh = mk.ret[m], mk.ret_low[m], mk.ret_high[m]
    mu = float(r.mean())
    c = ((r - mu) * notional).astype(np.float32)[:, None]
    l = (np.minimum(rl - mu, r - mu) * notional).astype(np.float32)[:, None]
    h = (np.maximum(rh - mu, r - mu) * notional).astype(np.float32)[:, None]
    return h, l, c, mk.dates[m].astype("datetime64[D]")


def one_bar_rule(o_engine: float):
    """_bracket_day for single-bar paths: a bar touching both levels -> the extreme nearer the entry first."""
    def rule(h, l, c, W, L):
        hh, ll = h[:, 0], l[:, 0]
        hitW, hitL = hh >= W, ll <= -L
        high_first = (hh - o_engine) <= (o_engine - ll)
        take = hitW & (~hitL | high_first); stop = hitL & ~take
        out = c[:, -1].copy()
        out[stop] = -L[stop]; out[take] = W[take]
        return out, stop, take
    return rule


def _engine(h, l, c, n):
    tot = RT_MCL * n
    return ((h * n - (tot - a8.RT_ENGINE)).astype(np.float32), (l * n - tot).astype(np.float32), (c * n - tot).astype(np.float32)), float(-tot + a8.RT_ENGINE)


def _row(r):
    return {k: r[k] for k in ("p_any_payout", "mean_net", "p_net_positive", "mean_attempts", "mean_fees")}


def run() -> dict:
    warnings.filterwarnings("ignore")
    with contextlib.redirect_stdout(io.StringIO()), np.errstate(all="ignore"):
        g.solve_all(21, keep_policy_at=21); g.solve_funded(21, "dollars", keep_policy_at=21)
    a2.STOP_FILL = "level"
    orig = a2._bracket_day
    out = {"grid": {}, "joint": {}}
    for era in ERAS:
        h, l, c, d = mcl_paths(era)
        out["grid"][era] = {"sessions": int(len(c)), "one_mcl_daily_sd": float(c[:, 0].std()), "sizes": {}}
        for n in SIZES:
            a2._PATHS["p"], o = _engine(h, l, c, n)
            a2._bracket_day = one_bar_rule(o)
            out["grid"][era]["sizes"][n] = {"replay": _row(a2.sequential(1, "replay")),
                                            "block": [_row(a2.sequential(1, "block", traders=6000, seed=s)) for s in (11, 12)]}
            a2._bracket_day = orig
            v = out["grid"][era]["sizes"][n]
            print(era, n, "MCL", json.dumps(v["replay"]), flush=True)
    # risk-matched size: the 2021-26 daily $ swing nearest 4 MNQ's RTH swing (A07), the rule used for gold (A08)
    sd_post = out["grid"]["post"]["one_mcl_daily_sd"]
    n_star = int(min(SIZES, key=lambda n: abs(n * sd_post - 4 * 698.0)))
    out["chosen_mcl"] = n_star
    for era in ERAS:
        h, l, c, d = mcl_paths(era)
        a2._PATHS["p"], o = _engine(h, l, c, n_star)
        a2._bracket_day = one_bar_rule(o)
        rc = a2.sequential(1, "replay", per_trader=True); a2._bracket_day = orig; a2._PATHS.clear()
        e = rc["each"]
        cl = {"date": d[e["start"]], "net": e["net"], "first": e["first_payout_day"], "fees": e["fees"], "paid": e["paid"]}
        mnq, mgc = j.per_start(era, "MNQ"), j.per_start(era, "MGC")
        common = np.intersect1d(np.intersect1d(mnq["date"], mgc["date"]), cl["date"])
        sel = lambda x: {k: v[np.searchsorted(x["date"], common)] for k, v in x.items()}
        A, B, C = sel(mnq), sel(mgc), sel(cl)
        net = A["net"] + B["net"] + C["net"]
        pays = (A["first"] > 0).astype(int) + (B["first"] > 0) + (C["first"] > 0)
        out["joint"][era] = {"common_starts": int(len(common)), "first": str(common[0]), "last": str(common[-1]),
                             "p_payout_each": [float((x["first"] > 0).mean()) for x in (A, B, C)],
                             "p_any_payout": float((pays > 0).mean()), "mean_payouts_streams": float(pays.mean()),
                             "mean_net": float(net.mean()), "median_net": float(np.median(net)),
                             "p_net_positive": float((net > 0).mean()), "net_p10": float(np.quantile(net, 0.1)),
                             "worst": float(net.min()), "mean_fees": float((A["fees"] + B["fees"] + C["fees"]).mean()),
                             "corr_net": np.corrcoef([A["net"], B["net"], C["net"]]).round(3).tolist(),
                             "two_market_p_net_positive": float(((A["net"] + B["net"]) > 0).mean())}
        print(era, "joint", json.dumps(out["joint"][era]), flush=True)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--log", action="store_true")
    a = ap.parse_args(argv)
    r = run()
    OUT.write_text(json.dumps(r, indent=1) + "\n")
    if a.log:
        from futuresres.stats.trials import Trial, TrialLog
        log = TrialLog(ROOT / "measurements.jsonl")
        rec = log.append(Trial(trial_id=log.next_id("m"), hypothesis_id="A-series", symbol="MCL+MNQ+MGC",
                               date_range=("2016-01-01", "2026-09-12"), status="completed", params={"kind": "crude_third_account", **r},
                               note="kind=computation; NOT a trial. A15: staking on MCL from owned daily bars; three accounts together. decisions.md 116."))
        print("logged", rec["trial_id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())

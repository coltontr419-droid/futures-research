"""Y04 - MNQ New York (09:30-16:00) and MGC London (03:00-11:30), both long, on ONE Tradeify account.

A COMPUTATION on Tradeify's confirmed rules (decisions.md 81-82) and demeaned real sessions; no market
claim, no trial. `--log` writes one record. decisions.md 84.

    python -m futuresres.reporting.y04_combined
    python -m futuresres.reporting.y04_combined --log

CONSTRUCTION, fixed before running:
  pairing    sessions paired BY DATE (dates both instruments have complete), so the two legs carry their
             real co-movement; each leg's drift is removed within its era first (y01.window_paths).
  the day    MGC long 03:00-11:30 ET, MNQ long 09:30-16:00 ET, one contract each, on one account: a
             single end-of-day floor, a single $1,000 soft daily limit (which flattens both legs), and
             the 40% consistency rule applied to the account's combined daily P&L.
  intrabar   the combined minute low is the SUM of the two legs' lows - as if both lows printed in the
             same minute. Conservative: it can only overstate an intraday excursion.
  cost       both round trips, $2.32 + $3.32 = $5.64 a day; a forced flatten slips one tick on each leg.
  compared   with each leg alone on its own account (Y03's cells), per $80 fee.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Final

import numpy as np

import futuresres.reporting.y01_structure_ev as y
import futuresres.reporting.y02_tradeify as z
import futuresres.reporting.y03_sessions as s3

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
OUT_JSON: Final[Path] = ROOT / "reports" / "y04_combined.json"
OUT_MD: Final[Path] = ROOT / "reports" / "y04_combined.md"
ACCOUNTS: Final[int] = 16_000
GRID: Final[tuple[int, int]] = (540, 1320)        # 03:00 -> 16:00 ET, minutes after 18:00
MGC_W: Final[tuple[int, int]] = (540, 1050)       # London 03:00-11:30
MNQ_W: Final[tuple[int, int]] = (930, 1320)       # New York 09:30-16:00


def _load(product: str):
    spec = s3.PRODUCTS[product]
    y.SERIES = y.ROOT / "data" / "continuous" / f"{spec['series']}.parquet"
    y.MULT = spec["mult"]
    return y.load_sessions()


def _leg(H, L, C, window, notional):
    """Demeaned $ paths for one contract over its window, placed on the 03:00-16:00 grid: zero before
    the window, frozen at the exit value after it."""
    name = f"_y04_{window[0]}_{window[1]}"
    y.WINDOWS[name] = window
    h, l, c, _ = y.window_paths(H, L, C, name, None)
    W = GRID[1] - GRID[0]
    a = window[0] - GRID[0]
    lo = np.zeros((len(c), W), np.float32); cl = np.zeros((len(c), W), np.float32)
    lo[:, a:a + l.shape[1]] = l * notional
    cl[:, a:a + c.shape[1]] = c * notional
    end = a + c.shape[1]
    if end < W:
        cl[:, end:] = cl[:, end - 1:end]
        lo[:, end:] = cl[:, end - 1:end]
    return lo, cl


def run(seed: int = 20261012) -> dict:
    d_nq, H_nq, L_nq, C_nq, n_nq = _load("MNQ")
    d_gc, H_gc, L_gc, C_gc, n_gc = _load("MGC")
    common = np.intersect1d(d_nq, d_gc)
    i_nq = np.searchsorted(d_nq, common); i_gc = np.searchsorted(d_gc, common)
    rng = np.random.default_rng(seed)
    out = {"paired_sessions": int(len(common)), "first": str(common[0]), "last": str(common[-1]), "eras": {}}
    for era, mask in (("pre_2021", common < y.ERA), ("post_2021", common >= y.ERA)):
        a, b = i_nq[mask], i_gc[mask]
        lo_q, cl_q = _leg(H_nq[a], L_nq[a], C_nq[a], MNQ_W, n_nq)
        lo_g, cl_g = _leg(H_gc[b], L_gc[b], C_gc[b], MGC_W, n_gc)
        rho = float(np.corrcoef(cl_q[:, -1], cl_g[:, -1])[0, 1])
        res = {"sessions": int(mask.sum()), "corr_daily_pnl": rho,
               "sigma_mnq": float(cl_q[:, -1].std()), "sigma_mgc": float(cl_g[:, -1].std())}
        # one account, both legs
        y.RT_COST, y.TICK_USD = 2.32 + 3.32, 0.50 + 1.00
        lo, cl = lo_q + lo_g, cl_q + cl_g
        paths = (cl, lo, cl)
        res["sigma_combined"] = float(cl[:, -1].std())
        e = z.run_eval(paths, 1, rng, True, z.CONSISTENCY, accounts=ACCOUNTS, lock=False)
        paid = z.run_funded(paths, 1, rng, True, 1, z.CAP, accounts=ACCOUNTS, live_after=3)
        res["combined"] = {"p_pass": e["p_pass"], "days_to_pass_median": e["days_to_pass_median"],
                           "expected_payout": float(paid.mean()), "p_any_payout": float((paid > 0).mean()),
                           "ev": e["p_pass"] * float(paid.mean()) - y.FEE,
                           "budget": z._budget(e["p_pass"], paid, rng)}
        # each leg alone on the SAME paired dates, for a like-for-like comparison
        for leg, (l_, c_, rt, tk) in (("mnq_alone", (lo_q, cl_q, 2.32, 0.50)),
                                     ("mgc_alone", (lo_g, cl_g, 3.32, 1.00))):
            y.RT_COST, y.TICK_USD = rt, tk
            e = z.run_eval((c_, l_, c_), 1, rng, True, z.CONSISTENCY, accounts=ACCOUNTS, lock=False)
            paid = z.run_funded((c_, l_, c_), 1, rng, True, 1, z.CAP, accounts=ACCOUNTS, live_after=3)
            res[leg] = {"p_pass": e["p_pass"], "expected_payout": float(paid.mean()),
                        "ev": e["p_pass"] * float(paid.mean()) - y.FEE,
                        "budget": z._budget(e["p_pass"], paid, rng)}
        out["eras"][era] = res
        print(era, json.dumps({k: (v["ev"] if isinstance(v, dict) and "ev" in v else v) for k, v in res.items()}),
              flush=True)
    return out


def render(r: dict) -> str:
    w: list[str] = []
    a = w.append
    a("# Y04 — MNQ New York and MGC London on ONE Tradeify account")
    a("")
    a("Generated by `python -m futuresres.reporting.y04_combined`. Tradeify's confirmed rules; drift removed; "
      "sessions paired by date; a computation, no trial. `decisions.md` §84.")
    a("")
    a(f"{r['paired_sessions']:,} sessions both instruments have complete, {r['first']} → {r['last']}.")
    a("")
    a("| era | daily $σ MNQ / MGC / combined | corr of daily P&L | policy | P(pass) | E[payout] | EV per $80 | "
      "10 evals P(net>0) | 40 evals |")
    a("|---|---|---|---|---|---|---|---|---|")
    for era, e in r["eras"].items():
        sig = f"{e['sigma_mnq']:,.0f} / {e['sigma_mgc']:,.0f} / {e['sigma_combined']:,.0f}"
        for k, label in (("combined", "**both, one account**"), ("mnq_alone", "MNQ NY alone"),
                         ("mgc_alone", "MGC London alone")):
            x = e[k]
            b = x["budget"]
            b10 = b.get("10", b.get(10)); b40 = b.get("40", b.get(40))
            a(f"| {era} | {sig} | {e['corr_daily_pnl']:+.2f} | {label} | {x['p_pass']:.1%} | "
              f"{x['expected_payout']:,.0f} | **{x['ev']:+,.0f}** | {b10['p_net_positive']:.0%} | {b40['p_net_positive']:.0%} |")
    a("")
    a("The combined minute low sums both legs' lows (conservative). Monte Carlo error ±$3–4 per EV at "
      "16,000 accounts, given the historical pool; the era-to-era difference is the better guide.")
    a("")
    return "\n".join(w)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.reporting.y04_combined")
    ap.add_argument("--log", action="store_true")
    args = ap.parse_args(argv)
    if OUT_JSON.exists() and args.log:
        r = json.loads(OUT_JSON.read_text())
    else:
        r = run()
        OUT_JSON.write_text(json.dumps(r, indent=1, default=float) + "\n")
        r = json.loads(OUT_JSON.read_text())
    OUT_MD.write_text(render(r))
    print(OUT_MD.read_text())
    if args.log:
        from futuresres.stats.trials import Trial, TrialLog
        log = TrialLog(ROOT / "measurements.jsonl")
        rec = log.append(Trial(
            trial_id=log.next_id("m"), hypothesis_id="Y-series", symbol="MNQ+MGC",
            date_range=(r["first"], r["last"]), status="completed",
            params={"kind": "structure_ev_combined_account",
                    "eras": {e: {k: (v["ev"] if isinstance(v, dict) and "ev" in v else v) for k, v in x.items()}
                             for e, x in r["eras"].items()}},
            note=("kind=computation; NOT a trial and NOT counted in N. Y04: MNQ NY and MGC London long on one "
                  "Tradeify account vs each alone. decisions.md 84."),
        ))
        print(f"logged {rec['trial_id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

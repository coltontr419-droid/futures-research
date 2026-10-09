"""Y03 - the Tradeify evaluation at zero edge, by session window, direction and instrument.

A COMPUTATION on Tradeify's confirmed rules (decisions.md 81-82) and demeaned real sessions; no market
claim, no trial. One instrument per process (the 2.7 GB machine). `--log` writes one record per product.
decisions.md 83.

    python -m futuresres.reporting.y03_sessions --product MNQ
    python -m futuresres.reporting.y03_sessions --product MGC
    python -m futuresres.reporting.y03_sessions --log

FIXED BEFORE RUNNING:
  windows    Asia 19:00-03:00 ET and London 03:00-11:30 ET - the repo's own session definitions
             (levels/definitions.py), so the names mean what they meant in earlier series; London
             overlaps the US morning by two hours, as defined. RTH 09:30-16:00, and its halves
             09:30-12:00 and 12:00-16:00 (the shorter-window check asked for after decisions.md 82).
  direction  long and short. Drift is removed, so the two differ only through the shape of the paths
             (skew, gaps, where the excursions fall). A short also gives up any real premium.
  size       one contract: 1 MNQ ($2.32 round trip, $0.50 tick) or 1 MGC ($3.32, $1.00 tick; X01).
  selection  per instrument, the cell with the highest 2015-2020 EV is the pick; its post-2021 EV is the
             confirmation. Monte Carlo error is ~$15-25 per cell, so cells closer than that are tied.
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

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
OUT_JSON: Final[Path] = ROOT / "reports" / "y03_sessions.json"
OUT_MD: Final[Path] = ROOT / "reports" / "y03_sessions.md"
PRODUCTS: Final[dict[str, dict]] = {
    "MNQ": {"series": "NQ_MNQ_spliced", "mult": 2.0, "rt": 2.32, "tick": 0.50},
    "MGC": {"series": "MGC", "mult": 10.0, "rt": 3.32, "tick": 1.00},
}
WINDOWS: Final[dict[str, tuple[int, int]]] = {       # minutes after 18:00 ET
    "asia_1900_0300": (60, 540),
    "london_0300_1130": (540, 1050),
    "rth_0930_1600": (930, 1320),
    "rth_am_0930_1200": (930, 1080),
    "rth_pm_1200_1600": (1080, 1320),
}


def run_product(product: str, seed: int = 20261010) -> dict:
    spec = PRODUCTS[product]
    y.SERIES = y.ROOT / "data" / "continuous" / f"{spec['series']}.parquet"
    y.MULT = spec["mult"]
    y.RT_COST = spec["rt"]
    y.TICK_USD = spec["tick"]
    y.WINDOWS.update(WINDOWS)
    dates, H, L, C, notional = y.load_sessions()
    rng = np.random.default_rng(seed)
    out = {"product": product, "sessions": int(len(dates)), "first": str(dates[0]), "last": str(dates[-1]),
           "notional": notional, "cells": []}
    for era, mask in (("pre_2021", dates < y.ERA), ("post_2021", dates >= y.ERA)):
        for window in WINDOWS:
            h, l, c, _ = y.window_paths(H[mask], L[mask], C[mask], window, None)
            sigma = float(c[:, -1].std() * notional)
            for direction in ("long", "short"):
                if direction == "long":
                    usd = (h * notional, l * notional, c * notional)
                else:                                   # a short's best is the long's worst
                    usd = (-l * notional, -h * notional, -c * notional)
                e = z.run_eval(usd, 1, rng, True, z.CONSISTENCY, lock=False)
                paid = z.run_funded(usd, 1, rng, True, 1, z.CAP, live_after=3)
                ev = e["p_pass"] * float(paid.mean()) - y.FEE
                out["cells"].append({"era": era, "window": window, "direction": direction,
                                     "sessions": int(mask.sum()), "daily_sigma_usd": sigma,
                                     "p_pass": e["p_pass"], "days_to_pass_median": e["days_to_pass_median"],
                                     "expected_payout": float(paid.mean()),
                                     "p_any_payout": float((paid > 0).mean()), "ev": ev})
                print(f"{product} {era:9} {window:18} {direction:5} sigma ${sigma:5.0f} pass {e['p_pass']:.3f} "
                      f"payout {paid.mean():5.0f} EV {ev:+5.0f}", flush=True)
    pre = [x for x in out["cells"] if x["era"] == "pre_2021"]
    pick = max(pre, key=lambda x: x["ev"])
    conf = next(x for x in out["cells"] if x["era"] == "post_2021" and x["window"] == pick["window"]
                and x["direction"] == pick["direction"])
    out["pick"] = {"window": pick["window"], "direction": pick["direction"], "ev_pre": pick["ev"],
                   "ev_post": conf["ev"]}
    return out


#: Contenders re-run at 4x the accounts, chosen AFTER the 4,000-account grid: the two cells stable across
#: both eras (MNQ RTH long, MGC London long), the pre-registered pick that failed to confirm (MNQ Asia
#: long), and MNQ RTH short. Re-running gives precision on those cells; it is not a new selection.
PRECISE: Final[dict[str, tuple[tuple[str, str], ...]]] = {
    "MNQ": (("rth_0930_1600", "long"), ("rth_0930_1600", "short"), ("asia_1900_0300", "long")),
    "MGC": (("london_0300_1130", "long"),),
}
PRECISE_ACCOUNTS: Final[int] = 16_000


def run_precise(product: str, seed: int = 20261011) -> list[dict]:
    spec = PRODUCTS[product]
    y.SERIES = y.ROOT / "data" / "continuous" / f"{spec['series']}.parquet"
    y.MULT, y.RT_COST, y.TICK_USD = spec["mult"], spec["rt"], spec["tick"]
    y.WINDOWS.update(WINDOWS)
    dates, H, L, C, notional = y.load_sessions()
    rng = np.random.default_rng(seed)
    out = []
    for era, mask in (("pre_2021", dates < y.ERA), ("post_2021", dates >= y.ERA)):
        for window, direction in PRECISE[product]:
            h, l, c, _ = y.window_paths(H[mask], L[mask], C[mask], window, None)
            usd = ((h * notional, l * notional, c * notional) if direction == "long"
                   else (-l * notional, -h * notional, -c * notional))
            e = z.run_eval(usd, 1, rng, True, z.CONSISTENCY, accounts=PRECISE_ACCOUNTS, lock=False)
            paid = z.run_funded(usd, 1, rng, True, 1, z.CAP, accounts=PRECISE_ACCOUNTS, live_after=3)
            ev = e["p_pass"] * float(paid.mean()) - y.FEE
            # standard error of EV: delta method over the two independent samples
            se = float(np.sqrt((paid.mean() ** 2) * e["p_pass"] * (1 - e["p_pass"]) / PRECISE_ACCOUNTS
                               + (e["p_pass"] ** 2) * paid.var() / PRECISE_ACCOUNTS))
            out.append({"product": product, "era": era, "window": window, "direction": direction,
                        "p_pass": e["p_pass"], "expected_payout": float(paid.mean()), "ev": ev, "ev_se": se,
                        "budget": z._budget(e["p_pass"], paid, rng)})
            print(f"PRECISE {product} {era} {window} {direction}: EV {ev:+.0f} ± {se:.0f}", flush=True)
    return out


def render(res: dict) -> str:
    w: list[str] = []
    a = w.append
    a("# Y03 — Tradeify evaluation at zero edge, by session, direction and instrument")
    a("")
    a("Generated by `python -m futuresres.reporting.y03_sessions`. Tradeify's confirmed rules (§81–§82); "
      "drift removed; one contract; a computation, no trial. `decisions.md` §83.")
    a("")
    for product in ("MNQ", "MGC"):
        r = res.get(product)
        if not r:
            continue
        a(f"## {product} — {r['sessions']:,} complete sessions {r['first']} → {r['last']}")
        a("")
        a("| window (ET) | daily $σ post-2021 | long 2015–20 | long post-2021 | short 2015–20 | short post-2021 |")
        a("|---|---|---|---|---|---|")
        for window in WINDOWS:
            cells = {(x["era"], x["direction"]): x for x in r["cells"] if x["window"] == window}
            sg = cells[("post_2021", "long")]["daily_sigma_usd"]
            a(f"| {window} | {sg:,.0f} | "
              + " | ".join(f"{cells[(e, d)]['ev']:+,.0f} ({cells[(e, d)]['p_pass']:.0%})"
                           for d in ("long", "short") for e in ("pre_2021", "post_2021")) + " |")
        p = r["pick"]
        a("")
        a(f"**Pick (highest 2015–20 EV): {p['window']}, {p['direction']} — {p['ev_pre']:+,.0f} → "
          f"confirmation post-2021 {p['ev_post']:+,.0f}.** Cells: EV per $80 (P(pass)); ±$15–25 MC error.")
        a("")
    if res.get("precise"):
        a("## Contenders at 16,000 accounts (precision, not a new selection)")
        a("")
        a("| product | window | direction | EV 2015–20 | EV post-2021 | 10 evals P(net>0), post-2021 | 40 evals |")
        a("|---|---|---|---|---|---|---|")
        keys = []
        for x in res["precise"]:
            k = (x["product"], x["window"], x["direction"])
            if k not in keys:
                keys.append(k)
        for k in keys:
            pre = next(x for x in res["precise"] if (x["product"], x["window"], x["direction"]) == k and x["era"] == "pre_2021")
            post = next(x for x in res["precise"] if (x["product"], x["window"], x["direction"]) == k and x["era"] == "post_2021")
            a(f"| {k[0]} | {k[1]} | {k[2]} | {pre['ev']:+,.0f} ± {pre['ev_se']:.0f} | {post['ev']:+,.0f} ± {post['ev_se']:.0f} | "
              f"{post['budget']['10']['p_net_positive'] if '10' in post['budget'] else post['budget'][10]['p_net_positive']:.0%} | "
              f"{post['budget']['40']['p_net_positive'] if '40' in post['budget'] else post['budget'][40]['p_net_positive']:.0%} |")
        a("")
    return "\n".join(w)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.reporting.y03_sessions")
    ap.add_argument("--product", choices=list(PRODUCTS))
    ap.add_argument("--log", action="store_true")
    ap.add_argument("--precise", choices=list(PRODUCTS))
    args = ap.parse_args(argv)
    res = json.loads(OUT_JSON.read_text()) if OUT_JSON.exists() else {}
    if args.precise:
        res["precise"] = [x for x in res.get("precise", []) if x["product"] != args.precise] + run_precise(args.precise)
        OUT_JSON.write_text(json.dumps(res, indent=1, default=float) + "\n")
    if args.product:
        res[args.product] = run_product(args.product)
        OUT_JSON.write_text(json.dumps(res, indent=1, default=float) + "\n")
    OUT_MD.write_text(render(res))
    print(OUT_MD.read_text())
    if args.log:
        from futuresres.stats.trials import Trial, TrialLog
        log = TrialLog(ROOT / "measurements.jsonl")
        for product, r in res.items():
            if product == "precise":
                continue
            rec = log.append(Trial(
                trial_id=log.next_id("m"), hypothesis_id="Y-series", symbol=product,
                date_range=(r["first"], r["last"]), status="completed",
                params={"kind": "structure_ev_sessions", "pick": r["pick"],
                        "cells": [{k: x[k] for k in ("era", "window", "direction", "daily_sigma_usd",
                                                     "p_pass", "expected_payout", "ev")} for x in r["cells"]]},
                note=("kind=computation; NOT a trial and NOT counted in N. Y03: Tradeify evaluation EV at "
                      "zero edge by session window, direction and instrument. decisions.md 83."),
            ))
            print(f"logged {rec['trial_id']} ({product})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

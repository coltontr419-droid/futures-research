"""A18 - the demo checker: do the live tickets behave like the backtest? decisions.md 126.

    python -m futuresres.reporting.a18_demo_check shadow_log.csv [demo_log.csv]
    python -m futuresres.reporting.a18_demo_check --export-expected      # bot/expected.json for the bot's weekly check
    python -m futuresres.reporting.a18_demo_check --review               # pull the droplet's logs; the full review (147)

For every finished ticket in the bot's shadow log (bot/schedule.py): the probability, on 2021-26 history (the same
1-minute paths as A07/A08, drift removed, stops at the stop price, a minute touching both = stop), that THIS bracket -
its take and stop in points, its contract count, its window - ends in a take, a stop or a time exit, and its expected
net P&L. Summed over the tickets: expected vs observed counts (a chi-square on three cells) and observed P&L against
the expected total with its standard deviation. Crude (MCL) uses the one-bar daily approximation (decisions.md 116),
so its expected rates are coarse. With demo_log.csv: on days marked traded, the change in the account's closing
balance against the shadow P&L - the execution gap (slippage, fills) per traded ticket.
"""

from __future__ import annotations

import argparse
import csv
import json
import datetime as dt
import math
import sys
from pathlib import Path

import numpy as np
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[3]
WINDOWS = {"MNQ": ("rth_0930_1600", 2.0), "MGC": ("london_0300_1130", 10.0)}
RT = {"MNQ": 2.32, "MGC": 3.32, "MCL": 3.32, "NKD": 4.0, "FDXM": 4.0, "ZS": 4.5}
_PATHS: dict = {}
ET = ZoneInfo("America/New_York")


def _paths(product: str):
    if product not in _PATHS:
        if product in ("NKD", "FDXM"):                      # accounts 4-5: A21's free-data paths (decisions.md 137-138)
            import futuresres.reporting.a21_more_accounts as a21
            z = np.load(a21.CACHE / f"a21_{'DAX' if product == 'FDXM' else 'NKD'}_post.npz")
            usd = float(a21.notional("DAX" if product == "FDXM" else "NKD"))
            per_pt = 5.0 * (1.12 if product == "FDXM" else 1.0)
            # one contract's GROSS $ paths, then re-expressed per "mult" so expected() can scale by points x mult x n
            _PATHS[product] = (z["h"] * usd, z["l"] * usd, z["c"] * usd, None)
        elif product == "ZS":                                # sixth (demo) account: A22's cleaned Yahoo hourly sessions,
            import futuresres.reporting.a22_more_markets as a22   # 3 points a bar (OHLC path rule), decisions.md 140-141
            p, _, _ = a22.hourly_paths("ZS")
            _PATHS[product] = (p, p, p, None)
        elif product == "MCL":
            import futuresres.reporting.a15_crude as c15
            h, l, c, _ = c15.mcl_paths("post")
            _PATHS[product] = (h, l, c, 100.0 / 1.0)          # one-MCL $ paths already
        else:
            import futuresres.reporting.a08_gold as a8
            h, l, c, _ = a8.era_paths("post", product, WINDOWS[product][0])
            _PATHS[product] = (h, l, c, None)                  # one-contract GROSS $ paths
    return _PATHS[product]


def expected(product: str, side: str, take_pts: float, stop_pts: float, n: int) -> dict:
    """P(take), P(stop), P(time exit) and the mean / SD of net P&L for one bracket on 2021-26 sessions."""
    import futuresres.reporting.a02_real as a2
    import futuresres.reporting.a15_crude as c15
    h, l, c, _ = _paths(product)
    mult = {"MNQ": 2.0, "MGC": 10.0, "MCL": 100.0, "NKD": 5.0, "FDXM": 5.0 * 1.12, "ZS": 50.0}[product]
    if side == "short":                                       # a short's high is the long's low, mirrored
        h, l, c = -l, -h, -c
    W = np.full(len(c), take_pts * mult * n); L = np.full(len(c), stop_pts * mult * n)
    a2.STOP_FILL = "level"
    if product == "MCL":
        gross, stop, take = c15.one_bar_rule(0.0)(h * n, l * n, c * n, W, L)
    else:
        gross, stop, take = a2._bracket_day(h * n, l * n, c * n, W, L)
    net = gross - RT[product] * n
    return {"p_take": float(take.mean()), "p_stop": float(stop.mean()), "p_time": float(1 - take.mean() - stop.mean()),
            "mean_net": float(net.mean()), "sd_net": float(net.std())}


def export_expected(path: Path | None = None) -> Path:
    """bot/expected.json: for every bracket the live policy can choose (W in A01's W_SET x L in the plan's menu, $100 units)
    and every product, the 2021-26 P(take), P(stop), P(time exit), mean and SD of net P&L - so the bot's weekly check needs
    no history on the droplet (decisions.md 139)."""
    import futuresres.reporting.a01_game as g
    import futuresres.reporting.a06_playbook as pb
    out = {}
    for prod, p in pb.PRODUCTS.items():
        n, cost = p["n"], p["rt"] * p["n"]
        out[prod] = {}
        for W in g.W_SET:
            for L in pb.PLAN_L_SET:
                tp = pb._pts(W * 100 + cost, n, p); sp = pb._pts(max(L * 100 - cost, 1.0), n, p)
                e = expected(prod, "long", tp, sp, n)
                out[prod][f"{W},{L}"] = [round(e[k], 4) for k in ("p_take", "p_stop", "p_time")] + [round(e["mean_net"], 1), round(e["sd_net"], 1)]
    path = path or (ROOT / "bot" / "expected.json")
    path.write_text(json.dumps(out, separators=(",", ":")))
    print(f"wrote {path}")
    return path


def check(shadow_csv: Path, demo_csv: Path | None = None) -> dict:
    rows = [r for r in csv.DictReader(open(shadow_csv)) if r["outcome"] in ("TAKE", "STOP", "TIME EXIT")]
    if not rows:
        return {"tickets": 0}
    exp = {"TAKE": 0.0, "STOP": 0.0, "TIME EXIT": 0.0}; obs = {"TAKE": 0, "STOP": 0, "TIME EXIT": 0}
    mu = var = 0.0; pnl = 0.0; per = []
    for r in rows:
        e = expected(r["product"], r["side"], float(r["take_pts"]), float(r["stop_pts"]), int(r["contracts"]))
        exp["TAKE"] += e["p_take"]; exp["STOP"] += e["p_stop"]; exp["TIME EXIT"] += e["p_time"]
        obs[r["outcome"]] += 1
        mu += e["mean_net"]; var += e["sd_net"] ** 2; pnl += float(r["pnl"])
        per.append({"entry": r["entry"], "product": r["product"], "outcome": r["outcome"], "pnl": float(r["pnl"]), **e})
    chi2 = sum((obs[k] - exp[k]) ** 2 / exp[k] for k in exp if exp[k] > 0)
    z = (pnl - mu) / math.sqrt(var) if var > 0 else float("nan")
    out = {"tickets": len(rows), "observed": obs, "expected": {k: round(v, 1) for k, v in exp.items()},
           "chi2_3cells": chi2, "chi2_p_approx": float(math.exp(-chi2 / 2)),        # 2 degrees of freedom
           "pnl_observed": pnl, "pnl_expected": mu, "pnl_sd": math.sqrt(var), "pnl_z": z, "per_ticket": per}
    if demo_csv and Path(demo_csv).exists():
        out["execution"] = execution_gap(rows, Path(demo_csv))
    return out


def _log_time(t: str) -> dt.datetime:
    """demo_log 'time': New York with offset from 2026-10-13; naive before that = the droplet's UTC clock."""
    x = dt.datetime.fromisoformat(t)
    return (x if x.tzinfo else x.replace(tzinfo=dt.timezone.utc)).astimezone(ET)


def execution_gap(shadow_rows: list[dict], demo_csv: Path) -> dict:
    """Each recorded close (EOD) against the shadow P&L of the ticket that had just ended for that product - the latest
    ticket whose entry precedes the close. Tickets marked `skipped` are left out; unmarked ones count (the user does not
    always send `!took`), and are flagged."""
    eods = [r for r in csv.DictReader(open(demo_csv)) if r["event"] == "EOD" and r["pnl"] not in ("", None)]
    shadow = {(r["product"], r["entry"]): r for r in shadow_rows}
    # every issued ticket (bot's tickets.json, pulled beside the logs): a close belongs to the latest ticket that had started
    tj = Path(demo_csv).with_name("tickets.json")
    issued = json.loads(tj.read_text()) if tj.exists() else [{"product": r["product"], "entry": r["entry"]} for r in shadow_rows]
    by_prod: dict = {}
    for r in issued:
        by_prod.setdefault(r["product"], set()).add(r["entry"])
    gaps = []
    for e in eods:
        t = _log_time(e["time"])
        started = [x for x in by_prod.get(e["product"], ()) if dt.datetime.fromisoformat(x) <= t]
        if not started or (e["product"], max(started)) not in shadow:     # its ticket is not finished / tracked yet
            continue
        r = shadow[(e["product"], max(started))]
        if r.get("traded") == "no":
            continue
        gaps.append({"product": r["product"], "exit": r["exit"], "shadow": float(r["pnl"]), "actual": float(e["pnl"]),
                     "gap": float(e["pnl"]) - float(r["pnl"]), "marked": r.get("traded") == "yes"})
    g = np.array([x["gap"] for x in gaps]) if gaps else np.array([])
    return {"traded_tickets_matched": len(gaps), "mean_gap": float(g.mean()) if len(g) else None,
            "median_gap": float(np.median(g)) if len(g) else None, "rows": gaps}


def per_product(r: dict) -> dict:
    out = {}
    for t in r.get("per_ticket", []):
        p = out.setdefault(t["product"], {"tickets": 0, "TAKE": 0, "STOP": 0, "TIME EXIT": 0, "exp_take": 0.0, "exp_stop": 0.0,
                                         "exp_time": 0.0, "pnl": 0.0, "exp_pnl": 0.0, "var": 0.0})
        p["tickets"] += 1; p[t["outcome"]] += 1; p["pnl"] += t["pnl"]
        p["exp_take"] += t["p_take"]; p["exp_stop"] += t["p_stop"]; p["exp_time"] += t["p_time"]
        p["exp_pnl"] += t["mean_net"]; p["var"] += t["sd_net"] ** 2
    return out


def accounts(state_json: Path, demo_csv: Path) -> dict:
    """Per product: phase, balance, evaluations bought, passes, payouts and fees, from the bot's state and log."""
    st = json.loads(Path(state_json).read_text())
    ev = list(csv.DictReader(open(demo_csv))) if Path(demo_csv).exists() else []
    out = {}
    for p, a in st.items():
        rows = [r for r in ev if r["product"] == p]
        out[p] = {"phase": a["phase"], "balance": a["balance"], "evals_bought": a.get("evals_bought"), "fees": a.get("fees"),
                  "passes": sum(r["event"] == "PASSED" for r in rows),
                  "payouts": sum(float(r["amount"] or 0) for r in rows if r["event"] == "PAYOUT"),
                  "closes_recorded": sum(r["event"] == "EOD" for r in rows), "paid_out": a.get("paid", 0.0)}
    return out


DEMO_DIR = ROOT / "data" / "cache" / "demo"


def pull() -> Path:
    """Copy the bot's logs and state from the droplet (read-only on the droplet; ssh host `futures-droplet`)."""
    import subprocess
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    for f in ("shadow_log.csv", "demo_log.csv", "state.json", "tickets.json"):
        subprocess.run(["scp", "-q", f"futures-droplet:/opt/futures-bot/{f}", str(DEMO_DIR / f)], check=True)
    return DEMO_DIR


def review(pull_first: bool = True) -> str:
    """The demo review in one call: pull, compare with the backtest overall and per product, execution, accounts."""
    d = pull() if pull_first else DEMO_DIR
    r = check(d / "shadow_log.csv", d / "demo_log.csv")
    w = [render(r)]
    pp = per_product(r)
    if pp:
        w += ["", "## By product (shadow-tracked; expected from the same brackets on 2021–26 history)", "",
              "| product | tickets | take / stop / time | expected | P&L | expected ± SD |", "|---|---|---|---|---|---|"]
        for p, x in sorted(pp.items()):
            w.append(f"| {p} | {x['tickets']} | {x['TAKE']} / {x['STOP']} / {x['TIME EXIT']} | {x['exp_take']:.1f} / {x['exp_stop']:.1f} / "
                     f"{x['exp_time']:.1f} | ${x['pnl']:+,.0f} | ${x['exp_pnl']:+,.0f} ± ${math.sqrt(x['var']):,.0f} |")
    if "execution" in r and r["execution"]["rows"]:
        w += ["", "## Execution: recorded close vs shadow P&L", "", "| product | ticket exit | shadow | recorded | gap | marked traded |",
              "|---|---|---|---|---|---|"]
        w += [f"| {x['product']} | {x['exit'][:16]} | ${x['shadow']:+,.2f} | ${x['actual']:+,.2f} | ${x['gap']:+,.2f} | "
              f"{'yes' if x['marked'] else 'unmarked'} |" for x in r["execution"]["rows"]]
    if (d / "state.json").exists():
        a = accounts(d / "state.json", d / "demo_log.csv")
        w += ["", "## Accounts", "", "| product | phase | balance | evaluations bought | passes | payouts | fees |", "|---|---|---|---|---|---|---|"]
        w += [f"| {p} | {x['phase']} | ${x['balance']:,.2f} | {x['evals_bought']} | {x['passes']} | ${x['payouts']:,.0f} | ${x['fees'] or 0:,.0f} |"
              for p, x in a.items()]
    text = "\n".join(w)
    (d / f"review_{dt.date.today().isoformat()}.md").write_text(text + "\n")
    return text


def render(r: dict) -> str:
    if not r.get("tickets"):
        return "No finished tickets in the shadow log yet."
    o, e = r["observed"], r["expected"]
    w = [f"# Demo check — {r['tickets']} finished tickets", "",
         "| outcome | observed | expected (2021–26 history, same brackets) |", "|---|---|---|"]
    w += [f"| {k} | {o[k]} | {e[k]} |" for k in ("TAKE", "STOP", "TIME EXIT")]
    w += ["", f"Chi-square {r['chi2_3cells']:.2f} (p ≈ {r['chi2_p_approx']:.2f}; below 0.05 means the live mix differs from history).",
          f"Shadow P&L ${r['pnl_observed']:+,.0f} against an expected ${r['pnl_expected']:+,.0f} ± ${r['pnl_sd']:,.0f} "
          f"(z {r['pnl_z']:+.2f}; zero edge, so the expected value is about minus the commissions)."]
    if "execution" in r:
        x = r["execution"]
        w += ["", f"Execution: {x['traded_tickets_matched']} traded tickets matched to closing balances; "
              + (f"mean gap actual − shadow ${x['mean_gap']:+,.2f}, median ${x['median_gap']:+,.2f} per ticket."
                 if x["mean_gap"] is not None else "none yet.")]
    return "\n".join(w)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("shadow", nargs="?"); ap.add_argument("demo", nargs="?")
    ap.add_argument("--export-expected", action="store_true")
    ap.add_argument("--review", action="store_true", help="pull the droplet's logs and print the full demo review")
    ap.add_argument("--no-pull", action="store_true", help="with --review: use the copies already in data/cache/demo")
    a = ap.parse_args(argv)
    if a.export_expected:
        export_expected(); return 0
    if a.review:
        print(review(not a.no_pull)); return 0
    print(render(check(Path(a.shadow), Path(a.demo) if a.demo else None)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

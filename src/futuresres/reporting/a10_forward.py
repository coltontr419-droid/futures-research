"""A10 - forward check on data no backtest has seen: both demo plans (4 MNQ 09:30-16:00 ET; 8 MGC 03:00-11:30 ET)
run day by day from 2026-08-28 to 2026-10-09 (batch GLBX-20261010-3KALFURKDJ). A COMPUTATION; no trial.
decisions.md 108.

    python -m futuresres.reporting.a10_forward [--log]

Unlike A03-A09, the paths here are REAL: actual dollars at each day's actual entry price, drift NOT removed - what a
trader following the playbook would have had. One account per product, starting a fresh $80 evaluation on the first
session, following `a06_playbook.ticket` each day (orders at the playbook's points; P&L gross minus commissions and
an optional slippage; stops fill AT the stop price, the user's reported execution, with the backtests'
bar-low fill shown for comparison), a failed account replaced by a new evaluation the next session, Tradeify rules as in
a02_real.sequential. Context: the historical distribution of the same 30-day stretch (2021-26 replay, drift removed).

Series: the update batch is parsed to data/parquet_update, rolled by the programme's own rule (roll.py: volume
crossover, crossover session dropped) to data/continuous_update, and the 2026-08-28 session - split across the two
purchases at 00:00 UTC - is completed with its first 120 bars from the existing series (same contract, checked).
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
import polars as pl

import futuresres.reporting.a01_game as g
import futuresres.reporting.a02_real as a2
import futuresres.reporting.a06_playbook as pb

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "a10_forward.json"
OUT_MD = ROOT / "reports" / "a10_forward.md"
UPD = ROOT / "data" / "continuous_update"
PLANS = {"MNQ": {"old": "NQ_MNQ_spliced", "window": (930, 1320)},     # minutes after 18:00 ET
         "MGC": {"old": "MGC", "window": (540, 1050)}}
FIRST = "2026-08-28"
START = 50_000.0


def forward_series(prod: str) -> Path:
    """The forward front-month series: old series' bars for the split first session + the update's."""
    target = UPD / f"{prod}_fwd.parquet"
    if target.exists():
        return target
    import futuresres.data.roll as r
    pq = ROOT / "data" / "parquet_update"
    cal = r.build_calendar(prod, r.daily_volume_streaming(pq, prod))
    new = UPD / f"{prod}_new.parquet"
    r.sink_continuous(pq, prod, cal, new)
    cols = ["ts_event", "symbol", "contract", "open", "high", "low", "close", "volume", "trades", "session"]
    head = (pl.scan_parquet(ROOT / "data" / "continuous" / f"{PLANS[prod]['old']}.parquet")
              .filter(pl.col("session") == pl.date(2026, 8, 28)).select(cols).collect())
    nw = pl.read_parquet(new).select(cols)
    first_new = nw.filter(pl.col("session") == pl.date(2026, 8, 28))["contract"].unique().to_list()
    assert head["contract"].unique().to_list() == first_new, "split session spans different contracts"
    pl.concat([head.with_columns(pl.col("trades").cast(nw.schema["trades"])), nw]).sort("ts_event").write_parquet(target)
    return target


def real_paths(prod: str):
    """Per complete window: dates, entry price, and 1-contract GROSS $ paths (h, l, c) - real drift, real prices."""
    mult = pb.PRODUCTS[prod]["mult"]
    a, b = PLANS[prod]["window"]
    et = pl.col("ts_event").dt.convert_time_zone("America/New_York")
    df = (pl.scan_parquet(forward_series(prod))
            .with_columns(((et.dt.hour().cast(pl.Int32) * 60 + et.dt.minute().cast(pl.Int32) - 1080) % 1440).alias("m"))
            .filter((pl.col("m") >= a - 1) & (pl.col("m") < b)).sort("ts_event").collect())
    dates, entry, H, L, C = [], [], [], [], []
    for (s,), d in df.group_by(["session"], maintain_order=True):
        m = d["m"].to_numpy()
        if m[0] != a - 1 or len(m) < 0.9 * (b - a + 1):
            continue                                      # need the entry minute and a near-complete window
        p0 = float(d["close"][0])                         # the close of minute a-1 = the price at the window's start
        mm = m[1:] - a
        hh = np.full(b - a, np.nan); ll = hh.copy(); cc = hh.copy()
        hh[mm] = d["high"].to_numpy()[1:]; ll[mm] = d["low"].to_numpy()[1:]; cc[mm] = d["close"].to_numpy()[1:]
        idx = np.where(np.isnan(cc), 0, np.arange(len(cc))); np.maximum.accumulate(idx, out=idx)
        cc = np.where(np.isnan(cc[0]), p0, cc)[idx] if np.isnan(cc[0]) else cc[idx]
        hh = np.where(np.isnan(hh), cc, hh); ll = np.where(np.isnan(ll), cc, ll)
        dates.append(str(s)); entry.append(p0)
        H.append((hh - p0) * mult); L.append((ll - p0) * mult); C.append((cc - p0) * mult)
    return dates, np.array(entry), np.array(H, np.float32), np.array(L, np.float32), np.array(C, np.float32)


def walk(prod: str, slip: float = 0.0) -> dict:
    """One trader: back-to-back accounts from the first session, following the playbook ticket."""
    p = pb.PRODUCTS[prod]; n = p["n"]; cost = p["rt"] * n
    dates, entry, H, L, C = real_paths(prod)
    phase, eq, pk, best, npay = "eval", START, START, 0.0, 0
    fees, paid, accounts, log = 80.0, 0.0, 1, []
    for i, d in enumerate(dates):
        t = pb.ticket(phase, eq, pk, best, npay, n, prod)
        row = {"date": d, "phase": phase, "balance_open": round(eq, 2), "entry": entry[i]}
        if t.get("finished"):               # within one day's costs of the floor: the account is over (decisions.md 113)
            row.update(action="finished", pnl=0.0, event=f"{phase} FINISHED (at the floor)")
            phase, eq, pk, best, npay = "eval", START, START, 0.0, 0
            if i + 1 < len(dates):
                fees += 80.0; accounts += 1
            log.append(row); continue
        if not t["trade"]:
            row.update(action="no trade", pnl=0.0); log.append(row); continue
        # orders at the playbook's points (what the trader actually enters), on this day's real path
        Wd = np.array([t["take_points"] * p["mult"] * n]); Ld = np.array([t["stop_points"] * p["mult"] * n])
        gross, stop, take = a2._bracket_day(H[i:i + 1] * n, L[i:i + 1] * n, C[i:i + 1] * n, Wd, Ld)
        pnl = float(gross[0]) - cost - slip
        exit_ = "take" if take[0] else "stop" if stop[0] else "close"
        floor = pk - 2000 if phase == "eval" else (START if pk >= START + 2000 else pk - 2000)
        eq += pnl; pk = max(pk, eq)
        row.update(take=t["take_net"], stop=t["stop_net"], exit=exit_, pnl=round(pnl, 2), balance_close=round(eq, 2))
        if eq <= floor:
            row["event"] = f"{phase} FAILED"; phase, eq, pk, best, npay = "eval", START, START, 0.0, 0
            if i + 1 < len(dates):
                fees += 80.0; accounts += 1
        elif phase == "eval":
            best = max(best, pnl)
            if eq - START >= 3000 and best <= 0.40 * (eq - START):
                row["event"] = "PASSED"; phase, eq, pk, best, npay = "funded", START, START, 0.0, 0
        else:
            amt = max(eq - (START + 2000), 0.0)
            amt = amt if npay >= 3 else min(amt, 1250.0)
            if amt > 0:
                paid += 0.9 * amt; eq -= amt; npay += 1; row["event"] = f"PAYOUT ${amt:,.0f} (you get ${0.9*amt:,.0f})"
        log.append(row)
    exits = [r["exit"] for r in log if "exit" in r]
    return {"product": prod, "contracts": n, "slippage": slip, "sessions": len(dates), "first": dates[0], "last": dates[-1],
            "accounts_bought": accounts, "fees": fees, "paid_to_you": paid, "net": paid - fees,
            "end_phase": phase, "end_balance": eq, "payouts": npay,
            "exits": {k: exits.count(k) for k in ("take", "stop", "close")}, "log": log}


def history_30(prod: str, days: int) -> dict:
    """The same plan's distribution over `days`-session stretches, 2021-26 replay, drift removed (A07/A08 paths)."""
    import futuresres.reporting.a08_gold as a8
    win = "rth_0930_1600" if prod == "MNQ" else "london_0300_1130"
    h, l, c, _ = a8.era_paths("post", prod, win)
    p = pb.PRODUCTS[prod]; n = p["n"]; tot = np.float32(p["rt"] * n)
    a2._PATHS["p"] = ((h * n - (tot - a8.RT_ENGINE)).astype(np.float32), (l * n - tot).astype(np.float32), (c * n - tot).astype(np.float32))
    r = a2.sequential(1, "replay", window=days)
    a2._PATHS.clear()
    return {k: r[k] for k in ("p_any_payout", "mean_net", "p_net_positive", "net_p10_p50_p90", "mean_attempts")}


def run() -> dict:
    warnings.filterwarnings("ignore")
    with contextlib.redirect_stdout(io.StringIO()), np.errstate(all="ignore"):
        g.solve_all(21, keep_policy_at=21); g.solve_funded(21, "dollars", keep_policy_at=21)
    out = {}
    for prod in PLANS:
        a2.STOP_FILL = "level"                 # the user's execution: stops fill at the stop, within ~$10
        w0, w10 = walk(prod, 0.0), walk(prod, 10.0)
        hist_level = history_30(prod, w0["sessions"])
        a2.STOP_FILL = "bar_low"               # the backtests' conservative assumption, for comparison
        wb = walk(prod, 0.0)
        out[prod] = {"forward": w0, "forward_slip10": {k: v for k, v in w10.items() if k != "log"},
                     "forward_bar_low": {k: v for k, v in wb.items() if k != "log"},
                     "history_same_length": hist_level, "history_same_length_bar_low": history_30(prod, w0["sessions"])}
    return out


def render(r: dict) -> str:
    w = ["# Forward check: both demo plans on unseen data (2026-08-28 → 2026-10-09)", "",
         "Generated by `python -m futuresres.reporting.a10_forward`. Real prices, real drift. `decisions.md` §108.", ""]
    for prod, v in r.items():
        f, s, h = v["forward"], v["forward_slip10"], v["history_same_length"]
        w += [f"## {f['contracts']} {prod}", "",
              f"{f['sessions']} sessions. Accounts bought {f['accounts_bought']} (fees ${f['fees']:,.0f}); paid to you "
              f"${f['paid_to_you']:,.0f}; **net {f['net']:+,.0f}** (with $10 slippage a trade: {s['net']:+,.0f}). Ends in "
              f"{f['end_phase']} at ${f['end_balance']:,.0f}. Exits: {f['exits']}. Stops fill at the stop price.", "",
              f"Under the backtests' bar-low stop fill instead: accounts {v['forward_bar_low']['accounts_bought']}, net "
              f"{v['forward_bar_low']['net']:+,.0f}, ends {v['forward_bar_low']['end_phase']} at ${v['forward_bar_low']['end_balance']:,.0f}.", "",
              f"History, the same {f['sessions']}-session stretch (2021–26 replay, stop-price fills): P(payout) {h['p_any_payout']:.0%}, mean net "
              f"{h['mean_net']:+,.0f}, P(net > 0) {h['p_net_positive']:.0%}, net 10/50/90 "
              + " / ".join(f"{x:+,.0f}" for x in h["net_p10_p50_p90"]) + ".", "",
              "| date | phase | open bal | take / stop | exit | P&L | close bal | event |", "|---|---|---|---|---|---|---|---|"]
        for x in f["log"]:
            w.append(f"| {x['date']} | {x['phase']} | {x['balance_open']:,.0f} | "
                     + (f"+{x['take']:,.0f} / −{x['stop']:,.0f} | {x['exit']} | {x['pnl']:+,.0f} | {x['balance_close']:,.0f}" if "exit" in x else "— | no trade | 0 | ")
                     + f" | {x.get('event', '')} |")
        w.append("")
    return "\n".join(w)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--log", action="store_true")
    a = ap.parse_args(argv)
    r = run()
    OUT.write_text(json.dumps(r, indent=1, default=float) + "\n"); OUT_MD.write_text(render(r))
    print(OUT_MD.read_text())
    if a.log:
        from futuresres.stats.trials import Trial, TrialLog
        log = TrialLog(ROOT / "measurements.jsonl")
        rec = log.append(Trial(trial_id=log.next_id("m"), hypothesis_id="A-series", symbol="MNQ+MGC",
                               date_range=(FIRST, r["MNQ"]["forward"]["last"]), status="completed",
                               params={"kind": "forward_unseen_data", **{k: {kk: vv for kk, vv in v.items()} for k, v in r.items()}},
                               note="kind=computation; NOT a trial. A10: both demo plans on 2026-08-28..10-09, unseen data, real prices. decisions.md 108."))
        print("logged", rec["trial_id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())

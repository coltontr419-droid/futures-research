"""Y05 (historical) - replay Tradeify accounts through REAL history, in order, from every start date.

The forward demo test (Y05) would take months; this replays the same policy through the history on
disk instead. Unlike Y01-Y04, sessions are NOT resampled: each account walks forward day by day through
the actual sequence, so volatility clustering, trends and regimes (2020, 2022) are kept.

    python -m futuresres.reporting.y05_replay --product MNQ     # one product per process
    python -m futuresres.reporting.y05_replay --product MGC
    python -m futuresres.reporting.y05_replay --log

TWO VERSIONS, reported side by side:
  actual     what would have happened - the market's real moves INCLUDED. For a long index position this
             contains the 2016-2026 rise. DESCRIPTIVE ONLY: it is not evidence of an edge, it asserts no
             premium, and it is not counted as one (decisions.md 79 decision 1).
  demeaned   each era's mean window return removed, as in Y01-Y04: the rule structure alone, in real order.

FIXED BEFORE RUNNING: the two stable policies of decisions.md 83 - MNQ 09:30-16:00 long and MGC London
03:00-11:30 long - one contract, separate accounts (decisions.md 84); Tradeify's confirmed rules
(decisions.md 81-82): evaluation floor trails the end-of-day balance with no lock, intraday breach
fails, 40% consistency rule; funded floor locks at $50,000 from $52,000, daily payouts above $52,000,
$1,250 cap until 3 payouts, 90%; $80 fee.

START DATES: every complete session from the first to the last that leaves 600 sessions of room (an
evaluation plus a 504-session funded period). An account still open when the data ends is CENSORED and
reported as such. Accounts from adjacent start dates share most of their days, so the count of start
dates overstates the independent evidence; results are also given by start year.
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
OUT_JSON: Final[Path] = ROOT / "reports" / "y05_replay.json"
OUT_MD: Final[Path] = ROOT / "reports" / "y05_replay.md"
POLICY: Final[dict[str, str]] = {"MNQ": "rth_0930_1600", "MGC": "london_0300_1130"}
ROOM: Final[int] = 600


def _replay_eval(paths, starts):
    """Each account i walks sessions starts[i], starts[i]+1, ... until it passes or fails."""
    _, l_all, c_all = paths
    S = len(c_all)
    A = len(starts)
    eq = np.full(A, y.START); peak = eq.copy(); best = np.zeros(A)
    state = np.zeros(A, int)                      # 0 open, 1 passed, -1 failed, 2 censored
    end_idx = np.full(A, -1); days = np.zeros(A, int)
    for k in range(S):
        act = np.flatnonzero(state == 0)
        if not len(act):
            break
        idx = starts[act] + k
        out = idx >= S
        state[act[out]] = 2
        act, idx = act[~out], idx[~out]
        if not len(act):
            break
        ne, pnl, br = z.day_eod(eq[act], peak[act], c_all[idx], l_all[idx], c_all[idx], 1, True, False)
        eq[act] = ne; days[act] += 1
        best[act] = np.maximum(best[act], pnl)
        peak[act] = np.maximum(peak[act], ne)
        profit = ne - y.START
        ok = (~br) & (profit >= y.TARGET) & (best[act] <= z.CONSISTENCY * profit)
        state[act[br]] = -1
        state[act[ok]] = 1
        end_idx[act[br | ok]] = idx[br | ok]
    return state, end_idx, days


def _replay_funded(paths, fstarts):
    """Funded accounts from session fstarts[i]; daily payouts, cap until 3 payouts; 504 sessions."""
    _, l_all, c_all = paths
    S = len(c_all)
    A = len(fstarts)
    eq = np.full(A, y.START); peak = eq.copy(); paid = np.zeros(A); npay = np.zeros(A, int)
    alive = np.ones(A, bool); censored = np.zeros(A, bool)
    for k in range(y.FUNDED_DAYS):
        act = np.flatnonzero(alive & ~censored)
        if not len(act):
            break
        idx = fstarts[act] + k
        out = idx >= S
        censored[act[out]] = True
        act, idx = act[~out], idx[~out]
        if not len(act):
            break
        ne, _, br = z.day_eod(eq[act], peak[act], c_all[idx], l_all[idx], c_all[idx], 1, True, True)
        eq[act] = ne
        peak[act] = np.maximum(peak[act], ne)
        alive[act[br]] = False
        live = act[~br]
        excess = np.maximum(eq[live] - (y.START + y.LOCK), 0.0)
        excess = np.where(npay[live] >= 3, excess, np.minimum(excess, z.CAP))
        npay[live] += excess > 0
        paid[live] += y.SPLIT * excess
        eq[live] -= excess
    return paid, alive, censored, npay


BLOCKS: Final[tuple[int, ...]] = (1, 21, 63, 252)
BLOCK_ACCOUNTS: Final[int] = 8_000


class _BlockIndex:
    """Per-account session index for a stationary-free block bootstrap: runs of `block` consecutive real
    sessions, each run starting at a random session; block 1 is the independent-day resampling of Y01-Y04."""

    def __init__(self, rng, S: int, accounts: int, block: int):
        self.rng, self.S, self.block = rng, S, block
        self.pos = rng.integers(0, S, accounts)
        self.left = np.full(accounts, block)

    def take(self, act: np.ndarray) -> np.ndarray:
        jump = (self.left[act] <= 0) | (self.pos[act] >= self.S)
        if jump.any():
            j = act[jump]
            self.pos[j] = self.rng.integers(0, self.S, len(j)); self.left[j] = self.block
        idx = self.pos[act].copy()
        self.pos[act] += 1; self.left[act] -= 1
        return idx


def _bootstrap(paths, block: int, rng) -> dict:
    _, l_all, c_all = paths
    S = len(c_all); A = BLOCK_ACCOUNTS
    bi = _BlockIndex(rng, S, A, block)
    eq = np.full(A, y.START); peak = eq.copy(); best = np.zeros(A)
    open_ = np.ones(A, bool); passed = np.zeros(A, bool)
    for _ in range(z.EVAL_MAX):
        act = np.flatnonzero(open_)
        if not len(act):
            break
        idx = bi.take(act)
        ne, pnl, br = z.day_eod(eq[act], peak[act], c_all[idx], l_all[idx], c_all[idx], 1, True, False)
        eq[act] = ne; best[act] = np.maximum(best[act], pnl); peak[act] = np.maximum(peak[act], ne)
        profit = ne - y.START
        ok = (~br) & (profit >= y.TARGET) & (best[act] <= z.CONSISTENCY * profit)
        open_[act[br | ok]] = False; passed[act[ok]] = True
    # funded accounts CONTINUE the same block stream from the session after passing
    fa = np.flatnonzero(passed)
    eqf = np.full(len(fa), y.START); pkf = eqf.copy(); paid = np.zeros(len(fa)); npay = np.zeros(len(fa), int)
    alive = np.ones(len(fa), bool)
    for _ in range(y.FUNDED_DAYS):
        act = np.flatnonzero(alive)
        if not len(act):
            break
        idx = bi.take(fa[act])
        ne, _, br = z.day_eod(eqf[act], pkf[act], c_all[idx], l_all[idx], c_all[idx], 1, True, True)
        eqf[act] = ne; pkf[act] = np.maximum(pkf[act], ne); alive[act[br]] = False
        live = act[~br]
        ex = np.maximum(eqf[live] - (y.START + y.LOCK), 0.0)
        ex = np.where(npay[live] >= 3, ex, np.minimum(ex, z.CAP))
        npay[live] += ex > 0; paid[live] += y.SPLIT * ex; eqf[live] -= ex
    net = np.full(A, -y.FEE); net[fa] += paid
    se = float(net.std(ddof=1) / np.sqrt(A))
    return {"block": block, "p_pass": float(passed.mean()), "ev": float(net.mean()), "ev_se": se,
            "mean_payout_given_pass": float(paid.mean()) if len(fa) else 0.0}


def run_blocks(product: str, seed: int = 20261013) -> dict:
    """Demeaned, post-2021 and pre-2021 separately; EV against block length."""
    spec = s3.PRODUCTS[product]
    y.SERIES = y.ROOT / "data" / "continuous" / f"{spec['series']}.parquet"
    y.MULT, y.RT_COST, y.TICK_USD = spec["mult"], spec["rt"], spec["tick"]
    y.WINDOWS.update(s3.WINDOWS)
    dates, H, L, C, notional = y.load_sessions()
    rng = np.random.default_rng(seed)
    out = {}
    for era, mask in (("pre_2021", dates < y.ERA), ("post_2021", dates >= y.ERA)):
        h, l, c, _ = y.window_paths(H[mask], L[mask], C[mask], POLICY[product], None)
        paths = (c * notional, l * notional, c * notional)
        out[era] = []
        for b in BLOCKS:
            r = _bootstrap(paths, b, rng)
            out[era].append(r)
            print(f"{product} {era} block {b:3d}: pass {r['p_pass']:.3f} EV {r['ev']:+.0f} ± {r['ev_se']:.0f}",
                  flush=True)
    return out


def run_product(product: str) -> dict:
    spec = s3.PRODUCTS[product]
    y.SERIES = y.ROOT / "data" / "continuous" / f"{spec['series']}.parquet"
    y.MULT, y.RT_COST, y.TICK_USD = spec["mult"], spec["rt"], spec["tick"]
    y.WINDOWS.update(s3.WINDOWS)
    dates, H, L, C, notional = y.load_sessions()
    window = POLICY[product]
    out = {"product": product, "window": window, "sessions": int(len(dates)), "first": str(dates[0]),
           "last": str(dates[-1]), "versions": {}}
    starts = np.arange(0, len(dates) - ROOM)
    for version in ("actual", "demeaned"):
        parts = []
        for era_mask in (dates < y.ERA, dates >= y.ERA):
            h, l, c, mu = y.window_paths(H[era_mask], L[era_mask], C[era_mask], window, None)
            if version == "actual":                 # undo the demeaning: re-add the era's own mean
                ramp = np.arange(1, c.shape[1] + 1, dtype=np.float32) / c.shape[1]
                l = l + mu * ramp; c = c + mu * ramp
            parts.append((l * notional, c * notional))
        l_all = np.concatenate([p[0] for p in parts]); c_all = np.concatenate([p[1] for p in parts])
        paths = (c_all, l_all, c_all)
        state, end_idx, days = _replay_eval(paths, starts)
        passed = state == 1
        paid = np.zeros(len(starts)); f_alive = np.zeros(len(starts), bool); f_cens = np.zeros(len(starts), bool)
        if passed.any():
            p_, a_, c_, _ = _replay_funded(paths, end_idx[passed] + 1)
            paid[passed] = p_; f_alive[passed] = a_; f_cens[passed] = c_
        net = paid - y.FEE
        years = dates[starts].astype("datetime64[Y]").astype(int) + 1970
        by_year = {}
        for yr in np.unique(years):
            m = years == yr
            by_year[int(yr)] = {"starts": int(m.sum()), "p_pass": float(passed[m].mean()),
                                "ev": float(net[m].mean()), "p_net_positive": float((net[m] > 0).mean())}
        out["versions"][version] = {
            "start_dates": int(len(starts)), "first_start": str(dates[starts[0]]),
            "last_start": str(dates[starts[-1]]),
            "p_pass": float(passed.mean()), "p_fail": float((state == -1).mean()),
            "p_eval_censored": float((state == 2).mean()),
            "days_to_pass_median": float(np.median(days[passed])) if passed.any() else None,
            "p_any_payout_given_pass": float((paid[passed] > 0).mean()) if passed.any() else None,
            "mean_payout_given_pass": float(paid[passed].mean()) if passed.any() else None,
            "p_funded_censored_given_pass": float(f_cens[passed].mean()) if passed.any() else None,
            "ev": float(net.mean()), "p_net_positive": float((net > 0).mean()),
            "net_p95": float(np.quantile(net, 0.95)), "net_max": float(net.max()),
            "by_start_year": by_year,
        }
        v = out["versions"][version]
        print(f"{product} {version:8} starts {v['start_dates']} pass {v['p_pass']:.3f} EV {v['ev']:+.0f} "
              f"net>0 {v['p_net_positive']:.3f}", flush=True)
    return out


def render(res: dict) -> str:
    w: list[str] = []
    a = w.append
    a("# Y05 (historical) — Tradeify accounts replayed through real history, every start date")
    a("")
    a("Generated by `python -m futuresres.reporting.y05_replay`. Sessions in their real order, not "
      "resampled. **actual** includes the market's real moves and is descriptive only — not evidence of an "
      "edge; **demeaned** is the rule structure alone. `decisions.md` §85.")
    a("")
    if res.get("blocks"):
        a("## Block bootstrap — does real-order clustering lower the value? (drift removed)")
        a("")
        a("Accounts built from random runs of consecutive real sessions; run length 1 is the independent-day "
          "resampling of Y01–Y04. 8,000 accounts per cell; ± is the standard error of EV.")
        a("")
        a("| product | era | " + " | ".join(f"runs of {b}" for b in BLOCKS) + " |")
        a("|---|---|" + "---|" * len(BLOCKS))
        for prod, eras in res["blocks"].items():
            for era, rows in eras.items():
                a(f"| {prod} | {era} | " + " | ".join(f"{x['ev']:+,.0f} ± {x['ev_se']:.0f} ({x['p_pass']:.0%})"
                                                      for x in rows) + " |")
        a("")
    for product in ("MNQ", "MGC"):
        r = res.get(product)
        if not r:
            continue
        a(f"## {product} — {r['window']}, long, one contract")
        a("")
        a("| version | start dates | P(pass) | P(fail) | eval still open at data end | median days to pass | "
          "payout given pass (mean) | P(any payout given pass) | EV per $80 | P(account net > 0) |")
        a("|---|---|---|---|---|---|---|---|---|---|")
        for ver in ("actual", "demeaned"):
            v = r["versions"][ver]
            a(f"| {ver} | {v['start_dates']:,} ({v['first_start']} → {v['last_start']}) | {v['p_pass']:.1%} | "
              f"{v['p_fail']:.1%} | {v['p_eval_censored']:.1%} | {v['days_to_pass_median']:.0f} | "
              f"${v['mean_payout_given_pass']:,.0f} | {v['p_any_payout_given_pass']:.0%} | **{v['ev']:+,.0f}** | "
              f"{v['p_net_positive']:.0%} |")
        a("")
        a("**By start year** — EV per $80 (P(pass)):")
        a("")
        yrs = sorted(r["versions"]["actual"]["by_start_year"], key=int)
        a("| version | " + " | ".join(str(yy) for yy in yrs) + " |")
        a("|---|" + "---|" * len(yrs))
        for ver in ("actual", "demeaned"):
            by = r["versions"][ver]["by_start_year"]
            a(f"| {ver} | " + " | ".join(f"{by[yy]['ev']:+,.0f} ({by[yy]['p_pass']:.0%})" for yy in yrs) + " |")
        a("")
    return "\n".join(w)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.reporting.y05_replay")
    ap.add_argument("--product", choices=list(POLICY))
    ap.add_argument("--log", action="store_true")
    ap.add_argument("--blocks", choices=list(POLICY))
    args = ap.parse_args(argv)
    res = json.loads(OUT_JSON.read_text()) if OUT_JSON.exists() else {}
    if args.blocks:
        res.setdefault("blocks", {})[args.blocks] = run_blocks(args.blocks)
        OUT_JSON.write_text(json.dumps(res, indent=1, default=float) + "\n")
        res = json.loads(OUT_JSON.read_text())
    if args.product:
        res[args.product] = run_product(args.product)
        OUT_JSON.write_text(json.dumps(res, indent=1, default=float) + "\n")
        res = json.loads(OUT_JSON.read_text())
    OUT_MD.write_text(render(res))
    print(OUT_MD.read_text())
    if args.log:
        from futuresres.stats.trials import Trial, TrialLog
        log = TrialLog(ROOT / "measurements.jsonl")
        for product, r in res.items():
            if product == "blocks":
                continue
            rec = log.append(Trial(
                trial_id=log.next_id("m"), hypothesis_id="Y-series", symbol=product,
                date_range=(r["first"], r["last"]), status="completed",
                params={"kind": "historical_replay", "window": r["window"],
                        "block_bootstrap": res.get("blocks", {}).get(product),
                        "versions": {k: {kk: vv for kk, vv in v.items() if kk != "by_start_year"}
                                     for k, v in r["versions"].items()}},
                note=("kind=computation; NOT a trial and NOT counted in N. Y05 historical replay of a policy "
                      "fixed in decisions.md 83 through real history from every start date; the 'actual' "
                      "version is descriptive and asserts no premium. decisions.md 85."),
            ))
            print(f"logged {rec['trial_id']} ({product})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""A121 (decisions.md 1091): the A120 rule-fitted, zero-edge strategy on more prop firms that allow bots. No trial.

Same engine and protocol as A120 (MNQ RTH paths, side randomised daily, one fixed bracket per stage, chosen on one era and scored on
the other), with the open profit fed to the trailing drawdown wherever a firm trails intraday, and each firm's daily loss limit
bounding the stop. Take Profit Trader PRO and Alpha Futures are left out: both prohibit bots. Rules are third-party summaries
(2026-08..10); doubtful ones are bracketed by two variants. References at the same settings: Tradeify Select (the live plan's firm,
at MNQ, not NKD) and Topstep XFA Consistency at the user-verified terms (§1090).

    python -m futuresres.reporting.a121_more_firms
"""

from __future__ import annotations

import itertools
import json
import sys
import warnings

import numpy as np

import futuresres.reporting.a120_firm_strategies as a120
from futuresres.reporting.a120_firm_strategies import FIRMS as F120, H, L_GRID, RT, ROOT, SEEDS, W_GRID, outcomes, paths, run

_bul_ft = dict(e_skip=True, e_fee=268.40, e_month=0.0, act=0.0, e_target=0, e_dd=2250, e_cons=None, e_cons_of="profit", e_dll=None,
               e_min_days=1, f_dd=2250, f_lock=100, f_dll=1200, q_days=0, q_amt=0, f_cons=[0.20, 0.25, 0.30], f_target=[3000, 2000],
               buffer=0, pay_frac=None, caps=[2000, 2000, 2000, 2500], cap_rule="above_buffer", pmin=1000, split=1.0, max_pay=99,
               floor_after_pay=None, intraday=True)
_bul_mo = dict(e_fee=78.65, e_month=0.0, act=0.0, e_target=2250, e_dd=3000, e_cons=None, e_cons_of="profit", e_dll=1200, e_min_days=1,
               f_dd=3000, f_lock=100, f_dll=1200, q_days=5, q_amt=150, f_cons=0.35, f_target=[3000, 0], buffer=3100, pay_frac=None,
               caps=[2000, 2000, 2000, 2500], cap_rule="above_buffer", pmin=1000, split=1.0, max_pay=99, floor_after_pay=None)
_mff_rapid = dict(e_fee=0.0, e_month=157.0, act=0.0, e_target=3000, e_dd=2000, e_cons=0.50, e_cons_of="profit", e_dll=None, e_min_days=2,
                  f_dd=2000, f_lock=100, q_days=0, q_amt=0, f_cons=None, buffer=2100, pay_frac=None, caps=[1e9], cap_rule="above_buffer",
                  pmin=500, split=0.9, max_pay=99, floor_after_pay=None, intraday="funded")

FIRMS = {
    "Tradeify Select Daily (ref, MNQ)": F120["Tradeify Select Daily (ref)"],
    "Topstep XFA Consistency ($59, DLL)": dict(F120["Topstep XFA Consistency"], e_month=59.0, e_dll=1000, api_month=29.0, intraday=True,
                                               caps=[6000]),
    "MFF Rapid ($157/mo)": _mff_rapid,
    "MFF Rapid ($79/mo, 50% code)": dict(_mff_rapid, e_month=79.0),
    "Bulenox Momentum ($78.65, reserve $3,100)": _bul_mo,
    "Bulenox Momentum ($143 list, reserve $3,000)": dict(_bul_mo, e_fee=143.0, buffer=3000),
    "Bulenox Fast Track ($268.40, no reserve)": _bul_ft,
    "Bulenox Fast Track ($488 list, reserve $2,350)": dict(_bul_ft, e_fee=488.0, buffer=2350),
    # help-center terms (copilink, 2026-10): $2,000 drawdown locking at +$100, no reserve beyond it, consistency per payout cycle
    "Bulenox Fast Track Opt 1 (intraday, no DLL)": dict(_bul_ft, e_dd=2000, f_dd=2000, f_dll=None, buffer=100),
    "Bulenox Fast Track Opt 2 (EOD, $1,200 DLL)": dict(_bul_ft, e_dd=2000, f_dd=2000, buffer=100, intraday=False),
    "Bulenox Fast Track Opt 1, 90% split": dict(_bul_ft, e_dd=2000, f_dd=2000, f_dll=None, buffer=100, split=0.9),
}


def value(F, h, l, c, We, Le, Wf, Lf, starts) -> float:
    out = []
    for seed in SEEDS:
        rng = np.random.default_rng(seed); side = rng.random(len(c)) < 0.5
        def pnl(W, L):
            n = max(1, int(round(max(W, L) / 600.0)))
            lo, ml = outcomes(h, l, c, W / n, L / n, mfe=True); sh, ms = outcomes(-l, -h, -c, W / n, L / n, mfe=True)
            return n * np.where(side, lo, sh) - n * RT, n * np.where(side, ml, ms)
        pe, me = pnl(We, Le); pf, mf = pnl(Wf, Lf)
        out.append(run(F, pe, pf, starts, me, mf).mean())
    return float(np.mean(out))


def main(only: str = "") -> int:
    warnings.filterwarnings("ignore")
    E = {era: paths(era) for era in ("pre", "post")}
    res = {}
    for name, F in FIRMS.items():
        if only not in name:
            continue
        res[name] = {}
        okE = lambda L: not F["e_dll"] or L <= F["e_dll"]
        okF = lambda L: not F.get("f_dll") or L <= F["f_dll"]
        egrid = [(300, 650)] if F.get("e_skip") else [(w, l) for w, l in itertools.product(W_GRID, L_GRID) if okE(l)]
        fgrid = [(w, l) for w, l in itertools.product(W_GRID, L_GRID) if okF(l)]
        for sel, oth in (("pre", "post"), ("post", "pre")):
            h, l, c = E[sel]; starts = np.arange(0, len(c) - H, 2)
            ge = {k: value(F, h, l, c, *k, 300, 650, starts) for k in egrid}
            be = max(ge, key=ge.get)
            gf = {k: value(F, h, l, c, *be, *k, starts) for k in fgrid}
            bf = max(gf, key=gf.get)
            ge2 = {k: value(F, h, l, c, *k, *bf, starts) for k in sorted(ge, key=ge.get, reverse=True)[:12]}
            be = max(ge2, key=ge2.get)
            h2, l2, c2 = E[oth]; starts2 = np.arange(0, len(c2) - H, 2)
            v_sel = value(F, h, l, c, *be, *bf, starts); v_oth = value(F, h2, l2, c2, *be, *bf, starts2)
            res[name][f"chosen_on_{sel}"] = {"eval": be, "funded": bf, f"value_{sel}": v_sel, f"value_{oth}": v_oth}
            print(f"{name:46} chosen on {sel}: eval {be}, funded {bf} | {sel} {v_sel:+8,.0f} | {oth} {v_oth:+8,.0f}", flush=True)
    out = ROOT / "reports" / "a121_more_firms.json"
    old = json.loads(out.read_text()) if out.exists() else {}
    out.write_text(json.dumps(old | res, indent=1, default=str) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(" ".join(sys.argv[1:])))

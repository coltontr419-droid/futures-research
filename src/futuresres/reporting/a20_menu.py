"""A20 - longer planning horizons again, with the solver restricted to stops of at least $500 (decisions.md 135-136): A19
showed long horizons buy tight stops that only work in the cost-free fair-coin model. Menus: the full A01 menu (L in {2,4,5,6,8,
10} x $100) and the restricted one (L in {5,6,8,10}); horizons He/Hf in {21/21, 21/63, 21/126, 42/21, 42/63}. Replayed as A19.
A COMPUTATION; zero edge; no trial.

    python -m futuresres.reporting.a20_menu --era post ; --era pre ; --log
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
from futuresres.reporting.a19_horizon import PLANS, _row

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "a20_menu.json"
MENUS = {"full": (2, 4, 5, 6, 8, 10), "stops>=500": (5, 6, 8, 10)}
COMBOS = ((21, 21), (21, 63), (21, 126), (42, 21), (42, 63))
WINDOWS = (84, 252)


def run(era: str) -> dict:
    warnings.filterwarnings("ignore")
    a2.STOP_FILL = "level"
    paths = {}
    for prod, (win, n, rt) in PLANS.items():
        h, l, c, _ = a8.era_paths(era, prod, win)
        tot = np.float32(n * rt)
        paths[prod] = ((h * n - (tot - a8.RT_ENGINE)).astype(np.float32), (l * n - tot).astype(np.float32), (c * n - tot).astype(np.float32))
    out = {}
    saved = g.L_SET
    for menu, lset in MENUS.items():
        g.L_SET = lset
        pe, pf = {}, {}
        with contextlib.redirect_stdout(io.StringIO()), np.errstate(all="ignore"):
            for he in sorted({c[0] for c in COMBOS}):
                g.solve_all(he, keep_policy_at=he); pe[he] = g.POLICY["eval"].copy()
            for hf in sorted({c[1] for c in COMBOS}):
                g.solve_funded(hf, "dollars", keep_policy_at=hf); pf[hf] = g.POLICY["funded"].copy()
        for he, hf in COMBOS:
            if menu == "full" and (he, hf) != (21, 21):
                continue                                       # A19 already has the full menu's long horizons
            g.POLICY["eval"], g.POLICY["funded"] = pe[he], pf[hf]
            key = f"{menu} He{he}_Hf{hf}"; out[key] = {}
            for prod in PLANS:
                a2._PATHS["p"] = paths[prod]; out[key][prod] = {}
                for w in WINDOWS:
                    rp = a2.sequential(1, "replay", window=w)
                    bl = [a2.sequential(1, "block", traders=4000, window=w, seed=s) for s in (11, 12)]
                    out[key][prod][w] = {"replay": _row(rp), "block": {k: float(np.mean([b[k] for b in bl])) for k in _row(rp)}}
            m = {w: sum(out[key][p][w]["block"]["mean_net"] for p in PLANS) for w in WINDOWS}
            pp = {p: out[key][p][84]["block"]["p_any_payout"] for p in PLANS}
            print(f"{era} {key:22}: block mean net 84d {m[84]:+,.0f} | 252d {m[252]:+,.0f} | 84d P(pay) MNQ {pp['MNQ']:.0%} MGC {pp['MGC']:.0%}", flush=True)
    g.L_SET = saved
    a2._PATHS.clear()
    return {era: out}


def _out(era: str) -> Path:
    return ROOT / "reports" / f"a20_{era}.json"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--era", choices=("post", "pre")); ap.add_argument("--log", action="store_true")
    a = ap.parse_args(argv)
    if a.era:
        _out(a.era).write_text(json.dumps(run(a.era), indent=1) + "\n"); return 0
    r = {**json.loads(_out("post").read_text()), **json.loads(_out("pre").read_text())}
    OUT.write_text(json.dumps(r, indent=1) + "\n")
    for e in ("post", "pre"):
        _out(e).unlink()
    if a.log:
        from futuresres.stats.trials import Trial, TrialLog
        log = TrialLog(ROOT / "measurements.jsonl")
        rec = log.append(Trial(trial_id=log.next_id("m"), hypothesis_id="A-series", symbol="MNQ+MGC",
                               date_range=("2011-02-01", "2026-08-27"), status="completed", params={"kind": "policy_menu_horizon", **r},
                               note="kind=computation; NOT a trial. A20: horizons with stops >= $500. decisions.md 136."))
        print("logged", rec["trial_id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())

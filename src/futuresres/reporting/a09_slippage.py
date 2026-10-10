"""A09 - the two demo plans (4 MNQ 09:30-16:00; 8 MGC 03:00-11:30 ET) with slippage added to commissions:
$0 / $10 / $20 per day's trade, on both histories, replay and block bootstrap. A COMPUTATION; zero edge; no
trial. decisions.md 107. The user reports fills within ~$10 a trade.

    python -m futuresres.reporting.a09_slippage reports/a09_slippage.json
"""

import contextlib, io, json, sys, warnings, numpy as np
import futuresres.reporting.a01_game as g, futuresres.reporting.a02_real as a2, futuresres.reporting.a08_gold as a8


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    warnings.filterwarnings("ignore")
    with contextlib.redirect_stdout(io.StringIO()), np.errstate(all="ignore"):
        g.solve_all(21, keep_policy_at=21); g.solve_funded(21, "dollars", keep_policy_at=21)
    out = {}
    for prod, win, n, rt in (("MNQ", "rth_0930_1600", 4, 2.32), ("MGC", "london_0300_1130", 8, 3.32)):
        for era in ("post", "pre"):
            h, l, c, _ = a8.era_paths(era, prod, win)
            for slip in (0, 10, 20):
                tot = np.float32(n * rt + slip)               # commissions + slippage per day's trade
                a2._PATHS["p"] = ((h * n - (tot - a8.RT_ENGINE)).astype(np.float32), (l * n - tot).astype(np.float32), (c * n - tot).astype(np.float32))
                rp = a2.sequential(1, "replay"); bl = [a2.sequential(1, "block", traders=6000, seed=s) for s in (11, 12)]
                k = f"{prod} x{n} {era} slip {slip}"
                out[k] = {"replay": [rp["p_any_payout"], rp["mean_net"]], "block": [np.mean([b["p_any_payout"] for b in bl]), np.mean([b["mean_net"] for b in bl])]}
                print(f"{k:24} replay {rp['p_any_payout']:.0%} {rp['mean_net']:+6.0f} | block {out[k]['block'][0]:.0%} {out[k]['block'][1]:+6.0f}", flush=True)
    json.dump(out, open(argv[0], "w"), indent=1, default=float)
    return 0


if __name__ == "__main__":
    sys.exit(main())

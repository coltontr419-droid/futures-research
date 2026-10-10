"""A10b - the 84-day results of A07/A08 re-run with stops filling AT the stop price (a02_real.STOP_FILL="level"),
the user's reported execution, beside the backtests' bar-low fill. A COMPUTATION; zero edge; no trial. decisions.md 108.

    python -m futuresres.reporting.a10_levelfill reports/a10_levelfill_84d.json
"""

import contextlib, io, json, sys, warnings, numpy as np
import futuresres.reporting.a01_game as g, futuresres.reporting.a02_real as a2, futuresres.reporting.a08_gold as a8


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    warnings.filterwarnings("ignore")
    with contextlib.redirect_stdout(io.StringIO()), np.errstate(all="ignore"):
        g.solve_all(21, keep_policy_at=21); g.solve_funded(21, "dollars", keep_policy_at=21)
    out = {}
    for prod, win, sizes, rt in (("MNQ", "rth_0930_1600", (2, 3, 4, 5, 6), 2.32), ("MGC", "london_0300_1130", (4, 6, 8, 10, 12), 3.32)):
        for era in ("post", "pre"):
            h, l, c, _ = a8.era_paths(era, prod, win)
            for n in sizes:
                tot = np.float32(n * rt)
                a2._PATHS["p"] = ((h * n - (tot - a8.RT_ENGINE)).astype(np.float32), (l * n - tot).astype(np.float32), (c * n - tot).astype(np.float32))
                res = {}
                for fill in ("bar_low", "level"):
                    a2.STOP_FILL = fill
                    rp = a2.sequential(1, "replay"); bl = [a2.sequential(1, "block", traders=6000, seed=s) for s in (11, 12)]
                    res[fill] = {"replay": [rp["p_any_payout"], rp["mean_net"], rp["p_net_positive"]],
                                 "block": [float(np.mean([b[k] for b in bl])) for k in ("p_any_payout", "mean_net", "p_net_positive")]}
                out[f"{prod} {n} {era}"] = res
                L, B = res["level"], res["bar_low"]
                print(f"{prod} {n:2d} {era:4}  bar_low: replay {B['replay'][0]:.0%} {B['replay'][1]:+5.0f} block {B['block'][0]:.0%} {B['block'][1]:+5.0f}"
                      f"  || level: replay {L['replay'][0]:.0%} {L['replay'][1]:+5.0f} block {L['block'][0]:.0%} {L['block'][1]:+5.0f} P(net>0) {L['block'][2]:.0%}", flush=True)
    json.dump(out, open(argv[0], "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""A14 - are 30-minute / 1-hour candles enough for the bracket replay? On MNQ and MGC (where 1-minute data exists),
the minute paths are rebuilt as coarse candles and the demo plans re-run, resolving a bar that touches both levels
by the OHLC path rule (open nearer the high -> high first). A COMPUTATION; no trial. decisions.md 115.

    python -m futuresres.reporting.a14_coarse_bars

Result (recorded in decisions.md 115): hourly within ~10-15% of the 1-minute answer on mean net, slightly
conservative in 3 of 4; plain pessimistic/optimistic tie rules span $500-$5,000 and are not usable.
"""

import contextlib
import io
import sys
import warnings

import numpy as np

import futuresres.reporting.a01_game as g, futuresres.reporting.a02_real as a2, futuresres.reporting.a08_gold as a8


def main(argv=None) -> int:
    warnings.filterwarnings("ignore")
    with contextlib.redirect_stdout(io.StringIO()), np.errstate(all="ignore"):
        g.solve_all(21, keep_policy_at=21); g.solve_funded(21, "dollars", keep_policy_at=21)
    a2.STOP_FILL = "level"
    orig = a2._bracket_day
    OPEN = {}
    def ohlc_rule(h, l, c, W, L):
        """Within a bar touching both levels: open nearer the high -> high first (take), else low first (stop)."""
        o = OPEN["o"]
        A, T = c.shape
        hitW = h >= W[:, None]; hitL = l <= -L[:, None]; big = T + 1
        tw = np.where(hitW.any(1), hitW.argmax(1), big); tl = np.where(hitL.any(1), hitL.argmax(1), big)
        rows = np.arange(A)
        same = (tw == tl) & (tw < big)
        ti = np.minimum(tw, T - 1)
        high_first = (h[rows, ti] - o[rows, ti]) <= (o[rows, ti] - l[rows, ti])
        take = (tw < big) & ((tw < tl) | (same & high_first)); stop = (tl < big) & ~take
        out = c[:, -1].copy(); out[stop] = -L[stop]; out[take] = W[take]
        return out, stop, take
    def coarse(h, l, c, k):
        S, T = c.shape; nb = -(-T // k); pad = nb * k - T
        def p(x): return np.concatenate([x, np.repeat(x[:, -1:], pad, 1)], 1) if pad else x
        H, Lw, C = p(h).reshape(S, nb, k), p(l).reshape(S, nb, k), p(c).reshape(S, nb, k)
        o = np.concatenate([np.zeros((S, 1), np.float32), C[:, :-1, -1]], 1)   # bar open = previous bar's close (0 at entry)
        return H.max(2), Lw.min(2), C[:, :, -1], o
    for prod, win, n, rt in (("MNQ", "rth_0930_1600", 4, 2.32), ("MGC", "london_0300_1130", 8, 3.32)):
        for era in ("post", "pre"):
            h, l, c, _ = a8.era_paths(era, prod, win)
            tot = np.float32(n * rt); row = []
            a2._bracket_day = orig
            a2._PATHS["p"] = ((h * n - (tot - a8.RT_ENGINE)).astype(np.float32), (l * n - tot).astype(np.float32), (c * n - tot).astype(np.float32))
            r = a2.sequential(1, "replay"); b = [a2.sequential(1, "block", traders=6000, seed=s) for s in (11, 12)]
            row.append(f"1m {r['p_any_payout']:.0%} {r['mean_net']:+.0f} (blk {np.mean([x['mean_net'] for x in b]):+.0f})")
            for k in (30, 60):
                hh, ll, cc, o = coarse(h, l, c, k)
                # paths are scaled/shifted for the engine; the open transforms the same way as the close
                OPEN["o_raw"] = o
                a2._PATHS["p"] = ((hh * n - (tot - a8.RT_ENGINE)).astype(np.float32), (ll * n - tot).astype(np.float32), (cc * n - tot).astype(np.float32))
                def rule(H, Lw, C, W, L, k=k, o=o):
                    # sequential passes h, l + rt1, c + rt1 per sampled session: recover which sessions via exact match of c
                    return ohlc_rule(H, Lw, C, W, L)
                # sequential indexes paths by idx each day; give ohlc_rule the matching opens through a wrapper on _PATHS
                idx_holder = {}
                orig_seq_paths = a2._PATHS["p"]
                a2._bracket_day = rule
                # rebuild the open in engine units aligned per call: easiest - monkeypatch sequential's slicing via a lookup on c
                Cfull = (cc * n - tot + a8.RT_ENGINE).astype(np.float32); Ofull = (o * n - tot + a8.RT_ENGINE).astype(np.float32)
                key = {Cfull[i].tobytes(): i for i in range(len(Cfull))}
                def rule2(H, Lw, C, W, L):
                    ii = np.array([key.get(C[j].tobytes(), -1) for j in range(len(C))])
                    OPEN["o"] = Ofull[ii]
                    return ohlc_rule(H, Lw, C, W, L)
                a2._bracket_day = rule2
                r = a2.sequential(1, "replay"); b = [a2.sequential(1, "block", traders=6000, seed=s) for s in (11, 12)]
                row.append(f"{k}m-OHLC {r['p_any_payout']:.0%} {r['mean_net']:+.0f} (blk {np.mean([x['mean_net'] for x in b]):+.0f})")
            a2._bracket_day = orig
            print(f"{prod} {n} {era:4}: " + " | ".join(row), flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())

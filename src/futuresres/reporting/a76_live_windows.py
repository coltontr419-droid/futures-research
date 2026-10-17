"""A76 - longer windows on live accounts (decisions.md 662). No trial.

    python -m futuresres.reporting.a76_live_windows --build      (the longer-window paths, cached under data/cache/a76/)
    python -m futuresres.reporting.a76_live_windows
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import sys
import warnings
from pathlib import Path

import numpy as np

import futuresres.reporting.a21_more_accounts as a21
import futuresres.reporting.a23_account_sizes as a23
import futuresres.reporting.a27_standalone as a27
import futuresres.reporting.a43_scale as a43
import futuresres.reporting.a63_firms as f
from futuresres.reporting.a60_live import data, summary
from futuresres.reporting.a67_cashpath import launch_paths
from futuresres.reporting.a73_100k_live import SEEDS, setup
from futuresres.reporting.a75_sim_contracts import LIVE

ROOT = Path(__file__).resolve().parents[3]
VCACHE = a21.CACHE / "a76"
EXITS = {"NKD": ((15, 0), (18, 0), (23, 0)), "FDXM": ((17, 30), (21, 30))}
SRC = {"NKD": "NKD", "FDXM": "DAX"}
PERS = ("2021-24", "2025 starts", "2021-26", "2010-20")


def _tag(e):
    return f"{e[0]:02d}{e[1]:02d}"


def build() -> None:
    VCACHE.mkdir(parents=True, exist_ok=True); orig = a21.CACHE
    try:
        for m, exits in EXITS.items():
            for e in exits[1:]:
                a21.CACHE = VCACHE / _tag(e); a21.CACHE.mkdir(exist_ok=True)
                t = list(a21.MARKETS[SRC[m]]); keep = tuple(t); t[3] = e; a21.MARKETS[SRC[m]] = tuple(t)
                try:
                    a21.build(SRC[m])
                finally:
                    a21.MARKETS[SRC[m]] = keep
    finally:
        a21.CACHE = orig


def _raw(m, era, e):
    """One-contract $ paths for market m with exit e, the dollar rules' sides applied; (h, l, c, {date: row})."""
    orig = a21.CACHE
    try:
        if e != EXITS[m][0]:
            a21.CACHE = VCACHE / _tag(e)
        h, l, c, d = a21.paths(SRC[m], era)
    finally:
        a21.CACHE = orig
    dd = [x.astype(object) for x in d.astype("datetime64[D]")]
    R = a43.masks()
    h, l, c = a27.flip(h, l, c, np.array([R[m](v) for v in dd]))
    return h, l, c, {v: i for i, v in enumerate(dd)}


def aligned(common, m, era, e, n):
    h, l, c, ix = _raw(m, era, e); T = c.shape[1]
    H = np.zeros((len(common), T), np.float32); Lo = H.copy(); C = H.copy(); has = np.zeros(len(common), bool)
    for j, v in enumerate(common):
        i = ix.get(v)
        if i is not None:
            H[j], Lo[j], C[j] = h[i] * n, l[i] * n, c[i] * n; has[j] = True
    return H, Lo, C, has


def pad(x, T):
    return x if x.shape[1] >= T else np.concatenate([x, np.repeat(x[:, -1:], T - x.shape[1], axis=1)], axis=1)


def setup_era(common, P, era, combo):
    """(paths with NKD / FDXM padded to the live width, live_paths) for combo = (NKD exit, FDXM exit)."""
    P = dict(P); live = {}
    for m, e in zip(("NKD", "FDXM"), combo):
        H, Lo, C, has = aligned(common, m, era, e, a23.MARKETS[m][0]); T = max(H.shape[1], P[m][0].shape[1])
        h0, l0, c0, cost, has0 = P[m]
        P[m] = (pad(h0, T), pad(l0, T), pad(c0, T), cost, has0)
        live[m] = (pad(H, T), pad(Lo, T), pad(C, T), has)
    return P, live


def randomised_both(P, live, seed):
    """Random sides per session, the same side for the account's evaluation / funded window and its live window."""
    rng = np.random.default_rng(seed); P2, L2 = {}, {}
    for m, (h, l, c, cost, has) in P.items():
        sh = rng.random(len(c)) < 0.5
        P2[m] = (*a27.flip(h, l, c, sh), cost, has)
        if m in live:
            hL, lL, cL, hasL = live[m]; L2[m] = (*a27.flip(hL, lL, cL, sh), hasL)
    return P2, L2


def main() -> int:
    warnings.filterwarnings("ignore")
    if "--build" in sys.argv:
        build(); return 0
    out = {"grid_2021_24": {}}
    cp, Pp = data("post"); cq, Pq = data("pre"); P1, Q1 = launch_paths(Pp), launch_paths(Pq)
    st = np.array(cp[: len(cp) - 84]); m24 = np.array([x < dt.date(2025, 1, 1) for x in st])
    F, _ = setup("50K", P1); Fq, _ = setup("50K", Q1); F.update(LIVE); Fq.update(LIVE)
    MIX = f.MIXES["5: 3NKD+2FDXM"]
    combos = list(itertools.product(EXITS["NKD"], EXITS["FDXM"]))

    def key(cb):
        return f"NKD to {_tag(cb[0])} | FDXM to {_tag(cb[1])}"

    def read(cb):
        P, L = setup_era(cp, P1, "post", cb); Q, LQ = setup_era(cq, Q1, "pre", cb)
        r = f.simulate(cp, P, 84, MIX, dict(F, live_paths=L)); rq = f.simulate(cq, Q, 84, MIX, dict(Fq, live_paths=LQ))
        x = {"2021-24": summary(r, m24), "2025 starts": summary(r, ~m24), "2021-26": summary(r, np.ones(len(st), bool)), "2010-20": summary(rq, np.ones(len(rq["net"]), bool))}
        z = [];  zq = []
        for s in SEEDS:
            P2, L2 = randomised_both(P, L, s); z.append(f.simulate(cp, P2, 84, MIX, dict(F, live_paths=L2))["net"].mean())
            Q2, LQ2 = randomised_both(Q, LQ, s); zq.append(f.simulate(cq, Q2, 84, MIX, dict(Fq, live_paths=LQ2))["net"].mean())
        x["zero edge 2021-26"], x["zero edge 2010-20"] = float(np.mean(z)), float(np.mean(zq))
        return x

    for cb in combos:
        P, L = setup_era(cp, P1, "post", cb)
        v = float(f.simulate(cp, P, 84, MIX, dict(F, live_paths=L))["net"][m24].mean()); out["grid_2021_24"][key(cb)] = v
        print(f"  {key(cb):26}: 2021-24 {v:+,.0f}", flush=True)
    best = max(combos, key=lambda cb: out["grid_2021_24"][key(cb)]); base = (EXITS["NKD"][0], EXITS["FDXM"][0])
    out["base"] = read(base); out["chosen"] = {"key": key(best), **read(best)}
    for lab in ("base", "chosen"):
        x = out[lab]
        print(f"{lab:6} {key(base) if lab == 'base' else key(best):26}: " + " | ".join(
            f"{p} {x[p]['net_mean']:+,.0f} (med {x[p]['net_median']:+,.0f}, {x[p]['p_pos']:.0%}, p10 {x[p]['p10']:+,.0f}; live {x[p]['paid_live']:,.0f})" for p in PERS)
            + f" | zero edge {x['zero edge 2021-26']:+,.0f} / {x['zero edge 2010-20']:+,.0f}", flush=True)
    c_, b_ = out["base"], out["chosen"]
    out["adopt"] = bool(best != base and b_["2025 starts"]["net_mean"] > c_["2025 starts"]["net_mean"] and b_["2010-20"]["net_mean"] >= c_["2010-20"]["net_mean"] - 250
                        and b_["zero edge 2021-26"] >= c_["zero edge 2021-26"] and b_["zero edge 2010-20"] >= c_["zero edge 2010-20"]
                        and b_["2025 starts"]["p10"] >= c_["2025 starts"]["p10"] - 1000)
    print(f"adopt (decisions.md 662): {out['adopt']}", flush=True)
    (ROOT / "reports" / "a76_live_windows.json").write_text(json.dumps(out, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

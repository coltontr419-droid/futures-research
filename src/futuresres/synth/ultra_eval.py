"""Synth Ultra (SN50 VHFT): evaluate 10-second microprice percentile models on recorded Binance spot data (ultra_record). decisions.md §1170.

Target (SPECIFICATION.md): spot microprice from the last book-ticker update at or before t + 10 s; score: pinball-loss CRPS over 100 centred percentiles,
in price units. Prompts every 20 s after a 5-minute warm-up.

    python -m futuresres.synth.ultra_eval [recording.jsonl.gz]
"""

from __future__ import annotations

import glob
import gzip
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
TAU = (2 * np.arange(1, 101) - 1) / 200.0


def crps(x: np.ndarray, y: float) -> float:
    u = y - x
    return float(2.0 / 100 * np.sum(u * (TAU - (u < 0))))


def load(path: str):
    book, trades = {}, {}
    for line in gzip.open(path, "rt"):
        r = json.loads(line)
        if r["k"] == "b":
            mp = (r["b"] * r["A"] + r["a"] * r["B"]) / (r["A"] + r["B"])
            book.setdefault(r["s"], []).append((r["t"], mp, (r["a"] + r["b"]) / 2, r["B"], r["A"]))
        else:
            trades.setdefault(r["s"], []).append((r["t"], r["p"], r["q"], r["m"]))
    return {s: np.array(v) for s, v in book.items()}, {s: np.array(v) for s, v in trades.items()}


def secs(b: np.ndarray, t_end: int, n: int) -> np.ndarray:
    """Microprice sampled each second over the last n seconds before t_end (last update at or before each second)."""
    grid = t_end - 1000 * np.arange(n)[::-1]
    i = np.searchsorted(b[:, 0], grid, side="right") - 1
    return b[np.maximum(i, 0), 1]


Z = {}


def quantiles(model: str) -> np.ndarray:
    if model not in Z:
        from scipy import stats
        if model.startswith("t"):
            df = float(model[1:]); q = stats.t.ppf(TAU, df); q = q / np.sqrt(df / (df - 2))
        elif model == "laplace":
            q = stats.laplace.ppf(TAU) / np.sqrt(2)
        else:
            q = stats.norm.ppf(TAU)
        Z[model] = q
    return Z[model]


def predict(b, tr, t, cfg) -> np.ndarray:
    i = np.searchsorted(b[:, 0], t, side="right") - 1; m0 = b[i, 1]
    s = secs(b, t, cfg["win"] + 1); r = np.diff(s)
    if cfg.get("ewma"):
        w = 0.5 ** (np.arange(len(r))[::-1] / cfg["ewma"]); var1 = (w * r ** 2).sum() / w.sum()
    else:
        var1 = np.mean(r ** 2)
    sig = np.sqrt(max(var1, 1e-12) * 10) * cfg.get("k", 1.0)
    mu = 0.0
    if cfg.get("flow") and tr is not None:                   # signed aggressive volume over the last 5 s, scaled by recent sigma
        j0, j1 = np.searchsorted(tr[:, 0], [t - 5000, t], side="right")
        q = tr[j0:j1]; sgn = np.where(q[:, 3] > 0, -1.0, 1.0) if len(q) else np.array([])   # buyer is maker -> aggressive sell
        flow = float((sgn * q[:, 2]).sum()) if len(q) else 0.0
        mu = cfg["flow"] * np.tanh(flow / cfg.get("fscale", 1.0)) * sig
    return m0 + mu + sig * quantiles(cfg.get("shape", "norm"))


def evaluate(path: str, configs: dict) -> None:
    B, T = load(path)
    for sym, b in B.items():
        tr = T.get(sym); t0, t1 = int(b[0, 0]) + 300_000, int(b[-1, 0]) - 11_000
        times = np.arange(t0, t1, 20_000); res = {k: [] for k in configs}
        for t in times:
            j = np.searchsorted(b[:, 0], t + 10_000, side="right") - 1; y = b[j, 1]
            for k, cfg in configs.items():
                res[k].append(crps(predict(b, tr, t, cfg), y))
        base = np.mean(res[next(iter(configs))])
        print(f"{sym}: {len(times)} prompts over {(t1 - t0) / 60000:.0f} min, price {b[-1, 1]:.2f}")
        for k, v in res.items():
            v = np.array(v); print(f"  {k:28} CRPS {v.mean():.4f} ({(v.mean() / base - 1) * 100:+.1f}% vs first)  se {v.std(ddof=1) / np.sqrt(len(v)):.4f}")


CONFIGS = {
    "norm win60": {"win": 60},
    "norm win300": {"win": 300},
    "norm ewma60 (win600)": {"win": 600, "ewma": 60},
    "t4 ewma60": {"win": 600, "ewma": 60, "shape": "t4"},
    "t3 ewma60": {"win": 600, "ewma": 60, "shape": "t3"},
    "laplace ewma60": {"win": 600, "ewma": 60, "shape": "laplace"},
    "t4 ewma60 k0.9": {"win": 600, "ewma": 60, "shape": "t4", "k": 0.9},
    "t4 ewma60 k1.1": {"win": 600, "ewma": 60, "shape": "t4", "k": 1.1},
    "t4 ewma60 flow0.3": {"win": 600, "ewma": 60, "shape": "t4", "flow": 0.3, "fscale": 2.0},
}

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else sorted(glob.glob(str(ROOT / "data" / "ultra" / "rec_*.jsonl.gz")))[-1]
    evaluate(path, CONFIGS)

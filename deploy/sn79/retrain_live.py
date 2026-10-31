"""MVTRX rolling live retrain (decisions.md §1199). Every few hours (systemd timer): take the newest ≈ 2 h of the live tape, fit the 30 s
predictor on its first 75%, score the new fit AND the deployed model on the last 25% (out of sample for both), and swap the new model in
(restart mvtrx-x1) only if it beats the deployed one by ≥ MARGIN rank IC and its own IC ≥ FLOOR. Acts only while the live config uses
model30_live.json. Log: /opt/mvtrx/retrain.log.
"""

import datetime as dt
import json
import os
import re
import subprocess
import sys

import numpy as np

DROPIN = "/etc/systemd/system/mvtrx-x1.service.d/tape.conf"
MODEL = "/opt/mvtrx/agents/model30_live.json"
TAIL_BYTES = 60_000_000                           # ≈ 2 h of tape at ≈ 28 MB/h
MARGIN, FLOOR = 0.02, 0.10
NAMES = ["flow5", "ret5", "ret30", "ret120", "imb1", "imb5", "micro"]
LOG = "/opt/mvtrx/retrain.log"


def log(msg: str) -> None:
    with open(LOG, "a") as f:
        f.write(f"{dt.datetime.utcnow():%Y-%m-%d %H:%M} UTC {msg}\n")


def features(path: str) -> np.ndarray:
    src = open("/opt/mvtrx/signal_fit.py").read().split("NAMES = [")[0]
    g = {"sys": sys}; argv = sys.argv; sys.argv = ["x", path]
    try:
        exec(src, g)
    finally:
        sys.argv = argv
    A = np.array(g["rows"], dtype=float)
    return A[np.argsort(A[:, 0])]


def ic(pred: np.ndarray, y: np.ndarray) -> float:
    ok = np.isfinite(y) & np.isfinite(pred)
    return float(np.corrcoef(np.argsort(np.argsort(pred[ok])), np.argsort(np.argsort(y[ok])))[0, 1]) if ok.sum() > 500 else float("nan")


def main() -> None:
    conf = open(DROPIN).read()
    if "model30_live.json" not in conf:
        log("skip: live config is not using model30_live.json"); return
    tape = re.search(r"tape=(\S+)", conf).group(1)
    tmp = "/tmp/retrain_tail.jsonl"
    with open(tape, "rb") as f:
        f.seek(max(0, os.path.getsize(tape) - TAIL_BYTES)); f.readline()   # drop the partial first line
        open(tmp, "wb").write(f.read())
    A = features(tmp); os.unlink(tmp)
    cut = int(len(A) * 0.75); tr, te = A[:cut], A[cut:]
    mu, sd = tr[:, 1:8].mean(0), tr[:, 1:8].std(0)
    ok = np.isfinite(tr[:, 9]); w, *_ = np.linalg.lstsq((tr[ok, 1:8] - mu) / sd, tr[ok, 9], rcond=None)
    new_ic = ic(((te[:, 1:8] - mu) / sd) @ w, te[:, 9])
    cur = json.load(open(MODEL))
    cur_ic = ic(((te[:, 1:8] - np.array(cur["mu"])) / np.array(cur["sd"])) @ np.array(cur["w"]), te[:, 9])
    msg = f"rows {len(A)} (test {len(te)}): new IC {new_ic:+.3f}, deployed IC {cur_ic:+.3f}"
    if np.isfinite(new_ic) and new_ic >= FLOOR and (not np.isfinite(cur_ic) or new_ic >= cur_ic + MARGIN):
        ok = np.isfinite(A[:, 9]); mu, sd = A[:, 1:8].mean(0), A[:, 1:8].std(0)       # refit on all rows for deployment
        w, *_ = np.linalg.lstsq((A[ok, 1:8] - mu) / sd, A[ok, 9], rcond=None)
        json.dump({"horizon": 30, "names": NAMES, "mu": mu.tolist(), "sd": sd.tolist(), "w0": 0.0, "w": w.tolist(), "rows": int(ok.sum()),
                   "source": f"rolling retrain {dt.datetime.utcnow():%Y-%m-%d %H:%M} UTC, {tape}"}, open(MODEL + ".tmp", "w"), indent=1)
        os.replace(MODEL + ".tmp", MODEL)
        subprocess.run(["systemctl", "restart", "mvtrx-x1"], check=False)
        log(msg + " -> SWAPPED in, miner restarted")
    else:
        log(msg + " -> kept deployed model")


if __name__ == "__main__":
    main()

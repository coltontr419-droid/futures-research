"""MVTRX rolling live retrain (decisions.md §1199). Every few hours (systemd timer): take the newest ≈ 2 h of the live tape, fit the 30 s
predictor on its first 75%, score the new fit AND the deployed model on the last 25% (out of sample for both), and swap the new model in
(restart mvtrx-x1) only if it beats the deployed one by ≥ MARGIN rank IC and its own IC ≥ FLOOR. Features are fit_orderflow.py's
(the 10 QuoteAgent._predict computes live, incl. order flow, §1206); acts on the model file the live config names, only when that model
uses exactly those features. Restarts are cheap since §1207. Log: /opt/mvtrx/retrain.log.
"""

import datetime as dt
import json
import os
import re
import subprocess
import sys

import numpy as np

DROPIN = "/etc/systemd/system/mvtrx-x1.service.d/tape.conf"
TAIL_BYTES = 60_000_000                           # ≈ 2 h of tape at ≈ 28 MB/h
MARGIN, FLOOR = 0.02, 0.10
LOG = "/opt/mvtrx/retrain.log"


def log(msg: str) -> None:
    with open(LOG, "a") as f:
        f.write(f"{dt.datetime.utcnow():%Y-%m-%d %H:%M} UTC {msg}\n")


sys.path.insert(0, "/opt/mvtrx")
from fit_orderflow import NAMES, rows as features   # noqa: E402  rows: [sec, 10 features, 30 s mid change], sorted by time


def ic(pred: np.ndarray, y: np.ndarray) -> float:
    ok = np.isfinite(y) & np.isfinite(pred)
    return float(np.corrcoef(np.argsort(np.argsort(pred[ok])), np.argsort(np.argsort(y[ok])))[0, 1]) if ok.sum() > 500 else float("nan")


def main() -> None:
    conf = open(DROPIN).read()
    MODEL = re.search(r"model=(\S+)", conf).group(1)
    if json.load(open(MODEL)).get("names") != NAMES:
        log(f"skip: live model {MODEL} does not use the order-flow features"); return
    tape = re.search(r"tape=(\S+)", conf).group(1)
    tmp = "/tmp/retrain_tail.jsonl"
    with open(tape, "rb") as f:
        f.seek(max(0, os.path.getsize(tape) - TAIL_BYTES)); f.readline()   # drop the partial first line
        open(tmp, "wb").write(f.read())
    A = features(tmp); os.unlink(tmp)
    cut = int(len(A) * 0.75); tr, te = A[:cut], A[cut:]
    mu, sd = tr[:, 1:11].mean(0), tr[:, 1:11].std(0); sd[sd == 0] = 1.0
    ok = np.isfinite(tr[:, 11]); w, *_ = np.linalg.lstsq((tr[ok, 1:11] - mu) / sd, tr[ok, 11], rcond=None)
    new_ic = ic(((te[:, 1:11] - mu) / sd) @ w, te[:, 11])
    cur = json.load(open(MODEL))
    cur_ic = ic(((te[:, 1:11] - np.array(cur["mu"])) / np.array(cur["sd"])) @ np.array(cur["w"]), te[:, 11])
    msg = f"rows {len(A)} (test {len(te)}): new IC {new_ic:+.3f}, deployed IC {cur_ic:+.3f}"
    if "--dry" in sys.argv:
        print(msg, "(dry run: nothing written)"); return
    if np.isfinite(new_ic) and new_ic >= FLOOR and (not np.isfinite(cur_ic) or new_ic >= cur_ic + MARGIN):
        ok = np.isfinite(A[:, 11]); mu, sd = A[:, 1:11].mean(0), A[:, 1:11].std(0); sd[sd == 0] = 1.0   # refit on all rows for deployment
        w, *_ = np.linalg.lstsq((A[ok, 1:11] - mu) / sd, A[ok, 11], rcond=None)
        json.dump({"horizon": 30, "names": NAMES, "mu": mu.tolist(), "sd": sd.tolist(), "w0": 0.0, "w": w.tolist(), "rows": int(ok.sum()),
                   "source": f"rolling retrain {dt.datetime.utcnow():%Y-%m-%d %H:%M} UTC, {tape}"}, open(MODEL + ".tmp", "w"), indent=1)
        os.replace(MODEL + ".tmp", MODEL)
        subprocess.run(["systemctl", "restart", "mvtrx-x1"], check=False)
        log(msg + " -> SWAPPED in, miner restarted")
    else:
        log(msg + " -> kept deployed model")


if __name__ == "__main__":
    main()

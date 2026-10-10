"""A01 - the evaluation solved as a game: the staking policy that maximises P(pass within N days).

A COMPUTATION on the account's rules only. No market data and no market claim: each day the trader
chooses a bracket - take profit +W, stop loss -L - and the market is a FAIR game, so the bracket wins
with probability L / (W + L) (zero edge; costs and days where neither is hit are added in A02). Solved
exactly by dynamic programming. decisions.md 93.

    python -m futuresres.reporting.a01_game

WHY STAKING MATTERS at zero edge: the evaluation ends at the target or at the floor, and a fair game
keeps expected balance at the start, so P(pass) = (start - E[balance at failure]) / (target balance -
E[balance at failure]). A policy whose failures happen at the INITIAL floor ($48,000) rather than after
the floor has trailed up raises P(pass); the ceiling at zero edge is (50,000-48,000)/(53,000-48,000) = 40%.
Continuous trading (our earlier strategies) reaches ~19-22%.

THE GAME - Tradeify Select Daily as the user confirmed (decisions.md 81-82), in $100 units:
  balance b = equity - $50,000; END-OF-DAY peak pk; floor = pk - 20 (never locks in the evaluation);
  breaching the floor fails (a stop that would cross it exits at the floor);
  soft daily loss limit $1,000 => L <= 10;
  pass at a day's close when b >= 30 AND the best day <= 40% of b (consistency);
  actions: no trade, or a bracket W in 1..30, L in 1..10 (L capped at the distance to the floor).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports" / "a01_game.json"

B_MIN, B_MAX = -20, 45          # balance range ($100 units); -20 is the initial floor
TARGET, DD, DAILY, CONS = 30, 20, 10, 0.40
W_SET = tuple(range(1, 16)) + (18, 20, 25, 30)
L_SET = (2, 4, 5, 6, 8, 10)
BD_MAX = 18                     # a best day above $1,800 can never satisfy 40% of a balance <= $4,500
HORIZONS = (5, 10, 21, 42, 84)


def solve(days: int) -> tuple[np.ndarray, dict]:
    """V[b, pk, bd] = max P(pass within `days`). Index offsets: b - B_MIN; pk 0..PK; bd 0..BD."""
    nb = B_MAX - B_MIN + 1
    PK = B_MAX                       # peak 0..B_MAX
    BD = BD_MAX
    b_idx = np.arange(nb)[:, None, None]
    b_val = (b_idx + B_MIN)
    pk = np.arange(PK + 1)[None, :, None]
    bd = np.arange(BD + 1)[None, None, :]
    valid = (pk >= np.maximum(b_val, 0)) & (b_val > pk - DD)       # alive states: above the floor

    def passed(b, best):
        return (b >= TARGET) & (best <= CONS * b)

    V = np.zeros((nb, PK + 1, BD + 1))
    best_action = None
    for t in range(days):
        newV = np.zeros_like(V)
        act = np.zeros(V.shape, int)              # encoded W*100 + L, 0 = no trade
        # no trade: state unchanged (a day passes)
        cand = V.copy()
        np.copyto(newV, cand)
        for W in W_SET:
            for L in L_SET:
                p = L / (W + L)
                # win: b+W, pk=max(pk, b+W), bd=max(bd, W)
                bw = np.minimum(b_val + W, B_MAX)
                pkw = np.minimum(np.maximum(pk, bw), PK)
                bdw = np.minimum(np.maximum(bd, W), BD)
                win_pass = passed(bw, bdw)
                vw = np.where(win_pass, 1.0, V[(bw - B_MIN), pkw, bdw])
                # loss: exit at max(b - L, floor); reaching the floor fails
                floor = pk - DD
                bl = b_val - L
                fail = bl <= floor
                bl_c = np.clip(bl, B_MIN, B_MAX)
                vl = np.where(fail, 0.0, V[(bl_c - B_MIN), np.broadcast_to(pk, bl_c.shape), np.broadcast_to(bd, bl_c.shape)])
                # a loss cannot trigger a pass; a stop that is beyond the floor behaves as the floor
                val = p * vw + (1 - p) * vl
                better = val > newV + 1e-12
                newV = np.where(better, val, newV)
                act = np.where(better, W * 100 + L, act)
        newV = np.where(valid, newV, 0.0)
        V = newV
        best_action = act
    start = (0 - B_MIN, 0, 0)
    return V, {"p_pass": float(V[start]), "first_action_W": int(best_action[start] // 100) * 100,
               "first_action_L": int(best_action[start] % 100) * 100}


POLICY: dict = {}


def solve_all(days: int = max(HORIZONS), keep_policy_at: int | None = None) -> dict:
    """One backward pass; V_t for every t is the max P(pass within t days)."""
    import time
    out = {}
    nb = B_MAX - B_MIN + 1
    b_val = (np.arange(nb)[:, None, None] + B_MIN)
    pk = np.arange(B_MAX + 1)[None, :, None]
    bd = np.arange(BD_MAX + 1)[None, None, :]
    valid = (pk >= np.maximum(b_val, 0)) & (b_val > pk - DD)
    V = np.zeros((nb, B_MAX + 1, BD_MAX + 1))
    start = (0 - B_MIN, 0, 0)
    pkB = np.broadcast_to(pk, (nb, B_MAX + 1, BD_MAX + 1)); bdB = np.broadcast_to(bd, pkB.shape)
    t0 = time.time()
    for t in range(1, days + 1):
        # NO "wait" action (decisions.md 93): in a fair game waiting never raises P(pass), but once values
        # settle it TIES with trading, and a tie resolved to waiting left reachable states idle for ever.
        newV = np.full(V.shape, -1.0); act = np.zeros(V.shape, int)
        for W in W_SET:
            bw = np.minimum(b_val + W, B_MAX) + 0 * pk + 0 * bd
            pkw = np.maximum(pkB, bw)
            bdw = np.minimum(np.maximum(bdB, W), BD_MAX)
            win_pass = (bw >= TARGET) & (np.maximum(bdB, W) <= CONS * bw)
            vw = np.where(win_pass, 1.0, V[bw - B_MIN, pkw, bdw])
            for L in L_SET:
                # FAIR odds on the stop actually reachable: a stop beyond the floor exits AT the floor, so
                # the effective loss is min(L, distance to floor) and the win probability is priced on it
                dist = b_val + 0 * pk + 0 * bd - (pkB - DD)
                Le = np.minimum(L, dist)
                p = Le / (W + Le)
                bl = b_val - Le
                fail = bl <= pkB - DD
                vl = np.where(fail, 0.0, V[np.clip(bl, B_MIN, B_MAX) - B_MIN, pkB, bdB])
                val = p * vw + (1 - p) * vl
                better = val > newV + 1e-12
                newV = np.where(better, val, newV)
                act = np.where(better, W * 100 + L, act)
        V = np.where(valid, newV, 0.0)
        if keep_policy_at == t:
            POLICY["eval"] = act.copy()
        if t in HORIZONS:
            out[t] = {"p_pass": float(V[start]), "first_W": int(act[start] // 100) * 100,
                      "first_L": int(act[start] % 100) * 100}
            print(f"within {t:3d} trading days: max P(pass) {out[t]['p_pass']:.3f}; first-day bracket "
                  f"+${out[t]['first_W']} / -${out[t]['first_L']}   ({time.time()-t0:.0f}s)", flush=True)
    return out


def main() -> int:
    res = solve_all()
    OUT.write_text(json.dumps(res, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())


# ------------------------------------------------------------------ the funded account, played optimally
F_BMIN, F_BMAX = -20, 60
BUFFER, CAP_UNITS, LIVE_AFTER = 20, 12, 3       # withdraw above $52,000; $1,200 cap until 3 payouts (unit-rounded)


def solve_funded(days: int, objective: str, keep_policy_at: int | None = None):
    """objective 'dollars': max E[payouts to the trader within `days`] ($, 90% split);
    'first': max P(a first payout within `days`). State: balance b, peak pk 0..20 (20 = locked: floor 0),
    payouts taken n 0..3. Returns V[t] at the start state for every t, and the stationary policy."""
    nb = F_BMAX - F_BMIN + 1
    b = (np.arange(nb)[:, None, None] + F_BMIN)
    pk = np.arange(BUFFER + 1)[None, :, None]
    n = np.arange(LIVE_AFTER + 1)[None, None, :]
    shape = (nb, BUFFER + 1, LIVE_AFTER + 1)
    B = np.broadcast_to(b, shape); PK = np.broadcast_to(pk, shape); N = np.broadcast_to(n, shape)
    floor = np.where(PK >= BUFFER, 0, PK - DD)
    valid = (B > floor) & (PK >= np.minimum(np.maximum(B, 0), BUFFER))
    V = np.zeros(shape)
    hist = {}

    def settle(bb, pkk, nn):
        """End of day: the peak updates (capped at the lock), then a payout above the buffer."""
        pk2 = np.minimum(np.maximum(pkk, np.clip(bb, 0, None)), BUFFER)
        amt = np.clip(bb - BUFFER, 0, None)
        amt = np.where(nn >= LIVE_AFTER, amt, np.minimum(amt, CAP_UNITS))
        b2 = bb - amt
        n2 = np.where(amt > 0, np.minimum(nn + 1, LIVE_AFTER), nn)
        return b2, pk2, n2, amt

    for t in range(1, days + 1):
        best = np.full(shape, -1.0)           # no "wait" action, as in the evaluation
        act = np.zeros(shape, int)
        for W in W_SET:
            for L in L_SET:
                dist = B - floor
                Le = np.minimum(L, np.maximum(dist, 1))
                p = Le / (W + Le)
                bw, pkw, nw, aw = settle(np.minimum(B + W, F_BMAX), PK, N)
                bl = B - Le
                failL = bl <= floor
                bl2, pkl, nl, al = settle(np.clip(bl, F_BMIN, F_BMAX), PK, N)
                if objective == "dollars":
                    rw = aw * 100 * 0.9 + V[bw - F_BMIN, pkw, nw]
                    rl = np.where(failL, 0.0, al * 100 * 0.9 + V[bl2 - F_BMIN, pkl, nl])
                else:
                    rw = np.where((aw > 0) & (N == 0), 1.0, V[bw - F_BMIN, pkw, nw])
                    rl = np.where(failL, 0.0, np.where((al > 0) & (N == 0), 1.0, V[bl2 - F_BMIN, pkl, nl]))
                val = np.where(valid, p * rw + (1 - p) * rl, 0.0)
                act = np.where(val > best + 1e-12, W * 100 + L, act)
                best = np.maximum(best, val)
        V = np.where(valid, np.maximum(best, 0.0), 0.0)
        if keep_policy_at == t:
            POLICY["funded"] = act.copy()
        hist[t] = float(V[0 - F_BMIN, 0, 0])
    return hist


def combine(eval_by_t: dict, funded_by_t: dict, horizon: int = 84) -> float:
    """Approximate the whole path: the evaluation's pass-day distribution from P(pass within t), and the
    funded value with the days that remain."""
    ts = sorted(eval_by_t)
    total, prev = 0.0, 0.0
    for t in range(1, horizon + 1):
        cur = eval_by_t.get(t, eval_by_t[max(k for k in ts if k <= t)] if any(k <= t for k in ts) else 0.0)
        dp = max(cur - prev, 0.0); prev = cur
        rem = horizon - t
        if rem > 0:
            total += dp * funded_by_t.get(rem, funded_by_t[max(funded_by_t)])
    return total

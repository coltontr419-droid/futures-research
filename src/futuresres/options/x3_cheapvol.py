"""X-family 3 (decisions.md 969): buy straddles on the top decile of realised / implied volatility, hold to the snapshot before expiry.

    python -m futuresres.options.x3_cheapvol form      # ATM quotes for every symbol at each month's first snapshot
    python -m futuresres.options.x3_cheapvol exits     # exit-snapshot quotes for the selected straddles
    python -m futuresres.options.x3_cheapvol [validate]
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

from futuresres.options.x1_straddle import COMM, PRIOR_SD, sql

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "options" / "x3"
SNAPS = ROOT / "data" / "options" / "x1" / "snapdates.json"
SEAL = "2024-01"


def snaps() -> list[str]:
    return sorted(d for d, n in json.loads(SNAPS.read_text()).items() if n > 0)


def form_dates() -> list[str]:
    S = snaps(); out, seen = [], set()
    for d in S:
        if "2020-02" <= d[:7] <= "2026-09" and d[:7] not in seen:
            seen.add(d[:7]); out.append(d)
    return out


def fetch_range(d: str, lo: str, hi: str, extra: str) -> list | None:
    rows = sql(f"SELECT act_symbol, expiration, strike, call_put, bid, ask, vol, delta FROM option_chain WHERE date='{d}' "
               f"AND act_symbol >= '{lo}' AND act_symbol < '{hi}' {extra}")
    return rows


def form() -> None:
    OUT.mkdir(parents=True, exist_ok=True); f = OUT / "form.jsonl"
    done = {json.loads(l)["date"] for l in open(f)} if f.exists() else set()
    for d in form_dates():
        if d in done:
            continue
        d0 = dt.date.fromisoformat(d)
        extra = (f"AND expiration BETWEEN '{(d0 + dt.timedelta(days=20)).isoformat()}' AND '{(d0 + dt.timedelta(days=45)).isoformat()}' "
                 f"AND ABS(delta) BETWEEN 0.35 AND 0.65")
        L = [chr(c) for c in range(ord("A"), ord("Z") + 1)]
        def kids(P: str) -> list[tuple[str, str]]:              # complete partition of the symbols starting with P (P itself included)
            return [(P, P + "A")] + [(P + c, P + chr(ord(c) + 1)) for c in L[:-1]] + [(P + "Z", P + "~")]
        stack, rows, ok = kids(""), [], True
        while stack:
            lo, hi = stack.pop()
            r = fetch_range(d, lo, hi, extra)
            if r is None:
                ok = False; break
            if len(r) >= 1000:                                   # row limit: split by the next character
                if len(hi) == len(lo) and hi[:-1] == lo[:-1]:
                    stack += kids(lo)
                else:
                    print("  unsplittable range at row limit", d, lo, hi); rows += r
                continue
            rows += r
        if not ok:
            print("  failed", d); continue
        q = [[r["act_symbol"], r["expiration"], float(r["strike"]), r["call_put"][0], float(r["bid"] or 0), float(r["ask"] or 0),
              float(r["vol"] or 0), float(r["delta"] or 0)] for r in rows]
        with open(f, "a") as fo:
            fo.write(json.dumps({"date": d, "q": q}) + "\n")
        print(d, len(q), "rows", len({x[0] for x in q}), "symbols", flush=True)


def selections() -> list[dict]:
    z = np.load(ROOT / "data" / "stocks" / "long" / "pack.npz"); cal = list(z["cal"]); syms = {s: i for i, s in enumerate(z["syms"])}
    A = z["A"].astype(np.float64); ci = {d: i for i, d in enumerate(cal)}; out = []
    for l in open(OUT / "form.jsonl"):
        x = json.loads(l); d = x["date"]; i = ci.get(d)
        if i is None or i < 260:
            continue
        by = collections.defaultdict(list)
        for r in x["q"]:
            by[r[0]].append(r)
        d0 = dt.date.fromisoformat(d); cand = []
        for s, rs in by.items():
            j = syms.get(s)
            if j is None or not np.isfinite(A[j, i - 250:i + 1]).all():
                continue
            exps = sorted({r[1] for r in rs}, key=lambda e: abs((dt.date.fromisoformat(e) - d0).days - 30))
            ex = exps[0]; C = [r for r in rs if r[1] == ex and r[3] == "C"]
            if not C:
                continue
            c = min(C, key=lambda r: abs(r[7] - 0.5)); p = next((r for r in rs if r[1] == ex and r[2] == c[2] and r[3] == "P"), None)
            if p is None or c[2] < 10 or min(c[4], p[4], c[5], p[5]) <= 0 or c[6] <= 0 or p[6] <= 0:
                continue
            ask, mid = c[5] + p[5], (c[4] + c[5] + p[4] + p[5]) / 2
            if (ask - (c[4] + p[4])) / mid > 0.20:
                continue
            hv = float(np.std(np.diff(np.log(A[j, i - 21:i + 1])), ddof=1) * np.sqrt(252))
            cand.append({"sym": s, "date": d, "ex": ex, "k": c[2], "ask": ask, "sig": np.log(hv / ((c[6] + p[6]) / 2))})
        if len(cand) < 50:
            continue
        cand.sort(key=lambda c: -c["sig"]); out += cand[:len(cand) // 10]
    return out


def exit_date(c: dict, S: list[str]) -> str | None:
    lim = (dt.date.fromisoformat(c["ex"]) - dt.timedelta(days=3)).isoformat()
    return max((t for t in S if c["date"] < t <= lim), default=None)


def exits() -> None:
    S = snaps(); f = OUT / "exits.jsonl"
    done = {(q["date"], q["sym"], q["ex"]) for q in map(json.loads, open(f))} if f.exists() else set()
    need = collections.defaultdict(set)
    for c in selections():
        y = exit_date(c, S)
        if y and (y, c["sym"], c["ex"]) not in done:
            need[y].add((c["sym"], c["ex"], c["k"]))
    print("exit symbol-dates", sum(map(len, need.values())))
    with open(f, "a") as fo:
        for d in sorted(need):
            pr = sorted(need[d])
            for i in range(0, len(pr), 20):
                ch = pr[i:i + 20]; w = " OR ".join(f"(act_symbol='{s}' AND expiration='{x}' AND strike={k})" for s, x, k in ch)
                rows = sql(f"SELECT act_symbol, expiration, strike, call_put, bid, ask FROM option_chain WHERE date='{d}' AND ({w})")
                if rows is None:
                    continue
                by = collections.defaultdict(list)
                for r in rows:
                    by[r["act_symbol"]].append([float(r["strike"]), r["call_put"][0], float(r["bid"] or 0), float(r["ask"] or 0)])
                for s, x, k in ch:
                    fo.write(json.dumps({"date": d, "sym": s, "ex": x, "q": by.get(s, [])}) + "\n")
                fo.flush()


def evaluate(validate: bool) -> None:
    S = snaps(); E = {(q["date"], q["sym"], q["ex"]): q["q"] for q in map(json.loads, open(OUT / "exits.jsonl"))}
    mon, skip = collections.defaultdict(list), 0
    for c in selections():
        if (c["date"][:7] >= SEAL) != validate:
            continue
        y = exit_date(c, S); q = E.get((y, c["sym"], c["ex"])) if y else None
        if q is None:
            skip += 1; continue
        bid = sum(next((r[2] for r in q if r[0] == c["k"] and r[1] == cp), 0.0) for cp in ("C", "P"))
        mon[c["date"][:7]].append((bid - c["ask"] - 4 * COMM) / (c["ask"] + 2 * COMM))
    x = np.array([np.mean(v) for _, v in sorted(mon.items())]); allr = np.concatenate([np.array(v) for v in mon.values()])
    m, t = float(x.mean()), float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
    s = (f"X3 {'sealed' if validate else 'discovery'}: straddles {len(allr)} (no exit {skip}), months {len(x)}, net {m*100:+.2f}%/month, t {t:+.2f}; "
         f"median {np.median(allr)*100:+.1f}%, win {np.mean(allr > 0)*100:.0f}%")
    if validate:
        rng = np.random.default_rng(969); pct = float((np.array([(x * rng.choice((-1.0, 1.0), len(x))).mean() for _ in range(4000)]) < m).mean() * 100)
        post = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / len(x))
        s += f", placebo {pct:.0f}th, posterior {post*100:+.2f}% -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 and post > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
    else:
        s += "  CARRIED" if m > 0 and t > 1.96 else "  not carried"
    print(s)


if __name__ == "__main__":
    a = sys.argv[1:2]
    {"form": form, "exits": exits}.get(a[0] if a else "", lambda: evaluate(a == ["validate"]))()

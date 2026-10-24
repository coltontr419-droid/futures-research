"""X-family 1 (decisions.md 966): buying ATM straddles into earnings, entry ~1 week before, exit the snapshot before the report.

    python -m futuresres.options.x1_straddle cal       # Nasdaq earnings calendar 2020-01 -> 2026-10 (cached, merges E2's cache)
    python -m futuresres.options.x1_straddle probe     # DoltHub snapshot dates (AAPL row count per weekday)
    python -m futuresres.options.x1_straddle chains    # near-ATM quotes for each event's entry/exit snapshot
    python -m futuresres.options.x1_straddle chainsy   # X2 exit-snapshot quotes (all strikes of the chosen expiry)
    python -m futuresres.options.x1_straddle [validate]
    python -m futuresres.options.x1_straddle x2 [validate]
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "options" / "x1"
E2CAL = ROOT / "data" / "stocks" / "e2" / "calendar.jsonl"
DOLT = "https://www.dolthub.com/api/v1alpha1/post-no-preference/options/master"
UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
START, END, SEAL, MINCAP, COMM, PRIOR_SD = "2020-01-01", "2026-10-16", "2024-01", 10e9, 0.0065, 0.02


def get(u: str, tries: int = 4):
    for k in range(tries):
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=120).read())
        except Exception:
            time.sleep(2 ** k)
    return None


def sql(q: str):
    r = get(DOLT + "?" + urllib.parse.urlencode({"q": q}))
    if not r or r.get("query_execution_status") not in ("Success", "RowLimit"):
        return None
    if r["query_execution_status"] == "RowLimit":
        print("  row limit hit:", q[:80])
    return r["rows"]


def days(a: str, b: str):
    d = dt.date.fromisoformat(a)
    while d.isoformat() <= b:
        if d.weekday() < 5:
            yield d.isoformat()
        d += dt.timedelta(days=1)


def cal() -> None:
    OUT.mkdir(parents=True, exist_ok=True); f = OUT / "calendar.jsonl"
    have = {json.loads(l)["date"] for l in open(f)} if f.exists() else set()
    if E2CAL.exists() and not have:
        f.write_text(E2CAL.read_text()); have = {json.loads(l)["date"] for l in open(f)}
    with open(f, "a") as fo:
        for d in days(START, END):
            if d in have:
                continue
            r = get(f"https://api.nasdaq.com/api/calendar/earnings?date={d}"); time.sleep(0.4)
            rows = ((r or {}).get("data") or {}).get("rows") or []
            fo.write(json.dumps({"date": d, "rows": rows}) + "\n"); fo.flush()
    print("calendar days", len({json.loads(l)["date"] for l in open(f)}))


def probe() -> None:
    f = OUT / "snapdates.json"; S = json.loads(f.read_text()) if f.exists() else {}
    for d in days(START, "2026-10-23"):
        if d in S:
            continue
        r = sql(f"SELECT COUNT(*) n FROM option_chain WHERE date='{d}' AND act_symbol='AAPL'")
        if r is None:
            continue                                            # retried next run
        S[d] = int(r[0]["n"])
        if len(S) % 50 == 0:
            f.write_text(json.dumps(S))
    f.write_text(json.dumps(S)); print("snapshot dates", sum(1 for v in S.values() if v > 0), "of", len(S))


def cap(s: str) -> float:
    try:
        return float(s.replace("$", "").replace(",", ""))
    except Exception:
        return 0.0


def events() -> list[dict]:
    snaps = sorted(d for d, n in json.loads((OUT / "snapdates.json").read_text()).items() if n > 0)
    seen, ev = set(), []
    for l in open(OUT / "calendar.jsonl"):
        x = json.loads(l); d = x["date"]
        if not (START <= d <= END):
            continue
        for r in x["rows"]:
            s = (r.get("symbol") or "").strip()
            if not s or cap(r.get("marketCap") or "") < MINCAP or (s, d) in seen:
                continue
            seen.add((s, d)); dd = dt.date.fromisoformat(d)
            prev = dd - dt.timedelta(days=3 if dd.weekday() == 0 else 1)  # d - 1 trading day (holidays: snapshot absent anyway)
            X = max((t for t in snaps if (dd - dt.timedelta(days=4)).isoformat() <= t <= prev.isoformat()), default=None)
            if X is None:
                continue
            xd = dt.date.fromisoformat(X)
            E = max((t for t in snaps if (xd - dt.timedelta(days=8)).isoformat() <= t <= (xd - dt.timedelta(days=4)).isoformat()), default=None)
            if E is None:
                continue
            ev.append({"sym": s, "d": d, "E": E, "X": X})
    return ev


def chains() -> None:
    ev = events(); f = OUT / "quotes.jsonl"
    done = {(q["date"], q["sym"]) for q in map(json.loads, open(f))} if f.exists() else set()
    need = collections.defaultdict(set)
    for e in ev:
        for k in ("E", "X"):
            if (e[k], e["sym"]) not in done:
                need[e[k]].add(e["sym"])
    print("events", len(ev), "dates", len(need), "symbol-dates", sum(map(len, need.values())))
    with open(f, "a") as fo:
        for d in sorted(need):
            syms = sorted(need[d])
            for i in range(0, len(syms), 15):
                ch = syms[i:i + 15]; lst = ",".join(f"'{s}'" for s in ch)
                rows = sql(f"SELECT act_symbol, expiration, strike, call_put, bid, ask, delta FROM option_chain WHERE date='{d}' "
                           f"AND act_symbol IN ({lst}) AND ABS(delta) BETWEEN 0.2 AND 0.8")
                if rows is None:
                    continue
                by = collections.defaultdict(list)
                for r in rows:
                    by[r["act_symbol"]].append([r["expiration"], float(r["strike"]), r["call_put"][0], float(r["bid"] or 0), float(r["ask"] or 0), float(r["delta"] or 0)])
                for s in ch:
                    fo.write(json.dumps({"date": d, "sym": s, "q": by.get(s, [])}) + "\n")
                fo.flush()


def x2_legs(e: dict, Q: dict) -> dict | None:
    """§967 legs at X: body at call delta ~0.50, wings at call delta ~+0.20 and put delta ~-0.20, nearest expiry after d."""
    qx = Q.get((e["X"], e["sym"]))
    if not qx:
        return None
    exps = sorted({r[0] for r in qx if r[0] > e["d"]})
    if not exps:
        return None
    ex = exps[0]; C = [r for r in qx if r[0] == ex and r[2] == "C"]; P = [r for r in qx if r[0] == ex and r[2] == "P"]
    if not C or not P:
        return None
    k = min(C, key=lambda r: abs(r[5] - 0.5))[1]; kc = min(C, key=lambda r: abs(r[5] - 0.2))[1]; kp = min(P, key=lambda r: abs(r[5] + 0.2))[1]
    if not (kc > k > kp):
        return None
    leg = lambda k_, cp: next((r for r in qx if r[0] == ex and r[1] == k_ and r[2] == cp), None)
    L = {"bc": leg(k, "C"), "bp": leg(k, "P"), "wc": leg(kc, "C"), "wp": leg(kp, "P")}
    if any(v is None for v in L.values()) or L["bc"][3] <= 0 or L["bp"][3] <= 0 or L["wc"][4] <= 0 or L["wp"][4] <= 0:
        return None
    return {"ex": ex, "k": k, "kc": kc, "kp": kp, "L": L}


def ydate(e: dict, snaps: list[str]) -> str | None:
    dd = dt.date.fromisoformat(e["d"])
    return min((t for t in snaps if (dd + dt.timedelta(days=1)).isoformat() <= t <= (dd + dt.timedelta(days=5)).isoformat()), default=None)


def chains_y() -> None:
    """Quotes at Y for the X2 legs: all strikes of the chosen expiry (no delta filter — strikes move after the report)."""
    Q = {(q["date"], q["sym"]): q["q"] for q in map(json.loads, open(OUT / "quotes.jsonl"))}
    snaps = sorted(d for d, n in json.loads((OUT / "snapdates.json").read_text()).items() if n > 0)
    f = OUT / "quotes_y.jsonl"; done = {(q["date"], q["sym"], q["ex"]) for q in map(json.loads, open(f))} if f.exists() else set()
    need = collections.defaultdict(set)
    for e in events():
        g = x2_legs(e, Q); y = ydate(e, snaps)
        if g and y and (y, e["sym"], g["ex"]) not in done:
            need[y].add((e["sym"], g["ex"]))
    print("Y symbol-dates", sum(map(len, need.values())))
    with open(f, "a") as fo:
        for d in sorted(need):
            pr = sorted(need[d])
            for i in range(0, len(pr), 6):
                ch = pr[i:i + 6]; w = " OR ".join(f"(act_symbol='{s}' AND expiration='{x}')" for s, x in ch)
                rows = sql(f"SELECT act_symbol, expiration, strike, call_put, bid, ask, delta FROM option_chain WHERE date='{d}' AND ({w})")
                if rows is None:
                    continue
                by = collections.defaultdict(list)
                for r in rows:
                    by[r["act_symbol"]].append([r["expiration"], float(r["strike"]), r["call_put"][0], float(r["bid"] or 0), float(r["ask"] or 0), float(r["delta"] or 0)])
                for s, x in ch:
                    fo.write(json.dumps({"date": d, "sym": s, "ex": x, "q": by.get(s, [])}) + "\n")
                fo.flush()


def close(sym: str, d: str) -> float | None:
    f = OUT / "yahoo" / f"{sym}.json"
    if not f.exists():
        f.parent.mkdir(exist_ok=True)
        r = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&period1=1577836800&period2=1792800000"); time.sleep(0.4)
        f.write_text(json.dumps(r or {}))
    try:
        r = json.loads(f.read_text())["chart"]["result"][0]
        c = {dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat(): x for t, x in zip(r["timestamp"], r["indicators"]["quote"][0]["close"]) if x}
        return c.get(d)
    except Exception:
        return None


def trade2(e: dict, Q: dict, QY: dict, snaps: list[str]) -> float | None:
    g = x2_legs(e, Q); y = ydate(e, snaps)
    if g is None or y is None:
        return None
    qy = QY.get((y, e["sym"], g["ex"]))
    if qy is None:
        return None                                              # never fetched (API failure)
    L = g["L"]; credit = L["bc"][3] + L["bp"][3] - L["wc"][4] - L["wp"][4]
    risk = max(g["kc"] - g["k"], g["k"] - g["kp"]) - credit + 4 * COMM
    if credit <= 0 or risk <= 0:
        return None
    S = None
    def q(k_, cp, side):
        nonlocal S
        r = next((r for r in qy if r[1] == k_ and r[2] == cp), None)
        if r and r[3] > 0 and r[4] > 0:
            return r[4] if side == "ask" else r[3]
        if S is None:
            S = close(e["sym"], y)
        if S is None:
            return float("nan")
        iv = max(S - k_, 0.0) if cp == "C" else max(k_ - S, 0.0)
        return iv + 0.02 * S if side == "ask" else iv
    cost = q(g["k"], "C", "ask") + q(g["k"], "P", "ask") - q(g["kc"], "C", "bid") - q(g["kp"], "P", "bid")
    pnl = credit - cost - 8 * COMM
    return max(pnl / risk, -1.0) if np.isfinite(pnl) else -1.0


def evaluate2(validate: bool) -> None:
    Q = {(q["date"], q["sym"]): q["q"] for q in map(json.loads, open(OUT / "quotes.jsonl"))}
    QY = {(q["date"], q["sym"], q["ex"]): q["q"] for q in map(json.loads, open(OUT / "quotes_y.jsonl"))}
    snaps = sorted(d for d, n in json.loads((OUT / "snapdates.json").read_text()).items() if n > 0)
    wk, n, skip = collections.defaultdict(list), 0, 0
    for e in events():
        if (e["d"][:7] >= SEAL) != validate:
            continue
        r = trade2(e, Q, QY, snaps)
        if r is None:
            skip += 1; continue
        y, w, _ = dt.date.fromisoformat(e["X"]).isocalendar(); wk[(y, w)].append(r); n += 1
    x = np.array([np.mean(v) for v in wk.values()]); allr = np.concatenate([np.array(v) for v in wk.values()])
    m, t = float(x.mean()), float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
    s = (f"X2 {'sealed' if validate else 'discovery'}: events {n} (untradable {skip}), weeks {len(x)}, return on risk {m*100:+.2f}%/event-week, "
         f"t {t:+.2f}; per-event median {np.median(allr)*100:+.1f}%, win {np.mean(allr > 0)*100:.0f}%")
    if validate:
        rng = np.random.default_rng(967); pct = float((np.array([(x * rng.choice((-1.0, 1.0), len(x))).mean() for _ in range(4000)]) < m).mean() * 100)
        post = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / len(x))
        s += f", placebo {pct:.0f}th, posterior {post*100:+.2f}% -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 and post > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
    else:
        s += "  CARRIED" if m > 0 and t > 1.96 else "  not carried"
    print(s)


def trade(e: dict, Q: dict) -> tuple[float, float] | None:
    qe, qx = Q.get((e["E"], e["sym"])), Q.get((e["X"], e["sym"]))
    if qe is None or qx is None:
        return None                                              # quotes never fetched (API failure), not a market outcome
    exps = sorted({r[0] for r in qe if r[0] > e["d"]})
    if not exps:
        return None                                              # no listed expiry spanning the report at entry: not tradable by the rule
    ex = exps[0]; calls = [r for r in qe if r[0] == ex and r[2] == "C"]
    if not calls:
        return None
    k = min(calls, key=lambda r: abs(r[5] - 0.5))[1]
    leg = lambda q, cp: next((r for r in q if r[0] == ex and r[1] == k and r[2] == cp), None)
    ce, pe = leg(qe, "C"), leg(qe, "P")
    if not ce or not pe or ce[4] <= 0 or pe[4] <= 0:
        return None
    ask = ce[4] + pe[4]; mid_e = (ce[3] + ce[4] + pe[3] + pe[4]) / 2
    cx, px = leg(qx, "C"), leg(qx, "P")
    if not cx or not px or cx[3] <= 0 or px[3] <= 0:
        return -1.0, -1.0                                        # §966.3: missing / zero bid at exit counted at -100%
    net = (cx[3] + px[3] - ask - 4 * COMM) / (ask + 2 * COMM)
    mid = ((cx[3] + cx[4] + px[3] + px[4]) / 2) / mid_e - 1
    return net, mid


def evaluate(validate: bool) -> None:
    Q = {(q["date"], q["sym"]): q["q"] for q in map(json.loads, open(OUT / "quotes.jsonl"))}
    wk, wm, n, skip = collections.defaultdict(list), collections.defaultdict(list), 0, 0
    for e in events():
        if (e["d"][:7] >= SEAL) != validate:
            continue
        r = trade(e, Q)
        if r is None:
            skip += 1; continue
        y, w, _ = dt.date.fromisoformat(e["E"]).isocalendar(); wk[(y, w)].append(r[0]); wm[(y, w)].append(r[1]); n += 1
    x = np.array([np.mean(v) for v in wk.values()]); xm = np.array([np.mean(v) for v in wm.values()])
    allr = np.concatenate([np.array(v) for v in wk.values()])
    m, t = float(x.mean()), float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
    s = (f"X1 {'sealed' if validate else 'discovery'}: events {n} (untradable/unfetched {skip}), weeks {len(x)}, net {m*100:+.2f}%/event-week, "
         f"t {t:+.2f}; per-event median {np.median(allr)*100:+.1f}%, win {np.mean(allr > 0)*100:.0f}%; mid-to-mid {xm.mean()*100:+.2f}%")
    if validate:
        rng = np.random.default_rng(966); pct = float((np.array([(x * rng.choice((-1.0, 1.0), len(x))).mean() for _ in range(4000)]) < m).mean() * 100)
        post = m * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / len(x))
        s += f", placebo {pct:.0f}th, posterior {post*100:+.2f}% -> " + ("CONFIRM" if t > 1.645 and pct >= 95 and m > 0 and post > 0 else ("WATCHLIST" if m > 0 else "REJECT"))
    else:
        s += "  CARRIED" if m > 0 and t > 1.96 else "  not carried"
    print(s)


if __name__ == "__main__":
    a = sys.argv[1:2]
    if a[:1] == ["x2"]:
        evaluate2(sys.argv[2:3] == ["validate"])
    else:
        {"cal": cal, "probe": probe, "chains": chains, "chainsy": chains_y}.get(a[0] if a else "", lambda: evaluate(a == ["validate"]))()

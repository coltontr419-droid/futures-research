"""X-family 1 (decisions.md 966): buying ATM straddles into earnings, entry ~1 week before, exit the snapshot before the report.

    python -m futuresres.options.x1_straddle cal       # Nasdaq earnings calendar 2020-01 -> 2026-10 (cached, merges E2's cache)
    python -m futuresres.options.x1_straddle probe     # DoltHub snapshot dates (AAPL row count per weekday)
    python -m futuresres.options.x1_straddle chains    # near-ATM quotes for each event's entry/exit snapshot
    python -m futuresres.options.x1_straddle fill      # X1 exit legs outside the delta filter, fetched exactly (§975)
    python -m futuresres.options.x1_straddle chainsy   # X2 exit-snapshot quotes (every listed expiry and strike)
    python -m futuresres.options.x1_straddle [validate]
    python -m futuresres.options.x1_straddle x2 [validate]
"""

from __future__ import annotations

import bisect
import collections
import datetime as dt
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

from futuresres.options import smile

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
    from concurrent.futures import ThreadPoolExecutor
    f = OUT / "snapdates.json"; S = json.loads(f.read_text()) if f.exists() else {}
    todo = [d for d in days(START, "2026-10-23") if d not in S]
    one = lambda d: (d, sql(f"SELECT COUNT(*) n FROM option_chain WHERE date='{d}' AND act_symbol='AAPL'"))
    with ThreadPoolExecutor(4) as ex:
        for k, (d, r) in enumerate(ex.map(one, todo)):
            if r is not None:                                   # failures are retried next run
                S[d] = int(r[0]["n"])
            if k % 50 == 49:
                f.write_text(json.dumps(S))
    f.write_text(json.dumps(S)); print("snapshot dates", sum(1 for v in S.values() if v > 0), "of", len(S), "missing", len([d for d in todo if d not in S]))


def cap(s: str) -> float:
    try:
        return float(s.replace("$", "").replace(",", ""))
    except Exception:
        return 0.0


def latest(snaps: list[str], lo: str, hi: str) -> str | None:
    i = bisect.bisect_right(snaps, hi) - 1
    return snaps[i] if i >= 0 and snaps[i] >= lo else None


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
            X = latest(snaps, (dd - dt.timedelta(days=4)).isoformat(), prev.isoformat())
            if X is None:
                continue
            xd = dt.date.fromisoformat(X)
            E = latest(snaps, (xd - dt.timedelta(days=8)).isoformat(), (xd - dt.timedelta(days=4)).isoformat())
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
    print("events", len(ev), "dates", len(need), "symbol-dates", sum(map(len, need.values())), flush=True)
    jobs = [(d, sorted(need[d])[i:i + 15]) for d in sorted(need) for i in range(0, len(need[d]), 15)]
    pmap(jobs, lambda d, ch: sql(f"SELECT act_symbol, expiration, strike, call_put, bid, ask, delta FROM option_chain WHERE date='{d}' "
                                 f"AND act_symbol IN ({','.join(repr(s) for s in ch)}) AND ABS(delta) BETWEEN 0.2 AND 0.8"),
         lambda d, ch, s: {"date": d, "sym": s}, f)


def pmap(jobs: list, query, key, f: Path, threads: int = 4) -> None:
    """Run (date, chunk) queries on a thread pool; one line per chunk member, written as results arrive (failed chunks are retried next run)."""
    from concurrent.futures import ThreadPoolExecutor
    with open(f, "a") as fo, ThreadPoolExecutor(threads) as ex:
        for (d, ch), rows in zip(jobs, ex.map(lambda j: query(*j), jobs)):
            if rows is None:
                continue
            by = collections.defaultdict(list)
            for r in rows:
                by[r["act_symbol"]].append([r["expiration"], float(r["strike"]), r["call_put"][0], float(r["bid"] or 0), float(r["ask"] or 0), float(r["delta"] or 0)])
            for m in ch:
                s = m if isinstance(m, str) else m[0]
                fo.write(json.dumps({**key(d, ch, m), "q": by.get(s, [])}) + "\n")
            fo.flush()


def x2_legs(e: dict, Q: dict, qy: list | None) -> dict | None:
    """§967/§975 legs at X: body at call delta ~0.50, wings at call delta ~+0.20 / put ~-0.20, nearest expiry after d listed at X and Y."""
    qx = Q.get((e["X"], e["sym"]))
    if not qx or qy is None:
        return None
    exps = sorted({r[0] for r in qx if r[0] > e["d"]} & {r[0] for r in qy})
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
    """Quotes at Y for X2: every listed expiry and strike (no delta filter — strikes move after the report)."""
    Q = {(q["date"], q["sym"]): q["q"] for q in map(json.loads, open(OUT / "quotes.jsonl"))}
    snaps = sorted(d for d, n in json.loads((OUT / "snapdates.json").read_text()).items() if n > 0)
    f = OUT / "quotes_y.jsonl"; done = {(q["date"], q["sym"]) for q in map(json.loads, open(f))} if f.exists() else set()
    need = collections.defaultdict(set)
    for e in events():
        y = ydate(e, snaps)
        if y and Q.get((e["X"], e["sym"])) and (y, e["sym"]) not in done:
            need[y].add(e["sym"])
    print("Y symbol-dates", sum(map(len, need.values())), flush=True)
    jobs = [(d, sorted(need[d])[i:i + 3]) for d in sorted(need) for i in range(0, len(need[d]), 3)]
    pmap(jobs, lambda d, ch: sql(f"SELECT act_symbol, expiration, strike, call_put, bid, ask, delta FROM option_chain WHERE date='{d}' "
                                 f"AND act_symbol IN ({','.join(repr(s) for s in ch)})"),
         lambda d, ch, s: {"date": d, "sym": s}, f)


def fill() -> None:
    """§975: X1 legs missing from X's delta-filtered pull, fetched exactly (strike + expiry)."""
    Q = load_q(); f = OUT / "quotes_fill.jsonl"; need = collections.defaultdict(set)
    for e in events():
        c = x1_choice(e, Q)
        if c and c[1] is None:
            need[e["X"]].add((e["sym"], c[0], c[2]))
    print("fill legs", sum(map(len, need.values())), flush=True)
    jobs = [(d, sorted(need[d])[i:i + 20]) for d in sorted(need) for i in range(0, len(need[d]), 20)]
    pmap(jobs, lambda d, ch: sql(f"SELECT act_symbol, expiration, strike, call_put, bid, ask, delta FROM option_chain WHERE date='{d}' AND ("
                                 + " OR ".join(f"(act_symbol='{s}' AND expiration='{x}' AND strike={k})" for s, x, k in ch) + ")"),
         lambda d, ch, m: {"date": d, "sym": m[0]}, f)


def load_q() -> dict:
    Q = {}
    for name in ("quotes.jsonl", "quotes_fill.jsonl"):
        if (OUT / name).exists():
            for l in open(OUT / name):
                q = json.loads(l); k = (q["date"], q["sym"])
                if k not in Q or not Q[k]:
                    Q[k] = [tuple(r) for r in q["q"]]
    return Q


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
    y = ydate(e, snaps); qy = QY.get((y, e["sym"])) if y else None
    g = x2_legs(e, Q, qy)
    if g is None:
        return None                                              # untradable, or Y never fetched
    qy = [r for r in qy if r[0] == g["ex"]]
    L = g["L"]; credit = L["bc"][3] + L["bp"][3] - L["wc"][4] - L["wp"][4]
    risk = max(g["kc"] - g["k"], g["k"] - g["kp"]) - credit + 4 * COMM
    if credit <= 0 or risk <= 0:
        return None
    S = None
    rows = [(r[1], r[2], r[3], r[4], r[5]) for r in qy]
    def q(k_, cp, side):
        nonlocal S
        v = smile.leg(rows, k_, cp, side, y, g["ex"])          # §976: listed quote or IV-smile value
        if v is not None:
            return v
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
    QY = {(q["date"], q["sym"]): q["q"] for q in map(json.loads, open(OUT / "quotes_y.jsonl"))}
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


def x1_choice(e: dict, Q: dict):
    """(expiry, X legs or None if a leg is missing at X, strike, E legs) per §966/§975; None if untradable at entry."""
    qe, qx = Q.get((e["E"], e["sym"])), Q.get((e["X"], e["sym"]))
    if not qe or qx is None:
        return None
    exps = sorted({r[0] for r in qe if r[0] > e["d"]} & {r[0] for r in qx})   # listed at both E and X (and spanning the report)
    if not exps:
        return None
    ex = exps[0]; calls = [r for r in qe if r[0] == ex and r[2] == "C"]
    if not calls:
        return None
    k = min(calls, key=lambda r: abs(r[5] - 0.5))[1]
    leg = lambda q, cp: next((r for r in q if r[0] == ex and r[1] == k and r[2] == cp), None)
    ce, pe = leg(qe, "C"), leg(qe, "P")
    if not ce or not pe or ce[4] <= 0 or pe[4] <= 0:
        return None
    cx, px = leg(qx, "C"), leg(qx, "P")
    return ex, (cx, px) if cx and px else None, k, (ce, pe)


def trade(e: dict, Q: dict) -> tuple[float, float] | None:
    c = x1_choice(e, Q)
    if c is None:
        return None                                              # untradable at entry, or never fetched
    (ce, pe), ex, k = c[3], c[0], c[2]
    ask = ce[4] + pe[4]; mid_e = (ce[3] + ce[4] + pe[3] + pe[4]) / 2
    rows = [(r[1], r[2], r[3], r[4], r[5]) for r in Q[(e["X"], e["sym"])] if r[0] == ex]
    v = {(cp, sd): smile.leg(rows, k, cp, sd, e["X"], ex) for cp in ("C", "P") for sd in ("bid", "ask")}
    if any(x is None or x <= 0 for x in v.values()):
        return -1.0, -1.0                                        # §966.3/§976: no quote and no IV at exit counted at -100%
    net = (v[("C", "bid")] + v[("P", "bid")] - ask - 4 * COMM) / (ask + 2 * COMM)
    mid = (sum(v.values()) / 2) / mid_e - 1
    return net, mid


def evaluate(validate: bool) -> None:
    Q = load_q()
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
        {"cal": cal, "probe": probe, "chains": chains, "chainsy": chains_y, "fill": fill}.get(a[0] if a else "", lambda: evaluate(a == ["validate"]))()

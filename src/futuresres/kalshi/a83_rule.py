"""A83 (decisions.md 710): sell state-gas long shots only with a price cushion and calm wholesale gasoline. No orders.

    python -m futuresres.kalshi.a83_rule
"""

from __future__ import annotations

import bisect
import collections
import datetime as dt
import itertools
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import futuresres.reporting.a22_more_markets as a22

ROOT = Path(__file__).resolve().parents[3]
IN = ROOT / "data" / "kalshi" / "taker"
META = ROOT / "data" / "kalshi" / "gas_meta.json"
OUT = ROOT / "reports" / "a83_rule.json"
ET = ZoneInfo("America/New_York")
XS, YS = (2, 4, 6), (3, 6, None)


def ts(x):
    return dt.datetime.fromisoformat(x.replace("Z", "+00:00"))


def event_day(ev: str):
    return dt.datetime.strptime(ev.split("-")[1][:7], "%y%b%d").date()


def load():
    meta = json.loads(META.read_text())
    settle = {}                                                    # (state series, date) -> settled AAA value
    for ev, d in meta.items():
        v = next((x["value"] for x in d.values() if x["value"] not in (None, "")), None)
        if v is not None:
            settle[(ev.split("-")[0], event_day(ev))] = float(str(v).replace(",", ""))
    z = a22.load("RB=F", "1d"); rb_d = [t.date() for t in z["ts"].to_list()]; rb_v = [float(x) * 100 for x in z["c"].to_list()]
    sales = []
    for sd in IN.iterdir():
        if not sd.name.startswith("KXAAAGASD"):
            continue
        for f in sd.glob("*.json"):
            ev = json.loads(f.read_text()); D = event_day(ev["event"]); md = meta.get(ev["event"], {})
            prev = [d for (s, d) in settle if s == sd.name and d < D]
            if not prev:
                continue
            L = settle[(sd.name, max(prev))]
            for m in ev.get("markets", []):
                info = md.get(m["ticker"])
                if not info or info["floor"] is None:
                    continue
                K = float(info["floor"])
                for t, yp, side, n in m["trades"]:
                    if side == "no" and yp <= 0.0301:
                        fav, p = "no", round(1 - yp, 2)
                    elif side == "yes" and yp >= 0.9699:
                        fav, p = "yes", round(yp, 2)
                    else:
                        continue
                    cushion = (L - K) * 100 if fav == "yes" else (K - L) * 100      # cents from losing, from the price already known
                    td = ts(t).astimezone(ET).date(); i = bisect.bisect_left(rb_d, td) - 1
                    move = abs(rb_v[i] - rb_v[i - 2]) if i >= 2 else None
                    win = m["result"] == fav; fee = 0.07 * p * (1 - p)
                    sales.append({"day": D, "n": n, "p": p, "net": n * (((1 - p) if win else -p) - fee), "cushion": cushion, "move": move, "win": win})
    return sales


def score(rows):
    by = collections.defaultdict(lambda: [0.0, 0.0, 0.0])
    for r in rows:
        b = by[r["day"]]; b[0] += r["net"]; b[1] += r["n"]; b[2] += r["n"] * r["p"]
    nets = [v[0] for v in by.values()]; cap = sum(v[2] for v in by.values()); n = sum(v[1] for v in by.values())
    return {"days": len(by), "contracts": n, "net": sum(nets), "net_per_contract_c": 100 * sum(nets) / max(n, 1),
            "return_per_capital": sum(nets) / max(cap, 1e-9), "days_positive": sum(1 for x in nets if x > 0),
            "worst_day": min(nets) if nets else 0.0, "contracts_per_day": n / max(len(by), 1)}


def rule(x, y):
    return lambda r: r["cushion"] >= x and (y is None or (r["move"] is not None and r["move"] <= y))


def main() -> int:
    S = load(); days = sorted({r["day"] for r in S}); cut = days[min(29, len(days) - 1)]
    disc = [r for r in S if r["day"] <= cut]; val = [r for r in S if r["day"] > cut]
    print(f"{len(S):,} long-shot sales, days {days[0]} -> {days[-1]}; discovery to {cut} ({len({r['day'] for r in disc})} days), validation {len({r['day'] for r in val})} days", flush=True)
    out = {"discovery_end": str(cut), "rules": {}}
    def show(lab, sc):
        print(f"  {lab:24} days {sc['days']:3} contracts/day {sc['contracts_per_day']:9,.0f} | net {sc['net_per_contract_c']:+.2f}c/contract, "
              f"{sc['return_per_capital']*100:+.3f}% of capital | positive days {sc['days_positive']}/{sc['days']} | worst day ${sc['worst_day']:+,.0f}", flush=True)
    print("DISCOVERY")
    base_d = score(disc); show("take everything", base_d); out["baseline_discovery"] = base_d
    for x, y in itertools.product(XS, YS):
        sc = score([r for r in disc if rule(x, y)(r)]); key = f"cushion>={x}c, move<={y if y else 'any'}c"
        out["rules"][key] = sc; show(key, sc)
    best = max(out["rules"], key=lambda k: out["rules"][k]["return_per_capital"])
    x = int(best.split(">=")[1].split("c")[0]); y_ = best.split("<=")[1].rstrip("c"); y = None if y_ == "any" else int(y_)
    print(f"chosen on discovery: {best}")
    print("VALIDATION (read once)")
    base_v = score(val); show("take everything", base_v); ch = score([r for r in val if rule(x, y)(r)]); show(best, ch)
    out.update(chosen=best, baseline_validation=base_v, chosen_validation=ch,
               candidate=bool(ch["net"] > 0 and ch["net_per_contract_c"] > base_v["net_per_contract_c"] and ch["worst_day"] > base_v["worst_day"]))
    print(f"candidate (decisions.md 710): {out['candidate']}")
    OUT.write_text(json.dumps(out, indent=1, default=str) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

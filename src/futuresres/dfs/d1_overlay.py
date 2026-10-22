"""D-family 1 (decisions.md 869): DraftKings guaranteed-prize overlays at lock — public lobby recorder and readout. No account, no entries.

    python -m futuresres.dfs.d1_overlay record HOURS
    python -m futuresres.dfs.d1_overlay                # readout
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "dfs" / "d1.jsonl"
SPORTS = ("NFL", "NBA", "NHL", "CFB", "MLB", "CBB", "SOC")


def lobby(sport: str) -> list[dict]:
    try:
        d = json.loads(urllib.request.urlopen(urllib.request.Request(f"https://www.draftkings.com/lobby/getcontests?sport={sport}",
                                                                   headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read())
        return d.get("Contests") or []
    except Exception:
        return []


def cash(c: dict) -> float | None:
    v = (c.get("pd") or {}).get("Cash")
    return float(re.sub(r"[^\d.]", "", v)) if v and re.sub(r"[^\d.]", "", v) else None


def record(hours: float) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True); end = time.time() + hours * 3600
    while time.time() < end:
        t0 = time.time(); now_ms = time.time() * 1000; rows = []
        for sp in SPORTS:
            for c in lobby(sp):
                st = int(re.search(r"\d+", c.get("sd", "0")).group(0))
                if (c.get("attr") or {}).get("IsGuaranteed") != "true" or not 0 <= st - now_ms <= 45 * 60_000:
                    continue
                p = cash(c)
                if p:
                    rows.append({"id": c["id"], "sp": sp, "n": c["n"][:80], "start": st, "fee": c["a"], "prize": p, "entries": c["nt"], "max": c["m"], "mec": c.get("mec")})
            time.sleep(1)
        with open(OUT, "a") as f:
            f.write(json.dumps({"t": dt.datetime.now(dt.timezone.utc).isoformat(), "rows": rows}) + "\n")
        time.sleep(max(10, 180 - (time.time() - t0)))


def readout() -> None:
    last = {}
    for l in open(OUT):
        s = json.loads(l); t = dt.datetime.fromisoformat(s["t"]).timestamp() * 1000
        for r in s["rows"]:
            if t <= r["start"]:
                last[r["id"]] = r | {"snap_ms_before": r["start"] - t}
    L = [r for r in last.values() if r["fee"] > 0 and r["entries"] > 0]
    days = max(len({dt.datetime.fromtimestamp(r["start"] / 1000, dt.timezone.utc).date() for r in L}), 1)
    ov = [r | {"overlay": r["prize"] - r["entries"] * r["fee"], "ev": r["prize"] / (r["entries"] * r["fee"])} for r in L if r["prize"] > r["entries"] * r["fee"]]
    cap = sum(min(r["mec"] or 1, r["max"] - r["entries"] + 1) * r["fee"] * (r["ev"] - 1) for r in ov)
    print(f"guaranteed contests at lock {len(L)} over {days} days; with overlay {len(ov)}; total overlay ${sum(r['overlay'] for r in ov):,.0f} "
          f"(${sum(r['overlay'] for r in ov) / days * 30.4:,.0f}/month); one account at its per-user cap, field-average: ${cap:,.0f} → ${cap / days * 30.4:,.0f}/month")
    for r in sorted(ov, key=lambda r: -r["overlay"])[:20]:
        print(f"  {r['sp']:4} {r['n'][:50]:50} fee ${r['fee']:>6} prize ${r['prize']:>9,.0f} entries {r['entries']:>6}/{r['max']:<6} overlay ${r['overlay']:>7,.0f} EV x{r['ev']:.2f} "
              f"(last snap {r['snap_ms_before'] / 60000:.0f} min before)")
    print("by sport:", collections.Counter(r["sp"] for r in ov))


if __name__ == "__main__":
    record(float(sys.argv[2])) if sys.argv[1:2] == ["record"] else readout()

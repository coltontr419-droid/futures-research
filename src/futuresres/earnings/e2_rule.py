"""E-family 1 (decisions.md 752): buy YES at the press-release time + 5 min on word markets whose word appears in the release and
whose last YES print is <= 85c. Count markets ("(N+ times)") are excluded: one mention in the release does not imply N on the call
(an interpretation fixed before any data, disclosed in 753).

    python -m futuresres.earnings.e2_rule            # discovery: events closing before 2026-06-01
    python -m futuresres.earnings.e2_rule validate   # sealed 2026-06-01 -> 2026-10-19, once
"""

from __future__ import annotations

import bisect
import datetime as dt
import json
import math
import re
import sys
from pathlib import Path

import numpy as np

from futuresres.kalshi.k1_longshot import PRIOR_SD

ROOT = Path(__file__).resolve().parents[3]
EV = ROOT / "data" / "kalshi" / "earnings"
ED = ROOT / "data" / "edgar"
SEAL = dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc)
END = dt.datetime(2026, 10, 19, 23, 59, tzinfo=dt.timezone.utc)
LAG = dt.timedelta(minutes=5)


def T(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def fee(p):
    return math.ceil(7 * p * (1 - p)) / 100


def forms(label: str) -> list[str]:
    return [f.strip().lower() for f in (label or "").split("/") if f.strip()]


def in_release(label: str, body: str) -> bool:
    return any(re.search(r"(?<![a-z0-9])" + re.escape(f) + r"(?:s|es|'s)?(?![a-z0-9])", body) for f in forms(label))


def run(validate: bool) -> dict:
    rel = json.loads((ED / "releases.json").read_text())["matched"]
    per, side, hits, cap = {}, {"in": [], "out": []}, [], 0.0
    used = 0
    for e, r in rel.items():
        close = T(r["close"])
        if (validate and not SEAL <= close <= END) or (not validate and close >= SEAL):
            continue
        body = (ED / f"{e}.txt").read_text().lower(); t0 = T(r["accepted"]); tt = t0 + LAG
        ev = json.loads((EV / f"{e}.json").read_text()); used += 1
        for m in ev["markets"]:
            if re.search(r"\(\s*\d+\s*\+", m.get("word") or "") or "does not qualify" in (m.get("word") or "").lower():
                continue
            tr = sorted(m["trades"], key=lambda x: x["created_time"]); ts = [T(x["created_time"]) for x in tr]
            i = bisect.bisect_left(ts, tt)
            if i == 0:
                continue
            p = float(tr[i - 1]["yes_price_dollars"]); yes = m["result"] == "yes"; inr = in_release(m["word"], body)
            side["in" if inr else "out"].append((yes, p))
            if inr and p <= 0.85:
                q = p + 0.01
                per.setdefault(e, []).append((1.0 if yes else 0.0) - q - fee(q)); hits.append(yes)
                cap += sum(float(x["count_fp"]) for x in tr[i:bisect.bisect_left(ts, t0 + dt.timedelta(minutes=30))])
    x = np.array([np.mean(v) for v in per.values()]); n = len(x)
    m_ = float(x.mean()) if n else float("nan"); t_ = float(m_ / (x.std(ddof=1) / np.sqrt(n))) if n > 2 else float("nan")
    r = {"window": "sealed" if validate else "discovery", "events_with_release": used, "events_traded": n, "markets": int(sum(len(v) for v in per.values())),
         "mean_net": m_, "t": t_, "hit_rate": float(np.mean(hits)) if hits else None, "next_30min_volume": cap,
         "in_release": {"n": len(side["in"]), "yes_rate": float(np.mean([y for y, _ in side["in"]])) if side["in"] else None,
                        "mean_price": float(np.mean([p for _, p in side["in"]])) if side["in"] else None},
         "not_in_release": {"n": len(side["out"]), "yes_rate": float(np.mean([y for y, _ in side["out"]])) if side["out"] else None,
                            "mean_price": float(np.mean([p for _, p in side["out"]])) if side["out"] else None}}
    if validate:
        rng = np.random.default_rng(752)
        pct = float((np.array([(x * rng.choice((-1.0, 1.0), n)).mean() for _ in range(2000)]) < m_).mean() * 100)
        post0 = m_ * PRIOR_SD ** 2 / (PRIOR_SD ** 2 + x.var(ddof=1) / n)
        r.update(placebo_pct=pct, posterior_zero_prior=post0, decision="CONFIRM" if (t_ > 1.645 and pct >= 95 and m_ > 0 and post0 > 0) else ("WATCHLIST" if m_ > 0 else "REJECT"))
    else:
        r["carried"] = bool(t_ > 1.96 and m_ > 0)
    print(json.dumps(r, indent=1))
    (ROOT / "reports" / ("e1_validation.json" if validate else "e1_discovery.json")).write_text(json.dumps(r, indent=1) + "\n")
    return r


if __name__ == "__main__":
    run(sys.argv[1:2] == ["validate"])

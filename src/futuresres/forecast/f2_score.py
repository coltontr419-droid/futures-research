"""F2 (decisions.md 1038-1039): score Bot A (latest market price), Bot B (Claude + research) and Naive (freeze value) on set 2026-10-25.

    python -m futuresres.forecast.f2_score     # downloads the latest resolution set for 2026-10-25 and prints Brier and Brier Index
"""

from __future__ import annotations

import json
import math
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
D = ROOT / "data" / "fbench"
URL = "https://raw.githubusercontent.com/forecastingresearch/forecastbench-datasets/main/datasets/resolution_sets/2026-10-25_resolution_set.json"


def main() -> None:
    try:
        raw = urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read()
    except Exception as e:
        print("resolution set not published yet:", e); return
    (D / "2026-10-25_resolution_set.json").write_bytes(raw)
    R = [r for r in json.loads(raw)["resolutions"] if r["source"] in ("kalshi", "polymarket", "metaculus") and r.get("resolved")
         and r.get("direction") in (None, "")]
    Q = {q["id"]: q for q in json.load(open(D / "2026-10-25-llm.json"))["questions"]}
    A, B = json.load(open(D / "f2_botA.json")), json.load(open(D / "f2_botB.json"))
    for src in ("all", "metaculus", "kalshi+polymarket"):
        rows = [r for r in R if r["id"] in A and (src == "all" or (src == "metaculus") == (r["source"] == "metaculus"))]
        if not rows:
            print(src, "no resolved questions yet"); continue
        out = []
        for name, F in (("naive", {r["id"]: float(Q[r["id"]]["freeze_datetime_value"]) for r in rows}), ("botA", A), ("botB", B)):
            b = sum((F[r["id"]] - float(r["resolved_to"])) ** 2 for r in rows) / len(rows)
            out.append(f"{name} Brier {b:.4f} index {(1 - math.sqrt(b)) * 100:.1f}")
        print(f"{src}: n {len(rows)} | " + " | ".join(out))


if __name__ == "__main__":
    main()

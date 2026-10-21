"""A97 episodes scored on closing-line value (decisions.md 787 readout, descriptive): each +EV ProphetX offer episode against
Pinnacle's no-vig at the same line in the last A96 Pinnacle snapshot before the start (lines_*.jsonl, decisions.md 793).

    python -m futuresres.sports.a97_clv
"""

from __future__ import annotations

import collections
import difflib
import json
import statistics as st
from pathlib import Path

from futuresres.sports.a96_prophetx import FEE, OUT as A96, dec
from futuresres.sports.a97_pxstream import OUT as A97


def main() -> None:
    rows = [json.loads(l) for p in sorted(A96.glob("2026*.jsonl")) for l in open(p)]
    pin_of = {r["px_event"]: (r["pin_id"], r["start"]) for r in rows}
    lines = collections.defaultdict(list)
    for p in sorted(A96.glob("lines_*.jsonl")):
        for l in open(p):
            x = json.loads(l); lines[x["pin_id"]].append((x["t"], x["lines"]))
    eps = [json.loads(l) for p in sorted(A97.glob("*.jsonl")) for l in open(p)]
    out = collections.defaultdict(list)
    for e in eps:
        if e["market"] not in ("spread", "total") or e["event"] not in pin_of:
            continue
        pid, start = pin_of[e["event"]]
        snaps = [ls for t, ls in lines.get(pid, []) if t < start]
        if not snaps:
            continue
        who, pts = e["side"].rsplit(" ", 1); pts = float(pts)
        hit = [x[3] for x in snaps[-1] if x[0] == e["market"] and x[2] == pts and (x[1] == who or difflib.SequenceMatcher(None, x[1], who).ratio() >= 0.85)]
        if not hit:
            continue
        p = hit[0]; D = dec(e["odds"]); clv = p * (D - 1) * (1 - FEE) - (1 - p)
        out[(e["sport"], e["market"])].append((e["ev"], clv, e["stake0"]))
    if not out:
        print("no scorable episodes yet (games not started, or no closing Pinnacle line at the episode's line)"); return
    for k, v in sorted(out.items()):
        print(f"{k[0][:10]} {k[1]:6} episodes {len(v):3}  entry EV {st.mean(x[0] for x in v)*100:+.2f}%  closing-line EV {st.mean(x[1] for x in v)*100:+.2f}%  "
              f"stake-weighted {sum(x[1]*x[2] for x in v)/max(sum(x[2] for x in v),1)*100:+.2f}%  positive {sum(x[1] > 0 for x in v)}/{len(v)}")


if __name__ == "__main__":
    main()

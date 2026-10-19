"""M5: are KXTRUMPSAY-type sweeps triggered by Truth Social posts, and how fast? CNN's public archive gives each post's created_at (ms).

    python -m futuresres.mention.m5_truth SERIES [SERIES ...]
"""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "kalshi_lip"))
os.environ.setdefault("KALSHI_RATE", "4")
from kalshi_api import Client  # noqa: E402

from futuresres.mention.m1_prize import T, jump  # noqa: E402

POSTS = ROOT / "data" / "mention" / "truth" / "cnn_archive.json"


def posts():
    out = []
    for p in json.load(open(POSTS)):
        txt = re.sub(r"<[^>]+>", " ", html.unescape(p.get("content") or "")).lower()
        out.append((T(p["created_at"]), txt))
    return sorted(out)


def forms(label: str) -> list[str]:
    label = re.sub(r"\(.*?\)", "", label)
    return [f.strip().lower() for f in label.split("/") if f.strip()]


def main(argv) -> int:
    c = Client(); P = posts(); allres = {}
    for s in argv:
        T_ = json.loads((ROOT / "data" / "kalshi" / "mention_series" / f"{s}.json").read_text())
        words = {}
        for ev in sorted({t.rsplit("-", 1)[0] for t in T_}):
            for m in c.req("GET", f"/markets?event_ticker={ev}&limit=200").get("markets", []):
                words[m["ticker"]] = m.get("yes_sub_title") or ""
        res = []
        for t, tr in T_.items():
            j = jump(tr)
            if not j:
                continue
            sweep = T(j["t"]); fs = forms(words.get(t, ""))
            cand = [pt for pt, txt in P if sweep - dt.timedelta(seconds=600) <= pt <= sweep + dt.timedelta(seconds=5)
                    and any(re.search(r"\b" + re.escape(f), txt) for f in fs)]
            lag = (sweep - max(cand)).total_seconds() if cand else None
            res.append({"ticker": t, "word": words.get(t), "sweep": j["t"], "prize": j["prize"], "post_lag_s": lag})
        hit = [r for r in res if r["post_lag_s"] is not None]
        lags = sorted(r["post_lag_s"] for r in hit)
        print(f"{s}: jumps {len(res)}, preceded by a matching post within 10 min: {len(hit)} (prize ${sum(r['prize'] for r in hit):,.0f} of "
              f"${sum(r['prize'] for r in res):,.0f})" + (f" | sweep - post: median {st.median(lags):.1f}s, p10 {lags[len(lags)//10]:.1f}s, p90 {lags[9*len(lags)//10]:.1f}s" if lags else ""))
        for r in sorted(hit, key=lambda r: -r["prize"])[:8]:
            print(f"   {r['word'][:24]:24} sweep {r['sweep'][11:23]} lag {r['post_lag_s']:6.1f}s prize ${r['prize']:,.0f}")
        allres[s] = res
    (ROOT / "reports" / "m5_truth.json").write_text(json.dumps(allres, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

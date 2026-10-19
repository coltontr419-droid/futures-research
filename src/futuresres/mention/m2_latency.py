"""M2: how fast do Kalshi's mention-market sweeps follow the spoken word? YouTube live-stream recordings (actual start time + word-timed
auto captions) give the spoken time; the first taker sweep (m1_prize) gives the market's reaction.

    python -m futuresres.mention.m2_latency EVENT VIDEO_ID [VIDEO_ID ...]
"""

from __future__ import annotations

import datetime as dt
import json
import re
import statistics as st
import sys
from pathlib import Path

from futuresres.mention.m1_prize import T, jump

ROOT = Path(__file__).resolve().parents[3]
YT = ROOT / "data" / "mention" / "yt"


def words(vid: str) -> list[tuple[dt.datetime, str]]:
    start = dt.datetime.fromtimestamp(int((YT / f"{vid}.start").read_text().strip()), dt.timezone.utc)
    d = json.load(open(YT / f"{vid}.en-orig.json3")); out = []
    for e in d["events"]:
        for s in e.get("segs", []):
            w = re.sub(r"[^a-z0-9']", "", s["utf8"].lower())
            if w:
                out.append((start + dt.timedelta(milliseconds=e["tStartMs"] + s.get("tOffsetMs", 0)), w))
    return out


def forms(label: str) -> list[list[str]]:
    """Kalshi labels like 'Deport / Deported / Deportation' or 'Tariff (x3)'; each form as a token sequence."""
    label = re.sub(r"\(.*?\)", "", label)
    return [re.sub(r"[^a-z0-9' ]", " ", f.lower()).split() for f in label.split("/") if f.strip()]


def spoken(ws, fs, before: dt.datetime, window_s: int = 180):
    best = None
    for i, (t, w) in enumerate(ws):
        if t > before + dt.timedelta(seconds=30) or t < before - dt.timedelta(seconds=window_s):
            continue
        for f in fs:
            if [x for _, x in ws[i:i + len(f)]] == f or (len(f) == 1 and w.startswith(f[0]) and len(f[0]) >= 4):
                best = t if best is None or abs((before - t).total_seconds()) < abs((before - best).total_seconds()) else best
    return best


def main(argv) -> int:
    ev, vids = argv[0], argv[1:]
    d = json.load(open(ROOT / "data" / "kalshi" / "mention_trades" / f"{ev}.json")); res = {}
    for vid in vids:
        ws = words(vid); deltas = []
        for m in d["markets"]:
            j = jump(m["trades"])
            if not j:
                continue
            sweep = T(j["t"]); t = spoken(ws, forms(m["word"]), sweep)
            if t is None:
                print(f"  {vid} {m['word'][:28]:28} sweep {sweep.time()} | not found in captions"); continue
            dlt = (sweep - t).total_seconds(); deltas.append(dlt)
            print(f"  {vid} {m['word'][:28]:28} sweep {sweep.time()} spoken {t.time()} -> sweep - spoken {dlt:+6.1f}s  prize ${j['prize']:,.0f}")
        if deltas:
            print(f"{vid}: n {len(deltas)}, median {st.median(deltas):+.1f}s, quartiles {sorted(deltas)[len(deltas)//4]:+.1f} / {sorted(deltas)[3*len(deltas)//4]:+.1f}")
        res[vid] = deltas
    (ROOT / "reports" / f"m2_{ev}.json").write_text(json.dumps(res, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

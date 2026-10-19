"""M7 (decisions.md 734 step 3): which public live stream hears a mention word first, and does any beat Kalshi's first sweep?

Inputs: the recorder's chunks (data/mention/live/<label>/<channel>/<UTC local-clock start>.opus, 10 s each) and log.jsonl (NTP offsets);
the event's YES-market trades (mention_trades/<event>.json, fetched here if missing). For each jump (m1_prize.jump), each channel's
audio from 45 s before to 15 s after the sweep is transcribed (faster-whisper base.en, word timestamps); the word's first occurrence
gives its arrival time on that stream. lead = sweep - arrival (positive: the stream had the word before the sweep).
Pass rule (fixed in §734): a channel is viable if lead >= 1.5 s on >= 60% of the jumps it covers.

    python -m futuresres.mention.m7_feedrace LABEL EVENT_TICKER
"""

from __future__ import annotations

import datetime as dt
import glob
import json
import os
import re
import statistics as st
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LIVE = ROOT / "data" / "mention" / "live"
TR = ROOT / "data" / "kalshi" / "mention_trades"
UTC = dt.timezone.utc


def ntp_offset(label: str) -> float:
    offs = [json.loads(l).get("ntp_offset") for l in open(LIVE / label / "log.jsonl")]
    offs = [o for o in offs if o is not None]
    return st.median(offs) if offs else 0.0           # true UTC = local clock + offset


def chunks(label: str, ch: str, off: float) -> list[tuple[dt.datetime, Path]]:
    out = []
    for f in sorted((LIVE / label / ch).glob("*.opus")):
        t = dt.datetime.strptime(f.stem, "%Y%m%dT%H%M%S").replace(tzinfo=UTC) + dt.timedelta(seconds=off)
        out.append((t, f))
    return out


def window_audio(cs, t0: dt.datetime, t1: dt.datetime) -> tuple[dt.datetime, Path] | None:
    sel = [(t, f) for t, f in cs if t0 - dt.timedelta(seconds=10) <= t <= t1]
    if not sel:
        return None
    tmp = Path(tempfile.mkdtemp()) / "w.wav"; lst = tmp.with_suffix(".txt")
    lst.write_text("".join(f"file '{f}'\n" for _, f in sel))
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-ac", "1", "-ar", "16000", str(tmp)], check=True)
    return sel[0][0], tmp


def forms(label: str) -> list[list[str]]:
    label = re.sub(r"\(.*?\)", "", label or "")
    return [re.sub(r"[^a-z0-9' ]", " ", f.lower()).split() for f in label.split("/") if f.strip()]


def main(argv) -> int:
    label, ev = argv[0], argv[1]
    sys.path.insert(0, str(ROOT / "kalshi_lip"))
    from futuresres.mention.m1_prize import T, jump
    from kalshi_api import Client
    from faster_whisper import WhisperModel
    live_file = TR / f"{ev}.live.json"
    if not live_file.exists():
        # right after the rally the said words are not settled yet: take every market and let jump() find the said ones
        from futuresres.mention.m0_download import trades
        c = Client(); ms = c.req("GET", f"/markets?event_ticker={ev}&limit=200")["markets"]
        live_file.write_text(json.dumps({"event": ev, "markets": [{"ticker": m["ticker"], "word": m.get("yes_sub_title"),
                                                                    "trades": trades(c, m["ticker"])} for m in ms]}))
    d = json.loads(live_file.read_text()); off = ntp_offset(label)
    chans = [p.name for p in (LIVE / label).iterdir() if p.is_dir()]
    model = WhisperModel("base.en", device="cpu", compute_type="int8", cpu_threads=4)
    res = {ch: [] for ch in chans}
    for m in d["markets"]:
        j = jump(m["trades"])
        if not j:
            continue
        sweep = T(j["t"]); fs = forms(m["word"])
        for ch in chans:
            w = window_audio(chunks(label, ch, off), sweep - dt.timedelta(seconds=45), sweep + dt.timedelta(seconds=15))
            if not w:
                continue
            t0, wav = w; segs, _ = model.transcribe(str(wav), word_timestamps=True, vad_filter=False)
            words = [(t0 + dt.timedelta(seconds=x.start), re.sub(r"[^a-z0-9']", "", x.word.lower())) for s in segs for x in (s.words or [])]
            hit = None
            for i, (t, wd) in enumerate(words):
                for f in fs:
                    if [x for _, x in words[i:i + len(f)]] == f or (len(f) == 1 and len(f[0]) >= 4 and wd.startswith(f[0])):
                        hit = t; break
                if hit:
                    break
            res[ch].append({"word": m["word"], "sweep": j["t"], "prize": j["prize"], "lead_s": (sweep - hit).total_seconds() if hit else None})
            print(f"  {ch:18} {m['word'][:26]:26} sweep {sweep:%H:%M:%S} " + (f"heard {hit:%H:%M:%S.%f}"[:-4] + f" lead {(sweep - hit).total_seconds():+6.1f}s" if hit else "not heard"), flush=True)
    print(f"\nNTP offset applied: {off:+.2f}s")
    for ch, rs in res.items():
        heard = [r["lead_s"] for r in rs if r["lead_s"] is not None]
        if not heard:
            print(f"{ch:18} no jumps heard"); continue
        ok = sum(x >= 1.5 for x in heard)
        print(f"{ch:18} jumps heard {len(heard)}/{len(rs)} | lead median {st.median(heard):+.1f}s | lead >= 1.5 s on {ok}/{len(heard)} ({ok/len(heard):.0%}) "
              f"-> {'VIABLE' if ok / len(heard) >= 0.60 else 'not viable'}")
    (ROOT / "reports" / f"m7_{label}.json").write_text(json.dumps(res, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

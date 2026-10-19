"""M3: record the audio of several public live streams in 10-second chunks named by arrival time (UTC, NTP-corrected), to find which
public feed hears a word first and whether any beats Kalshi's sweeps. Laptop only; no orders.

    python -m futuresres.mention.m3_record [--start HH:MM] LABEL UNTIL_UTC(HH:MM) [channel ...]
"""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import ntplib

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "mention" / "live"
FFMPEG = "/usr/bin/ffmpeg"                     # the system build (the bundled static one cannot resolve DNS in this container)
YTDLP = str(Path(sys.executable).with_name("yt-dlp"))
CHANNELS = ["RSBNetwork", "ForbesBreakingNews", "LiveNOWFOX", "NTDNews", "WhiteHouse", "cspan", "FoxNews", "ABCNews"]


def ntp_offset() -> float | None:
    for h in ("time.cloudflare.com", "time.google.com"):
        try:
            return ntplib.NTPClient().request(h, version=3, timeout=5).offset
        except Exception:
            pass
    return None


def record(label: str, ch: str, until: dt.datetime, log) -> None:
    d = OUT / label / ch; d.mkdir(parents=True, exist_ok=True)
    while dt.datetime.now(dt.timezone.utc) < until:
        try:
            url = subprocess.run([YTDLP, "-g", "-f", "bestaudio/best", f"https://www.youtube.com/@{ch}/live"], capture_output=True, text=True, timeout=90).stdout.strip().splitlines()
        except Exception:
            url = []
        if not url:
            time.sleep(60); continue
        log(ch, "live, recording")
        secs = max(10, int((until - dt.datetime.now(dt.timezone.utc)).total_seconds()))
        # local clock in names; the NTP offset log converts them. -rw_timeout: a stall (e.g. after a laptop sleep) ends ffmpeg in 15 s
        subprocess.run([FFMPEG, "-loglevel", "error", "-rw_timeout", "15000000", "-i", url[-1], "-t", str(secs), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "libopus", "-b:a", "24k", "-f", "segment",
                        "-segment_time", "10", "-strftime", "1", str(d / "%Y%m%dT%H%M%S.opus")], timeout=secs + 120,
                       env={**os.environ, "TZ": "UTC"})          # file names = UTC arrival time on the local clock
        log(ch, "stream ended or dropped")


def wait_until(hhmm: str) -> None:
    """Wall-clock wait (a monotonic sleep would run late after a laptop suspend)."""
    hh, mm = map(int, hhmm.split(":")); now = dt.datetime.now(dt.timezone.utc)
    t = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    t = t if t > now else t + dt.timedelta(days=1)
    while dt.datetime.now(dt.timezone.utc) < t:
        time.sleep(20)


def main(argv) -> int:
    if argv and argv[0] == "--start":
        wait_until(argv[1]); argv = argv[2:]
    label, until = argv[0], argv[1]; chans = argv[2:] or CHANNELS
    now = dt.datetime.now(dt.timezone.utc); hh, mm = map(int, until.split(":"))
    end = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if end <= now:
        end += dt.timedelta(days=1)
    (OUT / label).mkdir(parents=True, exist_ok=True); logf = open(OUT / label / "log.jsonl", "a")

    def log(*a):
        logf.write(json.dumps({"utc_local_clock": dt.datetime.now(dt.timezone.utc).isoformat(), "msg": " ".join(map(str, a)), "ntp_offset": ntp_offset()}) + "\n"); logf.flush()

    log("start", chans, "until", end.isoformat())
    ts = [threading.Thread(target=record, args=(label, c, end, log), daemon=True) for c in chans]
    for t in ts:
        t.start()
    while any(t.is_alive() for t in ts) and dt.datetime.now(dt.timezone.utc) < end + dt.timedelta(minutes=3):
        time.sleep(300); log("heartbeat")
    log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

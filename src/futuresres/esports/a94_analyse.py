"""A94 readout (decisions.md 776): lead of Riot's public livestats over Kalshi's in-play sweeps, from a94_lolrace recordings.

Jump: a Kalshi move >= 15c within 60 s; sweep time = its first trade >= 5c from the pre-move price. Game event = the last Riot
state change (kills, towers, inhibitors, barons, dragons, game state) with frame time before the sweep; lead = sweep time - OUR
receive time of that frame (both on the local clock; Kalshi's exchange time corrected by the median NTP offset). Pass: lead >= 1.5 s
on >= 60% of >= 10 jumps AND the value still tradeable after receive + 1.0 s (move-direction trades after that, valued at the
1-5 min later median, net of fee) has a median >= $300 a match.

    python -m futuresres.esports.a94_analyse LABEL [LABEL ...]
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import statistics as st
import sys
from pathlib import Path

from futuresres.kalshi.k1_longshot import fee

ROOT = Path(__file__).resolve().parents[3]
REC = ROOT / "data" / "esports" / "a94"


def T(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def load(label: str):
    d = REC / label
    rd = lambda k: [json.loads(l) for l in open(d / f"{k}.jsonl")] if (d / f"{k}.jsonl").exists() else []
    return rd("riot"), rd("kalshi"), rd("log")


def state(r: dict) -> tuple:
    return (r["state"], *r["k"], *r["tw"], *r["inh"], *r["bar"], *r["drg"])


def jumps(tr: list) -> list:
    px = [(T(x["t"]), float(x["p"]), float(x["q"]), x["side"]) for x in sorted(tr, key=lambda x: x["t"])]
    out, i = [], 0
    while i < len(px):
        t0, p0 = px[i][0], px[i][1]; j = i + 1
        while j < len(px) and (px[j][0] - t0).total_seconds() <= 60 and abs(px[j][1] - p0) < 0.15:
            j += 1
        if j < len(px) and (px[j][0] - t0).total_seconds() <= 60:
            k = next(k for k in range(i + 1, j + 1) if abs(px[k][1] - p0) >= 0.05)
            out.append((px[k][0], p0, px[j][1] > p0, px))
            m = j
            while m < len(px) and (px[m][0] - px[j][0]).total_seconds() < 300:
                m += 1
            i = m
        else:
            i += 1
    return out


def main(labels) -> int:
    leads, prizes = [], collections.defaultdict(float)
    for lb in labels:
        riot, kal, log = load(lb)
        offs = [r["ntp_offset"] for r in log if r.get("ntp_offset") is not None]; off = st.median(offs) if offs else 0.0
        frames = collections.defaultdict(list)
        for r in riot:
            frames[r["game"]].append(r)
        changes = []                                            # (frame time, our receive time on local clock)
        for g, fr in frames.items():
            fr.sort(key=lambda r: r["ts"])
            for a, b in zip(fr, fr[1:]):
                if state(a) != state(b):
                    changes.append((T(b["ts"]), T(b["rcv"])))
        by_tk = collections.defaultdict(list)
        for x in kal:
            by_tk[x["ticker"]].append(x)
        for tk, tr in by_tk.items():
            for sweep, p0, up, px in jumps(tr):
                sweep_local = sweep - dt.timedelta(seconds=off)    # exchange UTC -> our local clock
                ev = [c for c in changes if c[0] <= sweep and (sweep - c[0]).total_seconds() < 120]
                if not ev:
                    continue
                ft, rcv = max(ev); lead = (sweep_local - rcv).total_seconds(); leads.append(lead)
                after = [p for t, p, _, _ in px if sweep + dt.timedelta(seconds=60) <= t <= sweep + dt.timedelta(seconds=300)]
                if after:
                    pa = st.median(after); go = rcv + dt.timedelta(seconds=1.0 + off)
                    prizes[(lb, tk)] += sum(q * (((pa - p) if up else (p - pa)) - fee(p)) for t, p, q, sd in px
                                            if go <= t <= sweep + dt.timedelta(seconds=60) and (sd == "yes") == up)
                print(f"{lb} {tk[10:]} sweep {sweep:%H:%M:%S} frame {ft:%H:%M:%S} received {rcv:%H:%M:%S.%f}"[:-3] + f" lead {lead:+.1f}s", flush=True)
    if not leads:
        print("no jumps with a preceding Riot change"); return 0
    ok = sum(x >= 1.5 for x in leads) / len(leads); pz = list(prizes.values())
    print(f"jumps {len(leads)}; lead median {st.median(leads):+.1f}s; lead >= 1.5 s on {ok:.0%}; value after receive+1 s: median "
          f"${st.median(pz) if pz else 0:,.0f} a match -> {'PASS' if len(leads) >= 10 and ok >= 0.6 and pz and st.median(pz) >= 300 else 'not pass'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

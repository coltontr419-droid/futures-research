"""How do the profitable makers hold queue position? (decisions.md §1207) From a passive capture of the validator's state requests to our axon
(tcpdump → pcap), decode every state (raw wire dicts: each level lists its resting orders in queue order with id / timestamp / size) and, for
every maker fill in a state's events, look the filled order up in the PREVIOUS state: size ahead of it at its level (share), its age, and
the 30 s markout. Grouped by maker: us, the top makers by fills, the rest. Maker identity comes from the trade (Ma, Mi).

    python queue_study.py <in.pcap> <our uid>      (run from /opt/mvtrx/repo with the miner venv)
"""
import bisect
import struct
import sys
from collections import defaultdict

import json
import numpy as np

sys.path.insert(0, "/opt/mvtrx/repo")
from taos.im.protocol import MarketSimulationStateUpdate   # noqa: E402
from taos.im.utils.compress import decompress              # noqa: E402

TICK = 0.01


def bodies(path):
    """HTTP request bodies to the axon, reassembled per TCP stream (same logic as pcap_req.py)."""
    f = open(path, "rb"); gh = f.read(24); off = {1: 14, 113: 16, 276: 20}[struct.unpack("<I", gh[20:24])[0]]
    streams = defaultdict(dict)
    while True:
        h = f.read(16)
        if len(h) < 16:
            break
        _, _, incl, _ = struct.unpack("<IIII", h); ip = f.read(incl)[off:]
        if ip[0] >> 4 != 4:
            continue
        ihl = (ip[0] & 15) * 4; tot = struct.unpack(">H", ip[2:4])[0]; tcp = ip[ihl:tot]
        sp, _, seq = struct.unpack(">HHI", tcp[:8]); data = tcp[(tcp[12] >> 4) * 4:]
        if data:
            streams[(ip[12:16], sp)][seq] = data
    for segs in streams.values():
        parts = []; nxt = None                       # join once: growing one bytes object packet by packet is quadratic on a 130 MB stream
        for s in sorted(segs):
            d = segs[s]
            if nxt is not None and s < nxt:
                d = d[nxt - s:]
            parts.append(d); nxt = max(nxt or 0, s + len(segs[s]))
        buf = b"".join(parts); pos = 0
        while True:
            h = buf.find(b"\r\n\r\n", pos)
            if h < 0:
                break
            head = buf[pos:h]
            cl = [int(l.split(b":")[1]) for l in head.split(b"\r\n") if l.lower().startswith(b"content-length")]
            if not cl or h + 4 + cl[0] > len(buf):
                break
            body = buf[h + 4:h + 4 + cl[0]]; pos = h + 4 + cl[0]
            if head.startswith(b"POST /MarketSimulationStateUpdate"):
                yield body


def main(pcap, me):
    states = []
    for b in bodies(pcap):
        syn = MarketSimulationStateUpdate(**json.loads(b))
        d = decompress(syn.compressed, syn.compression_engine, syn.version)
        states.append((syn.timestamp, d["books"]))
    states.sort(key=lambda x: x[0])
    print(f"states {len(states)}, sim span {(states[-1][0] - states[0][0]) / 1e9:.0f} s")
    mids = defaultdict(list)
    for ts, books in states:
        for bid, bk in books.items():
            if bk.get("b") and bk.get("a"):
                mids[int(bid)].append((ts / 1e9, (bk["b"][0]["p"] + bk["a"][0]["p"]) / 2))
    rows = []   # (maker uid, share ahead or None, age s or None, markout, level index from touch or None)
    for k in range(1, len(states)):
        prev_ts, prev = states[k - 1]; _, cur = states[k]
        for bid, bk in cur.items():
            book = int(bid); pb = prev.get(bid) or prev.get(str(bid)) or {}
            where = {}
            for side_key, side in (("b", 0), ("a", 1)):
                for li, lv in enumerate(pb.get(side_key) or []):
                    ahead = 0.0; orders = lv.get("o") or []
                    for o in orders:
                        where[o.get("i")] = (ahead / lv["q"] if lv["q"] else None, (prev_ts - o.get("t", prev_ts)) / 1e9, li, len(orders) == 1)
                        ahead += o.get("q") or 0.0
            for e in bk.get("e") or []:
                if e.get("y") != "t" or e.get("Ma") is None or e["Ma"] < 0:
                    continue
                ml = mids[book]; i = bisect.bisect_left(ml, (e["t"] / 1e9 + 30,))
                if i >= len(ml):
                    continue
                maker = 1 if e["s"] == 1 else -1
                w = where.get(e.get("Mi"))
                rows.append((e["Ma"], *(w[:3] if w else (None, None, None)), maker * (ml[i][1] - e["p"]) / TICK, w[3] if w else None))
    by = defaultdict(list)
    for r in rows:
        by[r[0]].append(r)
    top = sorted((u for u in by if u != me), key=lambda u: -len(by[u]))[:10]
    def show(name, R):
        if not R:
            print(f"{name:>12}: no fills"); return
        known = [r for r in R if r[1] is not None]; mo = np.array([r[4] for r in R])
        sh = np.array([r[1] for r in known]); age = np.array([r[2] for r in known]); lvl = np.array([r[3] for r in known])
        mk = np.array([r[4] for r in known])
        front = sh < 0.5 if len(sh) else np.array([], bool)
        print(f"{name:>12}: fills {len(R):5d} markout {mo.mean():+.2f} | resting in the previous state {len(known) / len(R):4.0%} | "
              f"share ahead median {np.median(sh) if len(sh) else float('nan'):.2f} | age median {np.median(age) if len(age) else float('nan'):5.1f} s | "
              f"front-half fills {front.mean() if len(sh) else float('nan'):4.0%} at {mk[front].mean() if front.any() else float('nan'):+.2f}, "
              f"back-half {mk[~front].mean() if (~front).any() else float('nan'):+.2f} | level≥1 at fill {np.mean(lvl >= 1) if len(lvl) else float('nan'):.0%}")
        al = np.array([bool(r[5]) for r in known])
        if len(al):
            print(f"{'':>12}  alone at its price {al.mean():4.0%} (markout {mk[al].mean() if al.any() else float('nan'):+.2f}) vs sharing {mk[~al].mean() if (~al).any() else float('nan'):+.2f}")
    show("ours", by.get(me, []))
    for u in top:
        show(f"uid {u}", by[u])
    show("all others", [r for u in by if u != me for r in by[u]])


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]))

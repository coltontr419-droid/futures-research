"""Reassemble HTTP request bodies to the miner port from a tcpdump pcap (Linux cooked v1/v2 or Ethernet), write each as req_N.json."""
import struct, sys, json
from collections import defaultdict
f = open(sys.argv[1], "rb"); gh = f.read(24); link = struct.unpack("<I", gh[20:24])[0]
off = {1: 14, 113: 16, 276: 20}[link]
streams = defaultdict(dict)
while True:
    h = f.read(16)
    if len(h) < 16: break
    _, _, incl, _ = struct.unpack("<IIII", h); pkt = f.read(incl); ip = pkt[off:]
    if ip[0] >> 4 != 4: continue
    ihl = (ip[0] & 15) * 4; tot = struct.unpack(">H", ip[2:4])[0]; tcp = ip[ihl:tot]
    sp, dp, seq = struct.unpack(">HHI", tcp[:8]); doff = (tcp[12] >> 4) * 4; data = tcp[doff:]
    if data: streams[(ip[12:16], sp)][seq] = data
n = 0
for k, segs in streams.items():
    buf = b""; nxt = None
    for s in sorted(segs):
        d = segs[s]
        if nxt is not None and s < nxt: d = d[nxt - s:]
        buf += d; nxt = s + len(segs[s]) if nxt is None or s + len(segs[s]) > nxt else nxt
    while b"\r\n\r\n" in buf:
        head, rest = buf.split(b"\r\n\r\n", 1)
        cl = [int(l.split(b":")[1]) for l in head.split(b"\r\n") if l.lower().startswith(b"content-length")]
        if not cl or len(rest) < cl[0]: break
        body, buf = rest[:cl[0]], rest[cl[0]:]
        if head.startswith(b"POST /MarketSimulationStateUpdate"):
            open(f"{sys.argv[2]}/req_{n}.json", "wb").write(body); print("req", n, len(body), "bytes"); n += 1
        else:
            print("other", head.split(b"\r\n")[0][:60])

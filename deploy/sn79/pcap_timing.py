"""Per inbound TCP stream to the miner port: first/last data packet times, bytes, and whether it opened with a SYN (new connection)."""
import struct, sys
from collections import defaultdict
f = open(sys.argv[1], "rb"); gh = f.read(24); link = struct.unpack("<I", gh[20:24])[0]; off = {1: 14, 113: 16, 276: 20}[link]
st = defaultdict(lambda: {"syn": None, "first": None, "last": None, "bytes": 0, "posts": []})
while True:
    h = f.read(16)
    if len(h) < 16: break
    ts, us, incl, _ = struct.unpack("<IIII", h); t = ts + us / 1e6; pkt = f.read(incl); ip = pkt[off:]
    if ip[0] >> 4 != 4: continue
    ihl = (ip[0] & 15) * 4; tot = struct.unpack(">H", ip[2:4])[0]; tcp = ip[ihl:tot]
    sp = struct.unpack(">H", tcp[:2])[0]; flags = tcp[13]; doff = (tcp[12] >> 4) * 4; data = tcp[doff:]; s = st[sp]
    if flags & 2: s["syn"] = t
    if data:
        if data.startswith(b"POST"): s["posts"].append(t)
        s["first"] = s["first"] or t; s["last"] = t; s["bytes"] += len(data)
for sp, s in st.items():
    if s["first"]:
        p = s["posts"]
        print(f"port {sp}: new conn {'yes' if s['syn'] else 'no'}, {len(p)} POSTs, {s['bytes']/1e3:.0f} kB, POST gaps {[round(b - a, 2) for a, b in zip(p, p[1:])]}, "
              f"syn→first data {((s['first'] - s['syn']) * 1e3 if s['syn'] else float('nan')):.0f} ms, data span {(s['last'] - s['first']) * 1e3:.0f} ms")

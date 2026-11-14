"""Reassemble inbound TCP streams from a pcap, split HTTP POSTs, write each body to outdir/req_N.json (+ headers to req_N.hdr)."""
import struct, sys, os
from collections import defaultdict
f = open(sys.argv[1], "rb"); out = sys.argv[2]; os.makedirs(out, exist_ok=True)
gh = f.read(24); link = struct.unpack("<I", gh[20:24])[0]; off = {1: 14, 113: 16, 276: 20}[link]
segs = defaultdict(dict)
while True:
    h = f.read(16)
    if len(h) < 16: break
    ts, us, incl, _ = struct.unpack("<IIII", h); pkt = f.read(incl); ip = pkt[off:]
    if ip[0] >> 4 != 4: continue
    ihl = (ip[0] & 15) * 4; tot = struct.unpack(">H", ip[2:4])[0]; tcp = ip[ihl:tot]
    src = ip[12:16]; sp = struct.unpack(">H", tcp[:2])[0]; seq = struct.unpack(">I", tcp[4:8])[0]
    doff = (tcp[12] >> 4) * 4; data = tcp[doff:]
    if data: segs[(src, sp)].setdefault(seq, (ts + us / 1e6, data))
n = 0
for k, d in segs.items():
    seqs = sorted(d); buf = b""; nxt = None; t0 = None
    for s in seqs:
        t, data = d[s]
        if nxt is not None and s < nxt:
            data = data[nxt - s:] if s + len(data) > nxt else b""
        elif nxt is not None and s > nxt:
            buf += b"\0" * 0; print("gap in stream", k[1], s - nxt); break
        buf += data; nxt = s + len(data) if nxt is None or s >= nxt else nxt + len(data)
    i = 0
    while True:
        j = buf.find(b"POST ", i)
        if j < 0: break
        he = buf.find(b"\r\n\r\n", j)
        if he < 0: break
        hdr = buf[j:he].decode("latin1"); cl = None
        for line in hdr.split("\r\n"):
            if line.lower().startswith("content-length:"): cl = int(line.split(":")[1])
        if cl is None or he + 4 + cl > len(buf): break
        body = buf[he + 4:he + 4 + cl]
        if b"MarketSimulationStateUpdate" in hdr.encode() or hdr.startswith("POST /MarketSimulationStateUpdate"):
            open(f"{out}/req_{n}.json", "wb").write(body); open(f"{out}/req_{n}.hdr", "w").write(hdr); n += 1
        else:
            print("other POST", hdr.split("\r\n")[0])
        i = he + 4 + cl
print("bodies", n)

import sys, json, glob, time, statistics as st
sys.path.insert(0, "/opt/mvtrx/repo")
import pybase64, msgspec
from taos.im.utils.compress import decompressors
from taos.im.protocol import MarketSimulationStateUpdate
R = {"json_body": [], "pydantic": [], "b64": [], "codec": [], "msgpack": [], "rest": []}
for p in sorted(glob.glob("/opt/mvtrx/cap14/req_*.json")) * 3:
    b = open(p).read()
    t0 = time.perf_counter(); d = json.loads(b); t1 = time.perf_counter(); s = MarketSimulationStateUpdate(**d); t2 = time.perf_counter()
    eng = s.compression_engine; c = s.compressed
    t3 = time.perf_counter(); dec = pybase64.b64decode(c["payload"]); decb = pybase64.b64decode(c["books"]); t4 = time.perf_counter()
    raw = decompressors[eng](dec); rawb = decompressors[eng](decb); t5 = time.perf_counter()
    obj = msgspec.msgpack.decode(raw); obj["books"] = msgspec.msgpack.decode(rawb); t6 = time.perf_counter()
    s.decompress(lazy=True); t7 = time.perf_counter()
    R["json_body"].append(t1 - t0); R["pydantic"].append(t2 - t1); R["b64"].append(t4 - t3); R["codec"].append(t5 - t4); R["msgpack"].append(t6 - t5); R["rest"].append((t7 - t6) - (t6 - t3))
print("engine", eng, "version", s.version, "keys", list(c.keys()), "compressed MB", round((len(c["payload"]) + len(c["books"])) / 1e6, 2), "raw MB", round((len(raw) + len(rawb)) / 1e6, 2))
for k, v in R.items(): print(f"  {k:9} median {1e3 * st.median(v):6.1f} ms")
bk = obj["books"]; k0 = next(iter(bk)); d0 = bk[k0]
ne = sum(len(x.get("e") or []) for x in bk.values()); nlv = sum(len(x.get("b") or []) + len(x.get("a") or []) for x in bk.values()); no = sum(len(l.get("o") or []) for x in bk.values() for l in (x.get("b") or []) + (x.get("a") or []))
print("events", ne, "levels", nlv, "resting orders in levels", no, "| top keys", list(obj.keys()))

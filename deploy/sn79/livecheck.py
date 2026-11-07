"""Live rollback for auto-refit models (decisions.md §1268). Run by the watchdog every tick. If /opt/mvtrx/autorefit_deployed.json exists
({"model", "previous", "since_s"}), measure the taker's real opening entries since since_s: signed mid move 900 s later (the strategy holds ≥ 15 min) (bp, ±50 clip), from x3's tape.
With ≥ 150 measured entries and a mean below 0, put the previous model back, restart the taker and print an ALERT. --dry <since_s> reports without acting."""
import bisect, collections, json, os, subprocess, sys
D = "/opt/mvtrx/autorefit_deployed.json"; TAPE = "/opt/mvtrx/live_tape_x3.jsonl"; UNIT = "/etc/systemd/system/mvtrx-x1.service"
dry = "--dry" in sys.argv
if dry:
    info = {"since_s": float(sys.argv[sys.argv.index("--dry") + 1]), "model": "(dry run)", "previous": "(dry run)"}
elif os.path.exists(D):
    info = json.load(open(D))
else:
    sys.exit(0)
U = next((int(l.split()[0]) for l in open("/opt/mvtrx/our_uids.txt") if l.split()[1:2] == ["taker"]), None)
if U is None: sys.exit(0)
since = info["since_s"]; key = f'"Ta": {U},'.encode()
M = collections.defaultdict(lambda: ([], [])); E = []; inv = collections.defaultdict(float); last = 0
for l in open(TAPE, "rb"):
    i = l.find(b'"ts": '); t = int(l[i + 6:l.index(b",", i)]) / 1e9
    if t < last - 3600:                                     # a sim reset: only the current simulation counts
        M.clear(); E.clear(); inv.clear()
    last = t
    if t < since - 60: continue
    if b'"bid"' in l[:60]:
        j = l.find(b'"bids"'); r = json.loads(l[:j].rstrip(b', ') + b"}")
        if r.get("bid") and r.get("ask"): m = M[r["book"]]; m[0].append(t); m[1].append((r["bid"] + r["ask"]) / 2)
    elif key in l and t >= since:
        r = json.loads(l); b = r["book"]; d = r["q"] if r["s"] == 0 else -r["q"]; a = inv[b]; inv[b] = a + d
        if abs(a) * r["p"] < 1 and abs(a + d) * r["p"] >= 1: E.append((b, t, 1 if d > 0 else -1))
out = []
for b, t, s in E:
    ts, ms = M[b]; i = bisect.bisect_left(ts, t); j = bisect.bisect_left(ts, t + 900)
    if i < len(ts) and j < len(ts): out.append(max(-50, min(50, s * (ms[j] - ms[i]) / ms[i] * 1e4)))
n = len(out); mean = sum(out) / n if n else 0.0
print(f"  livecheck {info['model']}: {n} entries measured since sim s {since:.0f}, mean {mean:+.2f} bp at 900 s")
if not dry and n >= 150 and mean < 0:
    u = open(UNIT).read(); prev = info["previous"]
    open(UNIT, "w").write(__import__("re").sub(r"rev_model=\S+", "rev_model=" + prev, u))
    subprocess.run(["systemctl", "daemon-reload"]); subprocess.run(["systemctl", "restart", "mvtrx-x1"])
    os.replace(D, D + ".rolled_back")
    print(f"ALERT autorefit rollback: {os.path.basename(info['model'])} lost live ({mean:+.2f} bp over {n} entries); back to {os.path.basename(prev)}")

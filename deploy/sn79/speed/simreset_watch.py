"""§1540: run with the release watcher (every 10 min): detect a SIM-DAY RESET (tape clock jumps back) and check the book LAYOUT of the new day
(price level per book vs our book_map groups: $300 ≈ 300, $30 ≈ 30, 4-dec = 4 decimals). Logs to release_watch.log + ALERT."""
import json, os, time
T = "/opt/mvtrx/live_tape_x3.jsonl"; S = "/opt/mvtrx/simreset_watch.state"; L = "/opt/mvtrx/release_watch.log"; A = "/opt/mvtrx/alerts.txt"
f = open(T, "rb"); f.seek(max(0, os.path.getsize(T) - 3_000_000)); lines = f.read().split(b"\n")[1:-1]
ts = 0; px = {}
for l in lines:
    try: r = json.loads(l)
    except Exception: continue
    ts = max(ts, r.get("ts", 0) // 10**9)
    if r.get("bid") and r.get("ask"): px[r["book"]] = (r["bid"], r["ask"])
old = int(open(S).read()) if os.path.exists(S) else 0
open(S, "w").write(str(ts))
now = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
if old and ts + 3600 < old:
    bad = []
    for b, (bi, a) in px.items():
        mid = (bi + a) / 2; want = "300" if b < 128 else ("30" if b < 192 else "dec")
        dec = len(f"{bi:.10f}".rstrip("0").split(".")[1]) if "." in f"{bi:.10f}".rstrip("0") else 0
        got = "dec" if dec >= 3 else ("300" if mid > 100 else "30")
        if got != want: bad.append(b)
    msg = f"SIM RESET: tape clock {old} -> {ts} | layout check on {len(px)} books: {len(bad)} books not matching the $300 0-127 / $30 128-191 / 4-dec 192-255 map {bad[:20]}"
    open(L, "a").write(f"{now} {msg}\n"); open(A, "a").write(f"ALERT {int(time.time())} {msg} — re-check book_map + model edge (leanfreq) before trusting the leans (§1540)\n")

"""Forward the MVTRX lab box's watchdog alerts to Discord #miners (decisions.md §1256). Every 5 min: read /opt/mvtrx/alerts.txt through a key that can do nothing else
(forced command on the lab box), post each new alert. The same alert (numbers ignored) repeats at most every 6 hours."""
import json, re, subprocess, time, os, sys
sys.path.insert(0, "/opt/tag101")
import minerwatch as mw
S = "/opt/tag101/labalerts_state.json"; RE = 6 * 3600
RED, BLUE = 15158332, 3447003                                # user 11-10: completed runs blue, danger alerts red
DANGER = re.compile(r"\b(not|fail\w*|errors?|pruned|skipped|stopped|missing|down|over|dropped|no fills|self-trade|unreachable|traceback)\b", re.I)
INFO = re.compile(r"\bdone\b|read ready|restarted|applied|started", re.I)
def colour(text):
    """Completed runs / routine events → blue; anything that looks like trouble (or is unknown) → red."""
    return BLUE if INFO.search(text) and not DANGER.search(text) else RED
out = subprocess.run(["ssh", "-i", "/root/.ssh/lab_alerts", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "root@157.245.86.147"], capture_output=True, text=True, timeout=40)
try:
    st = json.load(open(S))
except Exception:
    st = {}
now = time.time()
if out.returncode != 0:
    if now - st.get("_ssh_fail", 0) > RE:
        mw.post({"title": "MVTRX lab box not reachable", "description": "The alert forwarder could not read the lab box. Miners may be fine; alerts are not being delivered.", "color": 15158332})
        st["_ssh_fail"] = now
else:
    last = st.get("_last_ts", 0); newest = last              # user 11-08: post only alerts stamped after the last one posted (old lines in the tail
    for line in dict.fromkeys(l.strip() for l in out.stdout.splitlines() if l.startswith("ALERT")):   # were re-sent once their 6-h repeat window ran out)
        m = re.match(r"ALERT (\d{10}) (.*)", line)
        if not m or int(m.group(1)) <= last:
            continue                                         # unstamped (written before 11-08) or already seen
        ts, text = int(m.group(1)), m.group(2); newest = max(newest, ts)
        k = re.sub(r"[\d,.$]+", "#", text)
        if now - st.get(k, 0) > RE:
            c = colour(text); mw.post({"title": "MVTRX update" if c == BLUE else "MVTRX alert", "description": text, "color": c}); st[k] = now
    st["_last_ts"] = newest
if out.returncode == 0:                     # the watchdog's heartbeat: a dead watchdog must be noticed from outside the box
    beats = [int(l.split()[1]) for l in out.stdout.splitlines() if l.startswith("HEARTBEAT")]
    if beats and now - max(beats) > 1800 and now - st.get("_beat", 0) > RE:
        mw.post({"title": "MVTRX watchdog stopped", "description": f"No heartbeat for {int((now - max(beats)) / 60)} minutes: the lab box's checks are not running.", "color": 15158332}); st["_beat"] = now
tmp = S + ".tmp"; json.dump(st, open(tmp, "w")); os.replace(tmp, S)

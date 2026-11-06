"""Forward the MVTRX lab box's watchdog alerts to Discord #miners (decisions.md §1256). Every 5 min: read /opt/mvtrx/alerts.txt through a key that can do nothing else
(forced command on the lab box), post each new alert. The same alert (numbers ignored) repeats at most every 6 hours."""
import json, re, subprocess, time, os, sys
sys.path.insert(0, "/opt/tag101")
import minerwatch as mw
S = "/opt/tag101/labalerts_state.json"; RE = 6 * 3600
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
    for line in dict.fromkeys(l.strip() for l in out.stdout.splitlines() if l.startswith("ALERT")):
        k = re.sub(r"[\d,.$]+", "#", line)
        if now - st.get(k, 0) > RE:
            mw.post({"title": "MVTRX alert", "description": line[6:], "color": 15158332}); st[k] = now
if out.returncode == 0:                     # the watchdog's heartbeat: a dead watchdog must be noticed from outside the box
    beats = [int(l.split()[1]) for l in out.stdout.splitlines() if l.startswith("HEARTBEAT")]
    if beats and now - max(beats) > 1800 and now - st.get("_beat", 0) > RE:
        mw.post({"title": "MVTRX watchdog stopped", "description": f"No heartbeat for {int((now - max(beats)) / 60)} minutes: the lab box's checks are not running.", "color": 15158332}); st["_beat"] = now
tmp = S + ".tmp"; json.dump(st, open(tmp, "w")); os.replace(tmp, S)

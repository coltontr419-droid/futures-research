"""§1524: poll upstream taos-im/sn-79 main every 10 min (systemd timer). On a new commit: log it with the changed files (configs / scoring flagged) and write an ALERT line."""
import json, urllib.request, time, os
S = "/opt/mvtrx/release_watch.state"; L = "/opt/mvtrx/release_watch.log"; A = "/opt/mvtrx/alerts.txt"
def get(u):
    return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "curl/8.5.0", "Accept": "application/vnd.github+json"}), timeout=30))
now = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
try:
    c = get("https://api.github.com/repos/taos-im/sn-79/commits/main")
except Exception as e:
    open(L, "a").write(f"{now} poll failed: {e}\n"); raise SystemExit
sha, msg = c["sha"], c["commit"]["message"].split("\n")[0]
old = open(S).read().strip() if os.path.exists(S) else ""
if not old:
    open(S, "w").write(sha); open(L, "a").write(f"{now} baseline {sha[:8]} {msg}\n"); raise SystemExit
if sha == old:
    raise SystemExit
try:
    files = [f["filename"] for f in get(f"https://api.github.com/repos/taos-im/sn-79/compare/{old}...{sha}").get("files", [])]
except Exception:
    files = []
key = [f for f in files if "config/" in f or f.endswith(".xml") or "validator/" in f or "reward" in f or "debeta" in f]
open(L, "a").write(f"{now} NEW RELEASE {sha[:8]} '{msg}' | {len(files)} files | sim-config/scoring files: {key[:40]}\n")
open(A, "a").write(f"ALERT {int(time.time())} UPSTREAM RELEASE {sha[:8]} '{msg}' — {len(key)} sim-config/scoring files changed; re-read configs + refit model (§1500)\n")
open(S, "w").write(sha)

"""10 random easy/medium single-container Terminal-Bench tasks (seed 1227) → /opt/tb/tasks.json + read-only workspaces (decisions.md §1227)."""
import json, random, re, shutil
from pathlib import Path
import yaml
T = Path("/opt/tb/terminal-bench/original-tasks"); ok = []
for d in sorted(T.iterdir()):
    try:
        y = yaml.safe_load((d / "task.yaml").read_text()); comp = (d / "docker-compose.yaml").read_text()
    except Exception:
        continue
    services = re.findall(r"^  ([A-Za-z0-9_-]+):\s*$", comp.split("services:", 1)[-1], re.M)
    if y.get("difficulty") in ("easy", "medium") and y.get("category") != "security" and "security" not in (y.get("tags") or []) and services == ["client"] and (d / "run-tests.sh").exists():
        ok.append((d.name, y))
pick = random.Random(1227).sample(ok, 10); out = []
W = Path("/opt/tb/ws"); W.mkdir(exist_ok=True)
for name, y in pick:
    ws = W / name; shutil.rmtree(ws, ignore_errors=True)
    shutil.copytree(T / name, ws, ignore=shutil.ignore_patterns("solution.sh", "run-tests.sh", "tests", "task.yaml", "docker-compose.yaml", "solution*"))
    instr = y["instruction"].strip() + ("\n\nYour Bash script will run as root inside a container built from the Dockerfile in this workspace, in its "
                                        "WORKDIR. The workspace holds the files used to build that container; you cannot run commands before submitting.")
    out.append({"task": name, "difficulty": y["difficulty"], "instruction": instr}); print(name, y["difficulty"], y.get("category"))
json.dump(out, open("/opt/tb/tasks.json", "w"), indent=1)
print("eligible", len(ok))

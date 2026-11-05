"""Hone's demo agent loop on Terminal-Bench tasks as terminal_script_v1 (decisions.md §1227); same client settings as swe_agent.py.
    sudo -u hone /opt/hone/venv/bin/python tb_agent.py <model> <results.jsonl>   → /opt/tb/out/<task>.sh"""
import asyncio, json, os, sys, time
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, "/opt/swe"); sys.path.insert(0, "/opt/hone/repo"); sys.path.insert(0, "/opt/hone")
os.environ.setdefault("PROVIDER", "openrouter"); os.environ.setdefault("REASKS", "6"); os.environ.setdefault("MAXTOK", "32768")
sys.argv, _argv = [sys.argv[0], "x", "x", "x"], sys.argv              # swe_agent.main() runs at import; give it inert args, then restore
import importlib.util
spec = importlib.util.spec_from_file_location("swe_agent_mod", "/opt/swe/swe_agent.py")
src = open("/opt/swe/swe_agent.py").read().rsplit("\nmain()", 1)[0]
mod = type(sys)("swe_agent_mod"); exec(compile(src, "/opt/swe/swe_agent.py", "exec"), mod.__dict__)
sys.argv = _argv


async def solve(t, model):
    identity = SimpleNamespace(task_type="terminal_script_v1", instruction=t["instruction"], working_directory=".", result_tree_path=".")
    task = {"instance_id": t["task"], "problem_statement": t["instruction"]}
    orig_ns = mod.SimpleNamespace
    mod.SimpleNamespace = lambda **kw: identity if kw.get("task_type") == "repository_patch_v1" else orig_ns(**kw)
    try:
        mod.Path = lambda p: Path("/opt/tb/ws") if str(p) == "/opt/swe/ws" else Path(p)
        return await mod.solve(task, model)
    finally:
        mod.SimpleNamespace = orig_ns


def main():
    model, results = sys.argv[1], sys.argv[2]; OUT = Path(os.getenv("OUTDIR", "/opt/tb/out")); OUT.mkdir(exist_ok=True)
    done = {json.loads(l)["instance_id"] for l in open(results)} if os.path.exists(results) else set()
    for t in json.load(open("/opt/tb/tasks.json")):
        if t["task"] in done: continue
        script, row = asyncio.run(solve(t, model))
        (OUT / f"{t['task']}.sh").write_text(script)
        with open(results, "a") as f: f.write(json.dumps(row) + "\n")
        print(json.dumps(row), flush=True)


main()

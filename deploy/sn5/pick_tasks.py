"""10 random SWE-bench Verified tasks (seed 1225) → /opt/swe/tasks.json (decisions.md §1226)."""
import json, random
from datasets import load_dataset
ds = load_dataset("princeton-nlp/SWE-bench_Verified", split="test")
idx = random.Random(1225).sample(range(len(ds)), 10)
tasks = [{k: ds[i][k] for k in ("instance_id", "repo", "base_commit", "problem_statement")} for i in idx]
json.dump(tasks, open("/opt/swe/tasks.json", "w"), indent=1)
for t in tasks: print(t["instance_id"], len(t["problem_statement"]), "chars")

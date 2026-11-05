#!/bin/sh
# §1226: pick tasks → workspaces → GLM-5.2 agent → SWE-bench harness grading. Detached; marks /opt/swe/run.done.
cd /opt/swe
until [ -f setup.done ]; do sleep 10; done
venv/bin/python pick_tasks.py > pick.log 2>&1
sh prep_ws.sh > prep.log 2>&1
chown hone /opt/swe; touch preds.jsonl results.jsonl; chown hone preds.jsonl results.jsonl
EFFORT=medium sudo -E -u hone /opt/hone/venv/bin/python swe_agent.py z-ai/glm-5.2 /opt/swe/preds.jsonl /opt/swe/results.jsonl > agent.log 2>&1
venv/bin/python -m swebench.harness.run_evaluation --dataset_name princeton-nlp/SWE-bench_Verified --predictions_path /opt/swe/preds.jsonl \
  --max_workers 2 --run_id hone_glm52 --namespace swebench --cache_level env > eval.log 2>&1
echo done > run.done

#!/bin/sh
cd /opt/swe
venv/bin/python -m swebench.harness.run_evaluation --dataset_name SWE-bench/SWE-bench_Verified --predictions_path /opt/swe/preds.jsonl \
  --max_workers 2 --run_id hone_glm52 > eval.log 2>&1
echo done > eval.done

#!/bin/sh
# §1227: GLM-5.2 on the same 10 Terminal-Bench tasks; graded after the DeepSeek grading finishes (one Docker job at a time).
cd /opt/tb; mkdir -p out_glm; chown hone out_glm; touch results_glm.jsonl; chown hone results_glm.jsonl
OUTDIR=/opt/tb/out_glm EFFORT=medium sudo -E -u hone /opt/hone/venv/bin/python tb_agent.py z-ai/glm-5.2 /opt/tb/results_glm.jsonl > agent_glm.log 2>&1
until [ -f grade.done ]; do sleep 30; done
OUT=out_glm GRADES=grades_glm.txt sh tb_grade2.sh > grade_glm.log 2>&1
echo done > glm.done

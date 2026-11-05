#!/bin/sh
cd /opt/tb
/opt/swe/venv/bin/python tb_pick.py > pick.log 2>&1
chown -R hone /opt/tb/ws; mkdir -p out; chown hone out; touch results.jsonl; chown hone results.jsonl /opt/tb
EFFORT=medium sudo -E -u hone /opt/hone/venv/bin/python tb_agent.py deepseek/deepseek-v4-pro-0813 /opt/tb/results.jsonl > agent.log 2>&1
sh tb_grade.sh > grade.log 2>&1
echo done > run.done

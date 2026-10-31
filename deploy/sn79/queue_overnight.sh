#!/bin/sh
# Overnight queue (decisions.md §1194): wait for run 7 to finish, score it, run 8 (two markets), score it. Results: /opt/mvtrx/overnight_results.txt
R=/opt/mvtrx/overnight_results.txt; PY=/opt/mvtrx/venv/bin/python; S=/opt/mvtrx/repo/agents/score_tape.py
cleanup() {
  pkill -f "agents/proxy/launcher.py --config" ; pkill -f "proxy.py --config /opt/mvtrx/repo/agents/proxy/lab" ; pkill -x taosim
  pkill -f "/opt/mvtrx/repo/agents/QuoteAgent.py --port" ; pkill -f "/opt/mvtrx/repo/agents/RandomTakerAgent.py --port" ; sleep 5
}
score() { echo "== $1 ($(date -u +%H:%M) UTC)" >> $R; nice -n 10 $PY $S $2 --repo /opt/mvtrx/repo 2>&1 | tail -7 >> $R; }
wait_sims() { while pgrep -x taosim >/dev/null; do sleep 30; done; }
echo "overnight queue started $(date -u +%H:%M) UTC" > $R
wait_sims; cleanup
echo "run 7: agents 0 = predictor x2 | 1 = + trend guard 1.0 sd | 2 = + trend guard 0.5 sd | 3 = guard 1.0 + inventory cap 10% | 4 = random taker" >> $R
score "run 7 market X" /opt/mvtrx/tape_run7x.jsonl; score "run 7 market Y" /opt/mvtrx/tape_run7y.jsonl
/opt/mvtrx/launch_lab.sh agents/proxy/lab8x.json /opt/mvtrx/run8x.log; sleep 20; /opt/mvtrx/launch_lab.sh agents/proxy/lab8y.json /opt/mvtrx/run8y.log _b
sleep 120; wait_sims; cleanup
echo "run 8: agents 0,1 = predictor x2 (two copies) | 2,3 = + trend guard 1.0 sd (two copies) | 4 = random taker" >> $R
score "run 8 market X" /opt/mvtrx/tape_run8x.jsonl; score "run 8 market Y" /opt/mvtrx/tape_run8y.jsonl
echo "queue done $(date -u +%H:%M) UTC" >> $R

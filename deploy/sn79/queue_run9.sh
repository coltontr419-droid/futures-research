#!/bin/sh
# Run 9 (decisions.md §1194): live model vs cross-market refits, two markets, low priority beside the live miner (mvtrx-x1).
R=/opt/mvtrx/run9_results.txt; PY=/opt/mvtrx/venv/bin/python; S=/opt/mvtrx/repo/agents/score_tape.py
echo "run 9 started $(date -u +%H:%M) UTC | agents 0 = LIVE model60 x2 | 1 = model60_v2 x2 | 2 = model5_v2 x4 | 3 = model5_v2 x8 | 4 = random taker" > $R
/opt/mvtrx/launch_lab.sh agents/proxy/lab9x.json /opt/mvtrx/run9x.log; sleep 20; /opt/mvtrx/launch_lab.sh agents/proxy/lab9y.json /opt/mvtrx/run9y.log _b
sleep 120; while pgrep -x taosim >/dev/null; do sleep 30; done
pkill -f "agents/proxy/launcher.py --config"; pkill -f "proxy.py --config /opt/mvtrx/repo/agents/proxy/lab"
pkill -f "/opt/mvtrx/repo/agents/QuoteAgent.py --port"; pkill -f "/opt/mvtrx/repo/agents/RandomTakerAgent.py --port"; sleep 5
for m in x y; do echo "== run 9 market $m ($(date -u +%H:%M) UTC)" >> $R; nice -n 10 $PY $S /opt/mvtrx/tape_run9$m.jsonl --repo /opt/mvtrx/repo 2>&1 | tail -7 >> $R; done
echo "done $(date -u +%H:%M) UTC" >> $R

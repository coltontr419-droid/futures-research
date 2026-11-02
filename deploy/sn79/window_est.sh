#!/bin/sh
# Validator-window estimate for UID 41 (decisions.md §1209 addendum 7): every tape since registration through the exact making code,
# plus the live public gauges. Appends to /opt/mvtrx/window_readouts.txt.
O=/opt/mvtrx/window_readouts.txt; T=/tmp/winest.jsonl
cd /opt/mvtrx && cat live_tape_x1_arms1.jsonl live_tape_x1_arms2.jsonl live_tape_x1_base3.jsonl > $T
echo "=== $(date -u +%H:%M) UTC" >> $O
cd repo && nice -n 10 /opt/mvtrx/venv/bin/python /opt/mvtrx/making_exact.py $T 41 1 2>&1 | grep -E "^ours|two-sided|^field:" >> $O
echo "  -- base period only (our fills since sim min 1280.6 = 01:17 UTC switch):" >> $O
nice -n 10 /opt/mvtrx/venv/bin/python /opt/mvtrx/making_exact.py $T 41 1 --since 1280.6 2>&1 | grep -E "^ours|two-sided" >> $O
rm -f $T
P=https://taos.simulate.trading/api/datasources/proxy/uid/c7665619-8b04-4227-9882-a44e8dad57a6/api/v1/query
for g in debeta_making debeta_making_rank combined_score score; do
  printf "  live %s: " $g >> $O
  curl -s -G "$P" --data-urlencode "query=miner_gauges{miner_gauge_name=\"$g\",agent_id=\"41\"}" | /opt/mvtrx/venv/bin/python -c "import json,sys; print([round(float(r[\"value\"][1]),4) for r in json.load(sys.stdin)[\"data\"][\"result\"]])" >> $O 2>&1
done
